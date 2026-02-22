"""Task Browser — wraps TaskView for the browser container."""

import logging
from typing import Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from .modals import HelpMixin
from .task_view import TaskView

logger = logging.getLogger(__name__)


class TaskBrowser(HelpMixin, Widget):
    """Browser wrapper for TaskView."""

    HELP_TITLE = "Task Browser"
    HELP_CATEGORIES = {
        "mark_done": "Actions",
        "mark_active": "Actions",
        "mark_blocked": "Actions",
    }

    BINDINGS = [
        ("question_mark", "show_help", "Help"),
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
            "[dim]1[/dim] Activity │ [bold]2[/bold] Tasks │ [dim]3[/dim] Q&A │ "
            "[dim]j/k[/dim] nav │ [dim]/[/dim] filter │ "
            "[dim]o[/dim] ready [dim]i[/dim] active [dim]x[/dim] blocked "
            "[dim]f[/dim] done [dim]*[/dim] all │ "
            "[dim]d[/dim] done │ [dim]a[/dim] active │ "
            "[dim]r[/dim] refresh │ [dim]?[/dim] help",
            id="task-help-bar",
        )

    def get_help_bindings(self) -> list[tuple[str, str, str]]:
        """Combine TaskBrowser + TaskView bindings for help display."""
        # Gather bindings from TaskView as well
        task_view_bindings = []
        if self.task_view:
            raw = getattr(self.task_view, "BINDINGS", [])
            categories = {**self._DEFAULT_CATEGORIES, **self.HELP_CATEGORIES}
            for binding in raw:
                if hasattr(binding, "key"):
                    key, action, desc = binding.key, binding.action, binding.description
                    show = getattr(binding, "show", True)
                else:
                    key, action, desc = binding[:3]
                    show = True
                if not show or action in ("close", "cancel"):
                    continue
                display_key = self._KEY_DISPLAY.get(key, key)
                category = categories.get(action, "Other")
                task_view_bindings.append((category, display_key, desc))

        # Get our own bindings via the mixin
        own_bindings = super().get_help_bindings()

        # Merge, dedup by key
        seen_keys: set[str] = set()
        merged = []
        for b in task_view_bindings + own_bindings:
            if b[1] not in seen_keys:
                seen_keys.add(b[1])
                merged.append(b)

        # Sort
        category_order = [
            "Navigation",
            "Actions",
            "View",
            "Other",
            "General",
        ]

        def sort_key(item: tuple[str, str, str]) -> tuple[int, str]:
            try:
                return (category_order.index(item[0]), item[1])
            except ValueError:
                return (len(category_order), item[1])

        merged.sort(key=sort_key)
        return merged

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
