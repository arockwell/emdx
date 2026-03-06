"""Task Browser — wraps TaskView for the browser container."""

import logging
from typing import Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Static

from .modals import HelpMixin
from .task_view import DONE_FOLD_PREFIX, HEADER_PREFIX, SEPARATOR_PREFIX, TaskView

logger = logging.getLogger(__name__)

# -- Footer key definitions per context --

_TASK_FOOTER = (
    "[dim]j/k[/dim] Navigate  "
    "[dim]d[/dim] Done  [dim]a[/dim] Active  "
    "[dim]b[/dim] Blocked  [dim]w[/dim] Won't do  "
    "[dim]/[/dim] Filter  [dim]?[/dim] Help"
)

_EPIC_HEADER_FOOTER = (
    "[dim]Enter[/dim] Expand/Collapse  "
    "[dim]e[/dim] Epic Filter  "
    "[dim]g[/dim] Group By  "
    "[dim]/[/dim] Filter  [dim]?[/dim] Help"
)

_DONE_FOLD_FOOTER = "[dim]Enter[/dim] Expand  [dim]/[/dim] Filter  [dim]?[/dim] Help"

_DEFAULT_FOOTER = "[dim]j/k[/dim] Navigate  [dim]/[/dim] Filter  [dim]?[/dim] Help"


class TaskBrowser(HelpMixin, Widget):
    """Browser wrapper for TaskView."""

    HELP_TITLE = "Task Browser"
    HELP_CATEGORIES = {
        "mark_done": "Actions",
        "mark_active": "Actions",
        "mark_blocked": "Actions",
        "mark_wontdo": "Actions",
        "mark_duplicate": "Actions",
        "mark_open": "Actions",
        "filter_open": "Filters",
        "filter_active": "Filters",
        "filter_blocked": "Filters",
        "filter_finished": "Filters",
        "clear_all_filters": "Filters",
        "filter_epic": "Filters",
        "toggle_grouping": "View",
        "open_urls": "Actions",
        "toggle_collapse": "Navigation",
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
        yield Static(_TASK_FOOTER, id="task-help-bar")

    def _get_current_row_key(self) -> str | None:
        """Return the row key string for the currently highlighted row."""
        if not self.task_view:
            return None
        try:
            table = self.task_view.query_one("#task-table", DataTable)
            if table.cursor_row is None or table.row_count == 0:
                return None
            return str(table.ordered_rows[table.cursor_row].key.value)
        except Exception:
            return None

    def _update_footer_context(self) -> None:
        """Update footer bar text based on the currently highlighted row."""
        try:
            bar = self.query_one("#task-help-bar", Static)
        except Exception:
            return

        row_key = self._get_current_row_key()
        if row_key is None:
            bar.update(_DEFAULT_FOOTER)
            return

        if row_key.startswith(DONE_FOLD_PREFIX):
            bar.update(_DONE_FOLD_FOOTER)
        elif row_key.startswith(HEADER_PREFIX) or row_key.startswith(SEPARATOR_PREFIX):
            bar.update(_EPIC_HEADER_FOOTER)
        elif self.task_view:
            # Check if this is an epic/group parent task
            task = self.task_view._row_key_to_task.get(row_key)
            if task and task.get("type") in ("epic", "group"):
                bar.update(_EPIC_HEADER_FOOTER)
            else:
                bar.update(_TASK_FOOTER)
        else:
            bar.update(_TASK_FOOTER)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """React to row highlight changes to update footer context."""
        self._update_footer_context()

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
            "Filters",
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
        """Focus the task table inside the task view."""
        if self.task_view:
            try:
                table = self.task_view.query_one("#task-table")
                table.focus()
            except Exception:
                logger.warning("TaskBrowser.focus: #task-table not found")
        return self

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Stub for compatibility — tasks don't select by doc ID."""
        return False
