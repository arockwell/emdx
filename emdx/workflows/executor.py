"""Workflow executor for orchestrating multi-stage agent runs."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .services import document_service
from .base import (
    StageConfig,
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

    Execution strategies are delegated to specialized strategy classes.
    """

    def __init__(self, max_concurrent: int = 10):
        """Initialize executor.

        Args:
            max_concurrent: Maximum concurrent agent runs (for parallel mode)
        """
        self.max_concurrent = max_concurrent

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
            final_outputs: List[int] = []
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
            strategy = get_strategy(stage.mode, self.max_concurrent)
            stage_input = strategy.resolve_template(stage.input, context) if stage.input else None

            # Execute using the appropriate strategy
            result = await strategy.execute(stage_run_id, stage, context, stage_input)

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


# Global executor instance
workflow_executor = WorkflowExecutor()
