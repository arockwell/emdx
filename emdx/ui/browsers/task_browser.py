"""
TaskBrowser - Task browser using the panel-based architecture.

A simplified reimplementation of TaskBrowser using ListPanel and PreviewPanel
for task listing with status indicators and task details display.

Features:
- ListPanel with vim navigation and status filter
- PreviewPanel for task details/dependencies
- Status filtering (0=all, 1=open, 2=active, 3=blocked, 4=done)
- Same functionality as original in ~100-150 lines
"""

import logging
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget

from emdx.models import tasks
from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
    SimpleStatusBar,
)

logger = logging.getLogger(__name__)

ICONS = {"open": "○", "active": "●", "blocked": "⚠", "done": "✓", "failed": "✗"}


class TaskBrowser(Widget):
    """Task browser using panel components.

    A simplified task browser that displays tasks with their status,
    dependencies, and details using the reusable panel system.
    """

    DEFAULT_CSS = """
    TaskBrowser {
        layout: vertical;
        height: 100%;
    }

    TaskBrowser #task-main {
        height: 1fr;
    }

    TaskBrowser #task-list {
        width: 55%;
        min-width: 40;
    }

    TaskBrowser #task-preview {
        width: 45%;
        min-width: 30;
        border-left: solid $primary;
    }

    TaskBrowser #task-status {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("0", "filter_all", "All"),
        Binding("1", "filter_open", "Open"),
        Binding("2", "filter_active", "Active"),
        Binding("3", "filter_blocked", "Blocked"),
        Binding("4", "filter_done", "Done"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.task_data: List[Dict[str, Any]] = []
        self.status_filter: Optional[List[str]] = ["open", "active", "blocked"]

    def compose(self) -> ComposeResult:
        with Horizontal(id="task-main"):
            yield ListPanel(
                columns=[
                    ColumnDef("", width=2),  # Status icon
                    ColumnDef("ID", width=5),
                    ColumnDef("Title", width=30),
                    ColumnDef("P", width=2),  # Priority
                    ColumnDef("Deps", width=5),
                    ColumnDef("GP", width=5),  # Gameplan
                ],
                config=ListPanelConfig(
                    show_search=True,
                    search_placeholder="Search tasks...",
                    status_format="{filtered}/{total} tasks",
                ),
                show_status=True,
                id="task-list",
            )
            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=False,
                    empty_message="Select a task to see details",
                ),
                id="task-preview",
            )
        yield SimpleStatusBar(id="task-status")

    async def on_mount(self) -> None:
        await self._load_tasks()
        self._update_status_bar()

    async def _load_tasks(self) -> None:
        """Load tasks with current filter."""
        try:
            self.task_data = tasks.list_tasks(status=self.status_filter, limit=100)
            items = [self._task_to_item(t) for t in self.task_data]
            self.query_one("#task-list", ListPanel).set_items(items)
        except Exception as e:
            logger.error(f"Error loading tasks: {e}", exc_info=True)

    def _task_to_item(self, t: Dict[str, Any]) -> ListItem:
        """Convert a task dict to a ListItem."""
        icon = ICONS.get(t["status"], "?")
        deps = tasks.get_dependencies(t["id"])
        deps_done = sum(1 for d in deps if d["status"] == "done")

        # Dependency display
        if not deps:
            dep_str = "—"
        elif deps_done == len(deps):
            dep_str = f"[green]{deps_done}/{len(deps)}[/green]"
        else:
            dep_str = f"[yellow]{deps_done}/{len(deps)}[/yellow]"

        # Title with status coloring
        title = t["title"][:28] if len(t["title"]) > 28 else t["title"]
        if t["status"] == "done":
            title = f"[dim]{title}[/dim]"
        elif t["status"] == "blocked":
            title = f"[yellow]{title}[/yellow]"
        elif t["status"] == "active":
            title = f"[green]{title}[/green]"

        gp_str = f"#{t['gameplan_id']}" if t.get("gameplan_id") else "—"

        return ListItem(
            id=t["id"],
            values=[icon, str(t["id"]), title, str(t["priority"]), dep_str, gp_str],
            data=t,
        )

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Update preview when task is selected."""
        t = event.item.data
        if not t:
            return

        preview = self.query_one("#task-preview", PreviewPanel)
        content = self._format_task_detail(t)
        await preview.show_content(content, title=f"Task #{t['id']}")

    def _format_task_detail(self, t: Dict[str, Any]) -> str:
        """Format task details for preview."""
        status = f"{ICONS.get(t['status'], '?')} {t['status']}"
        if t["status"] == "active":
            status = f"[green]{status}[/green]"
        elif t["status"] == "blocked":
            status = f"[yellow]{status}[/yellow]"
        elif t["status"] == "done":
            status = f"[dim]{status}[/dim]"

        lines = [
            f"# {t['title']}",
            "",
            f"**Status:** {status}  ",
            f"**Priority:** {t['priority']}  ",
        ]

        if t.get("gameplan_id"):
            lines.append(f"**Gameplan:** #{t['gameplan_id']}  ")
        if t.get("project"):
            lines.append(f"**Project:** {t['project']}  ")

        if t.get("description"):
            lines.extend(["", "## Description", t["description"][:500]])

        # Dependencies
        deps = tasks.get_dependencies(t["id"])
        if deps:
            lines.extend(["", f"## Dependencies ({len(deps)})"])
            for d in deps:
                icon = ICONS.get(d["status"], "?")
                lines.append(f"- {icon} #{d['id']} {d['title'][:30]}")

        # Dependents (tasks blocked by this one)
        try:
            dependents = tasks.get_dependents(t["id"])
            if dependents:
                lines.extend(["", f"## Blocks ({len(dependents)})"])
                for d in dependents[:5]:
                    icon = ICONS.get(d["status"], "?")
                    lines.append(f"- {icon} #{d['id']} {d['title'][:30]}")
                if len(dependents) > 5:
                    lines.append(f"- ... and {len(dependents) - 5} more")
        except Exception:
            pass

        return "\n".join(lines)

    def _update_status_bar(self) -> None:
        """Update status bar with filter info."""
        try:
            ready = tasks.get_ready_tasks()
            ready_text = f"{len(ready)} ready"
        except Exception:
            ready_text = ""

        filter_text = "+".join(self.status_filter) if self.status_filter else "all"
        status = self.query_one("#task-status", SimpleStatusBar)
        status.set(
            f"{ready_text} | Filter: {filter_text} | "
            "0=all 1=open 2=active 3=blocked 4=done | r=refresh"
        )

    async def _apply_filter(self, new_filter: Optional[List[str]]) -> None:
        """Apply a new status filter."""
        self.status_filter = new_filter
        await self._load_tasks()
        self._update_status_bar()

    async def action_refresh(self) -> None:
        await self._load_tasks()
        self._update_status_bar()
        self.notify("Refreshed")

    async def action_filter_all(self) -> None:
        await self._apply_filter(None)

    async def action_filter_open(self) -> None:
        await self._apply_filter(["open"])

    async def action_filter_active(self) -> None:
        await self._apply_filter(["active"])

    async def action_filter_blocked(self) -> None:
        await self._apply_filter(["blocked"])

    async def action_filter_done(self) -> None:
        await self._apply_filter(["done"])
