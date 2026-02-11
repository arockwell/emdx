"""Adversarial execution strategy — Advocate -> Critic -> Synthesizer pattern."""

from typing import Any, Dict, List, Optional

from .. import database as wf_db
from ..base import StageConfig, StageResult
from ..template import resolve_template
from ..agent_runner import run_agent
from ..services import document_service
from .base import ExecutionStrategy


class AdversarialStrategy(ExecutionStrategy):
    """Execute adversarial pattern: Advocate -> Critic -> Synthesizer."""

    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
        executor: "WorkflowExecutor",
    ) -> StageResult:
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
                title=f"Workflow Agent Run #{individual_run_id}",
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
