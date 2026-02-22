"""Task View — task browser with DataTable + detail pane.

Left pane: DataTable with tasks grouped by status (ready, active, blocked, done)
Right pane: RichLog with selected task detail (description, deps, log, executions)
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, Input, RichLog, Static

from emdx.models.tasks import (
    get_dependencies,
    get_dependents,
    get_epic_view,
    get_task_log,
    list_epics,
    list_tasks,
    update_task,
)
from emdx.models.types import EpicTaskDict, TaskDict, TaskLogEntryDict

logger = logging.getLogger(__name__)

# Status display order and icons
STATUS_ORDER = ["open", "active", "blocked", "done", "failed", "wontdo"]
STATUS_ICONS = {
    "open": "○",
    "active": "●",
    "blocked": "⚠",
    "done": "✓",
    "failed": "✗",
    "wontdo": "⊘",
}
STATUS_LABELS = {
    "open": "READY",
    "active": "ACTIVE",
    "blocked": "BLOCKED",
    "done": "DONE",
    "failed": "FAILED",
    "wontdo": "WON'T DO",
}
STATUS_COLORS = {
    "open": "",
    "active": "green",
    "blocked": "yellow",
    "done": "dim",
    "failed": "red",
    "wontdo": "dim",
}

# Row key prefix for section headers
HEADER_PREFIX = "header:"
SEPARATOR_PREFIX = "sep:"


def _format_time_ago(dt_str: str | None) -> str:
    """Format a datetime string as relative time."""
    if not dt_str:
        return ""
    try:
        if "T" in dt_str:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(dt_str)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()
        if seconds < 0:
            # Possibly UTC stored without tz — convert
            dt_utc = dt.replace(tzinfo=timezone.utc)
            dt_local = dt_utc.astimezone().replace(tzinfo=None)
            diff = datetime.now() - dt_local
            seconds = diff.total_seconds()
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return f"{int(seconds)}s ago"
        if seconds < 3600:
            return f"{int(seconds / 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds / 3600)}h ago"
        days = int(seconds / 86400)
        return f"{days}d ago"
    except Exception:
        return ""


def _format_time_short(dt_str: str | None) -> str:
    """Format a datetime string as a compact relative time (no 'ago')."""
    if not dt_str:
        return ""
    result = _format_time_ago(dt_str)
    return result.replace(" ago", "") if result else ""


def _priority_str(priority: int) -> str:
    """Return a short priority indicator."""
    if priority <= 1:
        return "!!!"
    if priority <= 2:
        return "!! "
    return "   "


def _priority_style(priority: int) -> str:
    """Return a Rich style for a priority level."""
    if priority <= 1:
        return "bold red"
    if priority <= 2:
        return "yellow"
    return "dim"


def _strip_epic_prefix(title: str, epic_key: str | None, epic_seq: int | None) -> str:
    """Strip the 'KEY-N: ' prefix from a title if it matches the epic."""
    if epic_key and epic_seq:
        prefix = f"{epic_key}-{epic_seq}: "
        if title.startswith(prefix):
            return title[len(prefix) :]
    return title


def _task_label(task: TaskDict) -> str:
    """Build a plain text label for tests and fallback display."""
    icon = STATUS_ICONS.get(task["status"], "?")
    title = task["title"]
    title = _strip_epic_prefix(title, task.get("epic_key"), task.get("epic_seq"))
    if len(title) > 50:
        title = title[:47] + "..."
    return f"{icon} {title}"


class TaskView(Widget):
    """Two-pane task browser view using DataTable."""

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("r", "refresh", "Refresh"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
        ("d", "mark_done", "Mark Done"),
        ("a", "mark_active", "Mark Active"),
        ("b", "mark_blocked", "Mark Blocked"),
        ("w", "mark_wontdo", "Won't Do"),
        ("slash", "show_filter", "Filter"),
        ("escape", "clear_filter", "Clear Filter"),
    ]

    DEFAULT_CSS = """
    TaskView {
        layout: vertical;
        height: 100%;
    }

    #task-status-bar {
        height: 1;
        background: $boost;
        padding: 0 1;
    }

    #task-filter-input {
        height: 3;
        padding: 0 1;
        border-bottom: solid $primary;
        display: none;
    }

    #task-main {
        height: 1fr;
    }

    #task-list-panel {
        width: 40%;
        height: 100%;
    }

    #task-list-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #task-table {
        height: 1fr;
        scrollbar-size: 1 1;
    }

    #task-detail-panel {
        width: 60%;
        height: 100%;
        border-left: solid $primary;
    }

    #task-detail-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #task-detail-log {
        height: 1fr;
        padding: 0 1;
    }
    """

    # Status filter key mapping: key -> set of statuses to show
    STATUS_FILTERS: dict[str, set[str]] = {
        "o": {"open"},
        "i": {"active"},
        "x": {"blocked"},
        "f": {"done", "failed", "wontdo"},
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tasks: list[TaskDict] = []
        self._tasks_by_status: dict[str, list[TaskDict]] = defaultdict(list)
        self._row_key_to_task: dict[str, TaskDict] = {}
        self._epics: dict[int, EpicTaskDict] = {}  # keyed by epic task ID
        self._filter_text: str = ""
        self._debounce_timer: Timer | None = None
        self._status_filter: set[str] | None = None  # None = show all
        self._group_by: str = "status"  # "status" or "epic"
        self._epic_filter: str | None = None  # Filter to specific epic key

    def compose(self) -> ComposeResult:
        yield Static("Loading tasks...", id="task-status-bar")
        yield Input(placeholder="Filter tasks...", id="task-filter-input")
        with Horizontal(id="task-main"):
            with Vertical(id="task-list-panel"):
                yield Static("TASKS", id="task-list-header")
                table: DataTable[str | Text] = DataTable(
                    id="task-table",
                    cursor_type="row",
                    zebra_stripes=True,
                    show_header=False,
                )
                yield table
            with Vertical(id="task-detail-panel"):
                yield Static("DETAIL", id="task-detail-header")
                yield RichLog(
                    id="task-detail-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                    auto_scroll=False,
                )

    async def on_mount(self) -> None:
        """Load tasks on mount."""
        table = self.query_one("#task-table", DataTable)
        table.add_column("icon", key="icon", width=3)
        table.add_column("epic", key="epic", width=7)
        table.add_column("title", key="title")
        table.add_column("age", key="age", width=4)
        await self._load_tasks()
        table.focus()

    async def _load_tasks(self, *, restore_row: int | None = None) -> None:
        """Load all manual tasks from the database."""
        try:
            self._tasks = list_tasks(exclude_delegate=True, limit=200)
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            self._tasks = []

        # Load epics for reference
        try:
            epics = list_epics()
            self._epics = {e["id"]: e for e in epics}
        except Exception as e:
            logger.error(f"Failed to load epics: {e}")
            self._epics = {}

        # Group by status (respecting active filters)
        self._tasks_by_status = defaultdict(list)
        for task in self._tasks:
            if not self._task_passes_filters(task):
                continue
            self._tasks_by_status[task["status"]].append(task)

        self._render_task_table(restore_row=restore_row)
        self._update_status_bar()

    def _row_key_for_task(self, task: TaskDict) -> str:
        """Generate a stable row key for a task."""
        return f"task:{task['id']}"

    def _render_task_table(self, *, restore_row: int | None = None) -> None:
        """Render the grouped task list into the DataTable.

        Args:
            restore_row: If given, restore cursor to this row index
                (clamped to table size) instead of following by key.
                Used after status changes so the cursor stays put.
        """
        table = self.query_one("#task-table", DataTable)

        # Remember current selection for key-based restore
        current_key: str | None = None
        if restore_row is None:
            try:
                if table.cursor_row is not None and table.row_count > 0:
                    current_key = str(table.ordered_rows[table.cursor_row].key.value)
            except (IndexError, AttributeError):
                pass

        table.clear()
        self._row_key_to_task = {}

        if self._group_by == "epic":
            self._render_groups_by_epic(table)
        else:
            self._render_groups_by_status(table)

        # Restore cursor
        if restore_row is not None and table.row_count > 0:
            target = min(restore_row, table.row_count - 1)
            table.move_cursor(row=target)
        elif current_key:
            self._select_row_by_key(current_key)

    def _render_task_row(
        self,
        table: "DataTable[str | Text]",
        task: TaskDict,
        indent: bool = False,
        tree_prefix: str = "",
    ) -> None:
        """Add a single task row to the table.

        Args:
            table: The DataTable to add the row to.
            task: The task data to render.
            indent: Whether to indent with spaces (epic grouping mode).
            tree_prefix: Tree connector string like "├─" or "└─" (status grouping mode).
        """
        row_key = self._row_key_for_task(task)
        self._row_key_to_task[row_key] = task
        is_epic = task.get("type") == "epic"
        color = STATUS_COLORS.get(task["status"], "")
        icon = "📋" if is_epic else STATUS_ICONS.get(task["status"], "?")
        title = _strip_epic_prefix(
            task["title"],
            task.get("epic_key"),
            task.get("epic_seq"),
        )
        if len(title) > 45:
            title = title[:42] + "..."

        # Epic badge: epics show "#id", children show "KEY-N"
        epic_key = task.get("epic_key")
        epic_seq = task.get("epic_seq")
        if is_epic:
            epic_text = Text(f"#{task['id']}", style="bold cyan")
        elif epic_key and epic_seq:
            epic_text = Text(f"{epic_key}-{epic_seq}", style="cyan")
        elif epic_key:
            epic_text = Text(epic_key, style="cyan")
        else:
            epic_text = Text("")

        title_style = "bold cyan" if is_epic else (f"{color}" if color else "")
        prefix = "  " if indent else ""

        # Show inline progress for epic tasks
        age_text = _format_time_short(task.get("created_at"))
        if is_epic:
            epic_data = self._epics.get(task["id"])
            if epic_data:
                done = epic_data.get("children_done", 0)
                total = epic_data.get("child_count", 0)
                age_text = f"{done}/{total}"

        # Build icon cell with tree connector or indent
        if tree_prefix:
            icon_cell = Text(f"{tree_prefix}{icon}", style=color)
        else:
            icon_cell = Text(f"{prefix}{icon}", style=color)

        table.add_row(
            icon_cell,
            epic_text,
            Text(title, style=title_style),
            Text(age_text, style="dim"),
            key=row_key,
        )

    def _render_groups_by_status(self, table: "DataTable[str | Text]") -> None:
        """Render tasks grouped by status, clustering children under epics."""
        first_group = True
        for status in STATUS_ORDER:
            tasks = self._tasks_by_status.get(status, [])
            if not tasks:
                continue

            label = STATUS_LABELS.get(status, status.upper())

            if not first_group:
                table.add_row(
                    "",
                    "",
                    Text(""),
                    "",
                    key=f"{SEPARATOR_PREFIX}{status}",
                )
            first_group = False

            header_text = f"{label} ({len(tasks)})"
            table.add_row(
                "",
                "",
                Text(header_text, style="bold"),
                "",
                key=f"{HEADER_PREFIX}{status}",
            )

            # Cluster children under their epic parent.
            # Epic tasks render first, then their children with tree connectors,
            # then orphan tasks (no parent) render normally.
            epic_ids_in_group = {t["id"] for t in tasks if t.get("type") == "epic"}
            children_by_parent: dict[int, list[TaskDict]] = defaultdict(list)
            orphans: list[TaskDict] = []
            epics_in_order: list[TaskDict] = []

            for task in tasks:
                parent_id = task.get("parent_task_id")
                if task.get("type") == "epic":
                    epics_in_order.append(task)
                elif parent_id and parent_id in epic_ids_in_group:
                    children_by_parent[parent_id].append(task)
                else:
                    orphans.append(task)

            # Render epics with their children
            for epic_task in epics_in_order:
                self._render_task_row(table, epic_task)
                children = children_by_parent.get(epic_task["id"], [])
                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    connector = "└─" if is_last else "├─"
                    self._render_task_row(table, child, tree_prefix=connector)

            # Render orphan tasks (no epic parent in this group)
            for task in orphans:
                self._render_task_row(table, task)

    def _render_groups_by_epic(self, table: "DataTable[str | Text]") -> None:
        """Render tasks grouped by epic with tree connectors."""
        # Collect all filtered tasks into epic groups
        tasks_by_epic: dict[str, list[TaskDict]] = defaultdict(list)
        for status in STATUS_ORDER:
            for task in self._tasks_by_status.get(status, []):
                epic_key = task.get("epic_key") or ""
                tasks_by_epic[epic_key].append(task)

        # Sort epic keys: named epics alphabetically, ungrouped last
        epic_keys = sorted(
            tasks_by_epic.keys(),
            key=lambda k: (k == "", k),
        )

        finished = {"done", "failed", "wontdo"}
        first_group = True
        for epic_key in epic_keys:
            all_tasks = tasks_by_epic[epic_key]
            # Separate epic tasks (headers) from child tasks
            epic_tasks = [t for t in all_tasks if t.get("type") == "epic"]
            child_tasks = [
                t for t in all_tasks if t.get("type") != "epic" and t["status"] not in finished
            ]
            if not child_tasks and not epic_tasks:
                continue

            if not first_group:
                table.add_row(
                    "",
                    "",
                    Text(""),
                    "",
                    key=f"{SEPARATOR_PREFIX}epic:{epic_key or 'none'}",
                )
            first_group = False

            # Render epic task row (uses 📋 icon and #id badge via _render_task_row)
            if epic_key and epic_tasks:
                self._render_task_row(table, epic_tasks[0])
            elif epic_key:
                # No epic task record — non-selectable header
                epic_data = next(
                    (e for e in self._epics.values() if e.get("epic_key") == epic_key),
                    None,
                )
                if epic_data:
                    done = epic_data.get("children_done", 0)
                    total = epic_data.get("child_count", 0)
                    header_text = f"{epic_key} ({done}/{total} done)"
                else:
                    header_text = f"{epic_key} ({len(child_tasks)})"
                table.add_row(
                    "",
                    "",
                    Text(header_text, style="bold cyan"),
                    "",
                    key=f"{HEADER_PREFIX}epic:{epic_key}",
                )
            else:
                table.add_row(
                    "",
                    "",
                    Text(f"UNGROUPED ({len(child_tasks)})", style="bold cyan"),
                    "",
                    key=f"{HEADER_PREFIX}epic:none",
                )

            # Render child tasks with tree connectors
            for i, task in enumerate(child_tasks):
                is_last = i == len(child_tasks) - 1
                connector = "└─" if is_last else "├─"
                self._render_task_row(table, task, tree_prefix=connector)

    def _select_row_by_key(self, key: str) -> None:
        """Move cursor to a row by its key string."""
        table = self.query_one("#task-table", DataTable)
        for i, row in enumerate(table.ordered_rows):
            if str(row.key.value) == key:
                table.move_cursor(row=i)
                return

    def _update_status_bar(self) -> None:
        """Update the status bar with summary counts."""
        status_bar = self.query_one("#task-status-bar", Static)

        counts = {s: len(self._tasks_by_status.get(s, [])) for s in STATUS_ORDER}
        parts = ["[bold]TASKS[/bold]"]

        if counts["open"]:
            parts.append(f"{counts['open']} ready")
        if counts["active"]:
            parts.append(f"[green]{counts['active']} active[/green]")
        if counts["blocked"]:
            parts.append(f"[yellow]{counts['blocked']} blocked[/yellow]")
        if counts["done"]:
            parts.append(f"[dim]{counts['done']} done[/dim]")
        if counts["failed"]:
            parts.append(f"[red]{counts['failed']} failed[/red]")
        if counts["wontdo"]:
            parts.append(f"[dim]{counts['wontdo']} wontdo[/dim]")

        if not any(counts.values()):
            if self._filter_text or self._status_filter:
                parts.append("[yellow]no matches[/yellow]")
            else:
                parts.append("[dim]no tasks[/dim]")

        # Show grouping mode indicator
        if self._group_by == "epic":
            parts.append("[magenta]by epic[/magenta]")

        # Show status filter indicator
        if self._status_filter:
            labels = [STATUS_LABELS.get(s, s) for s in sorted(self._status_filter)]
            parts.append(f"[magenta]{'+'.join(labels)}[/magenta]")

        # Show epic filter indicator
        if self._epic_filter:
            parts.append(f"[cyan]epic: {self._epic_filter}[/cyan]")

        # Show text filter count when active
        if self._filter_text:
            matched = sum(counts.values())
            total = len(self._tasks)
            parts.append(f"[cyan]filter: {matched}/{total}[/cyan]")

        status_bar.update(" · ".join(parts))

    # ------------------------------------------------------------------
    # Filter logic
    # ------------------------------------------------------------------

    def _task_matches_filter(self, task: TaskDict, query: str) -> bool:
        """Check if a task matches the filter query (case-insensitive substring)."""
        q = query.lower()
        fields = [
            task.get("title") or "",
            task.get("epic_key") or "",
            task.get("description") or "",
            task.get("tags") or "",
        ]
        return any(q in f.lower() for f in fields)

    def _task_passes_filters(self, task: TaskDict) -> bool:
        """Check if a task passes text, status, and epic filters."""
        if self._status_filter and task["status"] not in self._status_filter:
            return False
        if self._epic_filter and task.get("epic_key") != self._epic_filter:
            return False
        if self._filter_text and not self._task_matches_filter(task, self._filter_text):
            return False
        return True

    def _apply_filter(self) -> None:
        """Re-group tasks through the active filters and re-render."""
        self._tasks_by_status = defaultdict(list)
        for task in self._tasks:
            if not self._task_passes_filters(task):
                continue
            self._tasks_by_status[task["status"]].append(task)
        self._render_task_table()
        self._update_status_bar()

    def action_show_filter(self) -> None:
        """Show and focus the filter input."""
        filter_input = self.query_one("#task-filter-input", Input)
        filter_input.display = True
        filter_input.focus()

    def action_clear_filter(self) -> None:
        """Clear filter, hide input, refocus table."""
        filter_input = self.query_one("#task-filter-input", Input)
        if not filter_input.display:
            return
        filter_input.value = ""
        filter_input.display = False
        self._filter_text = ""
        self._apply_filter()
        table = self.query_one("#task-table", DataTable)
        table.focus()

    def on_key(self, event: events.Key) -> None:
        """Block vim keys when filter input has focus; handle status filter keys."""
        try:
            filter_input = self.query_one("#task-filter-input", Input)
            if filter_input.has_focus:
                vim_keys = {
                    "j",
                    "k",
                    "r",
                    "d",
                    "a",
                    "b",
                    "w",
                    "e",
                    "g",
                    "slash",
                    "1",
                    "2",
                    "3",
                    "o",
                    "i",
                    "x",
                    "f",
                    "asterisk",
                }
                if event.key in vim_keys:
                    return
        except Exception:
            pass

        # Status filter keys (only when filter input is not focused)
        if event.key in self.STATUS_FILTERS:
            new_filter = self.STATUS_FILTERS[event.key]
            # Toggle: pressing same key again clears the filter
            if self._status_filter == new_filter:
                self._status_filter = None
            else:
                self._status_filter = new_filter
            self._apply_filter()
            event.prevent_default()
            event.stop()
        elif event.key == "asterisk":
            self._status_filter = None
            self._epic_filter = None
            self._apply_filter()
            event.prevent_default()
            event.stop()
        elif event.key == "e":
            # Toggle epic filter to current task's epic
            task = self._get_selected_task()
            epic_key = task.get("epic_key") if task else None
            if epic_key and self._epic_filter != epic_key:
                self._epic_filter = epic_key
            else:
                self._epic_filter = None
            self._apply_filter()
            event.prevent_default()
            event.stop()
        elif event.key == "g":
            self._group_by = "epic" if self._group_by == "status" else "status"
            self._render_task_table()
            self._update_status_bar()
            event.prevent_default()
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes with debouncing."""
        if event.input.id != "task-filter-input":
            return

        query = event.value

        # Cancel pending filter
        if self._debounce_timer:
            try:
                self._debounce_timer.stop()
            except Exception:
                pass
            self._debounce_timer = None

        def do_filter() -> None:
            self._debounce_timer = None
            self._filter_text = query
            self._apply_filter()

        self._debounce_timer = self.set_timer(0.2, do_filter)

    def _get_selected_task(self) -> TaskDict | None:
        """Get the currently highlighted task."""
        table = self.query_one("#task-table", DataTable)
        try:
            if table.cursor_row is None or table.row_count == 0:
                return None
            row_key = str(table.ordered_rows[table.cursor_row].key.value)
            return self._row_key_to_task.get(row_key)
        except (IndexError, AttributeError):
            return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail pane when a task row is highlighted."""
        task = self._get_selected_task()
        if task:
            self._render_task_detail(task)

    def _render_task_detail(self, task: TaskDict) -> None:
        """Render full task detail in the right pane."""
        # Epic tasks get a specialized view with child task listing
        if task.get("type") == "epic":
            self._render_epic_detail(task)
            return

        detail_log = self.query_one("#task-detail-log", RichLog)
        header = self.query_one("#task-detail-header", Static)

        detail_log.clear()

        icon = STATUS_ICONS.get(task["status"], "?")
        header.update(f"{icon} Task #{task['id']}")

        # Title
        detail_log.write(f"[bold]{task['title']}[/bold]")
        detail_log.write("")

        # Status / Priority / Epic
        meta_parts = []
        meta_parts.append(f"Status: [bold]{task['status']}[/bold]")
        meta_parts.append(f"Priority: {task['priority']}")
        if task.get("epic_key"):
            parent_id = task.get("parent_task_id")
            epic = self._epics.get(parent_id) if parent_id else None
            if epic:
                done = epic.get("children_done", 0)
                total = epic.get("child_count", 0)
                meta_parts.append(f"Epic: {task['epic_key']} ({done}/{total} done)")
            else:
                meta_parts.append(f"Epic: {task['epic_key']}")
        detail_log.write("  ".join(meta_parts))

        # Timestamps
        time_parts = []
        if task.get("created_at"):
            time_parts.append(f"Created {_format_time_ago(task['created_at'])}")
        if task.get("updated_at"):
            time_parts.append(f"Updated {_format_time_ago(task['updated_at'])}")
        if task.get("completed_at"):
            time_parts.append(f"Completed {_format_time_ago(task['completed_at'])}")
        if time_parts:
            detail_log.write(f"[dim]{' · '.join(time_parts)}[/dim]")

        if task.get("tags"):
            detail_log.write(f"Tags: {task['tags']}")

        # Dependencies
        try:
            deps = get_dependencies(task["id"])
            if deps:
                detail_log.write("")
                detail_log.write("[bold]Depends on:[/bold]")
                for dep in deps:
                    dep_icon = STATUS_ICONS.get(dep["status"], "?")
                    detail_log.write(
                        f"  {dep_icon} #{dep['id']} {dep['title'][:60]} [{dep['status']}]"
                    )
        except Exception as e:
            logger.debug(f"Error loading dependencies: {e}")

        try:
            dependents = get_dependents(task["id"])
            if dependents:
                detail_log.write("")
                detail_log.write("[bold]Blocks:[/bold]")
                for dep in dependents:
                    dep_icon = STATUS_ICONS.get(dep["status"], "?")
                    detail_log.write(
                        f"  {dep_icon} #{dep['id']} {dep['title'][:60]} [{dep['status']}]"
                    )
        except Exception as e:
            logger.debug(f"Error loading dependents: {e}")

        # Description
        if task.get("description"):
            detail_log.write("")
            detail_log.write("[bold]Description:[/bold]")
            detail_log.write(task["description"])

        # Error info
        if task.get("error"):
            detail_log.write("")
            detail_log.write(f"[red bold]Error:[/red bold] {task['error']}")

        # Work log
        try:
            log_entries: list[TaskLogEntryDict] = get_task_log(task["id"], limit=20)
            if log_entries:
                detail_log.write("")
                detail_log.write("[bold]Work Log:[/bold]")
                for entry in log_entries:
                    time_str = _format_time_ago(entry.get("created_at"))
                    msg = entry["message"]
                    if len(msg) > 120:
                        msg = msg[:117] + "..."
                    detail_log.write(f"  [dim]{time_str}[/dim] {msg}")
        except Exception as e:
            logger.debug(f"Error loading task log: {e}")

        # Execution info
        if task.get("execution_id"):
            detail_log.write("")
            detail_log.write(f"[bold]Execution:[/bold] #{task['execution_id']}")
        if task.get("output_doc_id"):
            detail_log.write(f"Output doc: #{task['output_doc_id']}")

    def _render_epic_detail(self, task: TaskDict) -> None:
        """Render epic detail with child task listing in the right pane."""
        detail_log = self.query_one("#task-detail-log", RichLog)
        header = self.query_one("#task-detail-header", Static)
        detail_log.clear()

        icon = STATUS_ICONS.get(task["status"], "?")
        header.update(f"{icon} Epic #{task['id']}")

        # Title
        detail_log.write(f"[bold]{task['title']}[/bold]")
        detail_log.write("")

        # Progress summary from cached epic data
        epic_key = task.get("epic_key")
        epic_data = self._epics.get(task["id"])
        if epic_data:
            done = epic_data.get("children_done", 0)
            total = epic_data.get("child_count", 0)
            open_count = epic_data.get("children_open", 0)
            pct = int(done / total * 100) if total > 0 else 0
            bar_len = 20
            filled = int(bar_len * done / total) if total > 0 else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            detail_log.write(f"[bold]Progress:[/bold] {bar} {pct}%")
            detail_log.write(f"  [green]{done} done[/green] · {open_count} open · {total} total")
        else:
            detail_log.write(f"Status: [bold]{task['status']}[/bold]")

        # Description
        if task.get("description"):
            detail_log.write("")
            detail_log.write("[bold]Description:[/bold]")
            detail_log.write(task["description"])

        # Load and display child tasks
        try:
            epic_view = get_epic_view(task["id"])
            if epic_view and epic_view.get("children"):
                detail_log.write("")
                detail_log.write("[bold]Tasks:[/bold]")
                for child in epic_view["children"]:
                    c_icon = STATUS_ICONS.get(child["status"], "?")
                    c_color = STATUS_COLORS.get(child["status"], "")
                    c_title = child["title"][:55]
                    seq = child.get("epic_seq")
                    prefix = f"{epic_key}-{seq}" if epic_key and seq else ""
                    if c_color:
                        detail_log.write(
                            f"  [{c_color}]{c_icon}[/{c_color}] "
                            f"[cyan]{prefix:>7}[/cyan] "
                            f"[{c_color}]{c_title}[/{c_color}]"
                        )
                    else:
                        detail_log.write(f"  {c_icon} [cyan]{prefix:>7}[/cyan] {c_title}")
        except Exception as e:
            logger.debug(f"Error loading epic children: {e}")

        # Timestamps
        time_parts = []
        if task.get("created_at"):
            time_parts.append(f"Created {_format_time_ago(task['created_at'])}")
        if task.get("updated_at"):
            time_parts.append(f"Updated {_format_time_ago(task['updated_at'])}")
        if time_parts:
            detail_log.write("")
            detail_log.write(f"[dim]{' · '.join(time_parts)}[/dim]")

    # Navigation actions

    def action_cursor_down(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.action_cursor_up()

    async def action_refresh(self) -> None:
        """Reload tasks from database."""
        await self._load_tasks()

    def _toggle_filter_focus(self) -> None:
        """Toggle focus between filter input and task table."""
        filter_input = self.query_one("#task-filter-input", Input)
        table = self.query_one("#task-table", DataTable)
        if filter_input.display and not filter_input.has_focus:
            filter_input.focus()
        else:
            table.focus()

    def action_focus_next(self) -> None:
        """Toggle focus between filter and table."""
        self._toggle_filter_focus()

    def action_focus_prev(self) -> None:
        """Toggle focus between filter and table."""
        self._toggle_filter_focus()

    # Status mutation actions

    async def _set_task_status(self, new_status: str) -> None:
        """Change status of the selected task and refresh.

        Cursor stays at the same row position (not following the task
        into its new status group).
        """
        task = self._get_selected_task()
        if not task:
            return
        if task["status"] == new_status:
            return

        # Save row index — we want to stay at this position
        table = self.query_one("#task-table", DataTable)
        saved_row = table.cursor_row

        try:
            update_task(task["id"], status=new_status)
            self.notify(f"Task #{task['id']} → {new_status}", timeout=2)
            await self._load_tasks(restore_row=saved_row)
        except Exception as e:
            logger.error(f"Failed to update task: {e}")
            self.notify(f"Error: {e}", severity="error", timeout=3)

    async def action_mark_done(self) -> None:
        """Mark selected task as done."""
        await self._set_task_status("done")

    async def action_mark_active(self) -> None:
        """Mark selected task as active."""
        await self._set_task_status("active")

    async def action_mark_blocked(self) -> None:
        """Mark selected task as blocked."""
        await self._set_task_status("blocked")

    async def action_mark_wontdo(self) -> None:
        """Mark selected task as won't do."""
        await self._set_task_status("wontdo")
