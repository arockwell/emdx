"""Smart list panel - right side of Zoom 1 focus view with dependency info."""

import logging
from typing import Any, Dict, List, Optional, Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Static, TabbedContent, TabPane

from emdx.models import tasks

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


def render_dep_glyph(task: Dict[str, Any], deps: List[Dict], dependents: List[Dict]) -> str:
    """Render a compact dependency glyph for a task.

    Format: STATUS [blocked_by←] [→blocks] [!critical]
    Examples:
        ◆        - Ready, no deps
        ◆→2      - Ready, blocks 2 tasks
        ◇1←      - Waiting on 1 task
        ◇2←→3!   - Waiting on 2, blocks 3, critical
    """
    status = task['status']

    # Status character
    if status == 'done':
        char = '✓'
    elif status == 'failed':
        char = '✗'
    elif status == 'active':
        char = '●'
    elif status == 'blocked':
        char = '⚠'
    else:
        # Open - check if ready
        incomplete_deps = [d for d in deps if d['status'] != 'done']
        char = '◇' if incomplete_deps else '◆'

    parts = [char]

    # Blocked by count
    incomplete_deps = [d for d in deps if d['status'] != 'done']
    if incomplete_deps:
        parts.append(f"{len(incomplete_deps)}←")

    # Blocks count (dependents)
    if dependents:
        parts.append(f"→{len(dependents)}")

    return "".join(parts)


