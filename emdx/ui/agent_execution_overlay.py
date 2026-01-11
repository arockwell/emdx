#!/usr/bin/env python3
"""
Agent execution overlay - multi-stage agent execution interface.

This module provides the UI orchestration for multi-stage agent execution.
Data management is delegated to ExecutionDataManager for cleaner separation
of concerns.
"""

from typing import Optional, Dict, Any, Callable

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Label, Button
from textual.binding import Binding
from textual.message import Message

from ..utils.logging import get_logger
from .stages.base import OverlayStage
from .stages.document_selection import DocumentSelectionStage
from .stages.agent_selection import AgentSelectionStage
from .stages.project_selection import ProjectSelectionStage
from .stages.worktree_selection import WorktreeSelectionStage
from .stages.config_selection import ConfigSelectionStage
from .execution_data_manager import ExecutionDataManager, StageType

# Re-export StageType for backward compatibility
__all__ = ['AgentExecutionOverlay', 'StageType']

logger = get_logger(__name__)


class AgentExecutionOverlay(ModalScreen):
    """
    Multi-stage agent execution overlay.

    This class handles the UI orchestration for the agent execution workflow.
    Data management (selections, stage completion) is delegated to
    ExecutionDataManager for cleaner separation of concerns.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("enter", "proceed", "Proceed"),
        Binding("ctrl+s", "execute", "Execute"),
    ]

    DEFAULT_CSS = """
    AgentExecutionOverlay {
        align: center middle;
    }

    #overlay-container {
        width: 90%;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 0;
    }

    #overlay-header {
        height: 4;
        background: $boost;
        padding: 1 2;
    }

    #overlay-title {
        text-style: bold;
        color: $warning;
        text-align: left;
    }

    #stage-progress {
        text-align: right;
        color: $text-muted;
    }

    #stage-content {
        height: 1fr;
        padding: 1 2;
    }

    .stage-hidden {
        display: none;
    }

    #overlay-footer {
        height: 3;
        background: $boost;
        padding: 0 2;
        layout: horizontal;
        align: center middle;
    }

    .footer-help {
        color: $text-muted;
        margin: 0 1;
    }

    Button {
        margin: 0 1;
    }

    .stage-indicator {
        margin: 0 1;
    }

    .stage-active {
        color: $warning;
        text-style: bold;
    }

    .stage-completed {
        color: $success;
    }

    .stage-pending {
        color: $text-muted;
    }
    """

    class StageChanged(Message):
        """Message sent when stage changes."""
        def __init__(self, stage: StageType, stage_index: int) -> None:
            self.stage = stage
            self.stage_index = stage_index
            super().__init__()

    class ExecutionRequested(Message):
        """Message sent when execution is requested."""
        def __init__(self, execution_data: Dict[str, Any]) -> None:
            self.execution_data = execution_data
            super().__init__()

    def __init__(
        self,
        initial_document_id: Optional[int] = None,
        start_stage: Optional[StageType] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__()

        # Initialize data manager for selection state
        self._data_manager = ExecutionDataManager(initial_document_id)

        # UI state
        self.current_stage_index = 0
        self.callback = callback
        self.stage_widgets: Dict[StageType, Any] = {}

        # Set starting stage
        if start_stage and start_stage in self._data_manager.stages:
            self.current_stage_index = self._data_manager.stages.index(start_stage)

        # If we have an initial document, start at agent stage
        if initial_document_id and start_stage is None:
            self.current_stage_index = self._data_manager.stages.index(StageType.AGENT)

        logger.info(
            f"AgentExecutionOverlay initialized: start_stage={start_stage}, "
            f"initial_doc={initial_document_id}, current_stage_index={self.current_stage_index}"
        )

    # Property to expose data for backward compatibility with stages
    @property
    def data(self) -> ExecutionDataManager:
        """Expose data manager for stage access."""
        return self._data_manager

    @property
    def stages(self) -> list:
        """Expose stages list for backward compatibility."""
        return self._data_manager.stages

    @property
    def stage_completed(self) -> Dict[StageType, bool]:
        """Expose stage completion for backward compatibility."""
        return self._data_manager.stage_completed

    def compose(self) -> ComposeResult:
        """Create the overlay UI."""
        with Vertical(id="overlay-container"):
            # Header with title and progress
            with Horizontal(id="overlay-header"):
                yield Label("🤖 Agent Execution", id="overlay-title")
                yield Label("", id="stage-progress")

            # Main content area for stages
            with Vertical(id="stage-content"):
                pass

            # Footer with navigation and help
            with Horizontal(id="overlay-footer"):
                yield Static(
                    "Tab: Next Stage | Shift+Tab: Previous | Enter: Proceed | Esc: Cancel",
                    classes="footer-help"
                )
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Execute", variant="primary", id="execute-btn", disabled=True)

    async def on_mount(self) -> None:
        """Initialize overlay when mounted."""
        logger.info("AgentExecutionOverlay mounted")

        await self._initialize_all_stages()
        await self._update_stage_progress()
        await self._show_current_stage()

    async def _initialize_all_stages(self) -> None:
        """Mount all stage widgets once - they will be shown/hidden with CSS."""
        container = self.query_one("#stage-content", Vertical)

        # Create and mount all stages
        self.stage_widgets[StageType.DOCUMENT] = DocumentSelectionStage(self)
        self.stage_widgets[StageType.AGENT] = AgentSelectionStage(self)
        self.stage_widgets[StageType.PROJECT] = ProjectSelectionStage(self)
        self.stage_widgets[StageType.WORKTREE] = WorktreeSelectionStage(self)
        self.stage_widgets[StageType.CONFIG] = ConfigSelectionStage(self)

        # Mount all stages (they'll start hidden)
        for stage_type, stage in self.stage_widgets.items():
            await container.mount(stage)
            stage.add_class("stage-hidden")

        logger.info("All stages initialized and mounted")

    def get_current_stage(self) -> StageType:
        """Get the current stage."""
        return self._data_manager.stages[self.current_stage_index]

    async def _update_stage_progress(self) -> None:
        """Update the stage progress indicator."""
        progress = self.query_one("#stage-progress", Label)

        # Build progress indicator
        stage_indicators = []
        for i, stage in enumerate(self._data_manager.stages):
            stage_name = stage.value.title()

            if i < self.current_stage_index:
                stage_indicators.append(f"[green]✓ {stage_name}[/green]")
            elif i == self.current_stage_index:
                stage_indicators.append(f"[yellow]→ {stage_name}[/yellow]")
            else:
                stage_indicators.append(f"[dim]{stage_name}[/dim]")

        progress_text = f"Stage {self.current_stage_index + 1}/4: " + " | ".join(stage_indicators)
        progress.update(progress_text)

    async def _show_current_stage(self) -> None:
        """Display the current stage by hiding others and showing the current one."""
        current_stage = self.get_current_stage()
        logger.info(f"Showing stage: {current_stage}")

        # Hide all stages first
        for stage_type, stage in self.stage_widgets.items():
            if stage_type != current_stage:
                stage.add_class("stage-hidden")

        # Show current stage
        current_widget = self.stage_widgets[current_stage]
        current_widget.remove_class("stage-hidden")

        # Lazy load stage data only when it's shown
        await current_widget.ensure_loaded()

        # Update navigation state
        await self._update_navigation_state()

        # Post stage change message
        self.post_message(self.StageChanged(current_stage, self.current_stage_index))

    async def _update_navigation_state(self) -> None:
        """Update navigation button states."""
        execute_btn = self.query_one("#execute-btn", Button)

        # Delegate execution check to data manager
        execute_btn.disabled = not self._data_manager.can_execute()

        # Update execute button text based on stage
        if self.get_current_stage() == StageType.CONFIG:
            execute_btn.label = "Execute Now"
        else:
            execute_btn.label = "Quick Execute"

    # Navigation actions

    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        if self.current_stage_index < len(self._data_manager.stages) - 1:
            self.current_stage_index += 1
            self.run_worker(self._update_stage_progress(), exclusive=True, group="stage_update")
            self.run_worker(self._show_current_stage(), exclusive=True, group="stage_display")
            logger.info(f"Advanced to stage {self.current_stage_index}: {self.get_current_stage()}")

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        if self.current_stage_index > 0:
            self.current_stage_index -= 1
            self.run_worker(self._update_stage_progress(), exclusive=True, group="stage_update")
            self.run_worker(self._show_current_stage(), exclusive=True, group="stage_display")
            logger.info(f"Returned to stage {self.current_stage_index}: {self.get_current_stage()}")

    def action_proceed(self) -> None:
        """Proceed to next stage or execute if on last stage."""
        current_stage = self.get_current_stage()

        # Mark current stage as completed
        self._data_manager.stage_completed[current_stage] = True

        if current_stage == StageType.CONFIG:
            self.action_execute()
        else:
            self.action_next_stage()

    def action_execute(self) -> None:
        """Execute with current selections."""
        if not self._data_manager.can_execute():
            logger.warning("Cannot execute: missing required selections")
            return

        execution_data = self._data_manager.get_execution_data()
        logger.info(f"Executing with data: {execution_data}")

        self.post_message(self.ExecutionRequested(execution_data))
        self.dismiss(execution_data)

    def action_cancel(self) -> None:
        """Cancel overlay."""
        logger.info("AgentExecutionOverlay cancelled")
        self.dismiss(None)

    # Event handlers

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "execute-btn":
            self.action_execute()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_overlay_stage_selection_changed(self, message: OverlayStage.SelectionChanged) -> None:
        """Handle stage selection changes."""
        logger.info(f"Stage {message.stage_name} selection changed: {message.selection_data}")
        self._data_manager.update_stage_data(message.stage_name, message.selection_data)

    def on_overlay_stage_stage_completed(self, message: OverlayStage.StageCompleted) -> None:
        """Handle stage completion."""
        logger.info(f"Stage {message.stage_name} completed")
        self._data_manager.mark_stage_completed(message.stage_name)
        self.call_after_refresh(self._update_navigation_state)

    def on_overlay_stage_navigation_requested(self, message: OverlayStage.NavigationRequested) -> None:
        """Handle navigation requests from stages."""
        if message.direction == "next":
            self.action_next_stage()
        elif message.direction == "prev":
            self.action_prev_stage()
        elif message.direction == "execute":
            self.action_execute()

    def on_document_selection_stage_document_selected(self, message) -> None:
        """Handle document selection from document stage."""
        logger.info(f"Document selected via stage: {message.document_id}")
        self.call_after_refresh(self._update_stage_progress)

    def on_agent_selection_stage_agent_selected(self, message) -> None:
        """Handle agent selection from agent stage."""
        logger.info(f"Agent selected via stage: {message.agent_id}")
        self.call_after_refresh(self._update_stage_progress)

    def on_worktree_selection_stage_worktree_selected(self, message) -> None:
        """Handle worktree selection from worktree stage."""
        logger.info(f"Worktree selected via stage: {message.worktree_index}")
        self.call_after_refresh(self._update_stage_progress)

    def on_config_selection_stage_config_completed(self, message) -> None:
        """Handle config completion from config stage."""
        logger.info(f"Config completed via stage: {message.config}")
        self.call_after_refresh(self._update_stage_progress)

    # Public API for stages to set selections

    def set_document_selection(self, document_id: int) -> None:
        """Set selected document ID."""
        self._data_manager.set_document_selection(document_id)
        self.call_after_refresh(self._update_navigation_state)

    def set_agent_selection(self, agent_id: int) -> None:
        """Set selected agent ID."""
        self._data_manager.set_agent_selection(agent_id)
        self.call_after_refresh(self._update_navigation_state)

    def set_project_selection(
        self,
        project_index: int,
        project_path: str,
        worktrees: list = None
    ) -> None:
        """Set selected project and its worktrees."""
        self._data_manager.set_project_selection(project_index, project_path, worktrees)
        self.call_after_refresh(self._update_navigation_state)

    def set_worktree_selection(self, worktree_index: int) -> None:
        """Set selected worktree index."""
        self._data_manager.set_worktree_selection(worktree_index)
        self.call_after_refresh(self._update_navigation_state)

    def set_execution_config(self, config: Dict[str, Any]) -> None:
        """Set execution configuration."""
        self._data_manager.set_execution_config(config)
        self.call_after_refresh(self._update_navigation_state)

    def get_selection_summary(self) -> Dict[str, Any]:
        """Get summary of current selections - flatten all nested data."""
        return self._data_manager.get_selection_summary(
            self.get_current_stage(),
            self.current_stage_index
        )
