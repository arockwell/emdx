"""Iterative execution strategy - run agent N times sequentially."""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import ExecutionStrategy, StageResult

if TYPE_CHECKING:
    from ..base import StageConfig


class IterativeStrategy(ExecutionStrategy):
    """Execute N runs sequentially, each building on previous.

    This mode runs the agent multiple times in sequence, where each
    iteration can reference the output of previous iterations.
    Useful for refinement and improvement workflows.
    """

    async def execute(
        self,
        stage_run_id: int,
        stage: "StageConfig",
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
            strategy = self._get_iteration_strategy(stage.iteration_strategy)

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
            iter_context["input"] = stage_input or context.get("input", "")
            iter_context["prev"] = previous_outputs[-1] if previous_outputs else ""
            iter_context["all_prev"] = "\n\n---\n\n".join(previous_outputs)
            iter_context["run_number"] = run_number

            prompt = self._resolve_template(prompt_template, iter_context)

            # Create individual run record
            individual_run_id = self._create_individual_run(
                stage_run_id=stage_run_id,
                run_number=run_number,
                prompt_used=prompt,
                input_context=iter_context.get("prev", ""),
            )

            # Execute this iteration
            result = await self._run_agent(
                individual_run_id=individual_run_id,
                agent_id=stage.agent_id,
                prompt=prompt,
                context=iter_context,
            )

            if not result.get("success"):
                return StageResult(
                    success=False,
                    error_message=f"Iteration {run_number} failed: {result.get('error_message')}",
                    tokens_used=total_tokens,
                )

            # Collect output for next iteration
            if result.get("output_doc_id"):
                doc = self._get_document(result["output_doc_id"])
                if doc:
                    previous_outputs.append(doc.get("content", ""))
                    output_doc_ids.append(result["output_doc_id"])
                    last_output_id = result["output_doc_id"]

            total_tokens += result.get("tokens_used", 0)

            # Update stage progress
            self._update_stage_run(stage_run_id, runs_completed=run_number)

        return StageResult(
            success=True,
            output_doc_id=last_output_id,
            individual_outputs=output_doc_ids,
            tokens_used=total_tokens,
        )
