"""Git stash view - stash management."""

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
    GitStash,
    list_stashes,
    create_stash,
    apply_stash,
    pop_stash,
    drop_stash,
)

logger = logging.getLogger(__name__)


class StashListItem(ListItem):
    """A stash item in the list."""

    def __init__(self, stash: GitStash, **kwargs) -> None:
        super().__init__(**kwargs)
        self.stash = stash

    def compose(self) -> ComposeResult:
        """Compose the stash item."""
        # Format: stash@{n}: message (age)
        message = self.stash.message
        if len(message) > 50:
            message = message[:47] + "..."

        # Calculate relative time
        age = ""
        if self.stash.date:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            stash_time = self.stash.date
            if stash_time.tzinfo is None:
                stash_time = stash_time.replace(tzinfo=timezone.utc)

            delta = now - stash_time
            if delta.days > 0:
                age = f" ({delta.days}d ago)"
            elif delta.seconds > 3600:
                age = f" ({delta.seconds // 3600}h ago)"
            else:
                age = f" ({delta.seconds // 60}m ago)"

        yield Static(
            f"[bold]stash@{{{self.stash.index}}}[/bold]: {escape(message)}[dim]{age}[/dim]",
            classes="stash-item-content"
        )


class StashView(Widget):
    """Git stash view with stash list and preview."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("a", "apply_stash", "Apply", show=True),
        Binding("p", "pop_stash", "Pop", show=True),
        Binding("d", "drop_stash", "Drop", show=True),
        Binding("n", "new_stash", "New Stash", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    StashView {
        layout: horizontal;
        height: 100%;
    }

    StashView #stash-list-container {
        width: 45%;
        height: 100%;
        border-right: solid $primary;
    }

    StashView #stash-list-container ListView {
        height: 100%;
    }

    StashView #stash-preview {
        width: 55%;
        height: 100%;
        padding: 1;
        overflow-y: auto;
    }

    StashView .stash-item-content {
        width: 100%;
    }
    """

    def __init__(self, worktree_path: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._worktree_path = worktree_path
        self._stashes: List[GitStash] = []
        self._selected_index: int = 0

    def compose(self) -> ComposeResult:
        """Compose the view."""
        with Vertical(id="stash-list-container"):
            yield ListView(id="stash-list")
        yield Static("Select a stash to view files", id="stash-preview")

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.refresh()

    async def refresh(self) -> None:
        """Refresh the stash list."""
        self._stashes = await list_stashes(self._worktree_path)
        self._update_stash_list()
        self._update_stash_preview()

    def _update_stash_list(self) -> None:
        """Update the stash list widget."""
        list_view = self.query_one("#stash-list", ListView)
        list_view.clear()

        if not self._stashes:
            list_view.append(ListItem(Static("[dim]No stashes[/dim]")))
        else:
            for stash in self._stashes:
                list_view.append(StashListItem(stash))

            # Set selection
            if list_view.children:
                list_view.index = min(self._selected_index, len(list_view.children) - 1)

    def _update_stash_preview(self) -> None:
        """Update the stash preview."""
        preview = self.query_one("#stash-preview", Static)

        selected = self._get_selected_stash()
        if not selected:
            preview.update("Select a stash to view files")
            return

        # Build preview - escape user content to prevent markup injection
        lines = [
            f"[bold]Stash:[/bold] stash@{{{selected.index}}}",
            f"[bold]Message:[/bold] {escape(selected.message)}",
        ]

        if selected.branch:
            lines.append(f"[bold]Branch:[/bold] {escape(selected.branch)}")

        if selected.date:
            lines.append(f"[bold]Date:[/bold] {selected.date.strftime('%Y-%m-%d %H:%M:%S')}")

        lines.append("")
        lines.append("[bold]Files:[/bold]")

        if selected.files_changed:
            for f in selected.files_changed:
                lines.append(f"  • {escape(f)}")
        else:
            lines.append("  [dim]No file information available[/dim]")

        preview.update("\n".join(lines))

    def _get_selected_stash(self) -> Optional[GitStash]:
        """Get the currently selected stash."""
        list_view = self.query_one("#stash-list", ListView)
        if list_view.index is not None and list_view.highlighted_child:
            item = list_view.highlighted_child
            if isinstance(item, StashListItem):
                return item.stash
        return None

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle stash highlight change."""
        if isinstance(event.item, StashListItem):
            self._update_stash_preview()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_view = self.query_one("#stash-list", ListView)
        if list_view.index is not None and list_view.index < len(list_view.children) - 1:
            list_view.index += 1
            self._selected_index = list_view.index

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_view = self.query_one("#stash-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1
            self._selected_index = list_view.index

    async def action_apply_stash(self) -> None:
        """Apply selected stash."""
        selected = self._get_selected_stash()
        if selected:
            success, message = await apply_stash(selected.index, self._worktree_path)
            if success:
                self.notify(message)
            else:
                self.notify(message, severity="error")

    async def action_pop_stash(self) -> None:
        """Pop selected stash."""
        selected = self._get_selected_stash()
        if selected:
            success, message = await pop_stash(selected.index, self._worktree_path)
            if success:
                self.notify(message)
                await self.refresh()
            else:
                self.notify(message, severity="error")

    async def action_drop_stash(self) -> None:
        """Drop selected stash."""
        selected = self._get_selected_stash()
        if selected:
            success = await drop_stash(selected.index, self._worktree_path)
            if success:
                self.notify(f"Dropped stash@{{{selected.index}}}")
                await self.refresh()
            else:
                self.notify("Failed to drop stash", severity="error")

    async def action_new_stash(self) -> None:
        """Create a new stash."""
        success = await create_stash(worktree_path=self._worktree_path)
        if success:
            self.notify("Created new stash")
            await self.refresh()
        else:
            self.notify("Failed to create stash (no changes?)", severity="warning")

    async def action_refresh(self) -> None:
        """Refresh the view."""
        await self.refresh()
