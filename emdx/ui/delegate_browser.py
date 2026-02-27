"""Delegate Browser — wraps DelegateView for the browser container."""

import logging
from typing import Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from .delegate_view import DelegateView

logger = logging.getLogger(__name__)


class DelegateBrowser(Widget):
    """Browser wrapper for DelegateView."""

    BINDINGS = [
        ("question_mark", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    DelegateBrowser {
        layout: vertical;
        height: 100%;
    }

    #delegate-view {
        height: 1fr;
    }

    #delegate-help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.delegate_view: DelegateView | None = None

    def compose(self) -> ComposeResult:
        self.delegate_view = DelegateView(id="delegate-view")
        yield self.delegate_view
        yield Static(
            "[dim]1[/dim] Docs  [dim]2[/dim] Tasks  [bold]3[/bold] Delegates  "
            "[dim]j/k[/dim] Navigate  "
            "[dim]z[/dim] Zoom  "
            "[dim]r[/dim] Refresh",
            id="delegate-help-bar",
        )

    def update_status(self, text: str) -> None:
        """Update status — for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> Self:
        """Focus the table inside the delegate view."""
        if self.delegate_view:
            try:
                table = self.delegate_view.query_one("#delegate-table")
                table.focus()
            except Exception:
                logger.warning("DelegateBrowser.focus: #delegate-table not found")
        return self
