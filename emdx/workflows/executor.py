"""Workflow executor for orchestrating multi-stage agent runs.

Execution mode logic (single, parallel, iterative, adversarial, dynamic)
has been extracted into strategies/ — this module handles orchestration only.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .services import document_service
from .base import (
    ExecutionMode,
    StageConfig,
    StageResult,
    WorkflowConfig,
    WorkflowRun,
)
from . import database as wf_db
from .registry import workflow_registry
from .template import resolve_template
from .strategies import get_strategy
from emdx.config import DEFAULT_MAX_CONCURRENT_WORKFLOWS

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Executes workflows with support for different execution modes.

    Mode implementations live in strategies/. This class handles:
    - Workflow loading and variable merging
    - Sequential stage execution
    - Context propagation between stages
    - Task-to-prompt expansion
    - Document variable auto-loading
    """

    def __init__(self, max_concurrent: int = DEFAULT_MAX_CONCURRENT_WORKFLOWS):
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
        merged_variables = {}
        merged_variables.update(workflow.variables)
        merged_variables.update(preset_variables)
        if input_variables:
            merged_variables.update(input_variables)

        # Create workflow run record with preset tracking
        run_id = wf_db.create_workflow_run(
            workflow_id=workflow.id,
            input_doc_id=input_doc_id,
            input_variables=merged_variables,
            gameplan_id=gameplan_id,
            task_id=task_id,
        )

        # Update run with preset info
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

            # Apply merged variables
            context.update(merged_variables)

            # Auto-load document content for doc_N variables
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

                if result.individual_outputs:
                    outputs_content = []
                    for doc_id in result.individual_outputs:
                        doc = document_service.get_document(doc_id)
                        if doc:
                            outputs_content.append(doc.get('content', ''))
                    context[f"{stage.name}.outputs"] = outputs_content

                wf_db.update_workflow_run(
                    run_id,
                    context_json=json.dumps(context),
                )

            # All stages completed successfully
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

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
            try:
                wf_db.update_workflow_run(
                    run_id,
                    status='failed',
                    error_message=str(e),
                    completed_at=datetime.now(),
                )
                wf_db.increment_workflow_usage(workflow.id, success=False)
            except Exception as record_err:
                logger.error("Failed to record workflow failure for run %s: %s (original error: %s)", run_id, record_err, e)

        row = wf_db.get_workflow_run(run_id)
        return WorkflowRun.from_db_row(row)

    async def _load_document_variables(self, context: Dict[str, Any]) -> None:
        """Auto-load document content for doc_N variables.

        If a variable like doc_1, doc_2, etc. is an integer (document ID),
        load the document content and title into doc_N_content and doc_N_title.

        Args:
            context: Execution context (modified in place)
        """
        import re

        doc_pattern = re.compile(r'^doc_(\d+)$')
        docs_to_load = []

        for key, value in list(context.items()):
            match = doc_pattern.match(key)
            if match:
                try:
                    doc_id = int(value) if value else None
                    if doc_id:
                        docs_to_load.append((key, doc_id))
                except (ValueError, TypeError):
                    pass

        for var_name, doc_id in docs_to_load:
            try:
                doc = document_service.get_document(doc_id)
                if doc:
                    context[f"{var_name}_content"] = doc.get('content', '')
                    context[f"{var_name}_title"] = doc.get('title', '')
                    context[f"{var_name}_id"] = doc_id
                else:
                    context[f"{var_name}_content"] = f"[Document #{doc_id} not found]"
                    context[f"{var_name}_title"] = ""
                    context[f"{var_name}_id"] = None
            except Exception as e:
                context[f"{var_name}_content"] = f"[Error loading document #{doc_id}: {e}]"
                context[f"{var_name}_title"] = ""
                context[f"{var_name}_id"] = None

    async def _execute_stage(
        self,
        workflow_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
    ) -> StageResult:
        """Execute a single stage by dispatching to the appropriate strategy.

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

            # Dispatch to strategy
            strategy = get_strategy(stage.mode)
            result = await strategy.execute(
                stage_run_id=stage_run_id,
                stage=stage,
                context=context,
                stage_input=stage_input,
                executor=self,
            )

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

    def _expand_tasks_to_prompts(self, stage: StageConfig, context: Dict[str, Any]) -> None:
        """Expand tasks into prompts if tasks are provided.

        If context contains 'tasks' list and stage has a prompt template,
        generates one prompt per task by substituting {{task}}, {{task_title}},
        and {{task_id}} placeholders.

        Also stores the original task titles on stage._task_titles for use
        in execution titles (avoids garbled multi-line template titles).

        Args:
            stage: Stage configuration to modify
            context: Execution context with optional 'tasks' list
        """
        tasks = context.get('tasks')
        if not tasks or not stage.prompt:
            return

        from .tasks import resolve_tasks

        resolved_tasks = resolve_tasks(tasks)
        prompts = []

        for task_ctx in resolved_tasks:
            prompt = stage.prompt
            prompt = prompt.replace('{{task}}', task_ctx.content)
            prompt = prompt.replace('{{task_title}}', task_ctx.title)
            prompt = prompt.replace('{{task_id}}', str(task_ctx.id) if task_ctx.id else '')
            prompts.append(prompt)

        stage.prompts = prompts

        # Store original task titles for clean execution titles
        stage._task_titles = [
            task_ctx.title or task_ctx.content[:80]
            for task_ctx in resolved_tasks
        ]


# Global executor instance
workflow_executor = WorkflowExecutor()
