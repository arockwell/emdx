"""Delegate View — monitor running and recent delegates.

Left pane: DataTable with delegates grouped by status (ACTIVE, RECENT, FAILED)
Right pane: RichLog with selected delegate detail (prompt, subtasks, output doc)
"""

import logging
from datetime import datetime, timezone
from typing import Any

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.models.tasks import (
    get_active_delegate_tasks,
    get_children,
    get_failed_tasks,
    get_recent_completed_tasks,
)
from emdx.models.types import TaskDict

logger = logging.getLogger(__name__)

# Section header row key prefix
HEADER_PREFIX = "header:"

STATUS_ICONS = {
    "open": "○",
    "active": "●",
    "blocked": "⚠",
    "done": "✓",
    "failed": "✗",
    "wontdo": "⊘",
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
        if dt.year == now.year:
            return dt.strftime("%b %d")
        return dt.strftime("%b %d, %Y")
    except Exception:
        return ""


class DelegateView(Widget):
    """Two-pane delegate monitor view."""

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("r", "refresh", "Refresh"),
        ("z", "toggle_zoom", "Zoom"),
    ]

    DEFAULT_CSS = """
    DelegateView {
        layout: vertical;
        height: 100%;
    }

    #delegate-status-bar {
        height: 1;
        background: $boost;
        padding: 0 1;
    }

    #delegate-main {
        height: 1fr;
    }

    #delegate-list-panel {
        height: 40%;
        width: 100%;
    }

    #delegate-list-section {
        width: 100%;
    }

    #delegate-detail-panel {
        height: 60%;
        width: 100%;
        border-top: solid $primary;
    }

    #delegate-list-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #delegate-table {
        height: 1fr;
        scrollbar-size: 1 1;
    }

    #delegate-detail-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #delegate-detail-content {
        padding: 0 1;
    }

    /* Zoom: list hidden */
    #delegate-list-panel.zoom-content {
        display: none;
    }
    #delegate-detail-panel.zoom-content {
        height: 100%;
        border-top: none;
    }

    /* Zoom: detail hidden */
    #delegate-detail-panel.zoom-list {
        display: none;
    }
    #delegate-list-panel.zoom-list {
        height: 100%;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._row_data: dict[str, TaskDict] = {}
        self._refresh_timer: Timer | None = None
        self._refresh_in_progress = False
        self._zoom_state = "none"  # none, list, content

    def compose(self) -> ComposeResult:
        yield Static("", id="delegate-status-bar")
        with Vertical(id="delegate-main"):
            with Vertical(id="delegate-list-panel"):
                with Vertical(id="delegate-list-section"):
                    yield Static(
                        "[bold]Delegates[/bold]",
                        id="delegate-list-header",
                    )
                    dt: DataTable[str] = DataTable(id="delegate-table")
                    dt.cursor_type = "row"
                    dt.zebra_stripes = True
                    yield dt
            with Vertical(id="delegate-detail-panel"):
                yield Static(
                    "[bold]Detail[/bold]",
                    id="delegate-detail-header",
                )
                yield RichLog(
                    id="delegate-detail-content",
                    wrap=True,
                    markup=True,
                )

    def on_mount(self) -> None:
        """Set up table columns and load initial data."""
        table = self.query_one("#delegate-table", DataTable)
        table.add_columns("", "Task", "Progress", "Updated")
        self._load_data()
        self._refresh_timer = self.set_interval(5.0, self._periodic_refresh)

    def _periodic_refresh(self) -> None:
        """Auto-refresh if there are active delegates."""
        if self._refresh_in_progress:
            return
        self._load_data()

    def _load_data(self) -> None:
        """Load delegate data into the table."""
        self._refresh_in_progress = True
        try:
            table = self.query_one("#delegate-table", DataTable)

            # Save current selection so we can restore it after refresh
            selected_key: str | None = None
            try:
                if table.row_count > 0:
                    cursor_row = table.cursor_row
                    row_keys = list(table.rows.keys())
                    if 0 <= cursor_row < len(row_keys):
                        selected_key = str(row_keys[cursor_row].value)
            except Exception:
                pass

            table.clear()
            self._row_data.clear()

            active = get_active_delegate_tasks()
            recent = get_recent_completed_tasks(limit=10)
            failed = get_failed_tasks(limit=5)

            active_count = len(active)

            # ACTIVE section
            if active:
                table.add_row(
                    Text("", style="bold green"),
                    Text(f"ACTIVE ({len(active)})", style="bold green"),
                    Text("", style="dim"),
                    Text("", style="dim"),
                    key=f"{HEADER_PREFIX}active",
                )
                for atask in active:
                    key = f"task:{atask['id']}"
                    self._row_data[key] = atask
                    icon = Text("●", style="green")
                    title = atask["title"][:60]
                    child_count = atask.get("child_count", 0)
                    children_done = atask.get("children_done", 0)
                    if child_count > 0:
                        progress = f"{children_done}/{child_count}"
                    else:
                        progress = "—"
                    updated = _format_time_ago(atask.get("updated_at"))
                    table.add_row(icon, title, progress, updated, key=key)

            # RECENT section
            if recent:
                table.add_row(
                    Text("", style="dim"),
                    Text(f"RECENT ({len(recent)})", style="bold"),
                    Text("", style="dim"),
                    Text("", style="dim"),
                    key=f"{HEADER_PREFIX}recent",
                )
                for task in recent:
                    key = f"task:{task['id']}"
                    self._row_data[key] = task
                    icon = Text("✓", style="green dim")
                    title = task["title"][:60]
                    updated = _format_time_ago(task.get("completed_at") or task.get("updated_at"))
                    table.add_row(
                        icon,
                        Text(title, style="dim"),
                        Text("done", style="dim"),
                        Text(updated, style="dim"),
                        key=key,
                    )

            # FAILED section
            if failed:
                table.add_row(
                    Text("", style="red"),
                    Text(f"FAILED ({len(failed)})", style="bold red"),
                    Text("", style="dim"),
                    Text("", style="dim"),
                    key=f"{HEADER_PREFIX}failed",
                )
                for task in failed:
                    key = f"task:{task['id']}"
                    self._row_data[key] = task
                    icon = Text("✗", style="red")
                    title = task["title"][:60]
                    error = (task.get("error") or "")[:30]
                    updated = _format_time_ago(task.get("updated_at"))
                    table.add_row(
                        icon,
                        Text(title, style="red"),
                        Text(error, style="red dim"),
                        Text(updated, style="dim"),
                        key=key,
                    )

            if not active and not recent and not failed:
                table.add_row(
                    Text(""),
                    Text("No delegate activity", style="dim italic"),
                    Text(""),
                    Text(""),
                    key=f"{HEADER_PREFIX}empty",
                )

            # Restore cursor to previously selected row
            if selected_key and table.row_count > 0:
                try:
                    row_keys = list(table.rows.keys())
                    for idx, rk in enumerate(row_keys):
                        if str(rk.value) == selected_key:
                            table.move_cursor(row=idx)
                            break
                except Exception:
                    pass

            # Update status bar
            status_bar = self.query_one("#delegate-status-bar", Static)
            status_bar.update(
                f"[bold]{active_count}[/bold] active │ "
                f"[dim]{len(recent)}[/dim] recent │ "
                f"[dim]{len(failed)}[/dim] failed"
            )

        except Exception as e:
            logger.error(f"Failed to load delegate data: {e}", exc_info=True)
        finally:
            self._refresh_in_progress = False

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show detail for highlighted row."""
        if event.row_key is None:
            return
        key = str(event.row_key.value)
        if key.startswith(HEADER_PREFIX):
            return
        task = self._row_data.get(key)
        if task:
            self._show_detail(task)

    def _show_detail(self, task: TaskDict) -> None:
        """Render task detail in the right pane."""
        detail = self.query_one("#delegate-detail-content", RichLog)
        detail.clear()

        # Title
        status = task["status"]
        icon = STATUS_ICONS.get(status, "?")
        title_text = Text(f"{icon} {task['title']}", style="bold")
        detail.write(title_text)
        detail.write("")

        # Status + timestamps
        detail.write(Text(f"Status: {status}", style="dim"))
        if task.get("created_at"):
            detail.write(
                Text(
                    f"Created: {_format_time_ago(task.get('created_at'))}",
                    style="dim",
                )
            )
        if task.get("updated_at"):
            detail.write(
                Text(
                    f"Updated: {_format_time_ago(task.get('updated_at'))}",
                    style="dim",
                )
            )
        if task.get("completed_at"):
            detail.write(
                Text(
                    f"Completed: {_format_time_ago(task.get('completed_at'))}",
                    style="dim",
                )
            )

        # Prompt
        prompt = task.get("prompt")
        if prompt:
            detail.write("")
            detail.write(Text("Prompt:", style="bold"))
            # Truncate long prompts
            display_prompt = prompt if len(prompt) <= 500 else prompt[:500] + "..."
            detail.write(display_prompt)

        # Error
        error = task.get("error")
        if error:
            detail.write("")
            detail.write(Text(f"Error: {error}", style="bold red"))

        # Output document link
        output_doc_id = task.get("output_doc_id")
        if output_doc_id:
            detail.write("")
            link_style = Style(
                underline=True,
                color="bright_cyan",
            ) + Style(meta={"@click": f"app.select_doc({output_doc_id})"})
            doc_link = Text(f"Output: doc #{output_doc_id}", style=link_style)
            detail.write(doc_link)

        # Subtask tree
        task_id = task["id"]
        try:
            children = get_children(task_id)
            if children:
                detail.write("")
                detail.write(Text("Subtasks:", style="bold"))
                for i, child in enumerate(children):
                    is_last = i == len(children) - 1
                    connector = "└─" if is_last else "├─"
                    child_icon = STATUS_ICONS.get(child["status"], "?")
                    child_title = child["title"][:60]
                    child_line = Text(f"  {connector} {child_icon} {child_title}")
                    color = {
                        "done": "green dim",
                        "active": "green",
                        "failed": "red",
                        "open": "",
                    }.get(child["status"], "dim")
                    if color:
                        child_line.stylize(color)
                    detail.write(child_line)
        except Exception:
            pass  # Never crash on subtask display

    def action_cursor_down(self) -> None:
        """Move cursor down, skipping headers."""
        table = self.query_one("#delegate-table", DataTable)
        table.action_cursor_down()
        self._skip_header_rows("down")

    def action_cursor_up(self) -> None:
        """Move cursor up, skipping headers."""
        table = self.query_one("#delegate-table", DataTable)
        table.action_cursor_up()
        self._skip_header_rows("up")

    def _skip_header_rows(self, direction: str) -> None:
        """Skip header rows when navigating."""
        table = self.query_one("#delegate-table", DataTable)
        row_count = table.row_count
        if row_count == 0:
            return
        attempts = 0
        while attempts < row_count:
            try:
                cursor_row = table.cursor_row
                if cursor_row < len(table.rows):
                    row_key_obj = list(table.rows.keys())[cursor_row]
                    key_str = str(row_key_obj.value)
                    if key_str.startswith(HEADER_PREFIX):
                        if direction == "down":
                            table.action_cursor_down()
                        else:
                            table.action_cursor_up()
                        attempts += 1
                        continue
            except Exception:
                pass
            break

    def action_refresh(self) -> None:
        """Manual refresh."""
        self._load_data()

    def action_toggle_zoom(self) -> None:
        """Cycle zoom: none → list → content → none."""
        list_panel = self.query_one("#delegate-list-panel")
        detail_panel = self.query_one("#delegate-detail-panel")

        # Clear previous zoom classes
        list_panel.remove_class("zoom-content", "zoom-list")
        detail_panel.remove_class("zoom-content", "zoom-list")

        if self._zoom_state == "none":
            self._zoom_state = "content"
            list_panel.add_class("zoom-content")
            detail_panel.add_class("zoom-content")
        elif self._zoom_state == "content":
            self._zoom_state = "list"
            list_panel.add_class("zoom-list")
            detail_panel.add_class("zoom-list")
        else:
            self._zoom_state = "none"
