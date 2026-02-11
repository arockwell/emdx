"""Modal screen for entering a new cascade idea."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, TextArea


class NewIdeaScreen(ModalScreen):
    """Modal screen for entering a new cascade idea."""

    CSS = """
    NewIdeaScreen {
        align: center middle;
    }
    #idea-dialog {
        width: 70;
        max-height: 20;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #idea-label {
        width: 100%;
        padding-bottom: 1;
    }
    #idea-input {
        width: 100%;
        height: 8;
        min-height: 4;
        margin-bottom: 1;
    }
    #idea-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    #idea-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+enter", "submit", "Submit"),
    ]

    def __init__(self):
        super().__init__()
        self.idea_text = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="idea-dialog"):
            yield Label("\U0001f4a1 Enter new idea for the cascade (Ctrl+Enter to submit):", id="idea-label")
            yield TextArea(id="idea-input")
            with Horizontal(id="idea-buttons"):
                yield Button("Add Idea", variant="primary", id="add-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def _validate_and_submit(self) -> None:
        """Validate input and submit if valid."""
        idea_input = self.query_one("#idea-input", TextArea)
        self.idea_text = idea_input.text.strip()
        if self.idea_text:
            self.dismiss(self.idea_text)
        else:
            label = self.query_one("#idea-label", Label)
            label.update("[red]\u26a0\ufe0f Idea cannot be empty[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-btn":
            self._validate_and_submit()
        else:
            self.dismiss(None)

    def action_submit(self) -> None:
        """Handle Ctrl+Enter to submit the idea."""
        self._validate_and_submit()

    def on_mount(self) -> None:
        idea_input = self.query_one("#idea-input", TextArea)
        idea_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)
