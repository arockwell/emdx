#!/usr/bin/env python3
"""
Modal dialogs for creating and editing agents.
"""

import os

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea
from textual.binding import Binding

from ..agents.registry import agent_registry


class CreateAgentModal(ModalScreen):
    """Modal for creating a new agent."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Create Agent"),
    ]

    DEFAULT_CSS = """
    CreateAgentModal {
        align: center middle;
    }

    #create-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
        height: auto;
        max-height: 90%;
    }

    #create-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    .field-label {
        margin-top: 1;
        color: $text-muted;
    }

    Input, TextArea {
        margin-bottom: 1;
    }

    #button-container {
        margin-top: 2;
        align: center middle;
        height: 3;
    }

    Button {
        margin: 0 1;
    }

    .category-buttons {
        margin-bottom: 1;
    }

    .category-button {
        margin-right: 1;
    }

    ScrollableContainer {
        height: 1fr;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = "research"

    def compose(self) -> ComposeResult:
        """Create the agent creation form."""
        with Vertical(id="create-dialog"):
            yield Static("Create New Agent", id="create-title")

            with ScrollableContainer():
                # Basic info
                yield Label("Name (no spaces):", classes="field-label")
                yield Input(placeholder="my-agent", id="name-input")

                yield Label("Display Name:", classes="field-label")
                yield Input(placeholder="My Agent", id="display-name-input")

                yield Label("Description:", classes="field-label")
                yield Input(
                    placeholder="What this agent does...", id="description-input"
                )

                yield Label("Category:", classes="field-label")
                with Horizontal(classes="category-buttons"):
                    yield Button(
                        "Research",
                        id="cat-research",
                        variant="primary",
                        classes="category-button",
                    )
                    yield Button(
                        "Generation",
                        id="cat-generation",
                        variant="default",
                        classes="category-button",
                    )
                    yield Button(
                        "Analysis",
                        id="cat-analysis",
                        variant="default",
                        classes="category-button",
                    )
                    yield Button(
                        "Maintenance",
                        id="cat-maintenance",
                        variant="default",
                        classes="category-button",
                    )

                # Prompts
                yield Label("System Prompt:", classes="field-label")
                yield TextArea(id="system-prompt", height=5)

                yield Label("User Prompt Template:", classes="field-label")
                yield TextArea(
                    id="user-prompt",
                    height=5,
                    text="Analyze {{target}} and {{task}}. "
                    "Variables can be used with {{name}} syntax.",
                )

                # Tools
                yield Label("Allowed Tools (comma-separated):", classes="field-label")
                yield Input(
                    placeholder="Read, Grep, Glob, Write",
                    value="Read, Grep, Glob",
                    id="tools-input",
                )

                # Settings
                yield Label("Max Context Docs:", classes="field-label")
                yield Input(value="5", id="max-context-input")

                yield Label("Timeout (seconds):", classes="field-label")
                yield Input(value="3600", id="timeout-input")

                yield Label(
                    "Output Tags (comma-separated, optional):", classes="field-label"
                )
                yield Input(placeholder="analysis, report", id="tags-input")

            # Buttons outside scrollable area
            with Horizontal(id="button-container"):
                yield Button("Create", variant="primary", id="create-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        # Handle category selection
        if button_id.startswith("cat-"):
            # Reset all category buttons
            for cat in ["research", "generation", "analysis", "maintenance"]:
                self.query_one(f"#cat-{cat}").variant = "default"
            # Set selected category
            event.button.variant = "primary"
            self.category = button_id.replace("cat-", "")

        elif button_id == "create-button":
            self.action_submit()
        elif button_id == "cancel-button":
            self.action_cancel()

    def action_submit(self) -> None:
        """Submit the form."""
        # Gather form data
        config = {
            "name": self.query_one("#name-input", Input).value.strip(),
            "display_name": self.query_one("#display-name-input", Input).value.strip(),
            "description": self.query_one("#description-input", Input).value.strip(),
            "category": self.category,
            "system_prompt": self.query_one("#system-prompt", TextArea).text.strip(),
            "user_prompt_template": self.query_one(
                "#user-prompt", TextArea
            ).text.strip(),
            "allowed_tools": [
                t.strip()
                for t in self.query_one("#tools-input", Input).value.split(",")
            ],
            "max_context_docs": int(
                self.query_one("#max-context-input", Input).value or 5
            ),
            "timeout_seconds": int(
                self.query_one("#timeout-input", Input).value or 3600
            ),
            "created_by": os.environ.get("USER", "unknown"),
        }

        # Add tags if provided
        tags_input = self.query_one("#tags-input", Input).value.strip()
        if tags_input:
            from ..utils.emoji_aliases import EMOJI_ALIASES

            tags = []
            for tag in tags_input.split(","):
                tag = tag.strip()
                # Convert text aliases to emojis
                if tag in EMOJI_ALIASES:
                    tags.append(EMOJI_ALIASES[tag])
                else:
                    tags.append(tag)
            config["output_tags"] = tags

        self.dismiss(config)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class EditAgentModal(CreateAgentModal):
    """Modal for editing an existing agent."""

    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        self.category = self.agent.config.category

    def compose(self) -> ComposeResult:
        """Create the edit form with pre-filled values."""
        for widget in super().compose():
            if widget.id == "create-title":
                widget.update(f"Edit Agent: {self.agent.config.display_name}")
            elif widget.id == "create-button":
                widget.label = "Save"
            yield widget

    async def on_mount(self) -> None:
        """Pre-fill form with current values."""
        config = self.agent.config

        self.query_one("#name-input", Input).value = config.name
        self.query_one("#display-name-input", Input).value = config.display_name
        self.query_one("#description-input", Input).value = config.description

        # Set category button
        for cat in ["research", "generation", "analysis", "maintenance"]:
            button = self.query_one(f"#cat-{cat}")
            button.variant = "primary" if cat == config.category else "default"

        self.query_one("#system-prompt", TextArea).text = config.system_prompt
        self.query_one("#user-prompt", TextArea).text = config.user_prompt_template
        self.query_one("#tools-input", Input).value = ", ".join(config.allowed_tools)
        self.query_one("#max-context-input", Input).value = str(config.max_context_docs)
        self.query_one("#timeout-input", Input).value = str(config.timeout_seconds)

        if config.output_tags:
            self.query_one("#tags-input", Input).value = ", ".join(config.output_tags)

        # Disable name field for editing
        self.query_one("#name-input", Input).disabled = True
