"""Git log view - commit history browser."""

import asyncio
import logging
from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from rich.markup import escape
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from emdx.utils.git_ops import (
    GitCommit,
    get_commit_log,
    get_commit_diff,
    cherry_pick,
    revert_commit,
)

logger = logging.getLogger(__name__)


class CommitListItem(ListItem):
    """A commit item in the log list."""

    def __init__(self, commit: GitCommit, **kwargs) -> None:
        super().__init__(**kwargs)
        self.commit = commit

    def compose(self) -> ComposeResult:
        """Compose the commit item."""
        # Format: hash message (age)
        hash_short = self.commit.hash_short
        message = self.commit.message_subject
        if len(message) > 50:
            message = message[:47] + "..."

        # Calculate relative time
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        commit_time = self.commit.date
        if commit_time.tzinfo is None:
            commit_time = commit_time.replace(tzinfo=timezone.utc)

        delta = now - commit_time
        if delta.days > 0:
            age = f"{delta.days}d"
        elif delta.seconds > 3600:
            age = f"{delta.seconds // 3600}h"
        else:
            age = f"{delta.seconds // 60}m"

        yield Static(
            f"* [bold cyan]{hash_short}[/bold cyan] {escape(message)} [dim]({age})[/dim]",
            classes="commit-item-content"
        )


class LogView(Widget):
    """Git log view with commit history and diff preview."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("y", "copy_hash", "Copy Hash", show=True),
        Binding("p", "cherry_pick", "Cherry-pick", show=True),
        Binding("v", "revert", "Revert", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    LogView {
        layout: horizontal;
        height: 100%;
    }

    LogView #log-commit-list {
        width: 45%;
        height: 100%;
        border-right: solid $primary;
    }

    LogView #log-commit-list ListView {
        height: 100%;
    }

    LogView #log-commit-detail {
        width: 55%;
        height: 100%;
        padding: 1;
        overflow-y: auto;
    }

    LogView .commit-item-content {
        width: 100%;
    }
    """

    def __init__(self, worktree_path: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._worktree_path = worktree_path
        self._commits: List[GitCommit] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        """Compose the view."""
        with Vertical(id="log-commit-list"):
            yield ListView(id="commit-list")
        yield Static("Select a commit to view details", id="log-commit-detail")

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.refresh()

    async def refresh(self) -> None:
        """Refresh the commit list."""
        self._commits = await get_commit_log(limit=50, worktree_path=self._worktree_path)
        self._update_commit_list()
        await self._update_commit_detail()

    def _update_commit_list(self) -> None:
        """Update the commit list widget."""
        list_view = self.query_one("#commit-list", ListView)
        list_view.clear()

        for commit in self._commits:
            list_view.append(CommitListItem(commit))

        # Set selection
        if self._commits and list_view.children:
            list_view.index = min(self._selected_index, len(list_view.children) - 1)

    async def _update_commit_detail(self) -> None:
        """Update the commit detail view."""
        detail = self.query_one("#log-commit-detail", Static)

        selected = self._get_selected_commit()
        if not selected:
            detail.update("Select a commit to view details")
            return

        # Build detail text - escape user content to prevent markup injection
        lines = [
            f"[bold]Commit:[/bold] {escape(selected.hash_full)}",
            f"[bold]Author:[/bold] {escape(selected.author_name)} <{escape(selected.author_email)}>",
            f"[bold]Date:[/bold] {selected.date.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            escape(selected.message_full),
            "",
            f"[dim]{escape(selected.stats_summary)}[/dim]",
            "",
        ]

        # Get diff - escape to prevent any markup-like content from being interpreted
        diff = await get_commit_diff(selected.hash_short, self._worktree_path)
        lines.append(escape(diff))

        detail.update("\n".join(lines))

    def _get_selected_commit(self) -> Optional[GitCommit]:
        """Get the currently selected commit."""
        list_view = self.query_one("#commit-list", ListView)
        if list_view.index is not None and list_view.highlighted_child:
            item = list_view.highlighted_child
            if isinstance(item, CommitListItem):
                return item.commit
        return None

    @on(ListView.Highlighted)
    async def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle commit highlight change."""
        if isinstance(event.item, CommitListItem):
            await self._update_commit_detail()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_view = self.query_one("#commit-list", ListView)
        if list_view.index is not None and list_view.index < len(list_view.children) - 1:
            list_view.index += 1
            self._selected_index = list_view.index

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_view = self.query_one("#commit-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1
            self._selected_index = list_view.index

    def action_copy_hash(self) -> None:
        """Copy commit hash to clipboard."""
        selected = self._get_selected_commit()
        if selected:
            import pyperclip
            try:
                pyperclip.copy(selected.hash_full)
                self.notify(f"Copied {selected.hash_short}")
            except Exception:
                self.notify(f"Hash: {selected.hash_short}", timeout=5)

    async def action_cherry_pick(self) -> None:
        """Cherry-pick selected commit."""
        selected = self._get_selected_commit()
        if selected:
            success, message = await cherry_pick(selected.hash_short, self._worktree_path)
            if success:
                self.notify(message)
                await self.refresh()
            else:
                self.notify(message, severity="error")

    async def action_revert(self) -> None:
        """Revert selected commit."""
        selected = self._get_selected_commit()
        if selected:
            success, message = await revert_commit(selected.hash_short, self._worktree_path)
            if success:
                self.notify(message)
                await self.refresh()
            else:
                self.notify(message, severity="error")

    async def action_refresh(self) -> None:
        """Refresh the view."""
        await self.refresh()
