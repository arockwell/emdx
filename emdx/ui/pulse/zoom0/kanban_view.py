"""Kanban view - column-based task board for zoom 0."""

import logging
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from emdx.models import tasks

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}

# Column definitions
COLUMNS = [
    ('open', 'OPEN', '○'),
    ('active', 'ACTIVE', '●'),
    ('blocked', 'BLOCKED', '⚠'),
    ('done', 'DONE', '✓'),
]


class TaskCard(Static):
    """A single task card in the kanban board."""

    DEFAULT_CSS = """
    TaskCard {
        height: auto;
        min-height: 2;
        margin: 0 0 1 0;
        padding: 0 1;
        background: $surface;
    }

    TaskCard.selected {
        background: $accent;
    }

    TaskCard.active {
        border-left: tall $success;
    }

    TaskCard.blocked {
        border-left: tall $warning;
    }

    TaskCard.done {
        color: $text-muted;
    }
    """

    def __init__(self, task: Dict[str, Any]):
        self.task = task
        title = task['title'][:25] if len(task['title']) > 25 else task['title']
        dep_count = len(tasks.get_dependencies(task['id'])) if task['id'] else 0
        dep_text = f" ←{dep_count}" if dep_count > 0 else ""

        content = f"#{task['id']} {title}{dep_text}"
        super().__init__(content)

        # Add status class
        self.add_class(task['status'])


class KanbanColumn(Widget):
    """A single column in the kanban board."""

    DEFAULT_CSS = """
    KanbanColumn {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }

    .column-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    .column-count {
        color: $text-muted;
    }

    .column-content {
        height: 1fr;
        padding: 1 0;
    }

    .empty-column {
        color: $text-muted;
        padding: 1;
    }
    """

    selected_index = reactive(-1)

    def __init__(self, status: str, title: str, icon: str):
        super().__init__()
        self.status = status
        self.title = title
        self.icon = icon
        self.tasks: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Static(f"{self.icon} {self.title} [dim](0)[/dim]", classes="column-header", id=f"header-{self.status}")
        with ScrollableContainer(classes="column-content"):
            yield Static("[dim]Loading...[/dim]", classes="empty-column", id=f"empty-{self.status}")

    def update_tasks(self, task_list: List[Dict[str, Any]]) -> None:
        """Update the tasks in this column."""
        self.tasks = [t for t in task_list if t['status'] == self.status]

        # Update header count
        header = self.query_one(f"#header-{self.status}", Static)
        header.update(f"{self.icon} {self.title} [dim]({len(self.tasks)})[/dim]")

        # Update content
        content = self.query_one(".column-content", ScrollableContainer)

        # Remove old cards
        for card in list(content.query(TaskCard)):
            card.remove()

        # Remove empty message
        empty = self.query_one(f"#empty-{self.status}", Static)

        if not self.tasks:
            empty.update("[dim]No tasks[/dim]")
            empty.display = True
        else:
            empty.display = False
            for task in self.tasks:
                content.mount(TaskCard(task))

    def select_task(self, index: int) -> Optional[Dict[str, Any]]:
        """Select a task by index."""
        if 0 <= index < len(self.tasks):
            self.selected_index = index
            # Update visual selection
            for i, card in enumerate(self.query(TaskCard)):
                if i == index:
                    card.add_class("selected")
                else:
                    card.remove_class("selected")
            return self.tasks[index]
        return None

    def clear_selection(self) -> None:
        """Clear the selection."""
        self.selected_index = -1
        for card in self.query(TaskCard):
            card.remove_class("selected")


class KanbanView(Widget):
    """Kanban board view for zoom 0."""

    BINDINGS = [
        Binding("h", "move_left", "Left Column"),
        Binding("l", "move_right", "Right Column"),
        Binding("j", "move_down", "Down"),
        Binding("k", "move_up", "Up"),
    ]

    DEFAULT_CSS = """
    KanbanView {
        layout: horizontal;
        height: 100%;
    }
    """

    current_column = reactive(0)

    def __init__(self):
        super().__init__()
        self.all_tasks: List[Dict[str, Any]] = []
        self.columns: List[KanbanColumn] = []

    def compose(self) -> ComposeResult:
        for status, title, icon in COLUMNS:
            column = KanbanColumn(status, title, icon)
            self.columns.append(column)
            yield column

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.load_data()

    async def load_data(self) -> None:
        """Load all tasks and distribute to columns."""
        try:
            # Load all non-failed tasks
            self.all_tasks = tasks.list_tasks(limit=100)

            # Update each column
            for column in self.columns:
                column.update_tasks(self.all_tasks)

            # Select first task in first non-empty column
            for i, column in enumerate(self.columns):
                if column.tasks:
                    self.current_column = i
                    column.select_task(0)
                    break

        except Exception as e:
            logger.error(f"Error loading kanban data: {e}", exc_info=True)

    def action_move_left(self) -> None:
        """Move to the left column."""
        if self.current_column > 0:
            self.columns[self.current_column].clear_selection()
            self.current_column -= 1
            col = self.columns[self.current_column]
            if col.tasks:
                col.select_task(0)

    def action_move_right(self) -> None:
        """Move to the right column."""
        if self.current_column < len(self.columns) - 1:
            self.columns[self.current_column].clear_selection()
            self.current_column += 1
            col = self.columns[self.current_column]
            if col.tasks:
                col.select_task(0)

    def action_move_down(self) -> None:
        """Move down in current column."""
        col = self.columns[self.current_column]
        new_index = min(col.selected_index + 1, len(col.tasks) - 1)
        col.select_task(new_index)

    def action_move_up(self) -> None:
        """Move up in current column."""
        col = self.columns[self.current_column]
        new_index = max(col.selected_index - 1, 0)
        col.select_task(new_index)

    def get_selected_task(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected task."""
        col = self.columns[self.current_column]
        if 0 <= col.selected_index < len(col.tasks):
            return col.tasks[col.selected_index]
        return None
