"""Task View — read-only task browser with two-pane layout.

Left pane: OptionList with tasks grouped by status (ready, active, blocked, done)
Right pane: RichLog with selected task detail (description, deps, log, executions)
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import OptionList, RichLog, Static
from textual.widgets.option_list import Option

from emdx.models.tasks import (
    get_dependencies,
    get_dependents,
    get_task_log,
    list_epics,
    list_tasks,
)
from emdx.models.types import TaskDict, TaskLogEntryDict

logger = logging.getLogger(__name__)

# Status display order and icons
STATUS_ORDER = ["open", "active", "blocked", "done", "failed"]
STATUS_ICONS = {
    "open": "○",
    "active": "●",
    "blocked": "⚠",
    "done": "✓",
    "failed": "✗",
}
STATUS_LABELS = {
    "open": "READY",
    "active": "ACTIVE",
    "blocked": "BLOCKED",
    "done": "DONE",
    "failed": "FAILED",
}


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


def _task_label(task: TaskDict) -> str:
    """Build a compact label for the OptionList: icon + key + title."""
    icon = STATUS_ICONS.get(task["status"], "?")
    title = task["title"]
    # Truncate long titles
    if len(title) > 50:
        title = title[:47] + "..."
    return f"{icon} {title}"


class TaskView(Widget):
    """Two-pane task browser view."""

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("r", "refresh", "Refresh"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
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

    #task-option-list {
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tasks: list[TaskDict] = []
        self._tasks_by_status: dict[str, list[TaskDict]] = defaultdict(list)
        self._option_id_to_task: dict[str, TaskDict] = {}
        self._epics: dict[str | None, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Static("Loading tasks...", id="task-status-bar")
        with Horizontal(id="task-main"):
            with Vertical(id="task-list-panel"):
                yield Static("TASKS", id="task-list-header")
                yield OptionList(id="task-option-list")
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
        await self._load_tasks()
        self.query_one("#task-option-list", OptionList).focus()

    async def _load_tasks(self) -> None:
        """Load all manual tasks from the database."""
        try:
            self._tasks = list_tasks(exclude_delegate=True, limit=200)
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")
            self._tasks = []

        # Load epics for reference
        try:
            epics = list_epics()
            self._epics = {e.get("epic_key"): e for e in epics}
        except Exception as e:
            logger.error(f"Failed to load epics: {e}")
            self._epics = {}

        # Group by status
        self._tasks_by_status = defaultdict(list)
        for task in self._tasks:
            self._tasks_by_status[task["status"]].append(task)

        self._render_task_list()
        self._update_status_bar()

    def _render_task_list(self) -> None:
        """Render the grouped task list into the OptionList."""
        option_list = self.query_one("#task-option-list", OptionList)
        option_list.clear_options()
        self._option_id_to_task = {}

        first_option_added = False

        for status in STATUS_ORDER:
            tasks = self._tasks_by_status.get(status, [])
            if not tasks:
                continue

            label = STATUS_LABELS.get(status, status.upper())

            # Add blank line separator before groups (except the first)
            if first_option_added:
                option_list.add_option(Option("", disabled=True))

            # Section header as a disabled option
            option_list.add_option(
                Option(f"[bold]{label} ({len(tasks)})[/bold]", disabled=True)
            )

            for task in tasks:
                opt_id = f"task-{task['id']}"
                self._option_id_to_task[opt_id] = task
                option_list.add_option(
                    Option(f"  {_task_label(task)}", id=opt_id)
                )
                first_option_added = True

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

        if not any(counts.values()):
            parts.append("[dim]no tasks[/dim]")

        status_bar.update(" · ".join(parts))

    def _get_selected_task(self) -> TaskDict | None:
        """Get the currently highlighted task."""
        option_list = self.query_one("#task-option-list", OptionList)
        if option_list.highlighted is None:
            return None
        try:
            option = option_list.get_option_at_index(option_list.highlighted)
            if option and option.id:
                return self._option_id_to_task.get(option.id)
        except Exception:
            pass
        return None

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """Update detail pane when a task is highlighted."""
        if event.option_list.id != "task-option-list":
            return
        task = self._get_selected_task()
        if task:
            self._render_task_detail(task)

    def _render_task_detail(self, task: TaskDict) -> None:
        """Render full task detail in the right pane."""
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
            epic = self._epics.get(task["epic_key"])
            if epic:
                done = epic.get("children_done", 0)
                total = epic.get("child_count", 0)
                meta_parts.append(
                    f"Epic: {task['epic_key']} ({done}/{total} done)"
                )
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
            time_parts.append(
                f"Completed {_format_time_ago(task['completed_at'])}"
            )
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
                        f"  {dep_icon} #{dep['id']} {dep['title'][:60]}"
                        f" [{dep['status']}]"
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
                        f"  {dep_icon} #{dep['id']} {dep['title'][:60]}"
                        f" [{dep['status']}]"
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
            log_entries: list[TaskLogEntryDict] = get_task_log(
                task["id"], limit=20
            )
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
            detail_log.write(
                f"[bold]Execution:[/bold] #{task['execution_id']}"
            )
        if task.get("output_doc_id"):
            detail_log.write(f"Output doc: #{task['output_doc_id']}")

    # Actions

    def action_cursor_down(self) -> None:
        option_list = self.query_one("#task-option-list", OptionList)
        option_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        option_list = self.query_one("#task-option-list", OptionList)
        option_list.action_cursor_up()

    async def action_refresh(self) -> None:
        """Reload tasks from database."""
        await self._load_tasks()

    def action_focus_next(self) -> None:
        pass

    def action_focus_prev(self) -> None:
        pass
