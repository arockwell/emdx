"""Activity Browser - wraps ActivityView for the browser container."""

import logging
from typing import Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from .activity.activity_view import ActivityView

logger = logging.getLogger(__name__)


class ActivityBrowser(Widget):
    """Browser wrapper for ActivityView - Mission Control."""

    BINDINGS = [
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

    def __init__(self) -> None:
        super().__init__()
        self.activity_view: ActivityView | None = None

    def compose(self) -> ComposeResult:
        self.activity_view = ActivityView(id="activity-view")
        yield self.activity_view
        yield Static(
            "[dim]j/k[/dim] Navigate  "
            "[dim]Enter[/dim] Open  "
            "[dim]/[/dim] Filter  "
            "[dim]?[/dim] Help",
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

    def action_show_help(self) -> None:
        """Show help."""
        # Could show a help modal here
        pass

    def update_status(self, text: str) -> None:
        """Update status - for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> Self:
        """Focus the activity view."""
        if self.activity_view:
            try:
                table = self.activity_view.query_one("#activity-table")
                if table:
                    table.focus()
            except Exception:
                # Widget not mounted yet, will focus on mount
                pass
        return self

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select and show a document by its ID in the activity view."""
        if self.activity_view:
            return await self.activity_view.select_document_by_id(doc_id)
        return False
