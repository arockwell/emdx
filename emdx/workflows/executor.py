"""Workflow executor for orchestrating multi-stage agent runs."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .services import document_service, execution_service, claude_service
from .base import (
    ExecutionMode,
    StageConfig,
    WorkflowConfig,
    WorkflowRun,
)
from . import database as wf_db
from .registry import workflow_registry
from .strategies import get_strategy, StageResult


class WorkflowExecutor:
    """Executes workflows with support for different execution modes.

    Supports:
    - single: Run agent once
    - parallel: Run agent N times simultaneously, synthesize results
    - iterative: Run agent N times sequentially, building on previous
    - adversarial: Advocate -> Critic -> Synthesizer pattern
    - dynamic: Discover items at runtime, process each in parallel

    This class acts as the context in the Strategy pattern, delegating
    actual execution to strategy implementations based on execution mode.
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
        working_dir: Optional[str] = None,
    ) -> WorkflowRun:
        """Execute a workflow.

        Args:
            workflow_name_or_id: Workflow name or ID
            input_doc_id: Optional input document ID
            input_variables: Optional runtime variables
            gameplan_id: Optional link to gameplan
            task_id: Optional link to task
            working_dir: Optional working directory for agent execution (e.g., worktree path)

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

            # Merge workflow default variables first
            context.update(workflow.variables)

            # Then override with provided variables (so user input wins)
            if input_variables:
                context.update(input_variables)

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

    async def _execute_stage(
        self,
        workflow_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
    ) -> StageResult:
        """Execute a single stage using the appropriate strategy.

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
            stage_input = self.resolve_template(stage.input, context) if stage.input else None

            # Get the appropriate strategy for this execution mode
            strategy = get_strategy(stage.mode, self)

            # Execute using the strategy
            result = await strategy.execute(
                stage_run_id=stage_run_id,
                stage=stage,
                context=context,
                stage_input=stage_input,
            )

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

    # Protocol methods for strategies to use

    def resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
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

    # Kept for backward compatibility
    def _resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
        """Deprecated: Use resolve_template instead."""
        return self.resolve_template(template, context)

    async def run_agent(
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
            exec_id = execution_service.create_execution(
                doc_id=context.get('input_doc_id', 0),
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

            # Update execution status
            status = 'completed' if exit_code == 0 else 'failed'
            execution_service.update_execution_status(exec_id, status, exit_code)

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

                wf_db.update_individual_run(
                    individual_run_id,
                    status='completed',
                    output_doc_id=output_doc_id,
                    agent_execution_id=exec_id,
                    tokens_used=0,  # Note: Token usage tracking not yet implemented
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

    async def synthesize_outputs(
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

        base_prompt = self.resolve_template(
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
            exec_id = execution_service.create_execution(
                doc_id=context.get('input_doc_id', 0),
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

            return {
                'output_doc_id': doc_id,
                'tokens_used': 0,
            }

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Get a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict or None
        """
        return document_service.get_document(doc_id)

    def create_individual_run(
        self,
        stage_run_id: int,
        run_number: int,
        prompt_used: Optional[str] = None,
        input_context: Optional[str] = None,
    ) -> int:
        """Create an individual run record.

        Args:
            stage_run_id: Parent stage run ID
            run_number: Run number within the stage
            prompt_used: The prompt used for this run
            input_context: Input context for this run

        Returns:
            The individual run ID
        """
        return wf_db.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=run_number,
            prompt_used=prompt_used,
            input_context=input_context,
        )

    def update_stage_run(self, stage_run_id: int, **kwargs) -> None:
        """Update a stage run record.

        Args:
            stage_run_id: Stage run ID
            **kwargs: Fields to update
        """
        wf_db.update_stage_run(stage_run_id, **kwargs)

    def get_iteration_strategy(self, name: str):
        """Get an iteration strategy by name.

        Args:
            name: Strategy name

        Returns:
            IterationStrategy or None
        """
        return workflow_registry.get_iteration_strategy(name)


# Global executor instance
workflow_executor = WorkflowExecutor()
