"""Modal dialogs for file browser operations (STUB MODULE).

This module was deleted in PR #300 but is still imported by file_browser/actions.py.
These are stub implementations that show a "not implemented" message.
"""

from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class SaveFileModal(ModalScreen[Optional[dict]]):
    """Modal for saving file to EMDX (stub - functionality removed)."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, file_path: Path, **kwargs):
        """Initialize save modal."""
        super().__init__(**kwargs)
        self.file_path = file_path

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container():
            yield Label("Save to EMDX")
            yield Static(
                "This feature has been removed.\n"
                "Use the CLI 'emdx save' command instead."
            )
            yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)


class ExecuteFileModal(ModalScreen[Optional[dict]]):
    """Modal for executing file with Claude (stub - functionality removed)."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, file_path: Path, doc_id: Optional[int] = None, **kwargs):
        """Initialize execute modal."""
        super().__init__(**kwargs)
        self.file_path = file_path
        self.doc_id = doc_id

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container():
            yield Label("Execute with Claude")
            yield Static(
                "This feature has been removed.\n"
                "Use the CLI for execution functionality."
            )
            yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss(None)

    def action_cancel(self) -> None:
        """Cancel and close modal."""
        self.dismiss(None)
