"""Iterative execution strategy — run N times sequentially, each building on previous."""

from typing import Any, Dict, List, Optional

from .. import database as wf_db
from ..base import StageConfig, StageResult
from ..template import resolve_template
from ..agent_runner import run_agent
from ..services import document_service
from .base import ExecutionStrategy


class IterativeStrategy(ExecutionStrategy):
    """Execute N runs sequentially, each building on previous output."""

    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
        executor: "WorkflowExecutor",
    ) -> StageResult:
        previous_outputs: List[str] = []
        output_doc_ids: List[int] = []
        total_tokens = 0
        last_output_id = None
        task_titles = getattr(stage, '_task_titles', None)

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
            if task_titles and i < len(task_titles):
                title = f"Delegate: {task_titles[i][:60]}"
            else:
                title = f"Workflow Agent Run #{individual_run_id}"
            result = await run_agent(
                individual_run_id=individual_run_id,
                agent_id=stage.agent_id,
                prompt=prompt,
                context=iter_context,
                title=title,
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
