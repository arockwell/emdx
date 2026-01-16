#!/usr/bin/env python3
"""
Configuration selection stage for agent execution overlay.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from .base import OverlayStage

logger = get_logger(__name__)


class ConfigSelectionStage(OverlayStage):
    """Configuration selection stage for execution settings."""

    BINDINGS = [
        Binding("enter", "execute", "Execute Agent", show=True, priority=True),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    ConfigSelectionStage {
        height: 1fr;
        layout: vertical;
        align: center middle;
    }

    .config-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 2 1;
        text-align: center;
    }

    #config-summary {
        width: 80%;
        height: auto;
        border: thick $primary;
        padding: 2 3;
        margin: 0 0 2 0;
        background: $boost;
    }

    .summary-item {
        padding: 0 0 1 0;
        color: $text;
    }

    .summary-label {
        color: $success;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #config-help {
        height: 3;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }

    .execute-prompt {
        height: 5;
        text-align: center;
        padding: 2 0;
    }
    """

    class ConfigCompleted(Message):
        """Message sent when configuration is complete and ready to execute."""
        def __init__(self, config: Dict[str, Any]) -> None:
            self.config = config
            super().__init__()

    def __init__(self, host, **kwargs):
        super().__init__(host, "config", **kwargs)
        self.config_valid = True  # Always valid by default

    def compose(self) -> ComposeResult:
        """Create the configuration UI."""
        yield Static("[bold yellow]🚀 Ready to Execute[/bold yellow]", classes="config-header")

        # Summary of selections
        with Container(id="config-summary"):
            yield Static("[bold green]✓ Your Selection:[/bold green]", classes="summary-label")
            yield Static("", id="summary-document", classes="summary-item")
            yield Static("", id="summary-agent", classes="summary-item")
            yield Static("", id="summary-project", classes="summary-item")
            yield Static("", id="summary-worktree", classes="summary-item")

        # Execute prompt
        yield Static("[bold green]Press Enter to Execute Agent[/bold green]", classes="execute-prompt")
        yield Static("Shift+Tab: Back | Enter: Execute", id="config-help")

    async def on_mount(self) -> None:
        """Load stage when mounted."""
        await super().on_mount()

    async def load_stage_data(self) -> None:
        """Load configuration data and summary."""
        try:
            logger.info("Loading execution configuration")

            # Get summary of all selections from host
            summary = self.host.get_selection_summary()
            logger.info(f"Selection summary: {summary}")

            # Update summary display
            await self.update_summary_display(summary)

            # Mark as valid by default
            self._is_valid = True

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")

    async def update_summary_display(self, summary: Dict[str, Any]) -> None:
        """Update the summary display with current selections."""
        try:
            logger.info(f"Config screen updating summary with: {summary}")

            # Document summary
            doc_id = summary.get("document_id", "None")
            doc_title = summary.get("document_title", "Unknown")
            logger.info(f"Document display - ID: {doc_id}, Title: {doc_title}")
            doc_widget = self.query_one("#summary-document", Static)
            doc_widget.update(f"📄 Document:  [{doc_id}] {doc_title}")

            # Agent summary
            agent_id = summary.get("agent_id", "None")
            agent_name = summary.get("agent_display_name", summary.get("agent_name", "Unknown"))
            agent_widget = self.query_one("#summary-agent", Static)
            agent_widget.update(f"🤖 Agent: [{agent_id}] {agent_name}")

            # Project summary
            project_name = summary.get("project_name", "Unknown")
            project_widget = self.query_one("#summary-project", Static)
            project_widget.update(f"📁 Project:   {project_name}")

            # Worktree summary
            worktree_branch = summary.get("worktree_branch", "N/A")
            worktree_path = summary.get("worktree_path", ".")
            # Show just the worktree directory name, not full path
            from pathlib import Path
            worktree_name = Path(worktree_path).name if worktree_path != "." else "Current"
            worktree_widget = self.query_one("#summary-worktree", Static)
            worktree_widget.update(f"🌳 Worktree:  {worktree_branch} ({worktree_name})")

        except Exception as e:
            logger.error(f"Failed to update summary display: {e}")

    async def set_focus_to_primary_input(self) -> None:
        """No input to focus - just wait for Enter key."""
        pass

    def validate_selection(self) -> bool:
        """Configuration is always valid."""
        return True

    def get_selection_data(self) -> Dict[str, Any]:
        """Return minimal configuration (background execution enabled by default)."""
        return {
            "background": True,  # Always run in background
        }

    def action_execute(self) -> None:
        """Execute the agent with current configuration."""
        logger.info("Executing agent")

        # Update host with final configuration
        self.host.set_execution_config(self.get_selection_data())

        # Mark as valid and complete
        self._is_valid = True
        self.update_selection(self.get_selection_data())

        # Post configuration completed message
        self.post_message(self.ConfigCompleted(self.get_selection_data()))

        # Request execution
        self.request_navigation("execute")

    def action_next_stage(self) -> None:
        """Execute (this is the last stage)."""
        self.action_execute()

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        self.request_navigation("prev")

    def get_help_text(self) -> str:
        """Get help text for this stage."""
        return "Configure execution settings. Press Ctrl+S or Enter to execute, B to toggle background, Shift+Tab to go back."
