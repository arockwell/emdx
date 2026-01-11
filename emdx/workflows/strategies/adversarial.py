"""Adversarial execution strategy - Advocate -> Critic -> Synthesizer pattern."""

from typing import Any, Dict, List, Optional

from .base import ExecutionStrategy, StageResult
from ..base import StageConfig
from ..services import document_service
from ..registry import workflow_registry
from .. import database as wf_db


class AdversarialExecutionStrategy(ExecutionStrategy):
    """Execute adversarial pattern: Advocate -> Critic -> Synthesizer.

    This mode runs a structured debate pattern where:
    1. Advocate argues FOR a position
    2. Critic argues AGAINST
    3. Synthesizer provides balanced assessment

    Can be extended with more rounds of advocacy/criticism.
    """

    # Default adversarial prompts if no strategy provided
    DEFAULT_PROMPTS = [
        "ADVOCATE: Argue FOR this approach: {{input}}\n\nWhat are its strengths?",
        "CRITIC: Given this advocacy: {{prev}}\n\nArgue AGAINST. What are the weaknesses?",
        "SYNTHESIS: Advocate: {{all_prev[0]}}\nCritic: {{prev}}\n\nProvide balanced assessment.",
    ]

    async def execute(
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
                prompt_template = self.DEFAULT_PROMPTS[min(i, len(self.DEFAULT_PROMPTS) - 1)]

            # Build context
            iter_context = dict(context)
            iter_context['input'] = stage_input or context.get('input', '')
            iter_context['prev'] = outputs[-1] if outputs else ''
            iter_context['all_prev'] = outputs  # Keep as list for indexed access

            prompt = self.resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get('prev', ''),
            )

            # Execute
            result = await self.run_agent(
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
