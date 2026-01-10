#!/usr/bin/env python3
"""
Modal dialog for confirming agent deletion.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ..agents.registry import agent_registry


class DeleteAgentModal(ModalScreen):
    """Modal for confirming agent deletion."""

    DEFAULT_CSS = """
    DeleteAgentModal {
        align: center middle;
    }

    #delete-dialog {
        background: $surface;
        border: thick $error;
        padding: 2;
        width: 60;
        height: auto;
    }

    #delete-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }

    #delete-message {
        margin: 1 0;
        text-align: center;
    }

    #button-container {
        margin-top: 2;
        align: center middle;
        height: 3;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)

    def compose(self) -> ComposeResult:
        """Create the deletion confirmation dialog."""
        with Vertical(id="delete-dialog"):
            yield Static("Delete Agent", id="delete-title")
            yield Static(
                f"Are you sure you want to delete '{self.agent.config.display_name}'?\n"
                f"This agent has been used {self.agent.config.usage_count} times.",
                id="delete-message",
            )

            with Horizontal(id="button-container"):
                yield Button("Delete", variant="error", id="delete-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "delete-button":
            self.dismiss(True)
        else:
            self.dismiss(False)
