"""Workflow executor for orchestrating multi-stage agent runs."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .services import document_service

# Maximum size for content stored in workflow context (prevents OOM in multi-stage workflows)
MAX_CONTEXT_CONTENT_SIZE = 50000  # ~50KB per context entry
from .base import (
    ExecutionMode,
    IterationStrategy,
    StageConfig,
    StageResult,
    WorkflowConfig,
    WorkflowIndividualRun,
    WorkflowRun,
    WorkflowStageRun,
)
from . import database as wf_db
from .registry import workflow_registry
from .template import resolve_template
from .output_parser import extract_output_doc_id, extract_token_usage_detailed
from .agent_runner import run_agent
from .synthesis import synthesize_outputs
from emdx.database import groups as groups_db
from emdx.config import DEFAULT_MAX_CONCURRENT_WORKFLOWS

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Executes workflows with support for different execution modes.

    Supports:
    - single: Run agent once
    - parallel: Run agent N times simultaneously, synthesize results
    - iterative: Run agent N times sequentially, each building on previous
    - adversarial: Advocate -> Critic -> Synthesizer pattern
    """

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT_WORKFLOWS):
        """Initialize executor.

        Args:
            max_concurrent: Maximum concurrent agent runs (for parallel mode)
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _truncate_content(self, content: str, max_size: int = MAX_CONTEXT_CONTENT_SIZE) -> str:
        """Truncate content to prevent context bloat in multi-stage workflows.

        Preserves the beginning and end of the content to maintain context.

        Args:
            content: The content to truncate
            max_size: Maximum allowed size

        Returns:
            Truncated content with indicator if truncation occurred
        """
        if len(content) <= max_size:
            return content

        # Keep first 80% and last 10%, leave 10% for truncation message
        head_size = int(max_size * 0.8)
        tail_size = int(max_size * 0.1)
        truncated_chars = len(content) - head_size - tail_size

        return (
            content[:head_size] +
            f"\n\n[... truncated {truncated_chars} chars ...]\n\n" +
            content[-tail_size:]
        )

    async def _acquire_semaphore_with_timeout(
        self,
        semaphore: asyncio.Semaphore,
        timeout: float = 300.0,
    ) -> bool:
        """Acquire semaphore with timeout to prevent deadlock.

        Args:
            semaphore: The semaphore to acquire
            timeout: Maximum time to wait in seconds (default 5 minutes)

        Returns:
            True if acquired successfully

        Raises:
            RuntimeError: If acquisition times out
        """
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"Failed to acquire workflow execution slot within {timeout}s. "
                "This may indicate a deadlock or resource exhaustion."
            )

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

                # Store stage output in context for later stages (with size limits)
                if result.output_doc_id:
                    doc = document_service.get_document(result.output_doc_id)
                    if doc:
                        content = doc.get('content', '')
                        context[f"{stage.name}.output"] = self._truncate_content(content)
                        context[f"{stage.name}.output_id"] = result.output_doc_id

                if result.synthesis_doc_id:
                    doc = document_service.get_document(result.synthesis_doc_id)
                    if doc:
                        content = doc.get('content', '')
                        context[f"{stage.name}.synthesis"] = self._truncate_content(content)
                        context[f"{stage.name}.synthesis_id"] = result.synthesis_doc_id

                # Store individual outputs for parallel mode (with size limits)
                if result.individual_outputs:
                    outputs_content = []
                    for doc_id in result.individual_outputs:
                        doc = document_service.get_document(doc_id)
                        if doc:
                            content = doc.get('content', '')
                            outputs_content.append(self._truncate_content(content))
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
        # Expand tasks into prompts BEFORE creating stage run (so target_runs is correct)
        self._expand_tasks_to_prompts(stage, context)

        # Determine actual run count
        num_runs = len(stage.prompts) if stage.prompts else stage.runs

        # Create stage run record with correct target
        stage_run_id = wf_db.create_stage_run(
            workflow_run_id=workflow_run_id,
            stage_name=stage.name,
            mode=stage.mode.value,
            target_runs=num_runs,
        )

        wf_db.update_stage_run(stage_run_id, status='running', started_at=datetime.now())
        start_time = datetime.now()

        try:
            # Resolve input template if specified
            stage_input = resolve_template(stage.input, context) if stage.input else None

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
                runs_completed=num_runs if result.success else 0,
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
        prompt = resolve_template(stage.prompt, context) if stage.prompt else None
        individual_run_id = wf_db.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=1,
            prompt_used=prompt,
            input_context=stage_input,
        )

        # Execute agent
        result = await run_agent(
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
        # Create a group for this parallel execution's outputs
        workflow_name = context.get("workflow_name", "Workflow")
        stage_name = stage.name or f"Stage {stage_run_id}"
        run_id = context.get("run_id")

        # Determine run count: use prompts length if provided, otherwise stage.runs
        num_runs = len(stage.prompts) if stage.prompts else stage.runs

        group_id = None
        try:
            group_id = groups_db.create_group(
                name=f"{workflow_name} - {stage_name}",
                group_type="batch",
                workflow_run_id=run_id,
                description=f"Parallel outputs from {num_runs} runs",
                created_by="workflow",
            )
        except Exception as e:
            # Don't fail the workflow if group creation fails
            import logging
            logging.getLogger(__name__).warning(f"Could not create group for parallel stage: {e}")

        # Create individual run records
        individual_runs = []
        for i in range(num_runs):
            # Support per-run prompts (like iterative mode) or single prompt for all
            if stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = stage.prompt or ""
            prompt = resolve_template(prompt_template, context) if prompt_template else None
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=i + 1,
                prompt_used=prompt,
                input_context=stage_input,
            )
            individual_runs.append((individual_run_id, prompt))

        # Execute all runs in parallel with worktree isolation
        # Track completion count for progress updates
        completed_count = 0

        # Get max_concurrent from context or stage config
        max_concurrent = context.get('_max_concurrent_override') or stage.max_concurrent or self.max_concurrent

        # Use worktree pool for isolation when running multiple tasks
        from .worktree_pool import WorktreePool

        base_branch = context.get('base_branch', 'main')
        pool = WorktreePool(
            max_size=max_concurrent,
            base_branch=base_branch,
        )

        async def run_with_worktree(run_id: int, prompt: str, run_number: int):
            nonlocal completed_count
            try:
                async with pool.acquire(target_branch=f"parallel-{stage_run_id}-{run_number}") as worktree:
                    # Create isolated context with worktree path
                    run_context = dict(context)
                    run_context['_working_dir'] = worktree.path

                    result = await run_agent(
                        individual_run_id=run_id,
                        agent_id=stage.agent_id,
                        prompt=prompt or stage_input or "",
                        context=run_context,
                    )
                    # Update progress after each completion
                    completed_count += 1
                    wf_db.update_stage_run(stage_run_id, runs_completed=completed_count)
                    return result
            except Exception as e:
                return {'success': False, 'error_message': str(e)}

        try:
            tasks = [
                run_with_worktree(run_id, prompt, i + 1)
                for i, (run_id, prompt) in enumerate(individual_runs)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Clean up worktree pool
            await pool.cleanup()

        # Collect successful outputs
        output_doc_ids = []
        total_tokens = 0
        errors = []

        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
            elif result.get('success'):
                if result.get('output_doc_id'):
                    doc_id = result['output_doc_id']
                    output_doc_ids.append(doc_id)
                    # Add to group as exploration
                    if group_id:
                        try:
                            groups_db.add_document_to_group(
                                group_id, doc_id, role="exploration", added_by="workflow"
                            )
                        except Exception as e:
                            logger.debug("Failed to add doc %s to group %s: %s", doc_id, group_id, e)
                total_tokens += result.get('tokens_used', 0)
            else:
                errors.append(result.get('error_message', 'Unknown error'))

        if not output_doc_ids:
            return StageResult(
                success=False,
                error_message=f"All parallel runs failed: {'; '.join(errors)}",
            )

        # Synthesize results (skip for single task - nothing to synthesize)
        synthesis_doc_id = None
        if len(output_doc_ids) > 1 and stage.synthesis_prompt:
            # Emit synthesis phase status for UI display
            wf_db.update_stage_run(stage_run_id, status='synthesizing')

            synthesis_result = await synthesize_outputs(
                stage_run_id=stage_run_id,
                output_doc_ids=output_doc_ids,
                synthesis_prompt=stage.synthesis_prompt,
                context=context,
            )

            # Add synthesis doc to group as primary
            synthesis_doc_id = synthesis_result.get('output_doc_id')
            if group_id and synthesis_doc_id:
                try:
                    groups_db.add_document_to_group(
                        group_id, synthesis_doc_id, role="primary", added_by="workflow"
                    )
                except Exception as e:
                    logger.debug("Failed to add synthesis doc %s to group %s: %s", synthesis_doc_id, group_id, e)
            total_tokens += synthesis_result.get('tokens_used', 0)

        return StageResult(
            success=True,
            output_doc_id=synthesis_doc_id or output_doc_ids[-1],
            synthesis_doc_id=synthesis_doc_id,
            individual_outputs=output_doc_ids,
            tokens_used=total_tokens,
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
        previous_outputs: List[str] = []
        output_doc_ids: List[int] = []
        total_tokens = 0
        last_output_id = None

        for i in range(stage.runs):
            run_number = i + 1

            # Build prompt for this iteration
            if stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = stage.prompt or ""

            # Build context for template resolution
            iter_context = dict(context)
            iter_context['input'] = stage_input or context.get('input', '')
            iter_context['prev'] = previous_outputs[-1] if previous_outputs else ''
            iter_context['all_prev'] = '\n\n---\n\n'.join(previous_outputs)
            iter_context['run_number'] = run_number

            prompt = resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get('prev', ''),
            )

            # Execute this iteration
            result = await run_agent(
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
        # Default adversarial prompts
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
            if stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = default_prompts[min(i, len(default_prompts) - 1)]

            # Build context
            iter_context = dict(context)
            iter_context['input'] = stage_input or context.get('input', '')
            iter_context['prev'] = outputs[-1] if outputs else ''
            iter_context['all_prev'] = outputs  # Keep as list for indexed access

            prompt = resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get('prev', ''),
            )

            # Execute
            result = await run_agent(
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
        resolved_command = resolve_template(command, context)

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

        # Create a group for this dynamic execution's outputs
        workflow_name = context.get("workflow_name", "Workflow")
        stage_name = stage.name or f"Stage {stage_run_id}"
        run_id = context.get("run_id")

        group_id = None
        try:
            group_id = groups_db.create_group(
                name=f"{workflow_name} - {stage_name}",
                group_type="batch",
                workflow_run_id=run_id,
                description=f"Dynamic outputs from {len(items)} discovered items",
                created_by="workflow",
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not create group for dynamic stage: {e}")

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
            # Use timeout-based acquisition to prevent deadlock
            await self._acquire_semaphore_with_timeout(semaphore, timeout=600.0)
            try:
                async with pool.acquire(target_branch=item) as worktree:
                    # Build item-specific context
                    item_context = dict(context)
                    item_context[stage.item_variable] = item
                    item_context['_working_dir'] = worktree.path
                    item_context['item_index'] = item_index
                    item_context['total_items'] = len(items)

                    # Resolve prompt with item context
                    prompt = resolve_template(stage.prompt, item_context) if stage.prompt else item

                    # Create individual run record
                    individual_run_id = wf_db.create_individual_run(
                        stage_run_id=stage_run_id,
                        run_number=item_index + 1,
                        prompt_used=prompt,
                        input_context=item,
                    )

                    # Execute agent
                    result = await run_agent(
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
            finally:
                # Always release semaphore to prevent deadlock
                semaphore.release()

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
                        doc_id = result['output_doc_id']
                        output_doc_ids.append(doc_id)
                        # Add to group as exploration
                        if group_id:
                            try:
                                groups_db.add_document_to_group(
                                    group_id, doc_id, role="exploration", added_by="workflow"
                                )
                            except Exception as e:
                                logger.debug("Failed to add doc %s to group %s: %s", doc_id, group_id, e)
                    total_tokens += result.get('tokens_used', 0)
                else:
                    error_msg = f"Item '{result.get('item')}' failed: {result.get('error_message', 'Unknown error')}"
                    errors.append(error_msg)
                    if not stage.continue_on_failure:
                        break

            # Update stage progress
            wf_db.update_stage_run(stage_run_id, runs_completed=successful_items)

            # Step 4: Optional synthesis (skip for single task - nothing to synthesize)
            synthesis_doc_id = None
            if len(output_doc_ids) > 1 and stage.synthesis_prompt:
                # Emit synthesis phase status for UI display
                wf_db.update_stage_run(stage_run_id, status='synthesizing')

                synthesis_result = await synthesize_outputs(
                    stage_run_id=stage_run_id,
                    output_doc_ids=output_doc_ids,
                    synthesis_prompt=stage.synthesis_prompt,
                    context=context,
                )
                synthesis_doc_id = synthesis_result.get('output_doc_id')
                total_tokens += synthesis_result.get('tokens_used', 0)

                # Add synthesis doc to group as primary
                if group_id and synthesis_doc_id:
                    try:
                        groups_db.add_document_to_group(
                            group_id, synthesis_doc_id, role="primary", added_by="workflow"
                        )
                    except Exception as e:
                        logger.debug("Failed to add synthesis doc %s to group %s: %s", synthesis_doc_id, group_id, e)

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

    def _expand_tasks_to_prompts(self, stage: StageConfig, context: Dict[str, Any]) -> None:
        """Expand tasks into prompts if tasks are provided.

        If context contains 'tasks' list and stage has a prompt template,
        generates one prompt per task by substituting {{task}}, {{task_title}},
        and {{task_id}} placeholders.

        Args:
            stage: Stage configuration to modify
            context: Execution context with optional 'tasks' list
        """
        tasks = context.get('tasks')
        if not tasks or not stage.prompt:
            return

        # Import here to avoid circular imports
        from .tasks import resolve_tasks

        resolved_tasks = resolve_tasks(tasks)
        prompts = []

        for task_ctx in resolved_tasks:
            prompt = stage.prompt
            prompt = prompt.replace('{{task}}', task_ctx.content)
            prompt = prompt.replace('{{task_title}}', task_ctx.title)
            prompt = prompt.replace('{{task_id}}', str(task_ctx.id) if task_ctx.id else '')
            prompts.append(prompt)

        # Set prompts on stage (parallel strategy will use these)
        stage.prompts = prompts


# Global executor instance
workflow_executor = WorkflowExecutor()
