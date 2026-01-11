"""Parallel execution strategy - runs N agents simultaneously and synthesizes results."""

import asyncio
from typing import Any, Dict, List, Optional

from .base import ExecutionStrategy, StageResult
from ..base import StageConfig
from .. import database as wf_db


class ParallelExecutionStrategy(ExecutionStrategy):
    """Execute N runs in parallel and synthesize results.

    This mode runs the same agent N times simultaneously with the same prompt,
    then synthesizes all outputs into a single result.
    """

    def __init__(self, max_concurrent: int = 10):
        """Initialize parallel strategy.

        Args:
            max_concurrent: Maximum concurrent agent runs
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(
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
        individual_runs: List[tuple[int, Optional[str]]] = []
        for i in range(stage.runs):
            # Support per-run prompts (stage.prompts) or single prompt (stage.prompt)
            if stage.prompts and i < len(stage.prompts):
                prompt_template = stage.prompts[i]
            else:
                prompt_template = stage.prompt

            prompt = self.resolve_template(prompt_template, context) if prompt_template else None
            individual_run_id = wf_db.create_individual_run(
                stage_run_id=stage_run_id,
                run_number=i + 1,
                prompt_used=prompt,
                input_context=stage_input,
            )
            individual_runs.append((individual_run_id, prompt))

        # Execute all runs in parallel (with semaphore limiting)
        async def run_with_limit(run_id: int, prompt: Optional[str]) -> Dict[str, Any]:
            async with self._semaphore:
                return await self.run_agent(
                    individual_run_id=run_id,
                    agent_id=stage.agent_id,
                    prompt=prompt or stage_input or "",
                    context=context,
                )

        tasks = [run_with_limit(run_id, prompt) for run_id, prompt in individual_runs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful outputs
        output_doc_ids: List[int] = []
        total_tokens = 0
        errors: List[str] = []

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
        synthesis_result = await self.synthesize_outputs(
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
