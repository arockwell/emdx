"""Activity Browser - wraps ActivityView for the browser container."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from .activity.activity_view import ActivityView

logger = logging.getLogger(__name__)


class ActivityBrowser(Widget):
    """Browser wrapper for ActivityView - Mission Control."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_cascade", "Cascade"),
        ("3", "switch_search", "Search"),
        ("4", "switch_documents", "Documents"),
        ("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    ActivityBrowser {
        layout: vertical;
        height: 100%;
    }

    #activity-view {
        height: 1fr;
    }

    #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.activity_view: Optional[ActivityView] = None

    def compose(self) -> ComposeResult:
        self.activity_view = ActivityView(id="activity-view")
        yield self.activity_view
        yield Static(
            "[bold]1[/bold] Activity │ [dim]2[/dim] Cascade │ [dim]3[/dim] Search │ [dim]4[/dim] Docs │ "
            "[dim]j/k[/dim] nav │ [dim]Enter[/dim] expand │ [dim]?[/dim] help",
            id="help-bar",
        )

    def on_activity_view_view_document(self, event: ActivityView.ViewDocument) -> None:
        """Handle request to view document fullscreen."""
        # Forward to parent app for document viewing
        if hasattr(self.app, "view_document_fullscreen"):
            self.app.view_document_fullscreen(event.doc_id)
        else:
            # Fallback: switch to document browser and select the doc
            logger.info(f"Would view document #{event.doc_id}")

    async def action_switch_activity(self) -> None:
        """Already on activity, do nothing."""
        pass

    async def action_switch_cascade(self) -> None:
        """Switch to cascade browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("cascade")

    async def action_switch_documents(self) -> None:
        """Switch to document browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")

    async def action_switch_search(self) -> None:
        """Switch to search screen."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("search")

    def action_show_help(self) -> None:
        """Show help."""
        # Could show a help modal here
        pass

    def update_status(self, text: str) -> None:
        """Update status - for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the activity view."""
        if self.activity_view:
            try:
                tree = self.activity_view.query_one("#activity-tree")
                if tree:
                    tree.focus()
            except Exception:
                # Widget not mounted yet, will focus on mount
                pass

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select and show a document by its ID in the activity view."""
        if self.activity_view:
            return await self.activity_view.select_document_by_id(doc_id)
        return False
