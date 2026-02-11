"""Single execution strategy — run agent once."""

from typing import Any, Dict, Optional

from .. import database as wf_db
from ..base import StageConfig, StageResult
from ..template import resolve_template
from ..agent_runner import run_agent
from .base import ExecutionStrategy


class SingleStrategy(ExecutionStrategy):
    """Execute a single agent run."""

    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
        executor: "WorkflowExecutor",
    ) -> StageResult:
        # Create individual run record
        prompt = resolve_template(stage.prompt, context) if stage.prompt else None
        individual_run_id = wf_db.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=1,
            prompt_used=prompt,
            input_context=stage_input,
        )

        # Execute agent — use task title for clean display if available
        effective_prompt = prompt or stage_input or ""
        task_titles = getattr(stage, '_task_titles', None)
        if task_titles:
            title = f"Delegate: {task_titles[0][:60]}"
        else:
            title = f"Workflow Agent Run #{individual_run_id}"
        result = await run_agent(
            individual_run_id=individual_run_id,
            agent_id=stage.agent_id,
            prompt=effective_prompt,
            context=context,
            title=title,
        )

        return StageResult(
            success=result.get('success', False),
            output_doc_id=result.get('output_doc_id'),
            individual_outputs=[result.get('output_doc_id')] if result.get('output_doc_id') else [],
            tokens_used=result.get('tokens_used', 0),
            error_message=result.get('error_message'),
        )
