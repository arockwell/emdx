#!/usr/bin/env python3
"""
Stage progress display widget for agent execution overlay.

This module provides a reusable widget for displaying stage progress.
"""

from typing import List, Dict, Any

from textual.widgets import Static
from textual.reactive import reactive

from .execution_controller import StageType


class StageProgressDisplay(Static):
    """
    Widget for displaying stage progress in the execution overlay.

    This widget shows:
    - Current stage indicator
    - Completed stages (green checkmark)
    - Pending stages (dimmed)

    Separated from the main overlay for reusability and testability.
    """

    DEFAULT_CSS = """
    StageProgressDisplay {
        text-align: right;
        color: $text-muted;
    }
    """

    # Reactive property to trigger updates
    current_index: reactive[int] = reactive(0)
    total_stages: reactive[int] = reactive(5)

    def __init__(
        self,
        stages: List[StageType],
        current_index: int = 0,
        id: str | None = None,
        classes: str | None = None,
    ):
        """
        Initialize stage progress display.

        Args:
            stages: List of stages to display
            current_index: Current stage index
            id: Widget ID
            classes: CSS classes
        """
        super().__init__(id=id, classes=classes)
        self._stages = stages
        self.current_index = current_index
        self.total_stages = len(stages)

    def render(self) -> str:
        """Render the progress indicator."""
        return self._build_progress_text()

    def _build_progress_text(self) -> str:
        """Build the progress indicator text with markup."""
        stage_indicators = []

        for i, stage in enumerate(self._stages):
            stage_name = stage.value.title()

            if i < self.current_index:
                # Completed stage
                stage_indicators.append(f"[green]✓ {stage_name}[/green]")
            elif i == self.current_index:
                # Current stage
                stage_indicators.append(f"[yellow]→ {stage_name}[/yellow]")
            else:
                # Pending stage
                stage_indicators.append(f"[dim]{stage_name}[/dim]")

        # Use actual stage count, not hardcoded 4
        progress_text = f"Stage {self.current_index + 1}/{self.total_stages}: " + " | ".join(stage_indicators)
        return progress_text

    def update_progress(self, current_index: int) -> None:
        """
        Update the progress display.

        Args:
            current_index: New current stage index
        """
        self.current_index = current_index
        self.refresh()

    def set_stages(self, stages: List[StageType]) -> None:
        """
        Update the stages list.

        Args:
            stages: New list of stages
        """
        self._stages = stages
        self.total_stages = len(stages)
        self.refresh()

    @classmethod
    def from_progress_info(cls, progress_info: Dict[str, Any], **kwargs) -> "StageProgressDisplay":
        """
        Create a StageProgressDisplay from progress info dictionary.

        Args:
            progress_info: Dictionary from ExecutionController.get_progress_info()
            **kwargs: Additional widget arguments

        Returns:
            StageProgressDisplay instance
        """
        stages = [info['stage'] for info in progress_info['stages']]
        return cls(
            stages=stages,
            current_index=progress_info['current_index'],
            **kwargs
        )
