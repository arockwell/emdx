"""
ActivityBrowser - Mission Control for EMDX using panel components.

Provides a view of EMDX activity using reusable panels:
- ListPanel for activity stream with hierarchical expansion
- PreviewPanel for document content and live logs
- Status bar with tokens, cost, errors, sparkline

Key features:
- Hierarchical items (groups → workflows → documents)
- Live log streaming for running workflows
- GroupPicker integration for organization
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, RichLog

from ..activity.sparkline import sparkline
from ..activity.group_picker import GroupPicker
from ..modals import HelpMixin
from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
)

logger = logging.getLogger(__name__)


# Import services with fallbacks
try:
    from emdx.workflows import database as wf_db
    from emdx.workflows.registry import workflow_registry
    HAS_WORKFLOWS = True
except ImportError:
    wf_db = None
    workflow_registry = None
    HAS_WORKFLOWS = False

try:
    from emdx.database import documents as doc_db
    from emdx.database import groups as groups_db
    from emdx.database.documents import list_non_workflow_documents
    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_db = None
    groups_db = None
    HAS_DOCS = False
    HAS_GROUPS = False
    def list_non_workflow_documents(**kwargs):
        return []

try:
    from emdx.services.log_stream import LogStream, LogStreamSubscriber
    HAS_LOG_STREAM = True
except ImportError:
    LogStream = None
    LogStreamSubscriber = None
    HAS_LOG_STREAM = False


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ActivityItem:
    """Represents an item in the activity list."""
    item_type: str  # "group", "workflow", "document", "stage_run"
    item_id: int
    title: str
    time_ago: str
    icon: str = ""
    doc_id: Optional[int] = None
    workflow_run: Optional[Dict] = None
    group: Optional[Dict] = None
    stage_run: Optional[Dict] = None
    depth: int = 0
    expanded: bool = False
    children: List["ActivityItem"] = field(default_factory=list)
    parent: Optional["ActivityItem"] = None
    _has_workflow_outputs: bool = False


class AgentLogSubscriber:
    """Forwards log content to the activity browser."""
    def __init__(self, browser: "ActivityBrowser"):
        self.browser = browser

    def on_log_content(self, new_content: str) -> None:
        self.browser._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        logger.error(f"Log stream error: {error}")


# =============================================================================
# Helper Functions
# =============================================================================

def format_time_ago(dt: datetime) -> str:
    """Format datetime as relative time."""
    if not dt:
        return "—"
    from datetime import timezone
    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < -60:
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone().replace(tzinfo=None)
        diff = now - dt_local
        seconds = diff.total_seconds()
    if seconds < 0:
        return "now"
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def format_tokens(tokens: int) -> str:
    """Format token count with K/M abbreviations."""
    if tokens is None or tokens == 0:
        return "—"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)


def format_cost(cost: float) -> str:
    """Format cost in dollars."""
    if not cost or cost == 0:
        return "—"
    if cost < 0.01:
        return f"${cost:.3f}"
    return f"${cost:.2f}"


# =============================================================================
# ActivityBrowser
# =============================================================================

class ActivityBrowser(HelpMixin, Widget):
    """Mission Control browser using panel components."""

    HELP_TITLE = "Activity View"

    class ViewDocument(Message):
        """Request to view a document in the document browser."""
        def __init__(self, doc_id: int) -> None:
            self.doc_id = doc_id
            super().__init__()

    DEFAULT_CSS = """
    ActivityBrowser {
        layout: vertical;
        height: 100%;
    }

    ActivityBrowser #status-bar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    ActivityBrowser #main-content {
        height: 1fr;
    }

    ActivityBrowser #left-panel {
        width: 45%;
        min-width: 40;
    }

    ActivityBrowser #activity-list {
        height: 2fr;
    }

    ActivityBrowser #context-panel {
        height: 1fr;
        border-top: solid $primary;
    }

    ActivityBrowser #preview-panel {
        width: 55%;
        border-left: solid $primary;
    }

    ActivityBrowser #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "select", "Select/Expand"),
        Binding("l", "expand", "Expand"),
        Binding("h", "collapse", "Collapse"),
        Binding("f", "fullscreen", "Fullscreen"),
        Binding("r", "refresh", "Refresh"),
        Binding("g", "add_to_group", "Add to Group"),
        Binding("G", "create_group", "Create Group"),
        Binding("i", "create_gist", "New Gist"),
        Binding("u", "ungroup", "Ungroup"),
        Binding("tab", "focus_next", "Next Pane"),
        Binding("shift+tab", "focus_prev", "Prev Pane"),
        Binding("question_mark", "show_help", "Help"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Data
        self.groups: List[ActivityItem] = []
        self.workflows: List[ActivityItem] = []
        self.direct_saves: List[ActivityItem] = []
        self.flat_items: List[ActivityItem] = []
        self.selected_idx: int = 0
        # Log streaming
        self._log_stream: Optional[Any] = None
        self._log_subscriber: Optional[AgentLogSubscriber] = None
        self._streaming_item: Optional[ActivityItem] = None

    def compose(self) -> ComposeResult:
        """Compose the activity browser layout."""
        yield Static("Loading...", id="status-bar")

        with Horizontal(id="main-content"):
            with Vertical(id="left-panel"):
                yield ListPanel(
                    columns=[
                        ColumnDef("", width=2),   # Icon
                        ColumnDef("Time", width=4),
                        ColumnDef("Title", width=50),
                        ColumnDef("ID", width=6),
                    ],
                    config=ListPanelConfig(
                        show_search=True,
                        search_placeholder="Search activity...",
                        status_format="{filtered}/{total} items",
                    ),
                    show_status=True,
                    id="activity-list",
                )
                yield RichLog(
                    id="context-panel",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False,
                )

            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=False,
                    enable_selection=True,
                    empty_message="Select an item to preview",
                ),
                id="preview-panel",
            )

        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Workflows │ [dim]3[/dim] Documents │ "
            "[dim]j/k[/dim] nav │ [dim]Enter[/dim] expand │ [dim]f[/dim] fullscreen │ [dim]?[/dim] help",
            id="help-bar",
        )

        yield GroupPicker(id="group-picker")

    async def on_mount(self) -> None:
        """Initialize the browser."""
        # Disable focus on context panel
        try:
            context = self.query_one("#context-panel", RichLog)
            context.can_focus = False
        except Exception:
            pass

        await self._refresh_data()

    # =========================================================================
    # Data Loading
    # =========================================================================

    async def _refresh_data(self) -> None:
        """Load all activity data."""
        self.groups = []
        self.workflows = []
        self.direct_saves = []

        await self._load_groups()
        await self._load_workflows()
        await self._load_direct_saves()
        self._flatten_items()
        await self._update_list()
        await self._update_status_bar()

    async def _load_groups(self) -> None:
        """Load groups from database."""
        if not HAS_GROUPS or not groups_db:
            return
        try:
            raw_groups = groups_db.list_groups(include_archived=False)
            for g in raw_groups:
                if g.get("parent_group_id"):
                    continue
                created = g.get("created_at")
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                item = ActivityItem(
                    item_type="group",
                    item_id=g["id"],
                    title=g.get("name", f"Group {g['id']}"),
                    time_ago=format_time_ago(created),
                    icon="📁",
                    group=g,
                )
                self.groups.append(item)
        except Exception as e:
            logger.error(f"Error loading groups: {e}")

    async def _load_workflows(self) -> None:
        """Load workflow runs from database."""
        if not HAS_WORKFLOWS or not wf_db:
            return
        try:
            runs = wf_db.list_workflow_runs(limit=50)
            for run in runs:
                started = run.get("started_at")
                if isinstance(started, str):
                    started = datetime.fromisoformat(started.replace("Z", "+00:00"))

                status = run.get("status", "unknown")
                icon = {"running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "⚙️")

                wf_id = run.get("workflow_id")
                wf = wf_db.get_workflow(wf_id) if wf_id else None
                wf_name = wf.get("name", "Workflow") if wf else "Workflow"

                item = ActivityItem(
                    item_type="workflow",
                    item_id=run["id"],
                    title=f"{wf_name} #{run['id']}",
                    time_ago=format_time_ago(started),
                    icon=icon,
                    workflow_run=run,
                )

                # Check for outputs
                output_ids = wf_db.get_workflow_output_doc_ids(run["id"])
                item._has_workflow_outputs = len(output_ids) > 0

                self.workflows.append(item)
        except Exception as e:
            logger.error(f"Error loading workflows: {e}")

    async def _load_direct_saves(self) -> None:
        """Load direct saves (documents not from workflows)."""
        if not HAS_DOCS:
            return
        try:
            docs = list_non_workflow_documents(limit=30)
            for doc in docs:
                created = doc.get("created_at")
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                item = ActivityItem(
                    item_type="document",
                    item_id=doc["id"],
                    title=doc.get("title", f"Doc {doc['id']}"),
                    time_ago=format_time_ago(created),
                    icon="📄",
                    doc_id=doc["id"],
                )
                self.direct_saves.append(item)
        except Exception as e:
            logger.error(f"Error loading direct saves: {e}")

    def _flatten_items(self) -> None:
        """Flatten hierarchical items for display."""
        self.flat_items = []

        def add_item(item: ActivityItem, depth: int = 0):
            item.depth = depth
            self.flat_items.append(item)
            if item.expanded:
                for child in item.children:
                    add_item(child, depth + 1)

        for group in self.groups:
            add_item(group)
        for workflow in self.workflows:
            add_item(workflow)
        for doc in self.direct_saves:
            add_item(doc)

    async def _update_list(self) -> None:
        """Update the ListPanel with current items."""
        list_panel = self.query_one("#activity-list", ListPanel)

        items = []
        for item in self.flat_items:
            indent = "  " * item.depth
            expand_indicator = ""
            if item.item_type == "workflow" and item._has_workflow_outputs:
                expand_indicator = "▼ " if item.expanded else "▶ "
            elif item.item_type == "group":
                expand_indicator = "▼ " if item.expanded else "▶ "

            display_title = f"{indent}{expand_indicator}{item.title}"
            id_str = str(item.doc_id or item.item_id) if item.doc_id else str(item.item_id)

            items.append(ListItem(
                id=f"{item.item_type}:{item.item_id}",
                values=[item.icon, item.time_ago, display_title, id_str],
                data=item,
            ))

        list_panel.set_items(items)

    async def _update_status_bar(self) -> None:
        """Update the status bar with stats."""
        parts = []

        # Active workflows
        active = sum(1 for w in self.workflows if w.workflow_run and w.workflow_run.get("status") == "running")
        if active > 0:
            parts.append(f"[green]● {active} active[/green]")

        # Today's stats
        if HAS_WORKFLOWS and wf_db:
            try:
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                runs = wf_db.list_workflow_runs(limit=100)
                today_runs = [r for r in runs if r.get("started_at") and
                             datetime.fromisoformat(r["started_at"].replace("Z", "+00:00")).replace(tzinfo=None) >= today]

                total_input = sum(r.get("input_tokens", 0) or 0 for r in today_runs)
                total_output = sum(r.get("output_tokens", 0) or 0 for r in today_runs)
                total_cost = sum(r.get("total_cost", 0) or 0 for r in today_runs)
                errors = sum(1 for r in today_runs if r.get("status") == "failed")

                parts.append(f"In: {format_tokens(total_input)}")
                parts.append(f"Out: {format_tokens(total_output)}")
                parts.append(f"Cost: {format_cost(total_cost)}")
                if errors > 0:
                    parts.append(f"[red]Errors: {errors}[/red]")

                # Sparkline
                week_data = self._get_week_activity_data()
                if any(week_data):
                    spark = sparkline(week_data)
                    parts.append(f"[dim]{spark}[/dim]")
            except Exception as e:
                logger.error(f"Error calculating stats: {e}")

        status_text = " │ ".join(parts) if parts else "Activity"
        try:
            status_bar = self.query_one("#status-bar", Static)
            status_bar.update(status_text)
        except Exception:
            pass

    def _get_week_activity_data(self) -> List[int]:
        """Get activity counts for the last 7 days."""
        if not HAS_WORKFLOWS or not wf_db:
            return [0] * 7
        try:
            counts = [0] * 7
            now = datetime.now()
            runs = wf_db.list_workflow_runs(limit=200)
            for run in runs:
                started = run.get("started_at")
                if not started:
                    continue
                if isinstance(started, str):
                    started = datetime.fromisoformat(started.replace("Z", "+00:00")).replace(tzinfo=None)
                days_ago = (now - started).days
                if 0 <= days_ago < 7:
                    counts[6 - days_ago] += 1
            return counts
        except Exception:
            return [0] * 7

    # =========================================================================
    # Panel Event Handlers
    # =========================================================================

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Handle item selection - update preview and context."""
        item: ActivityItem = event.item.data
        if not item:
            return

        # Track selection
        for i, flat_item in enumerate(self.flat_items):
            if flat_item.item_id == item.item_id and flat_item.item_type == item.item_type:
                self.selected_idx = i
                break

        # Stop any existing log stream
        self._stop_stream()

        # Update preview
        await self._update_preview(item)

        # Update context panel
        await self._update_context(item)

    async def on_list_panel_item_activated(self, event: ListPanel.ItemActivated) -> None:
        """Handle Enter key - expand/collapse or view document."""
        item: ActivityItem = event.item.data
        if not item:
            return
        await self._toggle_expand(item)

    async def _update_preview(self, item: ActivityItem) -> None:
        """Update the preview panel for selected item."""
        preview = self.query_one("#preview-panel", PreviewPanel)

        # Check for running workflow - show live log
        if item.item_type == "workflow" and item.workflow_run:
            status = item.workflow_run.get("status")
            if status == "running":
                await self._show_live_log(item)
                return

        # Show document content
        if item.doc_id and HAS_DOCS and doc_db:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    await preview.show_content(content, title=item.title)
                    return
            except Exception as e:
                logger.error(f"Error loading document: {e}")

        # Show workflow summary
        if item.item_type == "workflow" and item.workflow_run:
            run = item.workflow_run
            lines = [
                f"# {item.title}",
                "",
                f"**Status:** {run.get('status', 'unknown')}",
                f"**Started:** {run.get('started_at', 'unknown')}",
            ]
            if run.get("input_tokens"):
                lines.append(f"**Input tokens:** {format_tokens(run['input_tokens'])}")
            if run.get("output_tokens"):
                lines.append(f"**Output tokens:** {format_tokens(run['output_tokens'])}")
            if run.get("total_cost"):
                lines.append(f"**Cost:** {format_cost(run['total_cost'])}")
            await preview.show_content("\n".join(lines), title=item.title)
            return

        # Show group summary
        if item.item_type == "group" and item.group:
            lines = [
                f"# {item.title}",
                "",
                f"**Type:** {item.group.get('group_type', 'unknown')}",
                f"**Created:** {item.group.get('created_at', 'unknown')}",
            ]
            await preview.show_content("\n".join(lines), title=item.title)
            return

        await preview.show_empty(f"No preview available for {item.title}")

    async def _show_live_log(self, item: ActivityItem) -> None:
        """Show live log for a running workflow."""
        if not HAS_LOG_STREAM or not LogStream:
            return

        run = item.workflow_run
        if not run:
            return

        log_path = run.get("log_path")
        if not log_path:
            return

        self._streaming_item = item
        preview = self.query_one("#preview-panel", PreviewPanel)
        await preview.show_content(f"# Live Log: {item.title}\n\nConnecting...", title=f"Live: {item.title}")

        try:
            self._log_subscriber = AgentLogSubscriber(self)
            self._log_stream = LogStream(log_path, self._log_subscriber)
            self._log_stream.start()
        except Exception as e:
            logger.error(f"Error starting log stream: {e}")

    def _handle_log_content(self, content: str) -> None:
        """Handle new log content from the stream."""
        if not self._streaming_item:
            return
        try:
            preview = self.query_one("#preview-panel", PreviewPanel)
            # Append content (PreviewPanel should handle this)
            import asyncio
            asyncio.create_task(preview.show_content(
                f"# Live Log: {self._streaming_item.title}\n\n```\n{content}\n```",
                title=f"Live: {self._streaming_item.title}"
            ))
        except Exception as e:
            logger.error(f"Error updating log content: {e}")

    def _stop_stream(self) -> None:
        """Stop any active log stream."""
        if self._log_stream:
            try:
                self._log_stream.stop()
            except Exception:
                pass
            self._log_stream = None
        self._log_subscriber = None
        self._streaming_item = None

    async def _update_context(self, item: ActivityItem) -> None:
        """Update the context panel with item details."""
        context = self.query_one("#context-panel", RichLog)
        context.clear()

        if item.item_type == "workflow" and item.workflow_run:
            run = item.workflow_run
            context.write(f"[bold]Workflow Run #{run['id']}[/bold]")
            context.write(f"Status: {run.get('status', 'unknown')}")
            context.write(f"Started: {run.get('started_at', 'unknown')}")
            if run.get("completed_at"):
                context.write(f"Completed: {run['completed_at']}")
            if run.get("input_tokens"):
                context.write(f"Input: {format_tokens(run['input_tokens'])}")
            if run.get("output_tokens"):
                context.write(f"Output: {format_tokens(run['output_tokens'])}")
        elif item.item_type == "document" and item.doc_id:
            context.write(f"[bold]Document #{item.doc_id}[/bold]")
            context.write(f"Title: {item.title}")
        elif item.item_type == "group" and item.group:
            context.write(f"[bold]Group: {item.title}[/bold]")
            context.write(f"Type: {item.group.get('group_type', 'unknown')}")

    # =========================================================================
    # Expansion/Collapse
    # =========================================================================

    async def _toggle_expand(self, item: ActivityItem) -> None:
        """Toggle expansion of an item."""
        if item.expanded:
            self._collapse_item(item)
        else:
            await self._expand_item(item)

        self._flatten_items()
        await self._update_list()

    async def _expand_item(self, item: ActivityItem) -> None:
        """Expand an item to show children."""
        if item.item_type == "workflow":
            await self._expand_workflow(item)
        elif item.item_type == "group":
            await self._expand_group(item)
        item.expanded = True

    async def _expand_workflow(self, item: ActivityItem) -> None:
        """Expand a workflow to show outputs."""
        if not HAS_WORKFLOWS or not wf_db:
            return

        run_id = item.item_id
        output_ids = wf_db.get_workflow_output_doc_ids(run_id)

        item.children = []
        for doc_id in output_ids:
            if HAS_DOCS and doc_db:
                try:
                    doc = doc_db.get_document(doc_id)
                    if doc:
                        child = ActivityItem(
                            item_type="document",
                            item_id=doc_id,
                            title=doc.get("title", f"Doc {doc_id}"),
                            time_ago="",
                            icon="📄",
                            doc_id=doc_id,
                            parent=item,
                        )
                        item.children.append(child)
                except Exception:
                    pass

    async def _expand_group(self, item: ActivityItem) -> None:
        """Expand a group to show members."""
        if not HAS_GROUPS or not groups_db:
            return

        group_id = item.item_id
        members = groups_db.get_group_documents(group_id)

        item.children = []
        for member in members:
            doc_id = member.get("document_id")
            if doc_id and HAS_DOCS and doc_db:
                try:
                    doc = doc_db.get_document(doc_id)
                    if doc:
                        child = ActivityItem(
                            item_type="document",
                            item_id=doc_id,
                            title=doc.get("title", f"Doc {doc_id}"),
                            time_ago="",
                            icon="📄",
                            doc_id=doc_id,
                            parent=item,
                        )
                        item.children.append(child)
                except Exception:
                    pass

    def _collapse_item(self, item: ActivityItem) -> None:
        """Collapse an item."""
        item.expanded = False
        item.children = []

    # =========================================================================
    # Actions
    # =========================================================================

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        list_panel = self.query_one("#activity-list", ListPanel)
        list_panel.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        list_panel = self.query_one("#activity-list", ListPanel)
        list_panel.action_cursor_up()

    async def action_select(self) -> None:
        """Select/expand current item."""
        if self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            await self._toggle_expand(item)

    async def action_expand(self) -> None:
        """Expand current item."""
        if self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            if not item.expanded:
                await self._expand_item(item)
                self._flatten_items()
                await self._update_list()

    async def action_collapse(self) -> None:
        """Collapse current item or go to parent."""
        if self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            if item.expanded:
                self._collapse_item(item)
                self._flatten_items()
                await self._update_list()
            elif item.parent:
                # Move to parent
                for i, flat_item in enumerate(self.flat_items):
                    if flat_item is item.parent:
                        self.selected_idx = i
                        list_panel = self.query_one("#activity-list", ListPanel)
                        list_panel.select_item_by_index(i)
                        break

    def action_fullscreen(self) -> None:
        """View selected document fullscreen."""
        if self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            if item.doc_id:
                self.post_message(self.ViewDocument(item.doc_id))

    def action_refresh(self) -> None:
        """Refresh the activity list."""
        import asyncio
        asyncio.create_task(self._refresh_data())
        self.notify("Refreshed")

    def action_add_to_group(self) -> None:
        """Show group picker to add item to group."""
        if self.selected_idx >= len(self.flat_items):
            return
        item = self.flat_items[self.selected_idx]
        picker = self.query_one("#group-picker", GroupPicker)

        if item.item_type == "group":
            picker.show(source_group_id=item.item_id)
        elif item.item_type == "workflow" and item.workflow_run:
            picker.show(workflow_run_id=item.workflow_run.get("id"))
        elif item.doc_id:
            picker.show(doc_id=item.doc_id)
        else:
            self.notify("Select a document, group, or workflow")

    async def action_create_group(self) -> None:
        """Create a new group."""
        picker = self.query_one("#group-picker", GroupPicker)
        picker.show(create_mode=True)

    async def action_create_gist(self) -> None:
        """Create a new gist document."""
        if not HAS_DOCS or not doc_db:
            self.notify("Documents not available")
            return
        try:
            from emdx.database.documents import save_document
            from emdx.utils.git import get_git_project
            project = get_git_project()
            doc_id = save_document(title="New Gist", content="", project=project)
            self.notify(f"Created gist #{doc_id}")
            await self._refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}")

    async def action_ungroup(self) -> None:
        """Remove item from its group."""
        if self.selected_idx >= len(self.flat_items):
            return
        item = self.flat_items[self.selected_idx]
        if item.parent and item.parent.item_type == "group" and item.doc_id:
            if HAS_GROUPS and groups_db:
                try:
                    groups_db.remove_document_from_group(item.parent.item_id, item.doc_id)
                    self.notify(f"Removed from group")
                    await self._refresh_data()
                except Exception as e:
                    self.notify(f"Error: {e}")

    def action_focus_next(self) -> None:
        """Focus next panel."""
        try:
            preview = self.query_one("#preview-panel", PreviewPanel)
            preview.focus()
        except Exception:
            pass

    def action_focus_prev(self) -> None:
        """Focus previous panel."""
        try:
            list_panel = self.query_one("#activity-list", ListPanel)
            list_panel.focus()
        except Exception:
            pass

    # =========================================================================
    # GroupPicker Event Handlers
    # =========================================================================

    async def on_group_picker_group_selected(self, event: GroupPicker.GroupSelected) -> None:
        """Handle group selection."""
        if not HAS_GROUPS or not groups_db:
            return
        try:
            if event.workflow_run_id:
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self.notify(f"Moved group under '{event.group_name}'")
            elif event.doc_id:
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self.notify(f"Added to '{event.group_name}'")
            await self._refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}")

        list_panel = self.query_one("#activity-list", ListPanel)
        list_panel.focus()

    async def on_group_picker_group_created(self, event: GroupPicker.GroupCreated) -> None:
        """Handle new group creation."""
        if not HAS_GROUPS or not groups_db:
            return
        try:
            if event.workflow_run_id:
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self.notify(f"Created '{event.group_name}' and moved group under it")
            elif event.doc_id:
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self.notify(f"Created '{event.group_name}' and added document")
            await self._refresh_data()
        except Exception as e:
            self.notify(f"Error: {e}")

        list_panel = self.query_one("#activity-list", ListPanel)
        list_panel.focus()

    async def _group_workflow_under(self, workflow_run_id: int, parent_group_id: int, parent_name: str) -> None:
        """Group a workflow's outputs under a parent group."""
        if not HAS_WORKFLOWS or not wf_db:
            return

        run = wf_db.get_workflow_run(workflow_run_id)
        if not run:
            self.notify("Workflow run not found")
            return

        wf_id = run.get("workflow_id")
        wf = wf_db.get_workflow(wf_id) if wf_id else None
        wf_name = wf.get("name", "Workflow") if wf else "Workflow"

        existing_groups = groups_db.list_groups(workflow_run_id=workflow_run_id)
        if existing_groups:
            for grp in existing_groups:
                if grp.get("parent_group_id") != parent_group_id:
                    groups_db.update_group(grp["id"], parent_group_id=parent_group_id)
            self.notify(f"Moved workflow under '{parent_name}'")
        else:
            wf_group_id = groups_db.create_group(
                name=f"{wf_name} #{workflow_run_id}",
                group_type="batch",
                parent_group_id=parent_group_id,
                workflow_run_id=workflow_run_id,
                created_by="user",
            )
            output_ids = wf_db.get_workflow_output_doc_ids(workflow_run_id)
            for doc_id in output_ids:
                try:
                    groups_db.add_document_to_group(wf_group_id, doc_id, role="member")
                except Exception:
                    pass
            self.notify(f"Grouped under '{parent_name}'")

    def on_group_picker_cancelled(self, event: GroupPicker.Cancelled) -> None:
        """Handle picker cancellation."""
        list_panel = self.query_one("#activity-list", ListPanel)
        list_panel.focus()

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the list panel."""
        try:
            list_panel = self.query_one("#activity-list", ListPanel)
            list_panel.focus()
        except Exception:
            pass
