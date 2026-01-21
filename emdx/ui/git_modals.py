"""Git-related modal dialogs."""

import logging
from typing import Callable, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from rich.markup import escape
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea

from emdx.utils.git_ops import git_commit

logger = logging.getLogger(__name__)


class CommitModal(ModalScreen[Optional[str]]):
    """Modal for entering commit message."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+enter", "submit", "Commit", show=True),
    ]

    DEFAULT_CSS = """
    CommitModal {
        align: center middle;
    }

    CommitModal #commit-container {
        width: 60%;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    CommitModal #commit-title {
        text-style: bold;
        margin-bottom: 1;
    }

    CommitModal #commit-message {
        height: 10;
        margin-bottom: 1;
    }

    CommitModal #commit-buttons {
        height: 3;
    }

    CommitModal Button {
        margin-right: 1;
    }
    """

    def __init__(
        self,
        staged_files: list[str] = None,
        worktree_path: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._staged_files = staged_files or []
        self._worktree_path = worktree_path

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="commit-container"):
            yield Label("Commit Changes", id="commit-title")

            # Show staged files - escape file paths to prevent markup injection
            if self._staged_files:
                files_text = "\n".join(f"  • {escape(f)}" for f in self._staged_files[:10])
                if len(self._staged_files) > 10:
                    files_text += f"\n  ... and {len(self._staged_files) - 10} more"
                yield Static(f"[dim]Staged files:[/dim]\n{files_text}", id="staged-files")

            yield Label("Commit message:", id="message-label")
            yield TextArea(id="commit-message")

            with Container(id="commit-buttons"):
                yield Button("Commit", variant="primary", id="btn-commit")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        """Focus the message input."""
        self.query_one("#commit-message", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-commit":
            self.action_submit()
        elif event.button.id == "btn-cancel":
            self.action_cancel()

    def action_submit(self) -> None:
        """Submit the commit."""
        message = self.query_one("#commit-message", TextArea).text.strip()
        if not message:
            self.notify("Commit message required", severity="warning")
            return

        self.dismiss(message)

    def action_cancel(self) -> None:
        """Cancel the commit."""
        self.dismiss(None)


class MergeConfirmModal(ModalScreen[bool]):
    """Modal to confirm merge operation."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "confirm", "Confirm", show=True),
    ]

    DEFAULT_CSS = """
    MergeConfirmModal {
        align: center middle;
    }

    MergeConfirmModal #merge-container {
        width: 50%;
        height: auto;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
    }

    MergeConfirmModal #merge-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    MergeConfirmModal #merge-buttons {
        height: 3;
        margin-top: 1;
    }

    MergeConfirmModal Button {
        margin-right: 1;
    }
    """

    def __init__(self, source_branch: str, target_branch: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._source = source_branch
        self._target = target_branch

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="merge-container"):
            yield Label("⚠️ Confirm Merge", id="merge-title")
            yield Static(
                f"Merge [bold]{escape(self._source)}[/bold] into [bold]{escape(self._target)}[/bold]?\n\n"
                "This will create a merge commit."
            )
            with Container(id="merge-buttons"):
                yield Button("Merge", variant="warning", id="btn-merge")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-merge":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        """Confirm the merge."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel the merge."""
        self.dismiss(False)


class DeleteBranchModal(ModalScreen[bool]):
    """Modal to confirm branch deletion."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    DeleteBranchModal {
        align: center middle;
    }

    DeleteBranchModal #delete-container {
        width: 50%;
        height: auto;
        background: $surface;
        border: solid $error;
        padding: 1 2;
    }

    DeleteBranchModal #delete-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }

    DeleteBranchModal #delete-buttons {
        height: 3;
        margin-top: 1;
    }

    DeleteBranchModal Button {
        margin-right: 1;
    }
    """

    def __init__(self, branch_name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._branch = branch_name

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="delete-container"):
            yield Label("🗑️ Delete Branch", id="delete-title")
            yield Static(
                f"Delete branch [bold]{escape(self._branch)}[/bold]?\n\n"
                "This cannot be undone."
            )
            with Container(id="delete-buttons"):
                yield Button("Delete", variant="error", id="btn-delete")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel the deletion."""
        self.dismiss(False)


class DiscardChangesModal(ModalScreen[bool]):
    """Modal to confirm discarding changes."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    DEFAULT_CSS = """
    DiscardChangesModal {
        align: center middle;
    }

    DiscardChangesModal #discard-container {
        width: 50%;
        height: auto;
        background: $surface;
        border: solid $error;
        padding: 1 2;
    }

    DiscardChangesModal #discard-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }

    DiscardChangesModal #discard-buttons {
        height: 3;
        margin-top: 1;
    }

    DiscardChangesModal Button {
        margin-right: 1;
    }
    """

    def __init__(self, file_path: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._file = file_path

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        with Container(id="discard-container"):
            yield Label("⚠️ Discard Changes", id="discard-title")
            yield Static(
                f"Discard all changes to [bold]{escape(self._file)}[/bold]?\n\n"
                "This cannot be undone."
            )
            with Container(id="discard-buttons"):
                yield Button("Discard", variant="error", id="btn-discard")
                yield Button("Cancel", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-discard":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_cancel(self) -> None:
        """Cancel the discard."""
        self.dismiss(False)
