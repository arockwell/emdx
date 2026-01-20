"""GitHub PR browser wrapper widget."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widget import Widget

from .github_view import GitHubView

logger = logging.getLogger(__name__)


class GitHubBrowser(Widget):
    """Browser wrapper for GitHub PR view.

    This widget wraps GitHubView and handles mounting/unmounting,
    similar to other browser patterns in the codebase.
    """

    BINDINGS = [
        Binding("q", "back", "Back", show=True),
        Binding("?", "show_help", "Help", show=True),
    ]

    DEFAULT_CSS = """
    GitHubBrowser {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    GitHubBrowser #github-container {
        height: 100%;
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._view: Optional[GitHubView] = None

    def compose(self) -> ComposeResult:
        """Compose the browser."""
        with Container(id="github-container"):
            self._view = GitHubView(id="github-view")
            yield self._view

    def action_back(self) -> None:
        """Go back to previous screen."""
        # This is handled by BrowserContainer
        pass

    def action_show_help(self) -> None:
        """Show help modal."""
        help_text = """
# GitHub PR Browser

## Navigation
- `j/k` - Navigate up/down
- `Enter` - Select PR

## Filters (press to toggle)
- `a` - All PRs
- `m` - My PRs
- `v` - Needs Review
- `d` - Drafts
- `x` - Has Conflicts
- `y` - Ready to Merge

## Actions
- `M` (Shift+M) - Merge PR
- `A` (Shift+A) - Approve PR
- `R` (Shift+R) - Request Changes
- `C` (Shift+C) - Close PR
- `o` - Checkout branch
- `b` - Open in browser
- `e` - View linked EMDX doc
- `r` - Refresh list

## General
- `q` - Go back
- `?` - Show this help
"""
        self.notify(help_text, title="GitHub PR Browser Help", timeout=10)

    def update_status(self, text: str) -> None:
        """Update status bar (delegate to view)."""
        # The view handles its own status
        pass

    def save_state(self) -> dict:
        """Save browser state."""
        if self._view and self._view._presenter:
            state = self._view._presenter.state
            return {
                "filter_mode": state.filter_mode.value,
                "selected_index": state.selected_index,
            }
        return {}

    def restore_state(self, state: dict) -> None:
        """Restore browser state."""
        if self._view and self._view._presenter and state:
            from emdx.services.github_service import FilterMode
            try:
                mode = FilterMode(state.get("filter_mode", "all"))
                self._view._presenter.set_filter_mode(mode)
                index = state.get("selected_index", 0)
                self._view._presenter.select_index(index)
            except (ValueError, KeyError):
                pass

    async def on_github_view_view_document(self, event: GitHubView.ViewDocument) -> None:
        """Handle view document request - bubble up to container."""
        # Bubble the event up
        event.stop()
        self.post_message(event)
