"""Base class for execution mode strategies."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..base import StageConfig, StageResult


def make_title(stage: StageConfig, index: int, individual_run_id: int, item_label: str | None = None) -> str:
    """Build a clean execution title for an agent run.

    Priority: item_label (dynamic mode) > task_titles > generic fallback.
    """
    if item_label:
        return f"Delegate: {item_label[:60]}"
    task_titles = getattr(stage, '_task_titles', None)
    if task_titles and index < len(task_titles):
        return f"Delegate: {task_titles[index][:60]}"
    return f"Workflow Agent Run #{individual_run_id}"


class ExecutionStrategy(ABC):
    """Base class for execution mode strategies.

    Each strategy implements a specific execution pattern (single, parallel, etc.)
    and is called by WorkflowExecutor._execute_stage().
    """

    @abstractmethod
    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
        executor: "WorkflowExecutor",
    ) -> StageResult:
        """Execute the strategy for a stage.

        Args:
            stage_run_id: Stage run ID for DB tracking
            stage: Stage configuration
            context: Execution context with variables and state
            stage_input: Resolved input for this stage
            executor: Parent executor (provides max_concurrent, DB ops)

        Returns:
            StageResult with execution results
        """
        ...
