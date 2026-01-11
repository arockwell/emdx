"""Task browser - view and manage tasks with dependencies."""

import logging
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.models import tasks

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


class TaskBrowser(Widget):
    """Task-focused browser showing all tasks with dependencies."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "select", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("a", "toggle_filter", "Filter"),
        Binding("1", "filter_open", "Open"),
        Binding("2", "filter_active", "Active"),
        Binding("3", "filter_blocked", "Blocked"),
        Binding("4", "filter_done", "Done"),
        Binding("0", "filter_all", "All"),
    ]

    DEFAULT_CSS = """
    TaskBrowser {
        layout: vertical;
        height: 100%;
    }

    #task-main {
        layout: horizontal;
        height: 1fr;
    }

    #task-list-panel {
        width: 55%;
        height: 100%;
        border-right: solid $primary;
    }

    #task-detail-panel {
        width: 45%;
        height: 100%;
    }

    .panel-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    #task-table {
        height: 1fr;
    }

    #task-detail {
        height: 100%;
        padding: 1;
    }

    #task-status {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.task_list: List[Dict[str, Any]] = []
        self.selected_task: Optional[Dict[str, Any]] = None
        self.status_filter: Optional[List[str]] = ['open', 'active', 'blocked']  # Default: not done

    def compose(self) -> ComposeResult:
        with Horizontal(id="task-main"):
            with Vertical(id="task-list-panel"):
                yield Static("📋 TASKS", id="task-header", classes="panel-header")
                yield DataTable(id="task-table", cursor_type="row")

            with Vertical(id="task-detail-panel"):
                yield Static("TASK DETAILS", classes="panel-header")
                with ScrollableContainer():
                    yield Static("", id="task-detail")

        yield Static("", id="task-status")

    async def on_mount(self) -> None:
        """Setup table and load data."""
        table = self.query_one("#task-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("ID", width=5)
        table.add_column("Title", width=30)
        table.add_column("P", width=2)  # Priority
        table.add_column("Deps", width=5)  # Dependencies
        table.add_column("GP", width=5)  # Gameplan

        await self._load_tasks()
        self._update_status()
        table.focus()

    async def _load_tasks(self) -> None:
        """Load tasks with current filter."""
        table = self.query_one("#task-table", DataTable)
        table.clear()

        try:
            self.task_list = tasks.list_tasks(status=self.status_filter, limit=100)

            if not self.task_list:
                table.add_row("", "", "[dim]No tasks found[/dim]", "", "", "")
                self._update_header()
                return

            for t in self.task_list:
                icon = ICONS.get(t['status'], '?')

                # Get dependency info
                deps = tasks.get_dependencies(t['id'])
                dep_count = len(deps)
                deps_done = sum(1 for d in deps if d['status'] == 'done')

                if dep_count == 0:
                    dep_str = "—"
                elif deps_done == dep_count:
                    dep_str = f"[green]{deps_done}/{dep_count}[/green]"
                else:
                    dep_str = f"[yellow]{deps_done}/{dep_count}[/yellow]"

                # Title with status coloring
                title = t['title'][:28] if len(t['title']) > 28 else t['title']
                if t['status'] == 'done':
                    title = f"[dim]{title}[/dim]"
                elif t['status'] == 'blocked':
                    title = f"[yellow]{title}[/yellow]"
                elif t['status'] == 'active':
                    title = f"[green]{title}[/green]"

                # Gameplan
                gp_str = f"#{t['gameplan_id']}" if t.get('gameplan_id') else "—"

                table.add_row(
                    icon,
                    str(t['id']),
                    title,
                    str(t['priority']),
                    dep_str,
                    gp_str
                )

            self._update_header()

            # Select first row
            if self.task_list:
                table.move_cursor(row=0)

        except Exception as e:
            logger.error(f"Error loading tasks: {e}", exc_info=True)
            table.add_row("", "", f"[red]Error: {e}[/red]", "", "", "")

    def _update_header(self) -> None:
        """Update header with count info."""
        header = self.query_one("#task-header", Static)

        if self.status_filter is None:
            filter_text = "all"
        else:
            filter_text = ", ".join(self.status_filter)

        header.update(f"📋 TASKS ({len(self.task_list)}) - {filter_text}")

    def _update_detail(self) -> None:
        """Update the detail panel for selected task."""
        detail = self.query_one("#task-detail", Static)

        if not self.selected_task:
            detail.update("[dim]Select a task to see details[/dim]")
            return

        t = self.selected_task

        # Status with icon
        status_display = f"{ICONS.get(t['status'], '?')} {t['status']}"
        if t['status'] == 'active':
            status_display = f"[green]{status_display}[/green]"
        elif t['status'] == 'blocked':
            status_display = f"[yellow]{status_display}[/yellow]"
        elif t['status'] == 'done':
            status_display = f"[dim]{status_display}[/dim]"

        lines = [
            f"[bold]#{t['id']} {t['title']}[/bold]",
            "",
            f"Status: {status_display}",
            f"Priority: {t['priority']}",
        ]

        # Gameplan
        if t.get('gameplan_id'):
            lines.append(f"Gameplan: #{t['gameplan_id']}")

        # Project
        if t.get('project'):
            lines.append(f"Project: {t['project']}")

        # Description
        if t.get('description'):
            lines.append("")
            lines.append("[bold]Description:[/bold]")
            lines.append(t['description'][:500])

        # Dependencies
        deps = tasks.get_dependencies(t['id'])
        if deps:
            lines.append("")
            lines.append(f"[bold]Dependencies ({len(deps)}):[/bold]")
            for d in deps:
                dep_icon = ICONS.get(d['status'], '?')
                dep_status = d['status']
                if dep_status == 'done':
                    lines.append(f"  [dim]{dep_icon} #{d['id']} {d['title'][:30]}[/dim]")
                elif dep_status == 'active':
                    lines.append(f"  [green]{dep_icon} #{d['id']} {d['title'][:30]}[/green]")
                elif dep_status == 'blocked':
                    lines.append(f"  [yellow]{dep_icon} #{d['id']} {d['title'][:30]}[/yellow]")
                else:
                    lines.append(f"  {dep_icon} #{d['id']} {d['title'][:30]}")

        # Blocked by (tasks that depend on this one)
        try:
            blocked_by = tasks.get_dependents(t['id'])
            if blocked_by:
                lines.append("")
                lines.append(f"[bold]Blocks ({len(blocked_by)}):[/bold]")
                for b in blocked_by[:5]:  # Limit to 5
                    b_icon = ICONS.get(b['status'], '?')
                    lines.append(f"  {b_icon} #{b['id']} {b['title'][:30]}")
                if len(blocked_by) > 5:
                    lines.append(f"  ... and {len(blocked_by) - 5} more")
        except Exception:
            pass  # get_dependents might not exist

        # Created
        if t.get('created_at'):
            created = t['created_at']
            if hasattr(created, 'strftime'):
                created = created.strftime('%Y-%m-%d %H:%M')
            lines.append("")
            lines.append(f"[dim]Created: {created}[/dim]")

        detail.update("\n".join(lines))

    def _update_status(self) -> None:
        """Update status bar."""
        status = self.query_one("#task-status", Static)

        # Count ready tasks
        try:
            ready = tasks.get_ready_tasks()
            ready_text = f"{len(ready)} ready"
        except Exception:
            ready_text = ""

        # Filter info
        if self.status_filter is None:
            filter_text = "all"
        else:
            filter_text = "+".join(self.status_filter)

        status.update(
            f"{ready_text} | Filter: {filter_text} | "
            "0=all 1=open 2=active 3=blocked 4=done | r=refresh | q=back"
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail when selection changes."""
        if event.cursor_row is not None and event.cursor_row < len(self.task_list):
            self.selected_task = self.task_list[event.cursor_row]
            self._update_detail()

    def action_cursor_down(self) -> None:
        self.query_one("#task-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#task-table", DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#task-table", DataTable)
        if self.task_list:
            table.move_cursor(row=len(self.task_list) - 1)

    def action_select(self) -> None:
        """Select current task (placeholder for future actions)."""
        if self.selected_task:
            self.notify(f"Task #{self.selected_task['id']}: {self.selected_task['title']}")

    async def action_refresh(self) -> None:
        await self._load_tasks()
        self._update_status()

    def action_toggle_filter(self) -> None:
        """Toggle between active filter modes."""
        if self.status_filter is None:
            self.status_filter = ['open', 'active', 'blocked']
        elif self.status_filter == ['open', 'active', 'blocked']:
            self.status_filter = ['active']
        elif self.status_filter == ['active']:
            self.status_filter = None
        else:
            self.status_filter = ['open', 'active', 'blocked']

        self.call_later(self._load_tasks)
        self._update_status()

    def action_filter_all(self) -> None:
        self.status_filter = None
        self.call_later(self._load_tasks)
        self._update_status()

    def action_filter_open(self) -> None:
        self.status_filter = ['open']
        self.call_later(self._load_tasks)
        self._update_status()

    def action_filter_active(self) -> None:
        self.status_filter = ['active']
        self.call_later(self._load_tasks)
        self._update_status()

    def action_filter_blocked(self) -> None:
        self.status_filter = ['blocked']
        self.call_later(self._load_tasks)
        self._update_status()

    def action_filter_done(self) -> None:
        self.status_filter = ['done']
        self.call_later(self._load_tasks)
        self._update_status()
