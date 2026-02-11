"""Parallel execution strategy — run N agents simultaneously, synthesize results."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from .. import database as wf_db
from ..base import StageConfig, StageResult
from ..template import resolve_template
from ..agent_runner import run_agent
from ..synthesis import synthesize_outputs
from emdx.database import groups as groups_db
from .base import ExecutionStrategy

logger = logging.getLogger(__name__)


class ParallelStrategy(ExecutionStrategy):
    """Execute N runs in parallel and synthesize results."""

    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
        executor: "WorkflowExecutor",
    ) -> StageResult:
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
            logger.warning(f"Could not create group for parallel stage: {e}")

        # Create individual run records
        task_titles = getattr(stage, '_task_titles', None)
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
            # Use original task title for clean display, fall back to run number
            if task_titles and i < len(task_titles):
                task_title = task_titles[i]
            else:
                task_title = None
            individual_runs.append((individual_run_id, prompt, task_title))

        # Execute all runs in parallel with worktree isolation
        completed_count = 0

        # Get max_concurrent from context or stage config
        max_concurrent = context.get('_max_concurrent_override') or stage.max_concurrent or executor.max_concurrent

        from ..worktree_pool import WorktreePool

        base_branch = context.get('base_branch', 'main')
        pool = WorktreePool(
            max_size=max_concurrent,
            base_branch=base_branch,
        )

        async def run_with_worktree(run_id: int, prompt: str, run_number: int, task_title: str | None = None):
            nonlocal completed_count
            try:
                async with pool.acquire(target_branch=f"parallel-{stage_run_id}-{run_number}") as worktree:
                    run_context = dict(context)
                    run_context['_working_dir'] = worktree.path

                    effective_prompt = prompt or stage_input or ""
                    if task_title:
                        title = f"Delegate: {task_title[:60]}"
                    else:
                        title = f"Workflow Agent Run #{run_id}"
                    result = await run_agent(
                        individual_run_id=run_id,
                        agent_id=stage.agent_id,
                        prompt=effective_prompt,
                        context=run_context,
                        title=title,
                    )
                    completed_count += 1
                    wf_db.update_stage_run(stage_run_id, runs_completed=completed_count)
                    return result
            except Exception as e:
                return {'success': False, 'error_message': str(e)}

        try:
            tasks = [
                run_with_worktree(run_id, prompt, i + 1, task_title)
                for i, (run_id, prompt, task_title) in enumerate(individual_runs)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
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

        # Synthesize results (skip for single task)
        synthesis_doc_id = None
        if len(output_doc_ids) > 1 and stage.synthesis_prompt:
            wf_db.update_stage_run(stage_run_id, status='synthesizing')

            synthesis_result = await synthesize_outputs(
                stage_run_id=stage_run_id,
                output_doc_ids=output_doc_ids,
                synthesis_prompt=stage.synthesis_prompt,
                context=context,
            )

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
