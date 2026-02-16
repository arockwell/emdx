"""Task Browser — wraps TaskView for the browser container."""

import logging
from typing import Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from .task_view import TaskView

logger = logging.getLogger(__name__)


class TaskBrowser(Widget):
    """Browser wrapper for TaskView."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_tasks", "Tasks"),
        ("3", "switch_search", "Search"),
        ("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    TaskBrowser {
        layout: vertical;
        height: 100%;
    }

    #task-view {
        height: 1fr;
    }

    #task-help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.task_view: TaskView | None = None

    def compose(self) -> ComposeResult:
        self.task_view = TaskView(id="task-view")
        yield self.task_view
        yield Static(
            "[dim]1[/dim] Activity │ [bold]2[/bold] Tasks │ "
            "[dim]3[/dim] Search │ [dim]4[/dim] Cascade │ "
            "[dim]j/k[/dim] nav │ [dim]r[/dim] refresh │ [dim]?[/dim] help",
            id="task-help-bar",
        )

    async def action_switch_activity(self) -> None:
        """Switch to activity browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    async def action_switch_search(self) -> None:
        """Switch to search screen."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("search")

    async def action_switch_tasks(self) -> None:
        """Already on tasks, do nothing."""
        pass

    def action_show_help(self) -> None:
        """Show help."""
        pass

    def update_status(self, text: str) -> None:
        """Update status — for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> Self:
        """Focus the task view."""
        if self.task_view:
            try:
                option_list = self.task_view.query_one("#task-option-list")
                if option_list:
                    option_list.focus()
            except Exception:
                pass
        return self

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Stub for compatibility — tasks don't select by doc ID."""
        return False
