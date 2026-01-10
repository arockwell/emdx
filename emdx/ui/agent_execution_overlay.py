#!/usr/bin/env python3
"""
Agent execution overlay - multi-stage agent execution interface.
"""

import logging
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Grid
from textual.screen import ModalScreen
from textual.widgets import Static, Label, Button
from textual.binding import Binding
from textual.message import Message

from ..utils.logging import get_logger
from .stages.base import OverlayStage, PlaceholderStage
from .stages.document_selection import DocumentSelectionStage
from .stages.agent_selection import AgentSelectionStage
from .stages.project_selection import ProjectSelectionStage
from .stages.worktree_selection import WorktreeSelectionStage
from .stages.config_selection import ConfigSelectionStage

logger = get_logger(__name__)


class StageType(Enum):
    """Available overlay stages."""
    DOCUMENT = "document"
    AGENT = "agent"
    PROJECT = "project"
    WORKTREE = "worktree"
    CONFIG = "config"


class AgentExecutionOverlay(ModalScreen):
    """Multi-stage agent execution overlay."""
    
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
        
        # Configuration
        self.stages = [
            StageType.DOCUMENT,
            StageType.AGENT,
            StageType.PROJECT,
            StageType.WORKTREE,
            StageType.CONFIG
        ]

        # State management
        self.current_stage_index = 0
        self.callback = callback

        # Selection data - everything in one dict!
        # Note: Using 'data' instead of 'selections' to avoid conflict with Textual's built-in selections attribute
        self.data = {
            'document_id': initial_document_id,
            'agent_id': None,
            'project_index': None,
            'project_path': None,
            'project_worktrees': [],  # Pre-loaded worktrees
            'worktree_index': None,
            'config': {},
            # Additional data from stages
            'document_data': {},
            'agent_data': {},
            'project_data': {},
            'worktree_data': {},
        }

        # Stage management
        self.stage_widgets: Dict[StageType, Any] = {}
        self.stage_completed: Dict[StageType, bool] = {
            stage: False for stage in self.stages
        }
        
        # Set starting stage
        if start_stage and start_stage in self.stages:
            self.current_stage_index = self.stages.index(start_stage)
            
        # If we have an initial document, mark document stage as completed
        if initial_document_id:
            self.stage_completed[StageType.DOCUMENT] = True
            # Fetch document data to populate document_title
            try:
                from ..models.documents import get_document
                doc = get_document(str(initial_document_id))
                if doc:
                    self.data['document_data'] = {
                        'document_id': doc['id'],
                        'document_title': doc.get('title', 'Untitled'),
                        'document_project': doc.get('project', 'Default')
                    }
                    logger.info(f"Pre-selected document data: {self.data['document_data']}")
                else:
                    logger.warning(f"Could not fetch document {initial_document_id}")
            except Exception as e:
                logger.error(f"Failed to fetch pre-selected document data: {e}", exc_info=True)
            # Start at agent stage if document is pre-selected
            if start_stage is None:
                self.current_stage_index = self.stages.index(StageType.AGENT)
        
        logger.info(f"AgentExecutionOverlay initialized: start_stage={start_stage}, "
                   f"initial_doc={initial_document_id}, current_stage_index={self.current_stage_index}")
    
    def compose(self) -> ComposeResult:
        """Create the overlay UI."""
        with Vertical(id="overlay-container"):
            # Header with title and progress
            with Horizontal(id="overlay-header"):
                yield Label("🤖 Agent Execution", id="overlay-title")
                yield Label("", id="stage-progress")

            # Main content area for stages - mount all stages at once
            with Vertical(id="stage-content"):
                # All stages are mounted but hidden by default
                # We'll show/hide them with CSS instead of removing/mounting
                pass

            # Footer with navigation and help
            with Horizontal(id="overlay-footer"):
                yield Static("Tab: Next Stage | Shift+Tab: Previous | Enter: Proceed | Esc: Cancel",
                           classes="footer-help")
                yield Button("Cancel", variant="default", id="cancel-btn")
                yield Button("Execute", variant="primary", id="execute-btn", disabled=True)
    
    async def on_mount(self) -> None:
        """Initialize overlay when mounted."""
        logger.info("AgentExecutionOverlay mounted")

        # Mount all stages once
        await self.initialize_all_stages()

        # Update display
        await self.update_stage_progress()
        await self.show_current_stage()

    async def initialize_all_stages(self) -> None:
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
            stage.add_class("stage-hidden")  # Hide by default

        logger.info("All stages initialized and mounted")
    
    def get_current_stage(self) -> StageType:
        """Get the current stage."""
        return self.stages[self.current_stage_index]
    
    async def update_stage_progress(self) -> None:
        """Update the stage progress indicator."""
        progress = self.query_one("#stage-progress", Label)
        
        # Build progress indicator
        stage_indicators = []
        for i, stage in enumerate(self.stages):
            stage_name = stage.value.title()
            
            if i < self.current_stage_index:
                # Completed stage
                stage_indicators.append(f"[green]✓ {stage_name}[/green]")
            elif i == self.current_stage_index:
                # Current stage
                stage_indicators.append(f"[yellow]→ {stage_name}[/yellow]")
            else:
                # Pending stage
                stage_indicators.append(f"[dim]{stage_name}[/dim]")
        
        progress_text = f"Stage {self.current_stage_index + 1}/4: " + " | ".join(stage_indicators)
        progress.update(progress_text)
    
    async def show_current_stage(self) -> None:
        """Display the current stage content by hiding all others and showing the current one."""
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
        await self.update_navigation_state()

        # Post stage change message
        self.post_message(self.StageChanged(current_stage, self.current_stage_index))
    
    async def update_navigation_state(self) -> None:
        """Update navigation button states."""
        execute_btn = self.query_one("#execute-btn", Button)

        # Enable execute button if we have minimum required selections
        can_execute = (
            self.data['document_id'] is not None and
            self.data['agent_id'] is not None
        )
        execute_btn.disabled = not can_execute

        # Update execute button text based on stage
        if self.get_current_stage() == StageType.CONFIG:
            execute_btn.label = "Execute Now"
        else:
            execute_btn.label = "Quick Execute"
    
    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        if self.current_stage_index < len(self.stages) - 1:
            self.current_stage_index += 1
            # Use run_worker to handle async operations properly
            self.run_worker(self.update_stage_progress(), exclusive=True, group="stage_update")
            self.run_worker(self.show_current_stage(), exclusive=True, group="stage_display")
            logger.info(f"Advanced to stage {self.current_stage_index}: {self.get_current_stage()}")

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        if self.current_stage_index > 0:
            self.current_stage_index -= 1
            # Use run_worker to handle async operations properly
            self.run_worker(self.update_stage_progress(), exclusive=True, group="stage_update")
            self.run_worker(self.show_current_stage(), exclusive=True, group="stage_display")
            logger.info(f"Returned to stage {self.current_stage_index}: {self.get_current_stage()}")
    
    def action_proceed(self) -> None:
        """Proceed to next stage or execute if on last stage."""
        current_stage = self.get_current_stage()
        
        # Mark current stage as completed
        self.stage_completed[current_stage] = True
        
        if current_stage == StageType.CONFIG:
            # Last stage - execute
            self.action_execute()
        else:
            # Move to next stage
            self.action_next_stage()
    
    def action_execute(self) -> None:
        """Execute with current selections."""
        if not self.data['document_id'] or not self.data['agent_id']:
            logger.warning("Cannot execute: missing required selections")
            return

        execution_data = {
            "document_id": self.data['document_id'],
            "agent_id": self.data['agent_id'],
            "worktree_index": self.data['worktree_index'],
            "config": self.data['config'].copy()
        }

        logger.info(f"Executing with data: {execution_data}")

        # Post execution message
        self.post_message(self.ExecutionRequested(execution_data))

        # Close overlay and pass result to the callback via dismiss
        # The callback will be called by push_screen's result handler
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
    
    def on_overlay_stage_selection_changed(self, message: OverlayStage.SelectionChanged) -> None:
        """Handle stage selection changes."""
        logger.info(f"Stage {message.stage_name} selection changed: {message.selection_data}")
        # Update selections dict directly
        if message.stage_name == "document":
            self.data['document_data'] = message.selection_data
        elif message.stage_name == "agent":
            self.data['agent_data'] = message.selection_data
        elif message.stage_name == "project":
            self.data['project_data'] = message.selection_data
        elif message.stage_name == "worktree":
            self.data['worktree_data'] = message.selection_data
        elif message.stage_name == "config":
            self.data['config'].update(message.selection_data)
    
    def on_overlay_stage_stage_completed(self, message: OverlayStage.StageCompleted) -> None:
        """Handle stage completion."""
        logger.info(f"Stage {message.stage_name} completed")
        # Mark stage as completed and possibly advance
        if message.stage_name == "document":
            self.stage_completed[StageType.DOCUMENT] = True
        elif message.stage_name == "agent":
            self.stage_completed[StageType.AGENT] = True
        elif message.stage_name == "worktree":
            self.stage_completed[StageType.WORKTREE] = True
        elif message.stage_name == "config":
            self.stage_completed[StageType.CONFIG] = True
        
        self.call_after_refresh(self.update_navigation_state)
    
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
        # The stage already called self.host.set_document_selection(),
        # so we just need to update our progress display
        self.call_after_refresh(self.update_stage_progress)

    def on_agent_selection_stage_agent_selected(self, message) -> None:
        """Handle agent selection from agent stage."""
        logger.info(f"Agent selected via stage: {message.agent_id}")
        self.call_after_refresh(self.update_stage_progress)

    def on_worktree_selection_stage_worktree_selected(self, message) -> None:
        """Handle worktree selection from worktree stage."""
        logger.info(f"Worktree selected via stage: {message.worktree_index}")
        self.call_after_refresh(self.update_stage_progress)

    def on_config_selection_stage_config_completed(self, message) -> None:
        """Handle config completion from config stage."""
        logger.info(f"Config completed via stage: {message.config}")
        self.call_after_refresh(self.update_stage_progress)
    
    def set_document_selection(self, document_id: int) -> None:
        """Set selected document ID."""
        self.data['document_id'] = document_id
        self.stage_completed[StageType.DOCUMENT] = True
        logger.info(f"Document selected: {document_id}")
        self.call_after_refresh(self.update_navigation_state)

    def set_agent_selection(self, agent_id: int) -> None:
        """Set selected agent ID."""
        self.data['agent_id'] = agent_id
        self.stage_completed[StageType.AGENT] = True
        logger.info(f"Agent selected: {agent_id}")
        self.call_after_refresh(self.update_navigation_state)

    def set_project_selection(self, project_index: int, project_path: str, worktrees: list = None) -> None:
        """Set selected project and its worktrees."""
        self.data['project_index'] = project_index
        self.data['project_path'] = project_path
        self.data['project_worktrees'] = worktrees or []
        self.stage_completed[StageType.PROJECT] = True
        logger.info(f"Project selected: index={project_index}, path={project_path}, worktrees={len(worktrees or [])}")
        self.call_after_refresh(self.update_navigation_state)

    def set_worktree_selection(self, worktree_index: int) -> None:
        """Set selected worktree index."""
        self.data['worktree_index'] = worktree_index
        self.stage_completed[StageType.WORKTREE] = True
        logger.info(f"Worktree selected: {worktree_index}")
        self.call_after_refresh(self.update_navigation_state)

    def set_execution_config(self, config: Dict[str, Any]) -> None:
        """Set execution configuration."""
        self.data['config'].update(config)
        self.stage_completed[StageType.CONFIG] = True
        logger.info(f"Config updated: {config}")
        self.call_after_refresh(self.update_navigation_state)

    def get_selection_summary(self) -> Dict[str, Any]:
        """Get summary of current selections - flatten all nested data."""
        summary = {}

        # Add base data (IDs and paths)
        summary.update({
            'document_id': self.data.get('document_id'),
            'agent_id': self.data.get('agent_id'),
            'project_index': self.data.get('project_index'),
            'project_path': self.data.get('project_path'),
            'worktree_index': self.data.get('worktree_index'),
        })

        # Flatten nested data dicts (document_data, agent_data, etc.)
        for key in ['document_data', 'agent_data', 'project_data', 'worktree_data', 'config']:
            if key in self.data and self.data[key]:
                logger.debug(f"Flattening {key}: {self.data[key]}")
                summary.update(self.data[key])

        logger.debug(f"Final summary: {summary}")

        # Add metadata
        summary['current_stage'] = self.get_current_stage().value
        summary['stage_index'] = self.current_stage_index
        summary['completed_stages'] = [
            stage.value for stage, completed in self.stage_completed.items()
            if completed
        ]
        return summary