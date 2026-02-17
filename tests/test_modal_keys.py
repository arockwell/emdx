#!/usr/bin/env python3
"""
Simple test to verify modal key bindings work correctly.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label


class DeleteConfirmScreen(ModalScreen):
    """Test modal screen for delete confirmation."""

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
        print(f"DeleteConfirmScreen initialized for doc #{doc_id}")

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
        print(f"Button pressed: {event.button.id}")
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_delete(self) -> None:
        print("action_confirm_delete called")
        self.dismiss(True)

    def action_cancel(self) -> None:
        print("action_cancel called")
        self.dismiss(False)

    def on_key(self, event) -> None:
        """Debug key events."""
        print(f"DeleteConfirmScreen.on_key: key={event.key}, character={event.character}")
        # Don't stop propagation - let bindings handle it

class ModalTestApp(App):
    """Test app to verify delete modal functionality."""

    BINDINGS = [
        Binding("d", "show_delete", "Delete"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        # Create a simple table
        table = DataTable()
        table.add_column("ID", width=5)
        table.add_column("Title", width=50)
        table.add_row("1", "Test Document 1")
        table.add_row("2", "Test Document 2")
        yield table
        yield Label("Press 'd' to test delete modal, 'q' to quit", id="status")

    def action_show_delete(self):
        """Show the delete confirmation modal."""
        print("Showing delete modal...")

        def handle_result(result: bool) -> None:
            print(f"Modal result: {result}")
            status = self.query_one("#status", Label)
            if result:
                status.update("Delete confirmed!")
            else:
                status.update("Delete cancelled!")

        self.push_screen(DeleteConfirmScreen(123, "Test Document"), handle_result)

    def on_key(self, event) -> None:
        """Debug all key events."""
        print(f"App.on_key: key={event.key}, character={event.character}")

if __name__ == "__main__":
    print("Starting modal key test app...")
    print("Press 'd' to show delete modal")
    print("In the modal, press 'y' to confirm or 'n'/'escape' to cancel")
    print("Press 'q' to quit\n")

    app = ModalTestApp()
    app.run()
