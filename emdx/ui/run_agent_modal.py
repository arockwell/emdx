#!/usr/bin/env python3
"""
Modal dialog for running an agent.
"""

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea
from textual.binding import Binding

from ..agents.registry import agent_registry
from ..database.documents import get_recent_documents


class RunAgentModal(ModalScreen):
    """Modal for running an agent."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Run Agent"),
    ]

    DEFAULT_CSS = """
    RunAgentModal {
        align: center middle;
    }

    #run-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 80;
        height: auto;
        max-height: 40;
    }

    #run-title {
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

    .radio-option {
        margin: 0 1;
    }
    """

    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        self.input_type = "document"

    def compose(self) -> ComposeResult:
        """Create the run agent dialog."""
        with Vertical(id="run-dialog"):
            yield Static(
                f"Run Agent: {self.agent.config.display_name}", id="run-title"
            )

            # Input type selection
            yield Label("Input Type:", classes="field-label")
            with Horizontal():
                yield Button(
                    "Document",
                    id="type-document",
                    variant="primary",
                    classes="radio-option",
                )
                yield Button(
                    "Query", id="type-query", variant="default", classes="radio-option"
                )

            # Document ID input
            yield Label(
                "Document ID (or leave empty to use most recent):",
                classes="field-label",
                id="doc-label",
            )
            yield Input(placeholder="123", id="doc-input")

            # Recent documents hint
            recent_docs = get_recent_documents(limit=5)
            if recent_docs:
                hints = []
                for doc in recent_docs:
                    hints.append(f"#{doc['id']}: {doc['title'][:40]}...")
                yield Static(
                    "Recent: " + " | ".join(hints),
                    classes="field-label",
                    id="recent-hint",
                )

            # Query input (hidden by default)
            yield Label("Query:", classes="field-label query-field")
            yield TextArea(id="query-input", classes="query-field")

            # Variables input (optional)
            yield Label("Variables (key=value, one per line):", classes="field-label")
            yield TextArea(id="vars-input", height=3)

            # Buttons
            with Horizontal(id="button-container"):
                yield Button("Run", variant="primary", id="run-button")
                yield Button("Cancel", variant="default", id="cancel-button")

    async def on_mount(self) -> None:
        """Set up initial state."""
        # Hide query fields initially
        for widget in self.query(".query-field"):
            widget.display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "type-document":
            self.input_type = "document"
            self.query_one("#type-document").variant = "primary"
            self.query_one("#type-query").variant = "default"

            # Show document fields, hide query fields
            self.query_one("#doc-label").display = True
            self.query_one("#doc-input").display = True
            if self.query_one("#recent-hint", Static):
                self.query_one("#recent-hint").display = True

            for widget in self.query(".query-field"):
                widget.display = False

        elif button_id == "type-query":
            self.input_type = "query"
            self.query_one("#type-document").variant = "default"
            self.query_one("#type-query").variant = "primary"

            # Hide document fields, show query fields
            self.query_one("#doc-label").display = False
            self.query_one("#doc-input").display = False
            if self.query_one("#recent-hint", Static):
                self.query_one("#recent-hint").display = False

            for widget in self.query(".query-field"):
                widget.display = True

        elif button_id == "run-button":
            self.action_submit()
        elif button_id == "cancel-button":
            self.action_cancel()

    def action_submit(self) -> None:
        """Submit the form."""
        result = {
            "agent_id": self.agent_id,
            "input_type": self.input_type,
        }

        if self.input_type == "document":
            doc_id_str = self.query_one("#doc-input", Input).value.strip()
            if doc_id_str:
                try:
                    result["doc_id"] = int(doc_id_str)
                except ValueError:
                    pass
            else:
                # Use most recent document
                recent_docs = get_recent_documents(limit=1)
                if recent_docs:
                    result["doc_id"] = recent_docs[0]["id"]
        else:
            result["query"] = self.query_one("#query-input", TextArea).text

        # Parse variables
        vars_text = self.query_one("#vars-input", TextArea).text
        if vars_text.strip():
            variables = {}
            for line in vars_text.strip().split("\n"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    variables[key.strip()] = value.strip()
            if variables:
                result["variables"] = variables

        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)
