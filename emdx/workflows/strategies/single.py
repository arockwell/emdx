"""Single execution strategy - runs agent once."""

from typing import Any, Dict, Optional

from .base import ExecutionStrategy, StageResult
from ..base import StageConfig
from .. import database as wf_db


class SingleExecutionStrategy(ExecutionStrategy):
    """Execute a single agent run.

    This is the simplest execution mode - runs the agent once with
    the given prompt and returns the result.
    """

    async def execute(
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
        prompt = self.resolve_template(stage.prompt, context) if stage.prompt else None
        individual_run_id = wf_db.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=1,
            prompt_used=prompt,
            input_context=stage_input,
        )

        # Execute agent
        result = await self.run_agent(
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
