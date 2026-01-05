#!/usr/bin/env python3
"""
Configuration selection stage for agent execution overlay.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Static, Input, Switch, Label
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from .base import OverlayStage

logger = get_logger(__name__)


class ConfigSelectionStage(OverlayStage):
    """Configuration selection stage for execution settings."""

    BINDINGS = [
        Binding("ctrl+s", "execute", "Execute Agent", show=True, priority=True),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("b", "toggle_background", "Toggle Background"),
        Binding("enter", "execute", "Execute Agent"),
    ]

    DEFAULT_CSS = """
    ConfigSelectionStage {
        height: 1fr;
        layout: vertical;
    }

    .config-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 1 1;
    }

    #config-summary {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    .summary-item {
        padding: 0 0 0 2;
        color: $text;
    }

    .summary-label {
        color: $text-muted;
        text-style: bold;
    }

    #config-options {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    .config-row {
        height: 3;
        layout: horizontal;
        align: left middle;
    }

    .config-label {
        width: 30;
        color: $text-muted;
    }

    .config-input {
        width: 1fr;
        height: 1;
    }

    #config-help {
        height: 3;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }

    .execute-button {
        height: 3;
        text-align: center;
        padding: 1 0;
    }
    """

    class ConfigCompleted(Message):
        """Message sent when configuration is complete and ready to execute."""
        def __init__(self, config: Dict[str, Any]) -> None:
            self.config = config
            super().__init__()

    def __init__(self, host, **kwargs):
        super().__init__(host, "config", **kwargs)
        self.background_execution = True  # Default to background
        self.timeout_seconds = 3600  # Default 1 hour
        self.variables: Dict[str, str] = {}
        self.config_valid = True  # Always valid by default

    def compose(self) -> ComposeResult:
        """Create the configuration UI."""
        yield Static("[bold yellow]⚙️  Execution Configuration[/bold yellow]", classes="config-header")

        # Summary of selections
        with Container(id="config-summary"):
            yield Static("[bold]Selected Configuration:[/bold]", classes="summary-label")
            yield Static("", id="summary-document", classes="summary-item")
            yield Static("", id="summary-agent", classes="summary-item")
            yield Static("", id="summary-worktree", classes="summary-item")

        # Configuration options
        with Container(id="config-options"):
            yield Static("[bold]Execution Options:[/bold]")

            # Background execution toggle
            with Horizontal(classes="config-row"):
                yield Label("Background Execution:", classes="config-label")
                yield Switch(value=True, id="background-switch")

            # Timeout input
            with Horizontal(classes="config-row"):
                yield Label("Timeout (seconds):", classes="config-label")
                yield Input(value="3600", placeholder="3600", id="timeout-input", classes="config-input")

            # Optional: Variables input (comma-separated key=value pairs)
            with Horizontal(classes="config-row"):
                yield Label("Variables (key=value):", classes="config-label")
                yield Input(placeholder="var1=value1,var2=value2", id="variables-input", classes="config-input")

        # Execute button
        yield Static("[bold green]✓ Press Ctrl+S or Enter to Execute[/bold green]", classes="execute-button")
        yield Static("Shift+Tab: Back | B: Toggle Background | Ctrl+S/Enter: Execute", id="config-help")

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
            # Document summary
            doc_id = summary.get("document_id", "None")
            doc_title = summary.get("document_title", "Unknown")
            doc_widget = self.query_one("#summary-document", Static)
            doc_widget.update(f"📄 Document: [{doc_id}] {doc_title}")

            # Agent summary
            agent_id = summary.get("agent_id", "None")
            agent_name = summary.get("agent_display_name", summary.get("agent_name", "Unknown"))
            agent_widget = self.query_one("#summary-agent", Static)
            agent_widget.update(f"🤖 Agent: [{agent_id}] {agent_name}")

            # Worktree summary
            worktree_branch = summary.get("worktree_branch", "N/A")
            worktree_path = summary.get("worktree_path", ".")
            worktree_widget = self.query_one("#summary-worktree", Static)
            worktree_widget.update(f"🌳 Worktree: {worktree_branch} ({worktree_path})")

        except Exception as e:
            logger.error(f"Failed to update summary display: {e}")

    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the background switch."""
        try:
            bg_switch = self.query_one("#background-switch", Switch)
            bg_switch.focus()
        except Exception as e:
            logger.warning(f"Could not focus background switch: {e}")

    def validate_selection(self) -> bool:
        """Configuration is always valid (uses defaults)."""
        return True

    def get_selection_data(self) -> Dict[str, Any]:
        """Return current configuration."""
        return {
            "background": self.background_execution,
            "timeout": self.timeout_seconds,
            "variables": self.variables.copy(),
        }

    def parse_variables(self, var_string: str) -> Dict[str, str]:
        """Parse comma-separated key=value pairs."""
        variables = {}
        if not var_string.strip():
            return variables

        for pair in var_string.split(','):
            pair = pair.strip()
            if '=' in pair:
                key, value = pair.split('=', 1)
                variables[key.strip()] = value.strip()

        return variables

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle background execution toggle."""
        if event.switch.id == "background-switch":
            self.background_execution = event.value
            logger.info(f"Background execution: {self.background_execution}")
            self.update_selection(self.get_selection_data())

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "timeout-input":
            try:
                timeout_value = event.value.strip()
                if timeout_value:
                    self.timeout_seconds = int(timeout_value)
                    logger.info(f"Timeout set to: {self.timeout_seconds}")
                    self.update_selection(self.get_selection_data())
            except ValueError:
                logger.warning(f"Invalid timeout value: {event.value}")

        elif event.input.id == "variables-input":
            try:
                self.variables = self.parse_variables(event.value)
                logger.info(f"Variables set to: {self.variables}")
                self.update_selection(self.get_selection_data())
            except Exception as e:
                logger.warning(f"Failed to parse variables: {e}")

    def action_toggle_background(self) -> None:
        """Toggle background execution."""
        try:
            bg_switch = self.query_one("#background-switch", Switch)
            bg_switch.toggle()
        except Exception as e:
            logger.error(f"Failed to toggle background switch: {e}")

    def action_execute(self) -> None:
        """Execute the agent with current configuration."""
        logger.info("Executing agent with configuration")

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
