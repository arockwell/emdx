#!/usr/bin/env python3
"""
Agent execution overlay - multi-stage agent execution interface.

This module provides the main overlay UI for agent execution, with
execution control and state management delegated to separate components:
- SelectionState: Manages selection data across stages
- ExecutionController: Handles navigation and execution flow
- StageProgressDisplay: Displays stage progress
"""

from typing import TYPE_CHECKING, Optional, Dict, Any, Callable, List

if TYPE_CHECKING:
    from emdx.utils.git_ops import GitWorktree

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
from .execution import SelectionState, ExecutionController, StageProgressDisplay
from .execution.execution_controller import StageType

# Re-export StageType for backward compatibility
__all__ = ['AgentExecutionOverlay', 'StageType']

logger = get_logger(__name__)


class AgentExecutionOverlay(ModalScreen):
    """
    Multi-stage agent execution overlay.

    This class provides the UI layer for agent execution, delegating
    state management and execution control to specialized components.
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

        # Initialize selection state
        self._selection_state = SelectionState(document_id=initial_document_id)

        # Determine initial stage
        initial_stage_index = 0
        if start_stage and start_stage in list(StageType):
            initial_stage_index = list(StageType).index(start_stage)

        # If we have an initial document, start at agent stage
        if initial_document_id:
            self._load_initial_document(initial_document_id)
            if start_stage is None:
                initial_stage_index = list(StageType).index(StageType.AGENT)

        # Initialize execution controller
        self._controller = ExecutionController(
            selection_state=self._selection_state,
            initial_stage_index=initial_stage_index,
            on_stage_change=self._on_stage_change,
            on_execute=self._on_execute,
        )

        # Mark document stage as completed if document is pre-selected
        if initial_document_id:
            self._controller.mark_stage_completed(StageType.DOCUMENT)

        # Store callback and stage widgets
        self.callback = callback
        self.stage_widgets: Dict[StageType, Any] = {}

        # Backward compatibility: expose data dict
        # This property provides dict-like access to selection state
        self._data_proxy = _SelectionStateProxy(self._selection_state)

        logger.info(
            f"AgentExecutionOverlay initialized: start_stage={start_stage}, "
            f"initial_doc={initial_document_id}, "
            f"current_stage_index={self._controller.current_stage_index}"
        )

    def _load_initial_document(self, document_id: int) -> None:
        """Load initial document data."""
        try:
            from ..models.documents import get_document
            doc = get_document(str(document_id))
            if doc:
                self._selection_state.set_document(
                    document_id,
                    {
                        'document_id': doc['id'],
                        'document_title': doc.get('title', 'Untitled'),
                        'document_project': doc.get('project', 'Default')
                    }
                )
                logger.info(f"Pre-selected document data: {self._selection_state.document_data}")
            else:
                logger.warning(f"Could not fetch document {document_id}")
        except Exception as e:
            logger.error(f"Failed to fetch pre-selected document data: {e}", exc_info=True)

    @property
    def data(self) -> "_SelectionStateProxy":
        """Backward compatibility: access selection state as dict-like object."""
        return self._data_proxy

    @property
    def stages(self) -> list:
        """Get list of stages."""
        return self._controller.stages

    @property
    def current_stage_index(self) -> int:
        """Get current stage index."""
        return self._controller.current_stage_index

    @current_stage_index.setter
    def current_stage_index(self, value: int) -> None:
        """Set current stage index."""
        self._controller.current_stage_index = value

    @property
    def stage_completed(self) -> Dict[StageType, bool]:
        """Get stage completion status."""
        return self._controller.stage_completed

    def compose(self) -> ComposeResult:
        """Create the overlay UI."""
        with Vertical(id="overlay-container"):
            # Header with title and progress
            with Horizontal(id="overlay-header"):
                yield Label("🤖 Agent Execution", id="overlay-title")
                yield StageProgressDisplay(
                    stages=self._controller.stages,
                    current_index=self._controller.current_stage_index,
                    id="stage-progress"
                )

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

        self.stage_widgets[StageType.DOCUMENT] = DocumentSelectionStage(self)
        self.stage_widgets[StageType.AGENT] = AgentSelectionStage(self)
        self.stage_widgets[StageType.PROJECT] = ProjectSelectionStage(self)
        self.stage_widgets[StageType.WORKTREE] = WorktreeSelectionStage(self)
        self.stage_widgets[StageType.CONFIG] = ConfigSelectionStage(self)

        for stage_type, stage in self.stage_widgets.items():
            await container.mount(stage)
            stage.add_class("stage-hidden")

        logger.info("All stages initialized and mounted")

    def get_current_stage(self) -> StageType:
        """Get the current stage."""
        return self._controller.get_current_stage()

    async def _update_stage_progress(self) -> None:
        """Update the stage progress indicator."""
        progress = self.query_one("#stage-progress", StageProgressDisplay)
        progress.update_progress(self._controller.current_stage_index)

    # Backward compatibility alias
    async def update_stage_progress(self) -> None:
        """Update the stage progress indicator (backward compatibility)."""
        await self._update_stage_progress()

    async def _show_current_stage(self) -> None:
        """Display the current stage content."""
        current_stage = self.get_current_stage()
        logger.info(f"Showing stage: {current_stage}")

        for stage_type, stage in self.stage_widgets.items():
            if stage_type != current_stage:
                stage.add_class("stage-hidden")

        current_widget = self.stage_widgets[current_stage]
        current_widget.remove_class("stage-hidden")
        await current_widget.ensure_loaded()

        await self._update_navigation_state()
        self.post_message(self.StageChanged(current_stage, self._controller.current_stage_index))

    # Backward compatibility alias
    async def show_current_stage(self) -> None:
        """Display the current stage content (backward compatibility)."""
        await self._show_current_stage()

    async def _update_navigation_state(self) -> None:
        """Update navigation button states."""
        execute_btn = self.query_one("#execute-btn", Button)
        can_execute = self._controller.can_execute()
        execute_btn.disabled = not can_execute

        if self.get_current_stage() == StageType.CONFIG:
            execute_btn.label = "Execute Now"
        else:
            execute_btn.label = "Quick Execute"

    # Backward compatibility alias
    async def update_navigation_state(self) -> None:
        """Update navigation button states (backward compatibility)."""
        await self._update_navigation_state()

    # Backward compatibility alias
    async def initialize_all_stages(self) -> None:
        """Mount all stage widgets (backward compatibility)."""
        await self._initialize_all_stages()

    def _on_stage_change(self, stage: StageType, stage_index: int) -> None:
        """Callback when stage changes via controller."""
        self.run_worker(self._update_stage_progress(), exclusive=True, group="stage_update")
        self.run_worker(self._show_current_stage(), exclusive=True, group="stage_display")

    def _on_execute(self, execution_data: Dict[str, Any]) -> None:
        """Callback when execution is triggered via controller."""
        self.post_message(self.ExecutionRequested(execution_data))
        self.dismiss(execution_data)

    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        if self._controller.go_next():
            logger.info(f"Advanced to stage {self._controller.current_stage_index}: {self.get_current_stage()}")

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        if self._controller.go_prev():
            logger.info(f"Returned to stage {self._controller.current_stage_index}: {self.get_current_stage()}")

    def action_proceed(self) -> None:
        """Proceed to next stage or execute if on last stage."""
        current_stage = self.get_current_stage()
        self._controller.mark_stage_completed(current_stage)

        if current_stage == StageType.CONFIG:
            self.action_execute()
        else:
            self.action_next_stage()

    def action_execute(self) -> None:
        """Execute with current selections."""
        if not self._controller.can_execute():
            logger.warning("Cannot execute: missing required selections")
            return

        execution_data = self._selection_state.to_execution_data()
        logger.info(f"Executing with data: {execution_data}")

        self.post_message(self.ExecutionRequested(execution_data))
        self.dismiss(execution_data)

    def action_cancel(self) -> None:
        """Cancel overlay."""
        logger.info("AgentExecutionOverlay cancelled")
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "execute-btn":
            self.action_execute()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    # Message handlers for stage events
    def on_overlay_stage_selection_changed(self, message: OverlayStage.SelectionChanged) -> None:
        """Handle stage selection changes."""
        logger.info(f"Stage {message.stage_name} selection changed: {message.selection_data}")
        if message.stage_name == "document":
            self._selection_state.document_data = message.selection_data
        elif message.stage_name == "agent":
            self._selection_state.agent_data = message.selection_data
        elif message.stage_name == "project":
            self._selection_state.project_data = message.selection_data
        elif message.stage_name == "worktree":
            self._selection_state.worktree_data = message.selection_data
        elif message.stage_name == "config":
            self._selection_state.update_config(message.selection_data)

    def on_overlay_stage_stage_completed(self, message: OverlayStage.StageCompleted) -> None:
        """Handle stage completion."""
        logger.info(f"Stage {message.stage_name} completed")
        stage_map = {
            "document": StageType.DOCUMENT,
            "agent": StageType.AGENT,
            "worktree": StageType.WORKTREE,
            "config": StageType.CONFIG,
        }
        if message.stage_name in stage_map:
            self._controller.mark_stage_completed(stage_map[message.stage_name])
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

    # Selection setter methods (backward compatibility)
    def set_document_selection(self, document_id: int) -> None:
        """Set selected document ID."""
        self._selection_state.set_document(document_id)
        self._controller.mark_stage_completed(StageType.DOCUMENT)
        logger.info(f"Document selected: {document_id}")
        self.call_after_refresh(self._update_navigation_state)

    def set_agent_selection(self, agent_id: int) -> None:
        """Set selected agent ID."""
        self._selection_state.set_agent(agent_id)
        self._controller.mark_stage_completed(StageType.AGENT)
        logger.info(f"Agent selected: {agent_id}")
        self.call_after_refresh(self._update_navigation_state)

    def set_project_selection(
        self,
        project_index: int,
        project_path: str,
        worktrees: Optional[List["GitWorktree"]] = None
    ) -> None:
        """Set selected project and its worktrees."""
        self._selection_state.set_project(project_index, project_path, worktrees)
        self._controller.mark_stage_completed(StageType.PROJECT)
        logger.info(f"Project selected: index={project_index}, path={project_path}, worktrees={len(worktrees or [])}")
        self.call_after_refresh(self._update_navigation_state)

    def set_worktree_selection(self, worktree_index: int) -> None:
        """Set selected worktree index."""
        self._selection_state.set_worktree(worktree_index)
        self._controller.mark_stage_completed(StageType.WORKTREE)
        logger.info(f"Worktree selected: {worktree_index}")
        self.call_after_refresh(self._update_navigation_state)

    def set_execution_config(self, config: Dict[str, Any]) -> None:
        """Set execution configuration."""
        self._selection_state.update_config(config)
        self._controller.mark_stage_completed(StageType.CONFIG)
        logger.info(f"Config updated: {config}")
        self.call_after_refresh(self._update_navigation_state)

    def get_selection_summary(self) -> Dict[str, Any]:
        """Get summary of current selections."""
        return self._selection_state.get_summary(
            current_stage=self.get_current_stage().value,
            stage_index=self._controller.current_stage_index,
            completed_stages=self._controller.get_completed_stages()
        )


class _SelectionStateProxy:
    """
    Proxy class to provide dict-like access to SelectionState.

    This maintains backward compatibility with code that accesses
    self.data['document_id'] directly.
    """

    def __init__(self, state: SelectionState):
        self._state = state

    def __getitem__(self, key: str) -> Any:
        if key == 'document_id':
            return self._state.document_id
        elif key == 'agent_id':
            return self._state.agent_id
        elif key == 'project_index':
            return self._state.project_index
        elif key == 'project_path':
            return self._state.project_path
        elif key == 'project_worktrees':
            return self._state.project_worktrees
        elif key == 'worktree_index':
            return self._state.worktree_index
        elif key == 'config':
            return self._state.config
        elif key == 'document_data':
            return self._state.document_data
        elif key == 'agent_data':
            return self._state.agent_data
        elif key == 'project_data':
            return self._state.project_data
        elif key == 'worktree_data':
            return self._state.worktree_data
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == 'document_id':
            self._state.document_id = value
        elif key == 'agent_id':
            self._state.agent_id = value
        elif key == 'project_index':
            self._state.project_index = value
        elif key == 'project_path':
            self._state.project_path = value
        elif key == 'project_worktrees':
            self._state.project_worktrees = value
        elif key == 'worktree_index':
            self._state.worktree_index = value
        elif key == 'config':
            self._state.config = value
        elif key == 'document_data':
            self._state.document_data = value
        elif key == 'agent_data':
            self._state.agent_data = value
        elif key == 'project_data':
            self._state.project_data = value
        elif key == 'worktree_data':
            self._state.worktree_data = value
        else:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def update(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            try:
                self[key] = value
            except KeyError:
                pass
