"""Workflow executor for orchestrating multi-stage agent runs."""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .services import document_service, execution_service, claude_service
from .base import (
    ExecutionMode,
    IterationStrategy,
    StageConfig,
    WorkflowConfig,
    WorkflowIndividualRun,
    WorkflowRun,
    WorkflowStageRun,
)
from . import database as wf_db
from .registry import workflow_registry
from emdx.database.documents import record_document_source


@dataclass
class StageResult:
    """Result of executing a stage."""
    success: bool
    output_doc_id: Optional[int] = None
    synthesis_doc_id: Optional[int] = None
    individual_outputs: List[int] = field(default_factory=list)
    tokens_used: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None


class WorkflowExecutor:
    """Executes workflows with support for different execution modes.

    Supports:
    - single: Run agent once
    - parallel: Run agent N times simultaneously, synthesize results
    - iterative: Run agent N times sequentially, each building on previous
    - adversarial: Advocate -> Critic -> Synthesizer pattern
    """

    def __init__(self, max_concurrent: int = 10):
        """Initialize executor.

        Args:
            max_concurrent: Maximum concurrent agent runs (for parallel mode)
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_workflow(
        self,
        workflow_name_or_id: str | int,
        input_doc_id: Optional[int] = None,
        input_variables: Optional[Dict[str, Any]] = None,
        preset_name: Optional[str] = None,
        gameplan_id: Optional[int] = None,
        task_id: Optional[int] = None,
        working_dir: Optional[str] = None,
    ) -> WorkflowRun:
        """Execute a workflow.

        Args:
            workflow_name_or_id: Workflow name or ID
            input_doc_id: Optional input document ID
            input_variables: Optional runtime variables (override preset variables)
            preset_name: Optional preset name to use for variables
            gameplan_id: Optional link to gameplan
            task_id: Optional link to task
            working_dir: Optional working directory for agent execution (e.g., worktree path)

        Returns:
            WorkflowRun with execution results

        Variable precedence (highest to lowest):
            1. Runtime input_variables (--var flags)
            2. Preset variables (--preset)
            3. Workflow default variables
        """
        # Load workflow
        workflow = workflow_registry.get_workflow(workflow_name_or_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_name_or_id}")

        # Load preset if specified
        preset_id = None
        preset_variables = {}
        if preset_name:
            preset_row = wf_db.get_preset_by_name(workflow.id, preset_name)
            if not preset_row:
                raise ValueError(f"Preset '{preset_name}' not found for workflow '{workflow.name}'")
            preset_id = preset_row['id']
            preset_variables = json.loads(preset_row['variables_json']) if preset_row.get('variables_json') else {}
            # Increment preset usage
            wf_db.increment_preset_usage(preset_id)

        # Merge all variables for storage: workflow defaults + preset + runtime
        # This captures the complete picture of what was used
        merged_variables = {}
        merged_variables.update(workflow.variables)
        merged_variables.update(preset_variables)
        if input_variables:
            merged_variables.update(input_variables)

        # Create workflow run record with preset tracking
        run_id = wf_db.create_workflow_run(
            workflow_id=workflow.id,
            input_doc_id=input_doc_id,
            input_variables=merged_variables,  # Store the fully merged variables
            gameplan_id=gameplan_id,
            task_id=task_id,
        )

        # Update run with preset info (separate call since create_workflow_run doesn't have these params yet)
        if preset_id or preset_name:
            with wf_db.db_connection.get_connection() as conn:
                conn.execute(
                    "UPDATE workflow_runs SET preset_id = ?, preset_name = ? WHERE id = ?",
                    (preset_id, preset_name, run_id),
                )
                conn.commit()

        # Start execution
        wf_db.update_workflow_run(
            run_id,
            status='running',
            started_at=datetime.now(),
        )

        start_time = datetime.now()
        context: Dict[str, Any] = {}
        total_tokens = 0

        # Set working directory - use provided path or current directory
        effective_working_dir = working_dir or str(Path.cwd())
        context['_working_dir'] = effective_working_dir

        try:
            # Load input document content if provided
            if input_doc_id:
                doc = document_service.get_document(input_doc_id)
                if doc:
                    context['input'] = doc.get('content', '')
                    context['input_title'] = doc.get('title', '')

            # Apply merged variables (already merged: workflow defaults + preset + runtime)
            context.update(merged_variables)

            # Auto-load document content for doc_N variables
            # If a variable like doc_1, doc_2, etc. is an integer, treat it as a document ID
            # and load the content into doc_N_content and doc_N_title
            await self._load_document_variables(context)

            # Execute stages sequentially
            for stage in workflow.stages:
                wf_db.update_workflow_run(run_id, current_stage=stage.name)

                result = await self._execute_stage(
                    workflow_run_id=run_id,
                    stage=stage,
                    context=context,
                )

                if not result.success:
                    # Stage failed - mark workflow as failed
                    wf_db.update_workflow_run(
                        run_id,
                        status='failed',
                        error_message=result.error_message,
                        completed_at=datetime.now(),
                    )
                    wf_db.increment_workflow_usage(workflow.id, success=False)

                    row = wf_db.get_workflow_run(run_id)
                    return WorkflowRun.from_db_row(row)

                # Update context with stage output
                total_tokens += result.tokens_used

                # Store stage output in context for later stages
                if result.output_doc_id:
                    doc = document_service.get_document(result.output_doc_id)
                    if doc:
                        context[f"{stage.name}.output"] = doc.get('content', '')
                        context[f"{stage.name}.output_id"] = result.output_doc_id

                if result.synthesis_doc_id:
                    doc = document_service.get_document(result.synthesis_doc_id)
                    if doc:
                        context[f"{stage.name}.synthesis"] = doc.get('content', '')
                        context[f"{stage.name}.synthesis_id"] = result.synthesis_doc_id

                # Store individual outputs for parallel mode
                if result.individual_outputs:
                    outputs_content = []
                    for doc_id in result.individual_outputs:
                        doc = document_service.get_document(doc_id)
                        if doc:
                            outputs_content.append(doc.get('content', ''))
                    context[f"{stage.name}.outputs"] = outputs_content

                # Update workflow run context
                wf_db.update_workflow_run(
                    run_id,
                    context_json=json.dumps(context),
                )

            # All stages completed successfully
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            # Get final output doc IDs from last stage
            final_outputs = []
            last_stage = workflow.stages[-1]
            if f"{last_stage.name}.output_id" in context:
                final_outputs.append(context[f"{last_stage.name}.output_id"])
            elif f"{last_stage.name}.synthesis_id" in context:
                final_outputs.append(context[f"{last_stage.name}.synthesis_id"])

            wf_db.update_workflow_run(
                run_id,
                status='completed',
                output_doc_ids=final_outputs,
                total_tokens_used=total_tokens,
                total_execution_time_ms=execution_time_ms,
                completed_at=datetime.now(),
            )
            wf_db.increment_workflow_usage(workflow.id, success=True)

        except Exception as e:
            wf_db.update_workflow_run(
                run_id,
                status='failed',
                error_message=str(e),
                completed_at=datetime.now(),
            )
            wf_db.increment_workflow_usage(workflow.id, success=False)

        row = wf_db.get_workflow_run(run_id)
        return WorkflowRun.from_db_row(row)

    async def _load_document_variables(self, context: Dict[str, Any]) -> None:
        """Auto-load document content for doc_N variables.

        If a variable like doc_1, doc_2, etc. is an integer (document ID),
        load the document content and title into doc_N_content and doc_N_title.

        This enables parameterized workflows where each parallel track can
        receive a different input document.

        Args:
            context: Execution context (modified in place)
        """
        import re

        # Find all doc_N variables that look like document IDs
        doc_pattern = re.compile(r'^doc_(\d+)$')
        docs_to_load = []

        for key, value in list(context.items()):
            match = doc_pattern.match(key)
            if match:
                # Try to interpret value as a document ID
                try:
                    doc_id = int(value) if value else None
                    if doc_id:
                        docs_to_load.append((key, doc_id))
                except (ValueError, TypeError):
                    # Not a document ID, skip
                    pass

        # Load documents
        for var_name, doc_id in docs_to_load:
            try:
                doc = document_service.get_document(doc_id)
                if doc:
                    context[f"{var_name}_content"] = doc.get('content', '')
                    context[f"{var_name}_title"] = doc.get('title', '')
                    context[f"{var_name}_id"] = doc_id
                else:
                    # Document not found - set empty values
                    context[f"{var_name}_content"] = f"[Document #{doc_id} not found]"
                    context[f"{var_name}_title"] = ""
                    context[f"{var_name}_id"] = None
            except Exception as e:
                # Log error but continue - don't fail the whole workflow
                context[f"{var_name}_content"] = f"[Error loading document #{doc_id}: {e}]"
                context[f"{var_name}_title"] = ""
                context[f"{var_name}_id"] = None

    async def _execute_stage(
        self,
        workflow_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
    ) -> StageResult:
        """Execute a single stage.

        Args:
            workflow_run_id: Parent workflow run ID
            stage: Stage configuration
            context: Current execution context

        Returns:
            StageResult with execution results
        """
        # Create stage run record
        stage_run_id = wf_db.create_stage_run(
            workflow_run_id=workflow_run_id,
            stage_name=stage.name,
            mode=stage.mode.value,
            target_runs=stage.runs,
        )

        wf_db.update_stage_run(stage_run_id, status='running', started_at=datetime.now())
        start_time = datetime.now()

        try:
            # Resolve input template if specified
            stage_input = self._resolve_template(stage.input, context) if stage.input else None

            # Execute based on mode
            if stage.mode == ExecutionMode.SINGLE:
                result = await self._execute_single(stage_run_id, stage, context, stage_input)
            elif stage.mode == ExecutionMode.PARALLEL:
                result = await self._execute_parallel(stage_run_id, stage, context, stage_input)
            elif stage.mode == ExecutionMode.ITERATIVE:
                result = await self._execute_iterative(stage_run_id, stage, context, stage_input)
            elif stage.mode == ExecutionMode.ADVERSARIAL:
                result = await self._execute_adversarial(stage_run_id, stage, context, stage_input)
            elif stage.mode == ExecutionMode.DYNAMIC:
                result = await self._execute_dynamic(stage_run_id, stage, context, stage_input)
            else:
                raise ValueError(f"Unknown execution mode: {stage.mode}")

            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            result.execution_time_ms = execution_time_ms

            # Update stage run record
            wf_db.update_stage_run(
                stage_run_id,
                status='completed' if result.success else 'failed',
                runs_completed=stage.runs if result.success else 0,
                output_doc_id=result.output_doc_id,
                synthesis_doc_id=result.synthesis_doc_id,
                error_message=result.error_message,
                tokens_used=result.tokens_used,
                execution_time_ms=execution_time_ms,
                completed_at=datetime.now(),
            )

            return result

        except Exception as e:
            wf_db.update_stage_run(
                stage_run_id,
                status='failed',
                error_message=str(e),
                completed_at=datetime.now(),
            )
            return StageResult(success=False, error_message=str(e))

    async def _execute_single(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute a single run.

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult
        """
        # Create individual run record
        prompt = self._resolve_template(stage.prompt, context) if stage.prompt else None
        individual_run_id = wf_db.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=1,
            prompt_used=prompt,
            input_context=stage_input,
        )

        # Execute agent
        result = await self._run_agent(
            individual_run_id=individual_run_id,
            agent_id=stage.agent_id,
            prompt=prompt or stage_input or "",
            context=context,
        )

        return StageResult(
            success=result.get('success', False),
            output_doc_id=result.get('output_doc_id'),
            individual_outputs=[result.get('output_doc_id')] if result.get('output_doc_id') else [],
            tokens_used=result.get('tokens_used', 0),
            error_message=result.get('error_message'),
        )

    async def _execute_parallel(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute N runs in parallel and synthesize results.

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult with synthesis
        """
        # Create individual run records
        individual_runs = []
        for i in range(stage.runs):
            # Support per-run prompts (like iterative mode) or single prompt for all
            if stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = stage.prompt or ""
            prompt = self._resolve_template(prompt_template, context) if prompt_template else None
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=i + 1,
                prompt_used=prompt,
                input_context=stage_input,
            )
            individual_runs.append((individual_run_id, prompt))

        # Execute all runs in parallel (with semaphore limiting)
        # Track completion count for progress updates
        completed_count = 0

        async def run_with_limit(run_id: int, prompt: str):
            nonlocal completed_count
            async with self._semaphore:
                result = await self._run_agent(
                    individual_run_id=run_id,
                    agent_id=stage.agent_id,
                    prompt=prompt or stage_input or "",
                    context=context,
                )
                # Update progress after each completion
                completed_count += 1
                wf_db.update_stage_run(stage_run_id, runs_completed=completed_count)
                return result

        tasks = [run_with_limit(run_id, prompt) for run_id, prompt in individual_runs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful outputs
        output_doc_ids = []
        total_tokens = 0
        errors = []

        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            elif result.get('success'):
                if result.get('output_doc_id'):
                    output_doc_ids.append(result['output_doc_id'])
                total_tokens += result.get('tokens_used', 0)
            else:
                errors.append(result.get('error_message', 'Unknown error'))

        if not output_doc_ids:
            return StageResult(
                success=False,
                error_message=f"All parallel runs failed: {'; '.join(errors)}",
            )

        # Synthesize results
        synthesis_result = await self._synthesize_outputs(
            stage_run_id=stage_run_id,
            output_doc_ids=output_doc_ids,
            synthesis_prompt=stage.synthesis_prompt,
            context=context,
        )

        return StageResult(
            success=True,
            output_doc_id=synthesis_result.get('output_doc_id'),
            synthesis_doc_id=synthesis_result.get('output_doc_id'),
            individual_outputs=output_doc_ids,
            tokens_used=total_tokens + synthesis_result.get('tokens_used', 0),
        )

    async def _execute_iterative(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute N runs sequentially, each building on previous.

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult
        """
        # Load iteration strategy if specified
        strategy = None
        if stage.iteration_strategy:
            strategy = workflow_registry.get_iteration_strategy(stage.iteration_strategy)

        previous_outputs: List[str] = []
        output_doc_ids: List[int] = []
        total_tokens = 0
        last_output_id = None

        for i in range(stage.runs):
            run_number = i + 1

            # Build prompt for this iteration
            if strategy:
                prompt_template = strategy.get_prompt_for_run(run_number)
            elif stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = stage.prompt or ""

            # Build context for template resolution
            iter_context = dict(context)
            iter_context['input'] = stage_input or context.get('input', '')
            iter_context['prev'] = previous_outputs[-1] if previous_outputs else ''
            iter_context['all_prev'] = '\n\n---\n\n'.join(previous_outputs)
            iter_context['run_number'] = run_number

            prompt = self._resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get('prev', ''),
            )

            # Execute this iteration
            result = await self._run_agent(
                individual_run_id=individual_run_id,
                agent_id=stage.agent_id,
                prompt=prompt,
                context=iter_context,
            )

            if not result.get('success'):
                return StageResult(
                    success=False,
                    error_message=f"Iteration {run_number} failed: {result.get('error_message')}",
                    tokens_used=total_tokens,
                )

            # Collect output for next iteration
            if result.get('output_doc_id'):
                doc = document_service.get_document(result['output_doc_id'])
                if doc:
                    previous_outputs.append(doc.get('content', ''))
                    output_doc_ids.append(result['output_doc_id'])
                    last_output_id = result['output_doc_id']

            total_tokens += result.get('tokens_used', 0)

            # Update stage progress
            wf_db.update_stage_run(stage_run_id, runs_completed=run_number)

        return StageResult(
            success=True,
            output_doc_id=last_output_id,
            individual_outputs=output_doc_ids,
            tokens_used=total_tokens,
        )

    async def _execute_adversarial(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute adversarial pattern: Advocate -> Critic -> Synthesizer.

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult
        """
        # Load iteration strategy (adversarial uses same mechanism)
        strategy = None
        if stage.iteration_strategy:
            strategy = workflow_registry.get_iteration_strategy(stage.iteration_strategy)

        # Default adversarial prompts if no strategy
        default_prompts = [
            "ADVOCATE: Argue FOR this approach: {{input}}\n\nWhat are its strengths?",
            "CRITIC: Given this advocacy: {{prev}}\n\nArgue AGAINST. What are the weaknesses?",
            "SYNTHESIS: Advocate: {{all_prev[0]}}\nCritic: {{prev}}\n\nProvide balanced assessment.",
        ]

        outputs: List[str] = []
        output_doc_ids: List[int] = []
        total_tokens = 0
        last_output_id = None

        num_runs = stage.runs if stage.runs else 3  # Default to 3 for adversarial

        for i in range(num_runs):
            run_number = i + 1

            # Get prompt for this role
            if strategy:
                prompt_template = strategy.get_prompt_for_run(run_number)
            elif stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = default_prompts[min(i, len(default_prompts) - 1)]

            # Build context
            iter_context = dict(context)
            iter_context['input'] = stage_input or context.get('input', '')
            iter_context['prev'] = outputs[-1] if outputs else ''
            iter_context['all_prev'] = outputs  # Keep as list for indexed access

            prompt = self._resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get('prev', ''),
            )

            # Execute
            result = await self._run_agent(
                individual_run_id=individual_run_id,
                agent_id=stage.agent_id,
                prompt=prompt,
                context=iter_context,
            )

            if not result.get('success'):
                return StageResult(
                    success=False,
                    error_message=f"Adversarial run {run_number} failed: {result.get('error_message')}",
                    tokens_used=total_tokens,
                )

            # Collect output
            if result.get('output_doc_id'):
                doc = document_service.get_document(result['output_doc_id'])
                if doc:
                    outputs.append(doc.get('content', ''))
                    output_doc_ids.append(result['output_doc_id'])
                    last_output_id = result['output_doc_id']

            total_tokens += result.get('tokens_used', 0)
            wf_db.update_stage_run(stage_run_id, runs_completed=run_number)

        return StageResult(
            success=True,
            output_doc_id=last_output_id,  # Final synthesis is the output
            synthesis_doc_id=last_output_id,
            individual_outputs=output_doc_ids,
            tokens_used=total_tokens,
        )

    async def _run_discovery(
        self,
        command: str,
        context: Dict[str, Any],
    ) -> List[str]:
        """Run discovery command and return list of items.

        Args:
            command: Shell command that outputs items (one per line)
            context: Execution context for template resolution

        Returns:
            List of discovered items (strings)
        """
        import subprocess

        # Resolve any templates in the command
        resolved_command = self._resolve_template(command, context)

        # Run command
        result = await asyncio.to_thread(
            subprocess.run,
            resolved_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=context.get('_working_dir'),
        )

        if result.returncode != 0:
            raise ValueError(f"Discovery command failed: {result.stderr}")

        # Parse output - one item per line, strip whitespace
        items = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
        return items

    async def _execute_dynamic(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute dynamic mode: discover items and process each in parallel.

        Dynamic mode:
        1. Runs discovery_command to get a list of items
        2. Creates a worktree for each item (up to max_concurrent)
        3. Processes items in parallel, respecting concurrency limits
        4. Optionally synthesizes results at the end

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult with all outputs
        """
        from .worktree_pool import WorktreePool

        # Get discovery command (CLI override takes precedence)
        discovery_command = context.get('_discovery_override') or stage.discovery_command

        # Validate configuration
        if not discovery_command:
            return StageResult(
                success=False,
                error_message="Dynamic mode requires discovery_command"
            )

        # Get max_concurrent (CLI override takes precedence)
        max_concurrent = context.get('_max_concurrent_override') or stage.max_concurrent

        # Step 1: Run discovery
        try:
            items = await self._run_discovery(discovery_command, context)
        except Exception as e:
            return StageResult(
                success=False,
                error_message=f"Discovery failed: {e}"
            )

        if not items:
            return StageResult(
                success=True,
                error_message="No items discovered"
            )

        # Update target_runs to reflect discovered item count
        wf_db.update_stage_run(stage_run_id, target_runs=len(items))

        # Step 2: Set up worktree pool
        base_branch = context.get('base_branch', 'main')
        pool = WorktreePool(
            max_size=max_concurrent,
            base_branch=base_branch,
            repo_root=context.get('_working_dir'),
        )

        output_doc_ids: List[int] = []
        total_tokens = 0
        errors: List[str] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_item(item_index: int, item: str) -> Dict[str, Any]:
            """Process a single discovered item."""
            async with semaphore:
                async with pool.acquire(target_branch=item) as worktree:
                    # Build item-specific context
                    item_context = dict(context)
                    item_context[stage.item_variable] = item
                    item_context['_working_dir'] = worktree.path
                    item_context['item_index'] = item_index
                    item_context['total_items'] = len(items)

                    # Resolve prompt with item context
                    prompt = self._resolve_template(stage.prompt, item_context) if stage.prompt else item

                    # Create individual run record
                    individual_run_id = wf_db.create_individual_run(
                        stage_run_id=stage_run_id,
                        run_number=item_index + 1,
                        prompt_used=prompt,
                        input_context=item,
                    )

                    # Execute agent
                    result = await self._run_agent(
                        individual_run_id=individual_run_id,
                        agent_id=stage.agent_id,
                        prompt=prompt,
                        context=item_context,
                    )

                    return {
                        'item': item,
                        'index': item_index,
                        **result
                    }

        try:
            # Step 3: Process all items in parallel
            tasks = [process_item(i, item) for i, item in enumerate(items)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            successful_items = 0
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                    if not stage.continue_on_failure:
                        break
                elif result.get('success'):
                    successful_items += 1
                    if result.get('output_doc_id'):
                        output_doc_ids.append(result['output_doc_id'])
                    total_tokens += result.get('tokens_used', 0)
                else:
                    error_msg = f"Item '{result.get('item')}' failed: {result.get('error_message', 'Unknown error')}"
                    errors.append(error_msg)
                    if not stage.continue_on_failure:
                        break

            # Update stage progress
            wf_db.update_stage_run(stage_run_id, runs_completed=successful_items)

            # Step 4: Optional synthesis
            synthesis_doc_id = None
            if output_doc_ids and stage.synthesis_prompt:
                synthesis_result = await self._synthesize_outputs(
                    stage_run_id=stage_run_id,
                    output_doc_ids=output_doc_ids,
                    synthesis_prompt=stage.synthesis_prompt,
                    context=context,
                )
                synthesis_doc_id = synthesis_result.get('output_doc_id')
                total_tokens += synthesis_result.get('tokens_used', 0)

            # Determine overall success
            if not stage.continue_on_failure and errors:
                return StageResult(
                    success=False,
                    error_message=f"Dynamic execution failed: {'; '.join(errors)}",
                    individual_outputs=output_doc_ids,
                    tokens_used=total_tokens,
                )

            # Success if at least one item succeeded
            success = successful_items > 0

            return StageResult(
                success=success,
                output_doc_id=synthesis_doc_id or (output_doc_ids[-1] if output_doc_ids else None),
                synthesis_doc_id=synthesis_doc_id,
                individual_outputs=output_doc_ids,
                tokens_used=total_tokens,
                error_message=f"Processed {successful_items}/{len(items)} items. Errors: {'; '.join(errors)}" if errors else None,
            )

        finally:
            # Clean up worktree pool
            await pool.cleanup()

    async def _run_agent(
        self,
        individual_run_id: int,
        agent_id: Optional[int],
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run an agent with the given prompt using the existing execution system.

        Uses execute_with_claude() from the existing exec system to actually
        call Claude and get results.

        Args:
            individual_run_id: Individual run ID for tracking
            agent_id: Optional agent ID to use
            prompt: The prompt to send
            context: Execution context

        Returns:
            Dict with success, output_doc_id, tokens_used, error_message
        """
        wf_db.update_individual_run(
            individual_run_id,
            status='running',
            started_at=datetime.now(),
        )

        try:
            # Set up log file for this agent run
            log_dir = Path.home() / ".config" / "emdx" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            log_file = log_dir / f"workflow-agent-{individual_run_id}-{timestamp}.log"

            # Get working directory from context (set by execute_workflow)
            working_dir = context.get('_working_dir', str(Path.cwd()))

            # Create execution record
            # Use None for doc_id if no input document (workflow agents don't always have one)
            exec_id = execution_service.create_execution(
                doc_id=context.get('input_doc_id'),
                doc_title=f"Workflow Agent Run #{individual_run_id}",
                log_file=str(log_file),
                working_dir=working_dir,
            )

            # Link execution to individual run immediately so TUI can show logs
            wf_db.update_individual_run(
                individual_run_id,
                agent_execution_id=exec_id,
            )

            # Build the full prompt with instructions to save output
            output_instruction = """

IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"

Report the document ID that was created."""

            full_prompt = prompt + output_instruction

            # Track execution start time
            exec_start_time = datetime.now()

            # Run Claude synchronously (in thread pool to not block async)
            loop = asyncio.get_event_loop()
            exit_code = await loop.run_in_executor(
                None,
                lambda: claude_service.execute_with_claude(
                    task=full_prompt,
                    execution_id=exec_id,
                    log_file=log_file,
                    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS", "Task", "TodoWrite", "WebFetch", "WebSearch"],
                    verbose=False,
                    working_dir=working_dir,
                    doc_id=str(context.get('input_doc_id', 0)),
                    context=None,
                )
            )

            # Calculate execution time
            exec_end_time = datetime.now()
            execution_time_ms = int((exec_end_time - exec_start_time).total_seconds() * 1000)

            # Update execution status
            status = 'completed' if exit_code == 0 else 'failed'
            execution_service.update_execution_status(exec_id, status, exit_code)

            # Extract token usage from the log file (detailed version with in/out and cost)
            token_usage = self._extract_token_usage_detailed(log_file)
            tokens_used = token_usage.get('total', 0)
            input_tokens = token_usage.get('input', 0) + token_usage.get('cache_in', 0) + token_usage.get('cache_create', 0)
            output_tokens = token_usage.get('output', 0)
            cost_usd = token_usage.get('cost_usd', 0.0)

            if exit_code == 0:
                # Try to extract output document ID from log
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # If no document was created, save the log content as output
                    log_content = log_file.read_text() if log_file.exists() else "No output captured"
                    output_doc_id = document_service.save_document(
                        title=f"Workflow Agent Output - {datetime.now().isoformat()}",
                        content=f"# Agent Execution Log\n\n{log_content}",
                        tags=['workflow-output'],
                    )
                    # Record document source for efficient querying
                    ir = wf_db.get_individual_run(individual_run_id)
                    if ir:
                        sr = wf_db.get_stage_run(ir["stage_run_id"])
                        if sr:
                            record_document_source(
                                document_id=output_doc_id,
                                workflow_run_id=sr.get("workflow_run_id"),
                                workflow_stage_run_id=ir["stage_run_id"],
                                workflow_individual_run_id=individual_run_id,
                                source_type="individual_output",
                            )

                wf_db.update_individual_run(
                    individual_run_id,
                    status='completed',
                    output_doc_id=output_doc_id,
                    agent_execution_id=exec_id,
                    tokens_used=tokens_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    execution_time_ms=execution_time_ms,
                    completed_at=exec_end_time,
                )

                return {
                    'success': True,
                    'output_doc_id': output_doc_id,
                    'tokens_used': tokens_used,
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'cost_usd': cost_usd,
                    'execution_time_ms': execution_time_ms,
                    'execution_id': exec_id,
                }
            else:
                error_msg = f"Claude execution failed with exit code {exit_code}"
                wf_db.update_individual_run(
                    individual_run_id,
                    status='failed',
                    agent_execution_id=exec_id,
                    error_message=error_msg,
                    tokens_used=tokens_used,
                    execution_time_ms=execution_time_ms,
                    completed_at=exec_end_time,
                )
                return {
                    'success': False,
                    'error_message': error_msg,
                    'tokens_used': tokens_used,
                    'execution_time_ms': execution_time_ms,
                    'execution_id': exec_id,
                }

        except Exception as e:
            wf_db.update_individual_run(
                individual_run_id,
                status='failed',
                error_message=str(e),
                completed_at=datetime.now(),
            )
            return {
                'success': False,
                'error_message': str(e),
            }

    def _extract_output_doc_id(self, log_file: Path) -> Optional[int]:
        """Extract output document ID from execution log.

        Looks for patterns like "Created document #123" or "Saved as #123"
        in the log file. Handles Rich/ANSI formatting codes.

        Args:
            log_file: Path to the execution log

        Returns:
            Document ID if found, None otherwise
        """
        if not log_file.exists():
            return None

        try:
            content = log_file.read_text()

            # Strip ANSI codes for cleaner matching
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_content = ansi_escape.sub('', content)

            # Also handle Rich markup-style codes like [32m, [0m, [1;32m
            rich_codes = re.compile(r'\[\d+(?:;\d+)*m')
            clean_content = rich_codes.sub('', clean_content)

            # Look for document creation patterns (check LAST match to get final save)
            patterns = [
                r'saved as document #(\d+)',  # Agent natural language
                r'Saved as #(\d+)',           # CLI output
                r'Created document #(\d+)',
                r'document ID[:\s]+#?(\d+)',
                r'doc_id[:\s]+(\d+)',
                r'✅ Saved as\s*#(\d+)',      # With emoji
            ]

            # Find ALL matches and return the LAST one (most likely the final output)
            last_match = None
            for pattern in patterns:
                for match in re.finditer(pattern, clean_content, re.IGNORECASE):
                    last_match = int(match.group(1))

            if last_match:
                return last_match

            return None
        except (OSError, IOError) as e:
            # Log file read errors
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Could not read log file {log_file} for output doc ID extraction: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            # Log unexpected errors during parsing
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Unexpected error extracting output doc ID from {log_file}: {type(e).__name__}: {e}")
            return None

    def _extract_token_usage(self, log_file: Path) -> int:
        """Extract total token usage from Claude execution log.

        Args:
            log_file: Path to the execution log

        Returns:
            Total tokens used, or 0 if not found
        """
        usage = self._extract_token_usage_detailed(log_file)
        return usage.get('total', 0)

    def _extract_token_usage_detailed(self, log_file: Path) -> Dict[str, int]:
        """Extract detailed token usage from Claude execution log.

        Parses the log file looking for the raw result JSON that was embedded
        by format_claude_output with the __RAW_RESULT_JSON__ marker.

        Args:
            log_file: Path to the execution log

        Returns:
            Dict with 'input', 'output', 'cache_in', 'cache_create', 'total', 'cost_usd' keys
        """
        empty = {'input': 0, 'output': 0, 'cache_in': 0, 'cache_create': 0, 'total': 0, 'cost_usd': 0.0}
        if not log_file.exists():
            return empty

        try:
            content = log_file.read_text()
            # Look for the raw result JSON marker added by format_claude_output
            marker = '__RAW_RESULT_JSON__:'
            for line in content.split('\n'):
                if line.startswith(marker):
                    json_str = line[len(marker):]
                    try:
                        data = json.loads(json_str)
                        if data.get('type') == 'result' and 'usage' in data:
                            usage = data['usage']
                            input_tokens = usage.get('input_tokens', 0)
                            output_tokens = usage.get('output_tokens', 0)
                            cache_creation = usage.get('cache_creation_input_tokens', 0)
                            cache_read = usage.get('cache_read_input_tokens', 0)
                            total = input_tokens + output_tokens + cache_creation + cache_read
                            cost_usd = data.get('total_cost_usd', 0.0)
                            return {
                                'input': input_tokens + cache_read,  # Effective input
                                'output': output_tokens,
                                'cache_in': cache_read,
                                'cache_create': cache_creation,
                                'total': total,
                                'cost_usd': cost_usd,
                            }
                    except json.JSONDecodeError:
                        continue

            return empty
        except (OSError, IOError) as e:
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Could not read log file {log_file} for token extraction: {type(e).__name__}: {e}")
            return empty
        except Exception as e:
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Unexpected error extracting tokens from {log_file}: {type(e).__name__}: {e}")
            return empty

    async def _synthesize_outputs(
        self,
        stage_run_id: int,
        output_doc_ids: List[int],
        synthesis_prompt: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize multiple outputs into one using Claude.

        Args:
            stage_run_id: Stage run ID
            output_doc_ids: List of output document IDs to synthesize
            synthesis_prompt: Prompt template for synthesis
            context: Execution context

        Returns:
            Dict with output_doc_id and tokens_used
        """
        # Gather all outputs
        outputs = []
        for doc_id in output_doc_ids:
            doc = document_service.get_document(doc_id)
            if doc:
                outputs.append(doc.get('content', ''))

        # Build synthesis context
        synth_context = dict(context)
        synth_context['outputs'] = '\n\n---\n\n'.join(outputs)
        synth_context['output_count'] = len(outputs)

        base_prompt = self._resolve_template(
            synthesis_prompt or "Synthesize these outputs into a coherent summary:\n\n{{outputs}}",
            synth_context,
        )

        # Add instruction to save output
        full_prompt = base_prompt + """

IMPORTANT: After synthesizing, save your synthesis as a document using:
echo "YOUR SYNTHESIS HERE" | emdx save --title "Synthesis" --tags "workflow-synthesis"

Report the document ID that was created."""

        try:
            # Set up log file
            log_dir = Path.home() / ".config" / "emdx" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            log_file = log_dir / f"workflow-synthesis-{stage_run_id}-{timestamp}.log"

            # Get working directory from context
            working_dir = context.get('_working_dir', str(Path.cwd()))

            # Create execution record
            # Use None instead of 0 for doc_id to avoid FK constraint errors
            input_doc_id = context.get('input_doc_id')
            if input_doc_id == 0:
                input_doc_id = None
            exec_id = execution_service.create_execution(
                doc_id=input_doc_id,
                doc_title=f"Workflow Synthesis #{stage_run_id}",
                log_file=str(log_file),
                working_dir=working_dir,
            )

            # Run Claude
            loop = asyncio.get_event_loop()
            exit_code = await loop.run_in_executor(
                None,
                lambda: claude_service.execute_with_claude(
                    task=full_prompt,
                    execution_id=exec_id,
                    log_file=log_file,
                    allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
                    verbose=False,
                    working_dir=working_dir,
                    doc_id=str(context.get('input_doc_id', 0)),
                    context=None,
                )
            )

            execution_service.update_execution_status(exec_id, 'completed' if exit_code == 0 else 'failed', exit_code)

            if exit_code == 0:
                # Try to extract output document ID
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # Fallback: save log content
                    log_content = log_file.read_text() if log_file.exists() else "No synthesis output"
                    output_doc_id = document_service.save_document(
                        title=f"Synthesis - {datetime.now().isoformat()}",
                        content=f"# Synthesis Log\n\n{log_content}",
                        tags=['workflow-synthesis'],
                    )
                    # Record document source for efficient querying
                    sr = wf_db.get_stage_run(stage_run_id)
                    if sr:
                        record_document_source(
                            document_id=output_doc_id,
                            workflow_run_id=sr.get("workflow_run_id"),
                            workflow_stage_run_id=stage_run_id,
                            source_type="synthesis",
                        )

                return {
                    'output_doc_id': output_doc_id,
                    'tokens_used': 0,
                    'execution_id': exec_id,
                }
            else:
                # Fallback on failure: just combine outputs manually
                combined = f"# Synthesis of {len(outputs)} outputs (fallback - Claude failed)\n\n"
                for i, output in enumerate(outputs, 1):
                    combined += f"## Output {i}\n{output}\n\n"

                doc_id = document_service.save_document(
                    title=f"Synthesis (fallback) - {datetime.now().isoformat()}",
                    content=combined,
                    tags=['workflow-synthesis'],
                )
                # Record document source for efficient querying
                sr = wf_db.get_stage_run(stage_run_id)
                if sr:
                    record_document_source(
                        document_id=doc_id,
                        workflow_run_id=sr.get("workflow_run_id"),
                        workflow_stage_run_id=stage_run_id,
                        source_type="synthesis",
                    )

                return {
                    'output_doc_id': doc_id,
                    'tokens_used': 0,
                }

        except Exception as e:
            # Fallback: manual combination
            combined = f"# Synthesis of {len(outputs)} outputs (error: {e})\n\n"
            for i, output in enumerate(outputs, 1):
                combined += f"## Output {i}\n{output}\n\n"

            doc_id = document_service.save_document(
                title=f"Synthesis (error) - {datetime.now().isoformat()}",
                content=combined,
                tags=['workflow-synthesis'],
            )
            # Record document source for efficient querying
            sr = wf_db.get_stage_run(stage_run_id)
            if sr:
                record_document_source(
                    document_id=doc_id,
                    workflow_run_id=sr.get("workflow_run_id"),
                    workflow_stage_run_id=stage_run_id,
                    source_type="synthesis",
                )

            return {
                'output_doc_id': doc_id,
                'tokens_used': 0,
        }

    def _resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
        """Resolve {{variable}} templates in a string.

        Args:
            template: String with {{variable}} placeholders
            context: Dictionary of values to substitute

        Returns:
            Resolved string
        """
        if not template:
            return ""

        result = template

        # Handle indexed access like {{all_prev[0]}}
        indexed_pattern = r'\{\{(\w+)\[(\d+)\]\}\}'
        for match in re.finditer(indexed_pattern, template):
            var_name = match.group(1)
            index = int(match.group(2))
            if var_name in context and isinstance(context[var_name], list):
                if index < len(context[var_name]):
                    result = result.replace(match.group(0), str(context[var_name][index]))
                else:
                    result = result.replace(match.group(0), '')

        # Handle simple variables like {{input}}
        simple_pattern = r'\{\{(\w+(?:\.\w+)*)\}\}'
        for match in re.finditer(simple_pattern, result):
            var_name = match.group(1)
            # Handle dotted access like stage_name.output
            if '.' in var_name:
                value = context.get(var_name, '')
            else:
                value = context.get(var_name, '')
            result = result.replace(match.group(0), str(value))

        return result


# Global executor instance
workflow_executor = WorkflowExecutor()
