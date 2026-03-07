"""Task View — task browser with DataTable + detail pane.

Left pane: DataTable with tasks grouped by status (ready, active, blocked, done)
Right pane: RichLog with selected task detail (description, deps, log, executions)
"""

import logging
import textwrap
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from rich.console import Console as RichConsole
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, Input, RichLog, Static

from emdx.models.task import Task, TaskLogEntry
from emdx.models.tasks import (
    count_tasks_by_status,
    get_dependencies,
    get_dependents,
    get_epic_view,
    get_task_log,
    list_epics,
    list_tasks,
    update_task,
)
from emdx.ui.link_helpers import extract_urls as _extract_urls
from emdx.ui.link_helpers import linkify_text as _linkify_text

logger = logging.getLogger(__name__)

# Status display order and icons
STATUS_ORDER = ["active", "open", "blocked", "done", "failed", "wontdo", "duplicate"]
STATUS_ICONS = {
    "open": "⚪",
    "active": "🟢",
    "blocked": "🟡",
    "done": "✅",
    "failed": "❌",
    "wontdo": "🚫",
    "duplicate": "🔁",
}
STATUS_LABELS = {
    "open": "READY",
    "active": "ACTIVE",
    "blocked": "BLOCKED",
    "done": "DONE",
    "failed": "FAILED",
    "wontdo": "WON'T DO",
    "duplicate": "DUPLICATE",
}
STATUS_COLORS = {
    "open": "cyan",
    "active": "green",
    "blocked": "yellow",
    "done": "dim",
    "failed": "red",
    "wontdo": "dim",
    "duplicate": "cyan",
}

# Legacy statuses that should be mapped to canonical ones
STATUS_ALIASES = {"closed": "done"}

# Row key prefix for section headers
HEADER_PREFIX = "header:"
SEPARATOR_PREFIX = "sep:"
DONE_FOLD_PREFIX = "done-fold:"


def _format_time_ago(dt_str: str | datetime | None) -> str:
    """Format a datetime string (or datetime) as relative time, or absolute date if > 7 days."""
    if not dt_str:
        return ""
    if isinstance(dt_str, datetime):
        dt_str = dt_str.isoformat()
    try:
        if isinstance(dt_str, datetime):
            dt = dt_str
        elif "T" in dt_str:
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
        if days < 7:
            return f"{days}d ago"
        # Older than 7 days — show absolute date
        if dt.year == now.year:
            return dt.strftime("%b %d")
        return dt.strftime("%b %d, %Y")
    except Exception:
        return ""


def _format_time_short(dt_str: str | datetime | None) -> str:
    """Format a datetime string (or datetime) as a compact relative time (no 'ago')."""
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


def _task_badge(task: Task) -> str:
    """Return the KEY-N badge for a task, or empty string if unavailable."""
    epic_key = task.epic_key
    epic_seq = task.epic_seq
    if epic_key and epic_seq:
        return f"{epic_key}-{epic_seq}"
    if epic_key:
        return str(epic_key)
    return ""


