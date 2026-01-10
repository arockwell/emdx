"""Task detail panel - left side of Zoom 1 focus view."""

import logging
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.containers import Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static, Markdown

from emdx.models import tasks
from emdx.models.executions import get_recent_executions

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}
STATUS_COLORS = {
    'open': 'white',
    'active': 'green',
    'blocked': 'yellow',
    'done': 'dim',
    'failed': 'red',
}


class TaskDetailPanel(Widget):
    """Detailed view of a single task."""

    DEFAULT_CSS = """
    TaskDetailPanel {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
    }

    .detail-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    .detail-section {
        height: auto;
        padding: 1;
        border-bottom: solid $surface;
    }

    .detail-label {
        color: $text-muted;
    }

    .detail-content {
        height: 1fr;
        padding: 1;
    }

    .detail-status-active {
        color: $success;
    }

    .detail-status-blocked {
        color: $warning;
    }

    .detail-status-done {
        color: $text-muted;
    }

    .execution-item {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    .execution-running {
        background: $success 20%;
    }
    """

    def __init__(self):
        super().__init__()
        self.current_task: Optional[Dict[str, Any]] = None

    def compose(self) -> ComposeResult:
        yield Static("📋 TASK DETAILS", classes="detail-header")
        with ScrollableContainer(classes="detail-content"):
            yield Static("[dim]Select a task to view details[/dim]", id="task-info")
            yield Static("", id="task-description")
            yield Static("", id="task-meta")
            yield Static("", id="task-executions")

    async def load_task(self, task_id: int) -> None:
        """Load and display task details."""
        try:
            task = tasks.get_task(task_id)
            if not task:
                self._show_error(f"Task #{task_id} not found")
                return

            self.current_task = task
            await self._update_display()

        except Exception as e:
            logger.error(f"Error loading task {task_id}: {e}", exc_info=True)
            self._show_error(str(e))

    async def _update_display(self) -> None:
        """Update the display with current task data."""
        if not self.current_task:
            return

        task = self.current_task
        status = task['status']
        icon = ICONS.get(status, '?')
        color = STATUS_COLORS.get(status, 'white')

        # Task info
        info = self.query_one("#task-info", Static)
        info.update(
            f"[bold]#{task['id']}[/bold] [{color}]{icon} {status.upper()}[/{color}]\n\n"
            f"[bold]{task['title']}[/bold]"
        )

        # Description
        desc = self.query_one("#task-description", Static)
        if task.get('description'):
            desc.update(f"\n[dim]Description:[/dim]\n{task['description']}")
        else:
            desc.update("\n[dim]No description[/dim]")

        # Meta info
        meta = self.query_one("#task-meta", Static)
        meta_parts = []

        if task.get('priority'):
            meta_parts.append(f"Priority: {task['priority']}")
        if task.get('gameplan_id'):
            meta_parts.append(f"Gameplan: #{task['gameplan_id']}")
        if task.get('project'):
            meta_parts.append(f"Project: {task['project']}")
        if task.get('created_at'):
            created_at = task['created_at']
            if hasattr(created_at, 'strftime'):
                meta_parts.append(f"Created: {created_at.strftime('%Y-%m-%d')}")
            else:
                meta_parts.append(f"Created: {str(created_at)[:10]}")

        meta.update("\n[dim]" + " | ".join(meta_parts) + "[/dim]" if meta_parts else "")

        # Recent executions for this task
        exec_widget = self.query_one("#task-executions", Static)
        try:
            # Get executions related to this task's gameplan
            if task.get('gameplan_id'):
                execs = get_recent_executions(limit=5)
                # Filter by doc_id matching gameplan_id (rough association)
                related = [e for e in execs if e.doc_id == task['gameplan_id']][:3]

                if related:
                    exec_text = "\n[dim]Recent Executions:[/dim]\n"
                    for ex in related:
                        status_icon = "🔄" if ex.is_running else ("✅" if ex.status == 'completed' else "❌")
                        exec_text += f"  {status_icon} #{ex.id} - {ex.status}\n"
                    exec_widget.update(exec_text)
                else:
                    exec_widget.update("")
            else:
                exec_widget.update("")
        except Exception:
            exec_widget.update("")

    def _show_error(self, message: str) -> None:
        """Show an error message."""
        info = self.query_one("#task-info", Static)
        info.update(f"[red]Error: {message}[/red]")

    def clear(self) -> None:
        """Clear the display."""
        self.current_task = None
        info = self.query_one("#task-info", Static)
        info.update("[dim]Select a task to view details[/dim]")
        self.query_one("#task-description", Static).update("")
        self.query_one("#task-meta", Static).update("")
        self.query_one("#task-executions", Static).update("")
