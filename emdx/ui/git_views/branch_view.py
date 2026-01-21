"""Git branch view - branch management."""

import asyncio
import logging
from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from rich.markup import escape
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static

from emdx.utils.git_ops import (
    GitBranch,
    list_branches,
    switch_branch,
    create_branch,
    delete_branch,
    merge_branch,
    git_fetch,
    git_pull,
    git_push,
)

logger = logging.getLogger(__name__)


class BranchListItem(ListItem):
    """A branch item in the list."""

    def __init__(self, branch: GitBranch, **kwargs) -> None:
        super().__init__(**kwargs)
        self.branch = branch

    def compose(self) -> ComposeResult:
        """Compose the branch item."""
        # Current branch marker
        current = "* " if self.branch.is_current else "  "

        # Name
        name = self.branch.name

        # Tracking status
        tracking = ""
        if not self.branch.is_remote:
            if self.branch.tracking_branch:
                ahead, behind = self.branch.ahead_behind
                if ahead or behind:
                    parts = []
                    if ahead:
                        parts.append(f"↑{ahead}")
                    if behind:
                        parts.append(f"↓{behind}")
                    tracking = f" [{' '.join(parts)}]"
            else:
                tracking = " [no upstream]"

        # Remote indicator
        remote_icon = "🌐 " if self.branch.is_remote else ""

        yield Static(
            f"{current}{remote_icon}[bold]{escape(name)}[/bold]{escape(tracking)}",
            classes="branch-item-content"
        )


class BranchView(Widget):
    """Git branch view with local and remote branches."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("enter", "switch", "Switch", show=True),
        Binding("n", "new_branch", "New", show=True),
        Binding("d", "delete_branch", "Delete", show=True),
        Binding("m", "merge", "Merge", show=True),
        Binding("f", "fetch", "Fetch", show=True),
        Binding("shift+p", "push", "Push", show=True),
        Binding("shift+l", "pull", "Pull", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    BranchView {
        layout: horizontal;
        height: 100%;
    }

    BranchView #branch-local-list {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
    }

    BranchView #branch-remote-list {
        width: 50%;
        height: 100%;
    }

    BranchView ListView {
        height: 100%;
    }

    BranchView .branch-item-content {
        width: 100%;
    }

    BranchView .section-header {
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }
    """

    class BranchCreated(Message):
        """Branch was created."""

        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, worktree_path: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._worktree_path = worktree_path
        self._local_branches: List[GitBranch] = []
        self._remote_branches: List[GitBranch] = []
        self._selected_index: int = 0
        self._focus_local: bool = True  # Which list has focus

    def compose(self) -> ComposeResult:
        """Compose the view."""
        with Vertical(id="branch-local-list"):
            yield Label("Local Branches", classes="section-header")
            yield ListView(id="local-list")
        with Vertical(id="branch-remote-list"):
            yield Label("Remote Branches", classes="section-header")
            yield ListView(id="remote-list")

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.refresh()

    async def refresh(self) -> None:
        """Refresh the branch lists."""
        branches = await list_branches(self._worktree_path)

        self._local_branches = [b for b in branches if not b.is_remote]
        self._remote_branches = [b for b in branches if b.is_remote]

        self._update_branch_lists()

    def _update_branch_lists(self) -> None:
        """Update the branch list widgets."""
        # Local branches
        local_list = self.query_one("#local-list", ListView)
        local_list.clear()
        for branch in self._local_branches:
            local_list.append(BranchListItem(branch))

        # Remote branches
        remote_list = self.query_one("#remote-list", ListView)
        remote_list.clear()
        for branch in self._remote_branches:
            remote_list.append(BranchListItem(branch))

        # Set selection
        if self._local_branches and local_list.children:
            local_list.index = min(self._selected_index, len(local_list.children) - 1)

    def _get_selected_branch(self) -> Optional[GitBranch]:
        """Get the currently selected branch."""
        if self._focus_local:
            list_view = self.query_one("#local-list", ListView)
        else:
            list_view = self.query_one("#remote-list", ListView)

        if list_view.index is not None and list_view.highlighted_child:
            item = list_view.highlighted_child
            if isinstance(item, BranchListItem):
                return item.branch
        return None

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_view = self.query_one("#local-list" if self._focus_local else "#remote-list", ListView)
        if list_view.index is not None and list_view.index < len(list_view.children) - 1:
            list_view.index += 1
            self._selected_index = list_view.index

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_view = self.query_one("#local-list" if self._focus_local else "#remote-list", ListView)
        if list_view.index is not None and list_view.index > 0:
            list_view.index -= 1
            self._selected_index = list_view.index

    async def action_switch(self) -> None:
        """Switch to selected branch."""
        selected = self._get_selected_branch()
        if selected and not selected.is_current:
            branch_name = selected.name
            # For remote branches, strip the remote prefix
            if selected.is_remote and "/" in branch_name:
                branch_name = branch_name.split("/", 1)[1]

            success = await switch_branch(branch_name, self._worktree_path)
            if success:
                self.notify(f"Switched to {branch_name}")
                await self.refresh()
            else:
                self.notify(f"Failed to switch to {branch_name}", severity="error")

    async def action_new_branch(self) -> None:
        """Create a new branch."""
        # For simplicity, prompt via notify. In a real app, use a modal.
        self.notify("Use 'git branch <name>' to create a branch", timeout=5)

    async def action_delete_branch(self) -> None:
        """Delete selected branch."""
        selected = self._get_selected_branch()
        if selected and not selected.is_current and not selected.is_remote:
            success = await delete_branch(selected.name, worktree_path=self._worktree_path)
            if success:
                self.notify(f"Deleted branch {selected.name}")
                await self.refresh()
            else:
                self.notify(f"Failed to delete {selected.name}", severity="error")
        elif selected and selected.is_current:
            self.notify("Cannot delete current branch", severity="warning")

    async def action_merge(self) -> None:
        """Merge selected branch into current."""
        selected = self._get_selected_branch()
        if selected and not selected.is_current:
            success, message = await merge_branch(selected.name, self._worktree_path)
            if success:
                self.notify(f"Merged {selected.name}")
                await self.refresh()
            else:
                self.notify(message, severity="error")

    async def action_fetch(self) -> None:
        """Fetch from remote."""
        self.notify("Fetching...")
        success, message = await git_fetch(worktree_path=self._worktree_path)
        if success:
            self.notify("Fetch complete")
            await self.refresh()
        else:
            self.notify(message, severity="error")

    async def action_push(self) -> None:
        """Push current branch to remote."""
        self.notify("Pushing...")
        success, message = await git_push(worktree_path=self._worktree_path)
        if success:
            self.notify("Push complete")
            await self.refresh()
        else:
            self.notify(message, severity="error")

    async def action_pull(self) -> None:
        """Pull from remote."""
        self.notify("Pulling...")
        success, message = await git_pull(worktree_path=self._worktree_path)
        if success:
            self.notify("Pull complete")
            await self.refresh()
        else:
            self.notify(message, severity="error")

    async def action_refresh(self) -> None:
        """Refresh the view."""
        await self.refresh()
