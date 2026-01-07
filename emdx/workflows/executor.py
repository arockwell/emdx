"""Workflow executor for orchestrating multi-stage agent runs."""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from emdx.database import db_connection
from emdx.models.documents import save_document, get_document
from emdx.models.executions import create_execution, get_execution, update_execution_status

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
        gameplan_id: Optional[int] = None,
        task_id: Optional[int] = None,
    ) -> WorkflowRun:
        """Execute a workflow.

        Args:
            workflow_name_or_id: Workflow name or ID
            input_doc_id: Optional input document ID
            input_variables: Optional runtime variables
            gameplan_id: Optional link to gameplan
            task_id: Optional link to task

        Returns:
            WorkflowRun with execution results
        """
        # Load workflow
        workflow = workflow_registry.get_workflow(workflow_name_or_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_name_or_id}")

        # Create workflow run record
        run_id = wf_db.create_workflow_run(
            workflow_id=workflow.id,
            input_doc_id=input_doc_id,
            input_variables=input_variables,
            gameplan_id=gameplan_id,
            task_id=task_id,
        )

        # Start execution
        wf_db.update_workflow_run(
            run_id,
            status='running',
            started_at=datetime.now(),
        )

        start_time = datetime.now()
        context: Dict[str, Any] = {}
        total_tokens = 0

        try:
            # Load input document content if provided
            if input_doc_id:
                doc = get_document(input_doc_id)
                if doc:
                    context['input'] = doc.get('content', '')
                    context['input_title'] = doc.get('title', '')

            # Merge with provided variables
            if input_variables:
                context.update(input_variables)

            # Also merge workflow default variables
            context.update(workflow.variables)

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
                    doc = get_document(result.output_doc_id)
                    if doc:
                        context[f"{stage.name}.output"] = doc.get('content', '')
                        context[f"{stage.name}.output_id"] = result.output_doc_id

                if result.synthesis_doc_id:
                    doc = get_document(result.synthesis_doc_id)
                    if doc:
                        context[f"{stage.name}.synthesis"] = doc.get('content', '')
                        context[f"{stage.name}.synthesis_id"] = result.synthesis_doc_id

                # Store individual outputs for parallel mode
                if result.individual_outputs:
                    outputs_content = []
                    for doc_id in result.individual_outputs:
                        doc = get_document(doc_id)
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
            prompt = self._resolve_template(stage.prompt, context) if stage.prompt else None
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=i + 1,
                prompt_used=prompt,
                input_context=stage_input,
            )
            individual_runs.append((individual_run_id, prompt))

        # Execute all runs in parallel (with semaphore limiting)
        async def run_with_limit(run_id: int, prompt: str):
            async with self._semaphore:
                return await self._run_agent(
                    individual_run_id=run_id,
                    agent_id=stage.agent_id,
                    prompt=prompt or stage_input or "",
                    context=context,
                )

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
                doc = get_document(result['output_doc_id'])
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
                doc = get_document(result['output_doc_id'])
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
        from emdx.commands.claude_execute import execute_with_claude

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

            # Create execution record
            exec_id = create_execution(
                doc_id=context.get('input_doc_id', 0),
                doc_title=f"Workflow Agent Run #{individual_run_id}",
                log_file=str(log_file),
                working_dir=str(Path.cwd()),
            )

            # Build the full prompt with instructions to save output
            output_instruction = """

IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"

Report the document ID that was created."""

            full_prompt = prompt + output_instruction

            # Run Claude synchronously (in thread pool to not block async)
            loop = asyncio.get_event_loop()
            exit_code = await loop.run_in_executor(
                None,
                lambda: execute_with_claude(
                    task=full_prompt,
                    execution_id=exec_id,
                    log_file=log_file,
                    allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS", "Task", "TodoWrite", "WebFetch", "WebSearch"],
                    verbose=False,
                    working_dir=str(Path.cwd()),
                    doc_id=str(context.get('input_doc_id', 0)),
                    context=None,
                )
            )

            # Update execution status
            status = 'completed' if exit_code == 0 else 'failed'
            update_execution_status(exec_id, status, exit_code)

            if exit_code == 0:
                # Try to extract output document ID from log
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # If no document was created, save the log content as output
                    log_content = log_file.read_text() if log_file.exists() else "No output captured"
                    output_doc_id = save_document(
                        title=f"Workflow Agent Output - {datetime.now().isoformat()}",
                        content=f"# Agent Execution Log\n\n{log_content}",
                        tags=['workflow-output'],
                    )

                wf_db.update_individual_run(
                    individual_run_id,
                    status='completed',
                    output_doc_id=output_doc_id,
                    agent_execution_id=exec_id,
                    tokens_used=0,  # TODO: Parse from log if available
                    completed_at=datetime.now(),
                )

                return {
                    'success': True,
                    'output_doc_id': output_doc_id,
                    'tokens_used': 0,
                    'execution_id': exec_id,
                }
            else:
                error_msg = f"Claude execution failed with exit code {exit_code}"
                wf_db.update_individual_run(
                    individual_run_id,
                    status='failed',
                    agent_execution_id=exec_id,
                    error_message=error_msg,
                    completed_at=datetime.now(),
                )
                return {
                    'success': False,
                    'error_message': error_msg,
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
        in the log file.

        Args:
            log_file: Path to the execution log

        Returns:
            Document ID if found, None otherwise
        """
        if not log_file.exists():
            return None

        try:
            content = log_file.read_text()
            # Look for document creation patterns
            patterns = [
                r'Created document #(\d+)',
                r'Saved as #(\d+)',
                r'document ID[:\s]+(\d+)',
                r'doc_id[:\s]+(\d+)',
                r'#(\d+)\s*\[green\]',  # Rich output format
            ]

            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            return None
        except Exception:
            return None

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
        from emdx.commands.claude_execute import execute_with_claude

        # Gather all outputs
        outputs = []
        for doc_id in output_doc_ids:
            doc = get_document(doc_id)
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

            # Create execution record
            exec_id = create_execution(
                doc_id=context.get('input_doc_id', 0),
                doc_title=f"Workflow Synthesis #{stage_run_id}",
                log_file=str(log_file),
                working_dir=str(Path.cwd()),
            )

            # Run Claude
            loop = asyncio.get_event_loop()
            exit_code = await loop.run_in_executor(
                None,
                lambda: execute_with_claude(
                    task=full_prompt,
                    execution_id=exec_id,
                    log_file=log_file,
                    allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
                    verbose=False,
                    working_dir=str(Path.cwd()),
                    doc_id=str(context.get('input_doc_id', 0)),
                    context=None,
                )
            )

            update_execution_status(exec_id, 'completed' if exit_code == 0 else 'failed', exit_code)

            if exit_code == 0:
                # Try to extract output document ID
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # Fallback: save log content
                    log_content = log_file.read_text() if log_file.exists() else "No synthesis output"
                    output_doc_id = save_document(
                        title=f"Synthesis - {datetime.now().isoformat()}",
                        content=f"# Synthesis Log\n\n{log_content}",
                        tags=['workflow-synthesis'],
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

                doc_id = save_document(
                    title=f"Synthesis (fallback) - {datetime.now().isoformat()}",
                    content=combined,
                    tags=['workflow-synthesis'],
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

            doc_id = save_document(
                title=f"Synthesis (error) - {datetime.now().isoformat()}",
                content=combined,
                tags=['workflow-synthesis'],
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
