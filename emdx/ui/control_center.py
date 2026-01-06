"""Control center browser - task and gameplan view."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.models import tasks
from emdx.models.tags import search_by_tags

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


class ControlCenterBrowser(Widget):
    """Task and gameplan browser."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("tab", "switch_panel", "Switch"),
        Binding("enter", "select", "Select"),
        Binding("n", "new_task", "New Task"),
        Binding("a", "toggle_active", "Active Only"),
        Binding("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    ControlCenterBrowser {
        layout: vertical;
        height: 100%;
    }

    #cc-main {
        height: 1fr;
    }

    #cc-left {
        width: 50%;
        border-right: solid $primary;
    }

    #cc-right {
        width: 50%;
    }

    .cc-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    .cc-subheader {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #cc-status {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    DataTable {
        height: 1fr;
    }

    .empty-message {
        padding: 1 2;
        color: $text-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self.gameplans = []
        self.task_list = []
        self.selected_gameplan = None
        self.focus_left = True
        self.active_only = True  # Default to showing only active gameplans

    def compose(self) -> ComposeResult:
        with Horizontal(id="cc-main"):
            with Vertical(id="cc-left"):
                yield Static("🎯 Gameplans (active)", id="gp-header", classes="cc-header")
                yield DataTable(id="gp-table", cursor_type="row")
            with Vertical(id="cc-right"):
                yield Static("📋 Tasks", id="task-header", classes="cc-header")
                yield Static("Select a gameplan to see tasks", classes="cc-subheader", id="task-subheader")
                yield DataTable(id="task-table", cursor_type="row")
        yield Static("", id="cc-status")

    def on_mount(self) -> None:
        # Setup gameplan table
        gp_table = self.query_one("#gp-table", DataTable)
        gp_table.add_column("", width=2)  # Status icon
        gp_table.add_column("ID", width=5)
        gp_table.add_column("Title", width=35)
        gp_table.add_column("Progress", width=8)

        # Setup task table
        task_table = self.query_one("#task-table", DataTable)
        task_table.add_column("", width=2)  # Status icon
        task_table.add_column("ID", width=5)
        task_table.add_column("Title", width=40)
        task_table.add_column("P", width=2)

        self._load_gameplans()
        self._update_status()

        gp_table.focus()

    def _load_gameplans(self) -> None:
        """Load docs tagged with 🎯, optionally filtered by 🚀 (active)."""
        table = self.query_one("#gp-table", DataTable)
        table.clear()

        try:
            if self.active_only:
                # Only show gameplans tagged with both 🎯 AND 🚀
                self.gameplans = search_by_tags(["🎯", "🚀"], mode="all", limit=50)
                header = self.query_one("#gp-header", Static)
                header.update("🎯 Gameplans (🚀 active)")
            else:
                # Show all gameplans
                self.gameplans = search_by_tags(["🎯"], mode="any", limit=50)
                header = self.query_one("#gp-header", Static)
                header.update("🎯 Gameplans (all)")

            if not self.gameplans:
                table.add_row("", "", "[dim]No gameplans found[/dim]", "")
                return

            for doc in self.gameplans:
                stats = tasks.get_gameplan_stats(doc['id'])
                total = stats['total']
                done = stats['done']

                # Progress indicator
                if total == 0:
                    progress = "[dim]—[/dim]"
                    icon = "📝"
                elif done == total:
                    progress = f"[green]{done}/{total}[/green]"
                    icon = "✅"
                else:
                    progress = f"{done}/{total}"
                    icon = "🚀" if "🚀" in doc.get('tags', []) else "📝"

                title = doc['title'][:35] if len(doc['title']) > 35 else doc['title']
                table.add_row(icon, str(doc['id']), title, progress)

        except Exception as e:
            logger.error(f"Load gameplans error: {e}", exc_info=True)

    def _load_tasks(self, gameplan_id: Optional[int] = None) -> None:
        """Load tasks for selected gameplan."""
        table = self.query_one("#task-table", DataTable)
        table.clear()

        # Update subheader
        subheader = self.query_one("#task-subheader", Static)

        try:
            if gameplan_id is None:
                subheader.update("Select a gameplan to see tasks")
                return

            self.task_list = tasks.list_tasks(gameplan_id=gameplan_id, limit=50)

            if not self.task_list:
                subheader.update(f"GP #{gameplan_id} - No tasks yet (press 'n' to create)")
                table.add_row("", "", "[dim]No tasks for this gameplan[/dim]", "")
                return

            # Count by status
            by_status = {}
            for t in self.task_list:
                by_status[t['status']] = by_status.get(t['status'], 0) + 1

            status_summary = " | ".join(f"{ICONS.get(s, '?')}{c}" for s, c in by_status.items())
            subheader.update(f"GP #{gameplan_id} - {status_summary}")

            for t in self.task_list:
                icon = ICONS.get(t['status'], '?')
                title = t['title'][:40] if len(t['title']) > 40 else t['title']

                # Color based on status
                if t['status'] == 'done':
                    title = f"[dim]{title}[/dim]"
                elif t['status'] == 'blocked':
                    title = f"[yellow]{title}[/yellow]"
                elif t['status'] == 'active':
                    title = f"[green]{title}[/green]"

                table.add_row(icon, str(t['id']), title, str(t['priority']))

        except Exception as e:
            logger.error(f"Load tasks error: {e}", exc_info=True)

    def _update_status(self) -> None:
        status = self.query_one("#cc-status", Static)
        gp_text = f"GP #{self.selected_gameplan}" if self.selected_gameplan else "No selection"

        try:
            ready_count = len(tasks.get_ready_tasks(gameplan_id=self.selected_gameplan))
            ready_text = f"{ready_count} ready" if ready_count else "0 ready"
        except:
            ready_text = ""

        filter_text = "active" if self.active_only else "all"
        status.update(f"{gp_text} | {ready_text} | [a] {filter_text} | [n] new | [Tab] switch | [q] back")

    def action_cursor_down(self) -> None:
        table_id = "#gp-table" if self.focus_left else "#task-table"
        self.query_one(table_id, DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        table_id = "#gp-table" if self.focus_left else "#task-table"
        self.query_one(table_id, DataTable).action_cursor_up()

    def action_switch_panel(self) -> None:
        self.focus_left = not self.focus_left
        table_id = "#gp-table" if self.focus_left else "#task-table"
        self.query_one(table_id, DataTable).focus()

    def action_select(self) -> None:
        if self.focus_left:
            table = self.query_one("#gp-table", DataTable)
            if table.cursor_row is not None and table.cursor_row < len(self.gameplans):
                self.selected_gameplan = self.gameplans[table.cursor_row]['id']
                self._load_tasks(self.selected_gameplan)
                self._update_status()

    def action_toggle_active(self) -> None:
        """Toggle between active-only and all gameplans."""
        self.active_only = not self.active_only
        self._load_gameplans()
        self._update_status()

    def action_new_task(self) -> None:
        """Show command to create a new task."""
        if self.selected_gameplan:
            self.notify(f"Run: emdx task create \"Task title\" -g {self.selected_gameplan}")
        else:
            self.notify("Run: emdx task create \"Task title\"")

    def action_refresh(self) -> None:
        """Refresh the view."""
        self._load_gameplans()
        if self.selected_gameplan:
            self._load_tasks(self.selected_gameplan)
        self._update_status()

    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection."""
        if self.focus_left and event.data_table.id == "gp-table":
            if event.cursor_row is not None and event.cursor_row < len(self.gameplans):
                gp = self.gameplans[event.cursor_row]
                self.selected_gameplan = gp['id']
                self._load_tasks(gp['id'])
                self._update_status()
