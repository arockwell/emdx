#!/usr/bin/env python3
"""
Modal screens for EMDX TUI.
"""

import logging

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label

# Set up logging for debugging
logger = logging.getLogger(__name__)
key_logger = logging.getLogger("key_events")



class DeleteConfirmScreen(ModalScreen):
    """Modal screen for delete confirmation."""

    CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 2;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }

    #question {
        column-span: 2;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    Button {
        width: 100%;
    }
    """

    BINDINGS = [
        ("y", "confirm_delete", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, doc_id: int, doc_title: str):
        super().__init__()
        self.doc_id = doc_id
        self.doc_title = doc_title
        logger.info(f"DeleteConfirmScreen initialized for doc #{doc_id}: {doc_title}")

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(
                f'Delete document #{self.doc_id}?\n"{self.doc_title}"\n\n'
                f"[dim]Press [bold]y[/bold] to delete, [bold]n[/bold] to cancel[/dim]",
                id="question",
            )
            yield Button("Cancel (n)", variant="primary", id="cancel")
            yield Button("Delete (y)", variant="error", id="delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.info(f"Button pressed: {event.button.id}")
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_delete(self) -> None:
        logger.info("action_confirm_delete called")
        self.dismiss(True)

    def action_cancel(self) -> None:
        logger.info("action_cancel called")
        self.dismiss(False)
    
    def on_dismiss(self, result) -> None:
        """Log when modal is dismissed."""
        logger.info(f"DeleteConfirmScreen dismissed with result: {result}")

    def on_mount(self) -> None:
        """Ensure modal has focus when mounted."""
        logger.info(f"DeleteConfirmScreen mounted for doc #{self.doc_id}")
        self.focus()
        # Log the current screen stack for debugging
        if hasattr(self.app, 'screen_stack'):
            logger.info(f"Screen stack after mount: {len(self.app.screen_stack)} screens")

    def on_key(self, event) -> None:
        """Log key events for debugging."""
        key_logger.info(f"DeleteConfirmScreen.on_key: key={event.key}, character={event.character}")
        # Don't consume the event - let bindings handle it
        # Important: Don't call event.stop() or event.prevent_default() here
        # as that would prevent the bindings from working
