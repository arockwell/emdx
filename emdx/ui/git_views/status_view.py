"""Git status view - file staging with grouping and diff preview."""

import asyncio
import logging
from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from rich.markup import escape
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from emdx.utils.git_ops import (
    GitFileStatus,
    get_git_status,
    get_comprehensive_git_diff,
    git_stage_file,
    git_unstage_file,
    git_discard_changes,
)

logger = logging.getLogger(__name__)


class FileListItem(ListItem):
    """A file item in the status list."""

    def __init__(self, file_status: GitFileStatus, **kwargs) -> None:
        super().__init__(**kwargs)
        self.file_status = file_status

    def compose(self) -> ComposeResult:
        """Compose the file item."""
        icon = self.file_status.status_icon
        status = self.file_status.status
        path = self.file_status.path
        staged_marker = "📦" if self.file_status.staged else "  "

        # Escape brackets to prevent markup interpretation
        yield Static(
            f"{staged_marker} {icon} \\[{status}] {escape(path)}",
            classes="file-item-content"
        )


class StatusView(Widget):
    """Git status view with file grouping and diff preview."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("a", "stage", "Stage", show=True),
        Binding("u", "unstage", "Unstage", show=True),
        Binding("shift+a", "stage_all", "Stage All", show=True),
        Binding("shift+r", "discard", "Discard", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    StatusView {
        layout: horizontal;
        height: 100%;
    }

    StatusView #status-file-list {
        width: 45%;
        height: 100%;
        border-right: solid $primary;
    }

    StatusView #status-file-list ListView {
        height: 100%;
    }

    StatusView #status-diff-preview {
        width: 55%;
        height: 100%;
        padding: 1;
        overflow-y: auto;
    }

    StatusView .file-item-content {
        width: 100%;
    }

    StatusView .section-header {
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }
    """

    class CommitRequested(Message):
        """Request to open commit dialog."""
        pass

    def __init__(self, worktree_path: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._worktree_path = worktree_path
        self._files: List[GitFileStatus] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        """Compose the view."""
        with Vertical(id="status-file-list"):
            yield ListView(id="file-list")
        yield Static("Select a file to view diff", id="status-diff-preview")

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.refresh()

    async def refresh(self) -> None:
        """Refresh the file list."""
        self._files = get_git_status(self._worktree_path)
        self._update_file_list()
        await self._update_diff_preview()

    def _update_file_list(self) -> None:
        """Update the file list widget."""
        list_view = self.query_one("#file-list", ListView)
        list_view.clear()

        # Group files by status
        staged = [f for f in self._files if f.staged]
        modified = [f for f in self._files if not f.staged and f.status != '?']
        untracked = [f for f in self._files if f.status == '?']

        # Add sections
        if staged:
            list_view.append(ListItem(Static(f"── Staged ({len(staged)}) ──", classes="section-header")))
            for f in staged:
                list_view.append(FileListItem(f))

        if modified:
            list_view.append(ListItem(Static(f"── Modified ({len(modified)}) ──", classes="section-header")))
            for f in modified:
                list_view.append(FileListItem(f))

        if untracked:
            list_view.append(ListItem(Static(f"── Untracked ({len(untracked)}) ──", classes="section-header")))
            for f in untracked:
                list_view.append(FileListItem(f))

        # Set selection
        if self._files and list_view.children:
            list_view.index = min(self._selected_index, len(list_view.children) - 1)

    async def _update_diff_preview(self) -> None:
        """Update the diff preview for selected file."""
        preview = self.query_one("#status-diff-preview", Static)

        selected_file = self._get_selected_file()
        if not selected_file:
            preview.update("Select a file to view diff")
            return

        # Get diff in background
        loop = asyncio.get_event_loop()
        diff = await loop.run_in_executor(
            None,
            get_comprehensive_git_diff,
            selected_file.path,
            self._worktree_path
        )
        # Escape diff content to prevent markup interpretation
        preview.update(escape(diff))

    def _get_selected_file(self) -> Optional[GitFileStatus]:
        """Get the currently selected file."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None and list_view.highlighted_child:
            item = list_view.highlighted_child
            if isinstance(item, FileListItem):
                return item.file_status
        return None

    @on(ListView.Selected)
    async def on_list_selected(self, event: ListView.Selected) -> None:
        """Handle file selection."""
        if isinstance(event.item, FileListItem):
            await self._update_diff_preview()

    @on(ListView.Highlighted)
    async def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle file highlight change."""
        if isinstance(event.item, FileListItem):
            await self._update_diff_preview()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None and list_view.index < len(list_view.children) - 1:
            list_view.index += 1
            self._selected_index = list_view.index

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_view = self.query_one("#file-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1
            self._selected_index = list_view.index

    async def action_stage(self) -> None:
        """Stage selected file."""
        selected = self._get_selected_file()
        if selected and not selected.staged:
            success = git_stage_file(selected.path, self._worktree_path)
            if success:
                await self.refresh()
                self.notify(f"Staged {selected.path}")
            else:
                self.notify(f"Failed to stage {selected.path}", severity="error")

    async def action_unstage(self) -> None:
        """Unstage selected file."""
        selected = self._get_selected_file()
        if selected and selected.staged:
            success = git_unstage_file(selected.path, self._worktree_path)
            if success:
                await self.refresh()
                self.notify(f"Unstaged {selected.path}")
            else:
                self.notify(f"Failed to unstage {selected.path}", severity="error")

    async def action_stage_all(self) -> None:
        """Stage all files."""
        for f in self._files:
            if not f.staged:
                git_stage_file(f.path, self._worktree_path)
        await self.refresh()
        self.notify("Staged all files")

    async def action_discard(self) -> None:
        """Discard changes to selected file."""
        selected = self._get_selected_file()
        if selected:
            success = git_discard_changes(selected.path, self._worktree_path)
            if success:
                await self.refresh()
                self.notify(f"Discarded changes to {selected.path}")
            else:
                self.notify(f"Failed to discard changes", severity="error")

    async def action_refresh(self) -> None:
        """Refresh the view."""
        await self.refresh()
