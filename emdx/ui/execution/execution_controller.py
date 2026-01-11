#!/usr/bin/env python3
"""
Execution controller for agent execution overlay.

This module provides execution control logic separated from UI display concerns.
"""

from typing import Dict, Any, List, Callable, Optional, TYPE_CHECKING
from enum import Enum

from ...utils.logging import get_logger

if TYPE_CHECKING:
    from .selection_state import SelectionState

logger = get_logger(__name__)


class StageType(Enum):
    """Available overlay stages."""
    DOCUMENT = "document"
    AGENT = "agent"
    PROJECT = "project"
    WORKTREE = "worktree"
    CONFIG = "config"


class ExecutionController:
    """
    Controls navigation and execution flow for the agent execution overlay.

    This class manages:
    - Stage navigation (next/prev)
    - Stage completion tracking
    - Execution triggering
    - Callbacks for state changes

    Separated from display logic for better testability and maintainability.
    """

    def __init__(
        self,
        selection_state: "SelectionState",
        stages: Optional[List[StageType]] = None,
        initial_stage_index: int = 0,
        on_stage_change: Optional[Callable[[StageType, int], None]] = None,
        on_execute: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        """
        Initialize execution controller.

        Args:
            selection_state: The selection state to manage
            stages: List of stages in order (defaults to all stages)
            initial_stage_index: Starting stage index
            on_stage_change: Callback when stage changes
            on_execute: Callback when execution is triggered
        """
        self.selection_state = selection_state
        self.stages = stages or [
            StageType.DOCUMENT,
            StageType.AGENT,
            StageType.PROJECT,
            StageType.WORKTREE,
            StageType.CONFIG,
        ]
        self.current_stage_index = initial_stage_index
        self.on_stage_change = on_stage_change
        self.on_execute = on_execute

        # Track stage completion
        self.stage_completed: Dict[StageType, bool] = {
            stage: False for stage in self.stages
        }

    def get_current_stage(self) -> StageType:
        """Get the current stage."""
        return self.stages[self.current_stage_index]

    def get_stage_count(self) -> int:
        """Get total number of stages."""
        return len(self.stages)

    def is_first_stage(self) -> bool:
        """Check if on the first stage."""
        return self.current_stage_index == 0

    def is_last_stage(self) -> bool:
        """Check if on the last stage."""
        return self.current_stage_index == len(self.stages) - 1

    def can_go_next(self) -> bool:
        """Check if navigation to next stage is possible."""
        return self.current_stage_index < len(self.stages) - 1

    def can_go_prev(self) -> bool:
        """Check if navigation to previous stage is possible."""
        return self.current_stage_index > 0

    def can_execute(self) -> bool:
        """Check if execution is possible with current selections."""
        return self.selection_state.can_execute()

    def go_next(self) -> bool:
        """
        Navigate to the next stage.

        Returns:
            True if navigation occurred, False if already at last stage
        """
        if not self.can_go_next():
            return False

        self.current_stage_index += 1
        stage = self.get_current_stage()
        logger.info(f"Advanced to stage {self.current_stage_index}: {stage}")

        if self.on_stage_change:
            self.on_stage_change(stage, self.current_stage_index)

        return True

    def go_prev(self) -> bool:
        """
        Navigate to the previous stage.

        Returns:
            True if navigation occurred, False if already at first stage
        """
        if not self.can_go_prev():
            return False

        self.current_stage_index -= 1
        stage = self.get_current_stage()
        logger.info(f"Returned to stage {self.current_stage_index}: {stage}")

        if self.on_stage_change:
            self.on_stage_change(stage, self.current_stage_index)

        return True

    def go_to_stage(self, stage: StageType) -> bool:
        """
        Navigate to a specific stage.

        Args:
            stage: The stage to navigate to

        Returns:
            True if navigation occurred, False if stage not found
        """
        if stage not in self.stages:
            return False

        self.current_stage_index = self.stages.index(stage)
        logger.info(f"Jumped to stage {self.current_stage_index}: {stage}")

        if self.on_stage_change:
            self.on_stage_change(stage, self.current_stage_index)

        return True

    def mark_stage_completed(self, stage: StageType) -> None:
        """Mark a stage as completed."""
        if stage in self.stage_completed:
            self.stage_completed[stage] = True
            logger.info(f"Stage {stage} marked as completed")

    def is_stage_completed(self, stage: StageType) -> bool:
        """Check if a stage is completed."""
        return self.stage_completed.get(stage, False)

    def get_completed_stages(self) -> List[str]:
        """Get list of completed stage names."""
        return [
            stage.value for stage, completed in self.stage_completed.items()
            if completed
        ]

    def proceed(self) -> bool:
        """
        Proceed to next stage or execute if on last stage.

        Returns:
            True if action was taken
        """
        current_stage = self.get_current_stage()
        self.mark_stage_completed(current_stage)

        if self.is_last_stage():
            return self.execute()
        else:
            return self.go_next()

    def execute(self) -> bool:
        """
        Execute with current selections.

        Returns:
            True if execution was triggered, False if requirements not met
        """
        if not self.can_execute():
            logger.warning("Cannot execute: missing required selections")
            return False

        execution_data = self.selection_state.to_execution_data()
        logger.info(f"Executing with data: {execution_data}")

        if self.on_execute:
            self.on_execute(execution_data)

        return True

    def get_stage_status(self, stage: StageType) -> str:
        """
        Get the status of a stage.

        Returns:
            'completed', 'current', or 'pending'
        """
        stage_index = self.stages.index(stage)

        if stage_index < self.current_stage_index:
            return 'completed'
        elif stage_index == self.current_stage_index:
            return 'current'
        else:
            return 'pending'

    def get_progress_info(self) -> Dict[str, Any]:
        """
        Get progress information for display.

        Returns:
            Dictionary with stage progress information
        """
        return {
            'current_index': self.current_stage_index,
            'total_stages': len(self.stages),
            'current_stage': self.get_current_stage(),
            'stages': [
                {
                    'stage': stage,
                    'name': stage.value.title(),
                    'status': self.get_stage_status(stage),
                }
                for stage in self.stages
            ],
        }