class SmartListPanel(Widget):
    """Smart list showing dependencies, dependents, and related tasks."""

    BINDINGS = [
        Binding("tab", "next_tab", "Next Tab"),
        Binding("shift+tab", "prev_tab", "Prev Tab"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("enter", "select", "Select"),
    ]

    DEFAULT_CSS = """
    SmartListPanel {
        width: 50%;
        height: 100%;
    }

    .list-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 0;
    }

    DataTable {
        height: 1fr;
    }

    .empty-list {
        padding: 1;
        color: $text-muted;
    }
    """

    def __init__(self, on_task_selected: Optional[Callable[[int], None]] = None):
        super().__init__()
        self.current_task_id: Optional[int] = None
        self.dependencies: List[Dict[str, Any]] = []
        self.dependents: List[Dict[str, Any]] = []
        self.same_gameplan: List[Dict[str, Any]] = []
        self.on_task_selected = on_task_selected

    def compose(self) -> ComposeResult:
        yield Static("🔗 RELATED TASKS", classes="list-header")
        with TabbedContent():
            with TabPane("Dependencies", id="tab-deps"):
                yield DataTable(id="deps-table", cursor_type="row")
            with TabPane("Blocked By Me", id="tab-dependents"):
                yield DataTable(id="dependents-table", cursor_type="row")
            with TabPane("Same Gameplan", id="tab-gameplan"):
                yield DataTable(id="gameplan-table", cursor_type="row")

    async def on_mount(self) -> None:
        """Setup tables."""
        # Setup dependencies table
        deps_table = self.query_one("#deps-table", DataTable)
        deps_table.add_column("Glyph", width=6)
        deps_table.add_column("ID", width=5)
        deps_table.add_column("Title", width=30)

        # Setup dependents table
        dependents_table = self.query_one("#dependents-table", DataTable)
        dependents_table.add_column("Glyph", width=6)
        dependents_table.add_column("ID", width=5)
        dependents_table.add_column("Title", width=30)

        # Setup gameplan table
        gp_table = self.query_one("#gameplan-table", DataTable)
        gp_table.add_column("Glyph", width=6)
        gp_table.add_column("ID", width=5)
        gp_table.add_column("Title", width=30)

    async def load_task(self, task_id: int) -> None:
        """Load related tasks for the given task."""
        self.current_task_id = task_id

        try:
            task = tasks.get_task(task_id)
            if not task:
                return

            # Load dependencies (tasks this one depends on)
            self.dependencies = tasks.get_dependencies(task_id)
            await self._update_deps_table()

            # Load dependents (tasks that depend on this one)
            # Note: get_dependents doesn't exist yet, we'll simulate it
            self.dependents = self._get_dependents(task_id)
            await self._update_dependents_table()

            # Load tasks from same gameplan
            if task.get('gameplan_id'):
                all_gp_tasks = tasks.list_tasks(gameplan_id=task['gameplan_id'], limit=20)
                # Exclude current task
                self.same_gameplan = [t for t in all_gp_tasks if t['id'] != task_id]
            else:
                self.same_gameplan = []
            await self._update_gameplan_table()

        except Exception as e:
            logger.error(f"Error loading related tasks for {task_id}: {e}", exc_info=True)

    def _get_dependents(self, task_id: int) -> List[Dict[str, Any]]:
        """Get tasks that depend on this task.

        Note: This is a workaround until get_dependents() is added to tasks.py.
        We scan all tasks and check their dependencies.
        """
        try:
            all_tasks = tasks.list_tasks(limit=100)
            dependents = []
            for t in all_tasks:
                deps = tasks.get_dependencies(t['id'])
                if any(d['id'] == task_id for d in deps):
                    dependents.append(t)
            return dependents
        except Exception as e:
            logger.error(f"Error getting dependents: {e}")
            return []

    async def _update_deps_table(self) -> None:
        """Update the dependencies table."""
        table = self.query_one("#deps-table", DataTable)
        table.clear()

        if not self.dependencies:
            table.add_row("", "", "[dim]No dependencies[/dim]")
            return

        for dep in self.dependencies:
            # Get this dep's own deps and dependents for glyph
            dep_deps = tasks.get_dependencies(dep['id'])
            dep_dependents = self._get_dependents(dep['id'])
            glyph = render_dep_glyph(dep, dep_deps, dep_dependents)

            title = dep['title'][:28] if len(dep['title']) > 28 else dep['title']
            table.add_row(glyph, str(dep['id']), title)

    async def _update_dependents_table(self) -> None:
        """Update the dependents table."""
        table = self.query_one("#dependents-table", DataTable)
        table.clear()

        if not self.dependents:
            table.add_row("", "", "[dim]No tasks depend on this[/dim]")
            return

        for dep in self.dependents:
            dep_deps = tasks.get_dependencies(dep['id'])
            dep_dependents = self._get_dependents(dep['id'])
            glyph = render_dep_glyph(dep, dep_deps, dep_dependents)

            title = dep['title'][:28] if len(dep['title']) > 28 else dep['title']
            table.add_row(glyph, str(dep['id']), title)

    async def _update_gameplan_table(self) -> None:
        """Update the same-gameplan table."""
        table = self.query_one("#gameplan-table", DataTable)
        table.clear()

        if not self.same_gameplan:
            table.add_row("", "", "[dim]No other tasks in gameplan[/dim]")
            return

        for task in self.same_gameplan:
            task_deps = tasks.get_dependencies(task['id'])
            task_dependents = self._get_dependents(task['id'])
            glyph = render_dep_glyph(task, task_deps, task_dependents)

            title = task['title'][:28] if len(task['title']) > 28 else task['title']
            table.add_row(glyph, str(task['id']), title)

    def action_cursor_down(self) -> None:
        """Move cursor down in active table."""
        try:
            # Find the active table
            for table_id in ["#deps-table", "#dependents-table", "#gameplan-table"]:
                table = self.query_one(table_id, DataTable)
                if table.has_focus:
                    table.action_cursor_down()
                    return
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        """Move cursor up in active table."""
        try:
            for table_id in ["#deps-table", "#dependents-table", "#gameplan-table"]:
                table = self.query_one(table_id, DataTable)
                if table.has_focus:
                    table.action_cursor_up()
                    return
        except Exception:
            pass

    def action_select(self) -> None:
        """Select the current row and notify."""
        if not self.on_task_selected:
            return

        try:
            # Find active table and get selected task
            for table_id, task_list in [
                ("#deps-table", self.dependencies),
                ("#dependents-table", self.dependents),
                ("#gameplan-table", self.same_gameplan),
            ]:
                table = self.query_one(table_id, DataTable)
                if table.has_focus and table.cursor_row is not None:
                    if 0 <= table.cursor_row < len(task_list):
                        task = task_list[table.cursor_row]
                        self.on_task_selected(task['id'])
                        return
        except Exception as e:
            logger.error(f"Error in select action: {e}")

    def action_next_tab(self) -> None:
        """Move to next tab."""
        try:
            tabs = self.query_one(TabbedContent)
            tabs.action_next_tab()
        except Exception:
            pass

    def action_prev_tab(self) -> None:
        """Move to previous tab."""
        try:
            tabs = self.query_one(TabbedContent)
            tabs.action_previous_tab()
        except Exception:
            pass

    def clear(self) -> None:
        """Clear all tables."""
        self.current_task_id = None
        self.dependencies = []
        self.dependents = []
        self.same_gameplan = []

        for table_id in ["#deps-table", "#dependents-table", "#gameplan-table"]:
            try:
                table = self.query_one(table_id, DataTable)
                table.clear()
            except Exception:
                pass