def _task_label(task: Task) -> str:
    """Build a plain text label for tests and fallback display."""
    icon = STATUS_ICONS.get(task.status, "?")
    title = task.title
    title = _strip_epic_prefix(title, task.epic_key, task.epic_seq)
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
        ("p", "mark_duplicate", "Duplicate"),
        ("u", "mark_open", "Reopen"),
        ("slash", "show_filter", "Filter"),
        ("escape", "clear_filter", "Clear Filter"),
        ("z", "toggle_zoom", "Zoom"),
        ("o", "filter_open", "Toggle Open"),
        ("i", "filter_active", "Toggle Active"),
        ("x", "filter_blocked", "Toggle Blocked"),
        ("f", "filter_finished", "Toggle Finished"),
        ("asterisk", "clear_all_filters", "Clear Filters"),
        ("e", "filter_epic", "Epic Filter"),
        ("g", "toggle_grouping", "Group By"),
        ("O", "open_urls", "Open URLs"),
        Binding("enter", "toggle_collapse", "Expand/Collapse", show=True),
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

    /* ── Top band: task list (+ future sidebar) ───────── */

    #task-list-panel {
        height: 40%;
        width: 100%;
    }

    /* Wide (>=120 cols, default): list section 70%, sidebar 30% */
    #task-list-section {
        width: 70%;
    }

    #task-sidebar-section {
        width: 30%;
        border-left: solid $secondary;
    }

    /* Narrow (<120 cols): sidebar hidden, list fills band */
    #task-list-panel.sidebar-hidden #task-sidebar-section {
        display: none;
    }

    #task-list-panel.sidebar-hidden #task-list-section {
        width: 100%;
    }

    /* ── Content pane: task detail ─────────────────────── */

    #task-detail-panel {
        height: 60%;
        width: 100%;
        border-top: solid $primary;
    }

    /* ── Zoom: content full-screen (list hidden) ──────── */
    #task-list-panel.zoom-content {
        display: none;
    }

    #task-detail-panel.zoom-content {
        height: 100%;
        border-top: none;
    }

    /* ── Zoom: list full-screen (content hidden) ──────── */
    #task-detail-panel.zoom-list {
        display: none;
    }

    #task-list-panel.zoom-list {
        height: 100%;
    }

    /* ── Table and headers ────────────────────────────── */

    #task-list-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #task-table {
        height: 1fr;
        scrollbar-size: 1 1;
    }

    #task-sidebar-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #task-sidebar-content {
        padding: 0 1;
    }

    #task-detail-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #task-detail-log {
        height: 1fr;
        padding: 0 1;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tasks: list[Task] = []
        self._tasks_by_status: dict[str, list[Task]] = defaultdict(list)
        self._row_key_to_task: dict[str, Task] = {}
        self._epics: dict[int, Task] = {}  # keyed by epic task ID
        self._filter_text: str = ""
        self._debounce_timer: Timer | None = None
        self._hidden_statuses: set[str] = set()  # statuses to hide (empty = show all)
        self._initial_select_done = False
        self._group_by: str = "epic"  # "epic" or "status"
        self._epic_filter: str | None = None  # Filter to specific epic key
        self._collapsed: set[int] = set()  # Explicitly collapsed parent IDs
        self._expanded: set[int] = set()  # Explicitly expanded parent IDs
        self._done_folds_expanded: set[int] = set()  # Epic IDs with done-fold open
        self._zoomed: bool = False
        self._sidebar_visible: bool = True
        self._current_task: Task | None = None
        self._refresh_in_progress: bool = False
        self._data_fingerprint: str = ""  # skip no-op refreshes
        self._true_status_counts: dict[str, int] = {}  # accurate DB counts

    def compose(self) -> ComposeResult:
        yield Static("Loading tasks...", id="task-status-bar")
        yield Input(placeholder="Filter tasks...", id="task-filter-input")
        with Vertical(id="task-main"):
            with Horizontal(id="task-list-panel"):
                # Left: task list
                with Vertical(id="task-list-section"):
                    yield Static("TASKS", id="task-list-header")
                    table: DataTable[str | Text] = DataTable(
                        id="task-table",
                        cursor_type="row",
                        zebra_stripes=True,
                        show_header=False,
                    )
                    yield table
                # Right: metadata sidebar (hidden at narrow widths)
                with Vertical(id="task-sidebar-section"):
                    yield Static("DETAILS", id="task-sidebar-header")
                    with ScrollableContainer(id="task-sidebar-scroll"):
                        yield RichLog(
                            id="task-sidebar-content",
                            highlight=True,
                            markup=True,
                            wrap=True,
                            auto_scroll=False,
                        )
            with Vertical(id="task-detail-panel"):
                yield Static("DETAIL", id="task-detail-header")
                yield RichLog(
                    id="task-detail-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                    auto_scroll=False,
                )

    # Width threshold for showing/hiding sidebar
    SIDEBAR_WIDTH_THRESHOLD = 120

    async def on_mount(self) -> None:
        """Load tasks on mount."""
        table = self.query_one("#task-table", DataTable)
        table.add_column("icon", key="icon", width=5)
        table.add_column("epic", key="epic", width=13)
        table.add_column("title", key="title", width=60)
        table.add_column("age", key="age", width=4)
        # Disable auto-width on title so it doesn't shrink to content
        try:
            from textual.widgets._data_table import ColumnKey

            col = table.columns.get(ColumnKey("title"))
            if col:
                col.auto_width = False
        except Exception as e:
            logger.warning(f"Failed to disable auto_width on title column: {e}")

        # Apply initial sidebar visibility based on current width
        self._update_sidebar_visibility()

        await self._load_tasks()
        table.focus()

        # After layout is complete, move the cursor to the first actual task
        # row (skipping section headers) and re-render the detail pane.
        # On first mount, RowHighlighted fires during _load_tasks before layout
        # is done, and the cursor lands on a header row — both issues cause
        # an empty detail pane.
        def _deferred_select_first_task() -> None:
            self._update_sidebar_visibility()
            self._sync_title_width()
            table = self.query_one("#task-table", DataTable)
            if table.size.width > 0 and table.size.height > 0:
                self._select_first_task_row()
                self._initial_select_done = True
            # else: on_resize will handle it once layout completes

        self.call_after_refresh(_deferred_select_first_task)

        # Auto-refresh every 1s (matches ActivityView pattern)
        self.set_interval(1.0, self._refresh_data_tick)

    def on_resize(self, event: events.Resize) -> None:
        """Toggle sidebar visibility and sync title column width."""
        self._update_sidebar_visibility()
        self._sync_title_width()
        if not self._initial_select_done:
            self._select_first_task_row()
            self._initial_select_done = True

    def _update_sidebar_visibility(self) -> None:
        """Show/hide sidebar based on current width."""
        try:
            panel = self.query_one("#task-list-panel")
        except Exception:
            return
        was_visible = self._sidebar_visible
        if self.size.width < self.SIDEBAR_WIDTH_THRESHOLD:
            panel.add_class("sidebar-hidden")
            self._sidebar_visible = False
        else:
            panel.remove_class("sidebar-hidden")
            self._sidebar_visible = True
        # Re-render detail if sidebar visibility changed
        if was_visible != self._sidebar_visible and self._current_task:
            self._render_task_detail(self._current_task)

    def _sync_title_width(self) -> None:
        """Set the title column to fill remaining horizontal space."""
        try:
            table = self.query_one("#task-table", DataTable)
        except Exception:
            return
        # icon(3) + epic(13) + age(4) + borders/padding(~4)
        overhead = 3 + 13 + 4 + 4
        # In sidebar-visible mode, the list section is 70% of width
        if self._sidebar_visible:
            avail = int(self.size.width * 0.7)
        else:
            avail = self.size.width
        title_w = max(20, avail - overhead)
        try:
            from textual.widgets._data_table import ColumnKey

            col = table.columns.get(ColumnKey("title"))
            if col and col.width != title_w:
                col.width = title_w
                col.auto_width = False
        except Exception as e:
            logger.warning(f"Failed to sync title column width: {e}")

    def _compute_fingerprint(self, tasks: list[Task]) -> str:
        """Fast fingerprint of task data to detect changes."""
        # id:status:updated_at for each task, sorted by id
        parts = sorted(f"{t.id}:{t.status}:{t.updated_at or ''}" for t in tasks)
        return "|".join(parts)

    async def _load_tasks(self, *, restore_row: int | None = None) -> None:
        """Load all manual tasks from the database."""
        try:
            active_tasks = list_tasks(status=["open", "active", "blocked", "failed"], limit=500)
            done_tasks = list_tasks(status=["done", "wontdo", "duplicate"], limit=200)
            new_tasks = active_tasks + done_tasks
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            new_tasks = []

        # Skip table rebuild if data hasn't changed (avoids scroll bounce)
        new_fp = self._compute_fingerprint(new_tasks)
        if restore_row is None and new_fp and new_fp == self._data_fingerprint:
            return
        self._data_fingerprint = new_fp
        self._tasks = new_tasks

        # Load epics for reference
        try:
            epics = list_epics()
            self._epics = {e.id: e for e in epics}
        except Exception as e:
            logger.error(f"Failed to load epics: {e}")
            self._epics = {}

        # Get accurate status counts (not limited by query caps)
        try:
            self._true_status_counts = count_tasks_by_status()
        except Exception as e:
            logger.error(f"Failed to count tasks: {e}")
            self._true_status_counts = {}

        # Group by status (respecting active filters)
        self._tasks_by_status = defaultdict(list)
        for task in self._tasks:
            if not self._task_passes_filters(task):
                continue
            status = STATUS_ALIASES.get(task.status, task.status)
            self._tasks_by_status[status].append(task)

        self._render_task_table(restore_row=restore_row)
        self._update_status_bar()

    def _ensure_done_tasks_loaded(self, epic_id: int) -> None:
        """Lazy-load done tasks for an epic when its fold is expanded.

        The initial load caps done tasks at 200. When a user expands a fold,
        fetch all done children for that epic and merge any missing ones.
        """
        loaded_ids = {t.id for t in self._tasks}
        try:
            epic_done = list_tasks(
                status=["done", "wontdo", "duplicate"],
                parent_task_id=epic_id,
                limit=5000,
            )
        except Exception as e:
            logger.error(f"Failed to lazy-load done tasks for epic {epic_id}: {e}")
            return
        new_tasks = [t for t in epic_done if t.id not in loaded_ids]
        if new_tasks:
            self._tasks.extend(new_tasks)
            # Invalidate fingerprint so next auto-refresh doesn't discard them
            self._data_fingerprint = ""

    def _row_key_for_task(self, task: Task) -> str:
        """Generate a stable row key for a task."""
        return f"task:{task.id}"

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

        # Show placeholder when table is empty
        if table.row_count == 0:
            table.add_row(
                "",
                "",
                Text('No tasks yet — add one with: emdx task add "Title"', style="dim"),
                "",
                key=f"{HEADER_PREFIX}empty",
            )

        # Restore cursor
        if restore_row is not None and table.row_count > 0:
            target = min(restore_row, table.row_count - 1)
            table.move_cursor(row=target)
        elif current_key:
            self._select_row_by_key(current_key)

    def _render_task_row(
        self,
        table: "DataTable[str | Text]",
        task: Task,
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
        is_parent = task.type in {"epic", "group"}
        color = STATUS_COLORS.get(task.status, "")
        icon = "📋" if is_parent else STATUS_ICONS.get(task.status, "?")
        title = _strip_epic_prefix(
            task.title,
            task.epic_key,
            task.epic_seq,
        )
        # Epic badge: parents and children show "KEY-N" colored by status
        epic_key = task.epic_key
        epic_seq = task.epic_seq
        badge_color = color or "cyan"
        bold_badge = f"bold {badge_color}" if badge_color else "bold"
        if is_parent and epic_key and epic_seq:
            epic_text = Text(f"{epic_key}-{epic_seq}", style=bold_badge)
        elif is_parent and epic_key:
            epic_text = Text(epic_key, style=bold_badge)
        elif is_parent:
            epic_text = Text("")
        elif epic_key and epic_seq:
            epic_text = Text(f"{epic_key}-{epic_seq}", style=badge_color)
        elif epic_key:
            epic_text = Text(epic_key, style=badge_color)
        else:
            epic_text = Text("")

        title_style = "bold" if is_parent else ""
        prefix = "  " if indent else ""

        # Show inline progress for parent tasks (epics/groups)
        age_text = _format_time_short(task.created_at)
        if is_parent:
            epic_data = self._epics.get(task.id)
            if epic_data:
                done = epic_data.children_done
                total = epic_data.child_count
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
            # Epic tasks render first, then their children with tree connectors.
            # Children whose epic is in another status group are clustered
            # together with tree connectors (cross-group siblings).
            # Tasks with no parent render normally.
            epic_ids_in_group = {t.id for t in tasks if t.type == "epic"}
            children_by_parent: dict[int, list[Task]] = defaultdict(list)
            cross_group_by_parent: dict[int, list[Task]] = defaultdict(list)
            true_orphans: list[Task] = []
            epics_in_order: list[Task] = []

            for task in tasks:
                parent_id = task.parent_task_id
                if task.type == "epic":
                    epics_in_order.append(task)
                elif parent_id and parent_id in epic_ids_in_group:
                    children_by_parent[parent_id].append(task)
                elif parent_id:
                    # Child whose epic is in a different status group
                    cross_group_by_parent[parent_id].append(task)
                else:
                    true_orphans.append(task)

            # Render epics with their children
            for epic_task in epics_in_order:
                self._render_task_row(table, epic_task)
                children = children_by_parent.get(epic_task.id, [])
                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    connector = "└─" if is_last else "├─"
                    self._render_task_row(table, child, tree_prefix=connector)

            # Render cross-group children clustered under their epic
            for parent_id, children in cross_group_by_parent.items():
                epic_data = self._epics.get(parent_id)
                if epic_data:
                    ek = epic_data.epic_key or ""
                    done = epic_data.children_done
                    total = epic_data.child_count
                    ref_text = f"{ek} ({done}/{total} done)"
                else:
                    ref_text = f"(parent {parent_id})"
                table.add_row(
                    "",
                    "",
                    Text(ref_text, style="dim cyan"),
                    "",
                    key=f"{HEADER_PREFIX}xepic:{parent_id}:{status}",
                )
                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    connector = "└─" if is_last else "├─"
                    self._render_task_row(table, child, tree_prefix=connector)

            # Render true orphan tasks (no epic parent at all)
            for task in true_orphans:
                self._render_task_row(table, task)

    def _render_groups_by_epic(self, table: "DataTable[str | Text]") -> None:
        """Render tasks grouped by parent epic, with status sub-groups.

        Groups tasks by their parent_task_id (actual epic relationship).
        Active epics (with open/active/blocked children) render first with
        non-finished status sub-groups. Fully-done epics render at the
        bottom as collapsed header-only rows showing progress.
        Orphan tasks (no parent) go to UNGROUPED.
        """
        finished = {"done", "failed", "wontdo", "duplicate"}
        showing_finished = not bool(self._hidden_statuses & finished)
        visible_statuses = [s for s in STATUS_ORDER if s not in self._hidden_statuses]

        # Group children by parent_task_id.
        # First pass: collect all tasks and find which IDs are parents.
        all_loaded: dict[int, Task] = {}
        referenced_parents: set[int] = set()
        for status in STATUS_ORDER:
            for task in self._tasks_by_status.get(status, []):
                all_loaded[task.id] = task
                pid = task.parent_task_id
                if pid is not None:
                    referenced_parents.add(pid)

        # Second pass: separate parents from children.
        parent_types = {"epic", "group"}
        children_by_parent: dict[int | None, list[Task]] = defaultdict(
            list,
        )
        epic_task_by_id: dict[int, Task] = {}
        for task in all_loaded.values():
            is_parent = task.type in parent_types or task.id in referenced_parents
            if is_parent:
                epic_task_by_id[task.id] = task
            else:
                parent = task.parent_task_id
                children_by_parent[parent].append(task)

        # Build ordered list of parent IDs: epics with children first,
        # then epics without children, then None (ungrouped).
        parent_ids: list[int | None] = []
        seen: set[int | None] = set()
        # Epics that have children in our data
        for pid in children_by_parent:
            if pid is not None and pid not in seen:
                parent_ids.append(pid)
                seen.add(pid)
        # Epics from the epics list that may not have children loaded
        for eid in self._epics:
            if eid not in seen:
                parent_ids.append(eid)
                seen.add(eid)

        # Sort: active epics first, then done, then ungrouped last.
        # Within each bucket: epics with in-progress children first,
        # then by most recent child activity (DESC), then epic age.
        def _max_child_timestamp(pid: int | None) -> str:
            kids = children_by_parent.get(pid, [])
            if not kids:
                return ""
            raw = max(
                (k.updated_at or k.created_at or "" for k in kids),
                default="",
            )
            return str(raw) if raw else ""

        def _sort_key(pid: int | None) -> tuple[int, int, str, str]:
            if pid is None:
                return (2, 0, "", "")
            epic = epic_task_by_id.get(pid) or self._epics.get(pid)
            kids = children_by_parent.get(pid, [])
            has_open = any(k.status not in finished for k in kids)
            epic_status = epic.status if epic else "done"
            # Bucket: 0=active, 1=done, 2=ungrouped
            bucket = 0 if (has_open or epic_status not in finished) else 1
            # Epics with active/in-progress children float to top
            has_active = any(k.status == "active" for k in kids)
            active_rank = 0 if has_active else 1
            # Most recent child activity (invert for DESC sort)
            max_ts = _max_child_timestamp(pid)
            inv_ts = "".join(chr(0xFFFF - ord(c)) for c in max_ts) if max_ts else "\uffff"
            # Epic creation as tiebreaker (DESC)
            raw_created = (epic.created_at or "") if epic else ""
            epic_created = str(raw_created) if raw_created else ""
            inv_created = (
                "".join(chr(0xFFFF - ord(c)) for c in epic_created) if epic_created else "\uffff"
            )
            return (bucket, active_rank, inv_ts, inv_created)

        parent_ids.sort(key=_sort_key)
        # Ensure None (ungrouped) is in the list
        if None not in seen and children_by_parent.get(None):
            parent_ids.append(None)

        # Partition into active and done groups
        active_parents: list[int | None] = []
        done_parents: list[int] = []
        for pid in parent_ids:
            kids = children_by_parent.get(pid, [])
            has_open = any(k.status not in finished for k in kids)
            if has_open or pid is None:
                active_parents.append(pid)
            else:
                # pid cannot be None here (handled by `pid is None` above)
                assert pid is not None
                epic = epic_task_by_id.get(pid) or self._epics.get(pid)
                epic_status = epic.status if epic else "done"
                if epic_status not in finished:
                    active_parents.append(pid)
                else:
                    done_parents.append(pid)

        first_group = True

        # Render active epic groups with status sub-groups
        for pid in active_parents:
            kids = children_by_parent.get(pid, [])
            if not kids and pid is not None:
                continue
            # Skip UNGROUPED when all children are in non-visible statuses
            if pid is None:
                visible_kids = [
                    k
                    for k in kids
                    if STATUS_ALIASES.get(
                        k.status,
                        k.status,
                    )
                    in set(visible_statuses)
                ]
                if not visible_kids:
                    continue

            if not first_group:
                table.add_row(
                    "",
                    "",
                    Text(""),
                    "",
                    key=f"{SEPARATOR_PREFIX}epic:{pid or 'none'}",
                )
            first_group = False

            # Render epic header
            if pid is not None:
                epic = epic_task_by_id.get(pid)
                if not epic:
                    # Epic not in loaded tasks — use _epics data
                    epic_data = self._epics.get(pid)
                    if epic_data:
                        epic = epic_data
                if epic:
                    self._render_task_row(table, epic)
                else:
                    table.add_row(
                        "",
                        "",
                        Text("Unknown parent", style="bold cyan"),
                        "",
                        key=f"{HEADER_PREFIX}epic:{pid}",
                    )
            else:
                table.add_row(
                    "",
                    "",
                    Text(
                        f"UNGROUPED ({len(kids)})",
                        style="bold cyan",
                    ),
                    "",
                    key=f"{HEADER_PREFIX}epic:none",
                )

            # Skip children if this parent is collapsed
            if pid is not None and pid in self._collapsed:
                continue

            # Split children into active and done groups
            active_kids: list[Task] = []
            done_kids: list[Task] = []
            for task in kids:
                normalized = STATUS_ALIASES.get(task.status, task.status)
                if normalized in finished:
                    done_kids.append(task)
                else:
                    active_kids.append(task)

            # Sort active kids by status order, then oldest-first (queue)
            status_rank = {s: i for i, s in enumerate(STATUS_ORDER)}
            active_kids.sort(
                key=lambda t: (
                    status_rank.get(
                        STATUS_ALIASES.get(t.status, t.status),
                        len(STATUS_ORDER),
                    ),
                    t.created_at or "",
                ),
            )

            # Sort done kids by completed_at descending (most recent first)
            done_kids.sort(
                key=lambda t: t.completed_at or t.updated_at or "",
                reverse=True,
            )

            # Determine if done-fold is expanded
            done_fold_open = pid is not None and pid in self._done_folds_expanded
            has_done = len(done_kids) > 0

            # Render active children
            for i, task in enumerate(active_kids):
                is_last = i == len(active_kids) - 1 and not has_done
                connector = "└─" if is_last else "├─"
                self._render_task_row(table, task, tree_prefix=connector)

            # Render done children
            if has_done:
                if pid is None:
                    # Ungrouped: show done kids inline
                    for i, task in enumerate(done_kids):
                        is_last = i == len(done_kids) - 1
                        connector = "└─" if is_last else "├─"
                        self._render_task_row(table, task, tree_prefix=connector)
                else:
                    # Epic children: collapsible done-fold
                    arrow = "▾" if done_fold_open else "▸"
                    latest_ts = done_kids[0].completed_at or done_kids[0].updated_at or ""
                    recency = _format_time_ago(latest_ts)
                    # Use accurate DB count from epic data when available
                    epic_info = self._epics.get(pid) if pid is not None else None
                    epic_done_count = epic_info.children_done if epic_info else len(done_kids)
                    if recency:
                        fold_label = f"{epic_done_count} completed (latest: {recency}) {arrow}"
                    else:
                        fold_label = f"{epic_done_count} completed {arrow}"
                    is_last_row = not done_fold_open
                    connector = "└─" if is_last_row else "├─"
                    table.add_row(
                        Text(f"{connector}✅", style="dim"),
                        Text(""),
                        Text(fold_label, style="dim italic"),
                        Text(""),
                        key=f"{DONE_FOLD_PREFIX}{pid}",
                    )
                    if done_fold_open:
                        for i, task in enumerate(done_kids):
                            is_last = i == len(done_kids) - 1
                            connector = "└─" if is_last else "├─"
                            self._render_task_row(table, task, tree_prefix=connector)

        # Render done epics — collapsed by default, expandable
        if done_parents and showing_finished:
            # Auto-collapse done parents that haven't been explicitly toggled
            for pid in done_parents:
                if pid not in self._collapsed and pid not in self._expanded:
                    # First render: default to collapsed
                    self._collapsed.add(pid)

            if not first_group:
                table.add_row(
                    "",
                    "",
                    Text(""),
                    "",
                    key=f"{SEPARATOR_PREFIX}done-epics",
                )
            first_group = False

            table.add_row(
                "",
                "",
                Text("COMPLETED", style="dim bold"),
                "",
                key=f"{HEADER_PREFIX}done-epics",
            )
            for pid in done_parents:
                epic = epic_task_by_id.get(pid)
                if not epic:
                    epic_data = self._epics.get(pid)
                    if epic_data:
                        epic = epic_data
                if epic:
                    self._render_task_row(table, epic)
                else:
                    table.add_row(
                        "",
                        "",
                        Text("Unknown parent", style="dim cyan"),
                        "",
                        key=f"{HEADER_PREFIX}epic:{pid}",
                    )
                # Show fold summary or expanded children
                kids = children_by_parent.get(pid, [])
                if pid in self._collapsed:
                    # Collapsed: show fold summary with recency hint
                    # Use accurate DB count from epic data when available
                    epic_info = self._epics.get(pid)
                    epic_done_count = epic_info.children_done if epic_info else len(kids)
                    if epic_done_count > 0:
                        if kids:
                            latest = kids[0].completed_at or kids[0].updated_at or ""
                            recency = _format_time_ago(latest)
                        else:
                            recency = ""
                        if recency:
                            fold_label = f"{epic_done_count} completed (latest: {recency}) ▸"
                        else:
                            fold_label = f"{epic_done_count} completed ▸"
                        table.add_row(
                            Text(""),
                            Text(""),
                            Text(f"  {fold_label}", style="dim"),
                            Text(""),
                            key=f"{DONE_FOLD_PREFIX}epic:{pid}",
                        )
                else:
                    for i, task in enumerate(kids):
                        is_last = i == len(kids) - 1
                        connector = "└─" if is_last else "├─"
                        self._render_task_row(
                            table,
                            task,
                            tree_prefix=connector,
                        )

    def _select_first_task_row(self) -> None:
        """Move cursor to the first actual task row with the header visible above."""
        table = self.query_one("#task-table", DataTable)
        for i, row in enumerate(table.ordered_rows):
            key = str(row.key.value)
            if key in self._row_key_to_task:
                # scroll=False prevents DataTable from auto-scrolling the cursor
                # to the top of the viewport, which would hide the header above.
                table.move_cursor(row=i, scroll=False)
                return

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

        # Use accurate DB counts when unfiltered, loaded counts when filtered
        is_filtered = bool(self._filter_text or self._epic_filter or self._hidden_statuses)
        if is_filtered or not self._true_status_counts:
            counts = {s: len(self._tasks_by_status.get(s, [])) for s in STATUS_ORDER}
        else:
            # Normalize raw DB statuses through aliases
            counts = dict.fromkeys(STATUS_ORDER, 0)
            for raw_status, cnt in self._true_status_counts.items():
                normalized = STATUS_ALIASES.get(raw_status, raw_status)
                counts[normalized] = counts.get(normalized, 0) + cnt
        parts: list[str] = []

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
            if self._filter_text or self._hidden_statuses:
                parts.append("[yellow]no matches[/yellow]")
            else:
                parts.append("[dim]no tasks[/dim]")

        # Mode indicators (separated from counts with │)
        mode_parts: list[str] = []

        if self._group_by == "status":
            mode_parts.append("[magenta]by status[/magenta]")

        if self._hidden_statuses:
            labels = [STATUS_LABELS.get(s, s) for s in sorted(self._hidden_statuses)]
            mode_parts.append(f"[magenta]hiding: {'+'.join(labels)}[/magenta]")

        if self._epic_filter:
            mode_parts.append(f"[cyan]epic: {self._epic_filter}[/cyan]")

        if self._filter_text:
            matched = sum(counts.values())
            total = len(self._tasks)
            mode_parts.append(f"[cyan]filter: {matched}/{total}[/cyan]")

        sections = [" · ".join(parts)] if parts else []
        if mode_parts:
            sections.append(" · ".join(mode_parts))
        status_bar.update(" │ ".join(sections))

    # ------------------------------------------------------------------
    # Filter logic
    # ------------------------------------------------------------------

    def _task_matches_filter(self, task: Task, query: str) -> bool:
        """Check if a task matches the filter query (case-insensitive substring)."""
        q = query.lower()
        fields = [
            task.title or "",
            task.epic_key or "",
            task.description or "",
        ]
        return any(q in f.lower() for f in fields)

    def _task_passes_filters(self, task: Task) -> bool:
        """Check if a task passes text, status, and epic filters."""
        if task.status in self._hidden_statuses:
            return False
        if self._epic_filter and task.epic_key != self._epic_filter:
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
            status = STATUS_ALIASES.get(task.status, task.status)
            self._tasks_by_status[status].append(task)
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
        """Block vim/action keys when filter input has focus.

        Also handles ``enter`` for collapse/expand since DataTable
        consumes it before BINDINGS can dispatch.
        """
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
                    "z",
                    "slash",
                    "1",
                    "2",
                    "3",
                    "o",
                    "i",
                    "x",
                    "f",
                    "asterisk",
                    "O",
                }
                if event.key in vim_keys:
                    return
        except Exception as e:
            logger.warning(
                "Failed to check focused widget for vim key passthrough: %s",
                e,
            )

        # Enter must be handled here because DataTable consumes it
        # before BINDINGS can dispatch.
        if event.key == "enter":
            self._toggle_collapse()
            event.prevent_default()
            event.stop()

    # ------------------------------------------------------------------
    # Status / epic / grouping filter actions
    # ------------------------------------------------------------------

    def _toggle_status_filter(self, statuses: set[str]) -> None:
        """Toggle visibility of specific statuses."""
        if statuses <= self._hidden_statuses:
            # Already hidden — show them
            self._hidden_statuses -= statuses
        else:
            # Currently visible — hide them
            self._hidden_statuses |= statuses
        self._apply_filter()

    def action_filter_open(self) -> None:
        """Toggle visibility of open/ready tasks."""
        self._toggle_status_filter({"open"})

    def action_filter_active(self) -> None:
        """Toggle visibility of active tasks."""
        self._toggle_status_filter({"active"})

    def action_filter_blocked(self) -> None:
        """Toggle visibility of blocked tasks."""
        self._toggle_status_filter({"blocked"})

    def action_filter_finished(self) -> None:
        """Toggle visibility of finished tasks (done/failed/wontdo/duplicate)."""
        self._toggle_status_filter({"done", "failed", "wontdo", "duplicate"})

    def action_clear_all_filters(self) -> None:
        """Clear all status and epic filters."""
        self._hidden_statuses = set()
        self._epic_filter = None
        self._apply_filter()

    def action_filter_epic(self) -> None:
        """Toggle epic filter to the current task's epic."""
        task = self._get_selected_task()
        epic_key = task.epic_key if task else None
        if epic_key and self._epic_filter != epic_key:
            self._epic_filter = epic_key
        else:
            self._epic_filter = None
        self._apply_filter()

    def action_toggle_grouping(self) -> None:
        """Toggle between epic and status grouping."""
        self._group_by = "epic" if self._group_by == "status" else "status"
        self._render_task_table()
        self._update_status_bar()

    def action_open_urls(self) -> None:
        """Open first URL found in the selected task."""
        self._open_task_urls()

    def action_toggle_collapse(self) -> None:
        """Toggle collapse state of the selected parent task."""
        self._toggle_collapse()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes with debouncing."""
        if event.input.id != "task-filter-input":
            return

        query = event.value

        # Cancel pending filter
        if self._debounce_timer:
            try:
                self._debounce_timer.stop()
            except Exception as e:
                logger.warning(f"Failed to stop debounce timer: {e}")
            self._debounce_timer = None

        def do_filter() -> None:
            self._debounce_timer = None
            self._filter_text = query
            self._apply_filter()

        self._debounce_timer = self.set_timer(0.2, do_filter)

    def _get_selected_task(self) -> Task | None:
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

    def _detail_content_width(self, detail_log: RichLog) -> int:
        """Return the usable content width of the detail RichLog.

        Uses ``scrollable_content_region`` which accounts for CSS padding,
        borders, AND the scrollbar gutter — matching what ``RichLog.write()``
        uses internally for its ``render_width``.
        """
        return max(30, detail_log.scrollable_content_region.width)

    def _write_wrapped(
        self,
        detail_log: RichLog,
        text: str,
        width: int,
        *,
        prefix: str = "",
        prefix_width: int = 0,
    ) -> None:
        """Write *text* to *detail_log*, pre-wrapped at *width*.

        If *prefix* is given it is prepended to every wrapped line, and
        *prefix_width* visible characters are subtracted from the available
        wrap width so that ``prefix + subline`` never exceeds *width*.
        """
        wrap_at = max(20, width - prefix_width)
        prefix_text = Text.from_markup(prefix) if prefix else None
        for line in text.split("\n"):
            if not line:
                detail_log.write(prefix if prefix else "")
                continue
            wrapped = textwrap.wrap(line, width=wrap_at) or [""]
            for subline in wrapped:
                linkified = _linkify_text(subline)
                if prefix_text is not None:
                    out = prefix_text.copy()
                    out.append_text(linkified)
                    detail_log.write(out)
                else:
                    detail_log.write(linkified)

    def _write_markdown_guttered(
        self,
        detail_log: RichLog,
        text: str,
        width: int,
        *,
        gutter: str = "  [dim]│[/dim] ",
        gutter_width: int = 4,
    ) -> None:
        """Render *text* as markdown, prefixing every output line with *gutter*.

        Renders the Markdown into a width-constrained Console, captures the
        ANSI output, then re-emits each line prefixed with the gutter as a
        ``Text`` object into the RichLog.  This preserves markdown styling
        (headings, bold, code blocks, lists) while keeping lines aligned to
        the right of the gutter — respecting the pre-wrap constraint from
        PR #881.

        Long unbreakable tokens (URLs) are hard-folded at *render_width* so
        they never overflow the gutter.
        """
        from emdx.ui.markdown_config import MarkdownConfig

        render_width = max(20, width - gutter_width)
        md = MarkdownConfig.create_markdown(text)

        # Render markdown into a string buffer with constrained width.
        # Use overflow="fold" so long URLs are hard-broken at render_width
        # instead of overflowing as a single unbroken line.
        buf = StringIO()
        console = RichConsole(file=buf, width=render_width, force_terminal=True, no_color=False)
        console.print(md, highlight=False, overflow="fold")
        rendered = buf.getvalue()

        # Strip the trailing newline that console.print always adds
        lines = rendered.rstrip("\n").split("\n")

        # Build the gutter prefix as a Text object for consistent joining
        gutter_text = Text.from_markup(gutter)

        for line in lines:
            content = Text.from_ansi(line)
            # Linkify URLs so they are clickable in the RichLog
            plain = content.plain
            if "http" in plain:
                content = _linkify_text(plain)
            # Safety: hard-break any line still wider than render_width
            chunks: list[Text] = []
            while content.cell_len > render_width:
                left = content[:render_width]
                content = content[render_width:]
                chunks.append(left)
            chunks.append(content)

            for chunk in chunks:
                prefixed = gutter_text.copy()
                prefixed.append_text(chunk)
                prefixed.overflow = "fold"
                detail_log.write(prefixed)

    def _render_task_detail(self, task: Task) -> None:
        """Render full task detail — routes metadata to sidebar or inline."""
        self._current_task = task

        # Epic tasks get a specialized view with child task listing
        if task.type == "epic":
            self._render_epic_detail(task)
            return

        try:
            detail_log = self.query_one("#task-detail-log", RichLog)
            header = self.query_one("#task-detail-header", Static)
        except Exception as e:
            logger.warning("_render_task_detail: detail widgets not found: %s", e)
            return

        detail_log.clear()

        icon = STATUS_ICONS.get(task.status, "?")
        badge = _task_badge(task)
        header_label = f"{icon} {badge}" if badge else f"{icon} Task"
        header.update(header_label)

        # Title (strip KEY-N prefix since badge already shows it)
        title = _strip_epic_prefix(task.title, task.epic_key, task.epic_seq)
        detail_log.write(f"[bold]{title}[/bold]")
        detail_log.write("")

        if self._sidebar_visible:
            # Wide: metadata in sidebar, content in detail pane
            try:
                sidebar_log = self.query_one("#task-sidebar-content", RichLog)
                sidebar_header = self.query_one("#task-sidebar-header", Static)
                sidebar_log.clear()
                sidebar_label = f"{icon} {badge}" if badge else f"{icon} Task"
                sidebar_header.update(sidebar_label)
                self._render_task_metadata(sidebar_log, task)
            except Exception as e:
                logger.warning("Sidebar not ready: %s", e)
        else:
            # Narrow: metadata inline in detail pane
            self._render_task_metadata(detail_log, task)
            detail_log.write("")
            detail_log.write("[dim]───[/dim]")

        self._render_task_content(detail_log, task)

    def _render_task_metadata(self, target: RichLog, task: Task) -> None:
        """Write task metadata (status, deps, blocks) to a RichLog target.

        Works for both the sidebar (30 cols) and the detail pane (full width).
        """
        # Status / Priority / Epic
        meta_parts: list[str] = []
        meta_parts.append(f"Status: [bold]{task.status}[/bold]")
        pri = task.priority
        if pri <= 1:
            meta_parts.append(f"Priority: [bold red]{pri} !!![/bold red]")
        elif pri <= 2:
            meta_parts.append(f"Priority: [yellow]{pri} !![/yellow]")
        else:
            meta_parts.append(f"Priority: {pri}")
        if task.epic_key:
            parent_id = task.parent_task_id
            epic = self._epics.get(parent_id) if parent_id else None
            if epic:
                done = epic.children_done
                total = epic.child_count
                meta_parts.append(f"Epic: [cyan]{task.epic_key}[/cyan] ({done}/{total} done)")
            else:
                meta_parts.append(f"Epic: [cyan]{task.epic_key}[/cyan]")
        target.write("  ".join(meta_parts))

        # Timestamps
        time_parts: list[str] = []
        if task.created_at:
            time_parts.append(f"Created {_format_time_ago(task.created_at)}")
        if task.updated_at:
            time_parts.append(f"Updated {_format_time_ago(task.updated_at)}")
        if task.completed_at:
            time_parts.append(f"Completed {_format_time_ago(task.completed_at)}")
        if time_parts:
            target.write(f"[dim]{' · '.join(time_parts)}[/dim]")

        # Dependencies
        try:
            deps = get_dependencies(task.id)
            if deps:
                target.write("")
                target.write("[bold]Depends on:[/bold]")
                for dep in deps:
                    dep_icon = STATUS_ICONS.get(dep.status, "?")
                    dep_badge = _task_badge(dep)
                    dep_label = f"{dep_badge} " if dep_badge else ""
                    target.write(f"  {dep_icon} {dep_label}{dep.title[:60]} [{dep.status}]")
        except Exception as e:
            logger.debug(f"Error loading dependencies: {e}")

        try:
            dependents = get_dependents(task.id)
            if dependents:
                target.write("")
                target.write("[bold]Blocks:[/bold]")
                for dep in dependents:
                    dep_icon = STATUS_ICONS.get(dep.status, "?")
                    dep_badge = _task_badge(dep)
                    dep_label = f"{dep_badge} " if dep_badge else ""
                    target.write(f"  {dep_icon} {dep_label}{dep.title[:60]} [{dep.status}]")
        except Exception as e:
            logger.debug(f"Error loading dependents: {e}")

    def _render_task_content(self, target: RichLog, task: Task) -> None:
        """Write task content (description, error, work log) to a RichLog target."""
        content_w = self._detail_content_width(target)

        # Description
        desc = task.description or ""
        if desc:
            target.write("")
            target.write("[bold]Description:[/bold]")
            self._write_markdown_guttered(target, desc, content_w, gutter="", gutter_width=0)

        # Work log
        try:
            log_entries: list[TaskLogEntry] = get_task_log(task.id, limit=20)
            if log_entries:
                target.write("")
                target.write("[bold]Work Log:[/bold]")
                gutter = "  [dim]│[/dim] "
                gutter_width = 4
                last = len(log_entries) - 1
                for i, entry in enumerate(log_entries):
                    raw_ts = entry.created_at
                    time_str = _format_time_ago(raw_ts)
                    ts_part = f" {time_str}" if time_str else ""
                    target.write(f"  [bold cyan]●[/bold cyan] [dim]{ts_part}[/dim]")
                    self._write_markdown_guttered(
                        target,
                        entry.message,
                        content_w,
                        gutter=gutter,
                        gutter_width=gutter_width,
                    )
                    if i < last:
                        target.write("  [dim]│[/dim]")
                    else:
                        target.write("  [dim]╵[/dim]")
        except Exception as e:
            logger.debug(f"Error loading task log: {e}")

    def _render_epic_detail(self, task: Task) -> None:
        """Render epic detail with child task listing in the right pane."""
        detail_log = self.query_one("#task-detail-log", RichLog)
        header = self.query_one("#task-detail-header", Static)
        detail_log.clear()

        icon = STATUS_ICONS.get(task.status, "?")
        badge = _task_badge(task)
        epic_header = f"{icon} {badge}" if badge else f"{icon} Epic"
        header.update(epic_header)

        # Title (strip KEY-N prefix since badge already shows it)
        title = _strip_epic_prefix(task.title, task.epic_key, task.epic_seq)
        detail_log.write(f"[bold]{title}[/bold]")
        detail_log.write("")

        # Progress summary from cached epic data
        epic_key = task.epic_key
        epic_data = self._epics.get(task.id)
        if epic_data:
            done = epic_data.children_done
            total = epic_data.child_count
            open_count = epic_data.children_open
            pct = int(done / total * 100) if total > 0 else 0
            bar_len = 20
            filled = int(bar_len * done / total) if total > 0 else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            detail_log.write(f"[bold]Progress:[/bold] {bar} {pct}%")
            detail_log.write(f"  [green]{done} done[/green] · {open_count} open · {total} total")
        else:
            detail_log.write(f"Status: [bold]{task.status}[/bold]")

        # Description
        content_w = self._detail_content_width(detail_log)
        epic_desc = task.description or ""
        if epic_desc:
            detail_log.write("")
            detail_log.write("[bold]Description:[/bold]")
            self._write_markdown_guttered(
                detail_log, epic_desc, content_w, gutter="", gutter_width=0
            )

        # Load and display child tasks
        try:
            epic_view = get_epic_view(task.id)
            if epic_view and epic_view.children:
                detail_log.write("")
                detail_log.write("[bold]Tasks:[/bold]")
                for child in epic_view.children:
                    c_icon = STATUS_ICONS.get(child.status, "?")
                    c_color = STATUS_COLORS.get(child.status, "")
                    c_title = _strip_epic_prefix(child.title, child.epic_key, child.epic_seq)[:55]
                    seq = child.epic_seq
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
        if task.created_at:
            time_parts.append(f"Created {_format_time_ago(task.created_at)}")
        if task.updated_at:
            time_parts.append(f"Updated {_format_time_ago(task.updated_at)}")
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

    def _refresh_data_tick(self) -> None:
        """Sync callback for set_interval — dispatches to async refresh."""
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        self.run_worker(self._refresh_data(), exclusive=True, group="refresh")

    async def _refresh_data(self) -> None:
        """Periodic refresh of task data."""
        try:
            await self._load_tasks()
        except Exception as e:
            logger.warning(f"Auto-refresh failed: {e}")
        finally:
            self._refresh_in_progress = False

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

    def action_toggle_zoom(self) -> None:
        """Cycle zoom: normal -> content full-screen -> list full-screen -> normal."""
        list_panel = self.query_one("#task-list-panel")
        detail_panel = self.query_one("#task-detail-panel")

        if not self._zoomed:
            # Normal -> zoom content (list hidden, detail full)
            self._zoomed = True
            list_panel.add_class("zoom-content")
            detail_panel.add_class("zoom-content")
            self.query_one("#task-detail-log", RichLog).focus()
        elif list_panel.has_class("zoom-content"):
            # Zoom content -> zoom list (detail hidden, list full)
            list_panel.remove_class("zoom-content")
            detail_panel.remove_class("zoom-content")
            list_panel.add_class("zoom-list")
            detail_panel.add_class("zoom-list")
            self.query_one("#task-table", DataTable).focus()
        else:
            # Zoom list -> normal
            self._zoomed = False
            list_panel.remove_class("zoom-list")
            detail_panel.remove_class("zoom-list")
            self.query_one("#task-table", DataTable).focus()

    def action_focus_next(self) -> None:
        """Toggle focus between filter and table."""
        if self._zoomed:
            return
        self._toggle_filter_focus()

    def action_focus_prev(self) -> None:
        """Toggle focus between filter and table."""
        if self._zoomed:
            return
        self._toggle_filter_focus()

    # Collapse/expand

    def _toggle_collapse(self) -> None:
        """Toggle collapse state of the selected parent task or done-fold."""
        # Check if cursor is on a done-fold row
        table = self.query_one("#task-table", DataTable)
        try:
            if table.cursor_row is not None and table.row_count > 0:
                row_key = str(table.ordered_rows[table.cursor_row].key.value)
                if row_key.startswith(DONE_FOLD_PREFIX):
                    suffix = row_key[len(DONE_FOLD_PREFIX) :]
                    # "done-fold:epic:N" = done-epics section fold
                    if suffix.startswith("epic:"):
                        epic_id = int(suffix[len("epic:") :])
                        # Toggle in _collapsed (controls done-epic expand)
                        if epic_id in self._collapsed:
                            self._collapsed.discard(epic_id)
                            self._expanded.add(epic_id)
                            self._ensure_done_tasks_loaded(epic_id)
                        else:
                            self._collapsed.add(epic_id)
                            self._expanded.discard(epic_id)
                    else:
                        # "done-fold:N" = active-epic done children fold
                        epic_id = int(suffix)
                        if epic_id in self._done_folds_expanded:
                            self._done_folds_expanded.discard(epic_id)
                        else:
                            self._done_folds_expanded.add(epic_id)
                            self._ensure_done_tasks_loaded(epic_id)
                    self._render_task_table()
                    return
        except (IndexError, AttributeError, ValueError):
            pass

        task = self._get_selected_task()
        if not task:
            return
        tid = task.id
        # Toggle: if currently shown as collapsed, expand; otherwise collapse
        if tid in self._collapsed:
            self._collapsed.discard(tid)
            self._expanded.add(tid)
        elif tid in self._expanded:
            self._expanded.discard(tid)
            self._collapsed.add(tid)
        else:
            # First toggle — default state depends on context;
            # just collapse it (active parents default to expanded)
            self._collapsed.add(tid)
        self._render_task_table()

    # Status mutation actions

    async def _set_task_status(self, new_status: str) -> None:
        """Change status of the selected task and refresh.

        Cursor stays at the same row position (not following the task
        into its new status group).
        """
        task = self._get_selected_task()
        if not task:
            return
        if task.status == new_status:
            return

        # Save row index — we want to stay at this position
        table = self.query_one("#task-table", DataTable)
        saved_row = table.cursor_row

        try:
            update_task(task.id, status=new_status)
            badge = _task_badge(task)
            label = badge if badge else task.title[:30]
            self.notify(f"{label} → {new_status}", timeout=2)
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

    async def action_mark_duplicate(self) -> None:
        """Mark selected task as duplicate."""
        await self._set_task_status("duplicate")

    async def action_mark_open(self) -> None:
        """Reopen a task (mark as open/ready)."""
        await self._set_task_status("open")

    # ------------------------------------------------------------------
    # URL opening (keyboard Shift+O)
    # ------------------------------------------------------------------

    def _open_task_urls(self) -> None:
        """Open first URL found in the selected task (Shift+O shortcut)."""
        task = self._get_selected_task()
        if not task:
            return
        urls: list[str] = []
        for field in ("description", "error"):
            val = getattr(task, field, None)
            if isinstance(val, str) and val:
                urls.extend(_extract_urls(val))
        if not urls:
            self.notify("No URLs in this task", timeout=2)
            return
        import webbrowser

        webbrowser.open(urls[0])
        if len(urls) > 1:
            self.notify(f"Opened 1 of {len(urls)} URLs", timeout=2)
        else:
            self.notify(f"Opened {urls[0][:60]}", timeout=2)
