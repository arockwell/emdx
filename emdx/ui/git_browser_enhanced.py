"""Enhanced Git Browser with Tab-switchable view modes."""

import asyncio
import logging
from enum import Enum
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Label, Static, TabbedContent, TabPane

from emdx.utils.git_ops import get_current_branch, is_git_repository
from .git_views import StatusView, LogView, BranchView, StashView

logger = logging.getLogger(__name__)


class GitViewMode(Enum):
    """Git browser view modes."""

    STATUS = "status"
    LOG = "log"
    BRANCH = "branch"
    STASH = "stash"


class GitBrowserEnhanced(Widget):
    """Enhanced Git Browser with multiple view modes.

    Provides Tab-switchable modes:
    - Status: File staging with diff preview
    - Log: Commit history browser
    - Branch: Branch management
    - Stash: Stash management
    """

    BINDINGS = [
        Binding("tab", "next_mode", "Next Mode", show=True),
        Binding("shift+tab", "prev_mode", "Prev Mode", show=True),
        Binding("c", "commit", "Commit", show=True),
        Binding("w", "switch_worktree", "Worktree", show=True),
        Binding("q", "back", "Back", show=True),
        Binding("?", "show_help", "Help", show=True),
    ]

    DEFAULT_CSS = """
    GitBrowserEnhanced {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    GitBrowserEnhanced #git-mode-bar {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    GitBrowserEnhanced #git-mode-bar Button {
        min-width: 10;
        margin-right: 1;
    }

    GitBrowserEnhanced #git-mode-bar Button.active {
        background: $primary;
    }

    GitBrowserEnhanced #git-view-container {
        height: 1fr;
    }

    GitBrowserEnhanced #git-status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    current_mode: reactive[GitViewMode] = reactive(GitViewMode.STATUS)

    def __init__(self, worktree_path: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._worktree_path = worktree_path
        self._views: dict[GitViewMode, Widget] = {}
        self._current_view: Optional[Widget] = None
        self._is_git_repo = False

    def compose(self) -> ComposeResult:
        """Compose the browser."""
        # Mode selector bar
        with Horizontal(id="git-mode-bar"):
            yield Button("Status", id="mode-status", classes="active")
            yield Button("Log", id="mode-log")
            yield Button("Branch", id="mode-branch")
            yield Button("Stash", id="mode-stash")

        # View container
        yield Container(id="git-view-container")

        # Status bar
        yield Static("Loading...", id="git-status-bar")

    async def on_mount(self) -> None:
        """Initialize on mount."""
        # Check if we're in a git repo
        self._is_git_repo = is_git_repository(self._worktree_path)

        if not self._is_git_repo:
            status = self.query_one("#git-status-bar", Static)
            status.update("Not a git repository")
            container = self.query_one("#git-view-container", Container)
            await container.mount(Static("Not in a git repository"))
            return

        # Update status bar
        await self._update_status_bar()

        # Create and mount initial view
        await self._switch_to_mode(GitViewMode.STATUS)

    async def _update_status_bar(self) -> None:
        """Update the status bar with current git info."""
        status = self.query_one("#git-status-bar", Static)

        if not self._is_git_repo:
            status.update("Not a git repository")
            return

        branch = get_current_branch(self._worktree_path)

        # Get basic status counts
        from emdx.utils.git_ops import get_git_status
        files = get_git_status(self._worktree_path)
        staged = sum(1 for f in files if f.staged)
        modified = sum(1 for f in files if not f.staged and f.status != '?')
        untracked = sum(1 for f in files if f.status == '?')

        from rich.markup import escape
        parts = [f"[bold]{escape(branch)}[/]"]
        if staged:
            parts.append(f"[green]{staged} staged[/]")
        if modified:
            parts.append(f"[yellow]{modified} modified[/]")
        if untracked:
            parts.append(f"[dim]{untracked} untracked[/dim]")

        status.update(" | ".join(parts))

    async def _switch_to_mode(self, mode: GitViewMode) -> None:
        """Switch to a different view mode."""
        container = self.query_one("#git-view-container", Container)

        # Remove current view
        if self._current_view:
            await container.remove_children()

        # Update mode buttons
        for m in GitViewMode:
            btn = self.query_one(f"#mode-{m.value}", Button)
            if m == mode:
                btn.add_class("active")
            else:
                btn.remove_class("active")

        # Create view if not cached
        if mode not in self._views:
            if mode == GitViewMode.STATUS:
                self._views[mode] = StatusView(worktree_path=self._worktree_path)
            elif mode == GitViewMode.LOG:
                self._views[mode] = LogView(worktree_path=self._worktree_path)
            elif mode == GitViewMode.BRANCH:
                self._views[mode] = BranchView(worktree_path=self._worktree_path)
            elif mode == GitViewMode.STASH:
                self._views[mode] = StashView(worktree_path=self._worktree_path)

        # Mount the view
        self._current_view = self._views[mode]
        await container.mount(self._current_view)

        self.current_mode = mode

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle mode button press."""
        btn_id = event.button.id
        if btn_id and btn_id.startswith("mode-"):
            mode_str = btn_id.replace("mode-", "")
            try:
                mode = GitViewMode(mode_str)
                asyncio.create_task(self._switch_to_mode(mode))
            except ValueError:
                pass

    def action_next_mode(self) -> None:
        """Switch to next mode."""
        modes = list(GitViewMode)
        current_idx = modes.index(self.current_mode)
        next_idx = (current_idx + 1) % len(modes)
        asyncio.create_task(self._switch_to_mode(modes[next_idx]))

    def action_prev_mode(self) -> None:
        """Switch to previous mode."""
        modes = list(GitViewMode)
        current_idx = modes.index(self.current_mode)
        prev_idx = (current_idx - 1) % len(modes)
        asyncio.create_task(self._switch_to_mode(modes[prev_idx]))

    def action_commit(self) -> None:
        """Open commit dialog."""
        # For now, just show a notification
        self.notify("Use 'git commit' in terminal to commit staged changes", timeout=5)

    def action_switch_worktree(self) -> None:
        """Switch to a different worktree."""
        # This would open a worktree picker modal
        self.notify("Worktree switching coming soon", timeout=3)

    def action_back(self) -> None:
        """Go back to previous screen."""
        # This is handled by BrowserContainer
        pass

    def action_show_help(self) -> None:
        """Show help."""
        help_text = f"""
# Enhanced Git Browser

## Current Mode: {self.current_mode.value.title()}

## Mode Switching
- `Tab` - Next mode (Status → Log → Branch → Stash)
- `Shift+Tab` - Previous mode

## Global Keys
- `c` - Commit (opens commit dialog)
- `w` - Switch worktree
- `q` - Go back
- `?` - Show this help

## Status Mode
- `j/k` - Navigate files
- `a` - Stage file
- `u` - Unstage file
- `A` (Shift+A) - Stage all
- `R` (Shift+R) - Discard changes

## Log Mode
- `j/k` - Navigate commits
- `y` - Copy commit hash
- `p` - Cherry-pick commit
- `v` - Revert commit

## Branch Mode
- `j/k` - Navigate branches
- `Enter` - Switch to branch
- `n` - New branch
- `d` - Delete branch
- `m` - Merge branch
- `f` - Fetch
- `P` (Shift+P) - Push
- `L` (Shift+L) - Pull

## Stash Mode
- `j/k` - Navigate stashes
- `a` - Apply stash
- `p` - Pop stash
- `d` - Drop stash
- `n` - New stash
"""
        self.notify(help_text, title="Git Browser Help", timeout=15)

    def update_status(self, text: str) -> None:
        """Update status bar."""
        pass  # Use internal status bar

    def save_state(self) -> dict:
        """Save browser state."""
        return {
            "mode": self.current_mode.value,
        }

    def restore_state(self, state: dict) -> None:
        """Restore browser state."""
        if state and "mode" in state:
            try:
                mode = GitViewMode(state["mode"])
                asyncio.create_task(self._switch_to_mode(mode))
            except ValueError:
                pass
