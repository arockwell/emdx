"""
ActivityBrowser - Activity browser matching the original ActivityView exactly.

This browser provides a view of EMDX activity:
- Status bar with active count, tokens (today), docs today, cost, errors, sparkline
- Activity stream showing groups, workflows, and direct saves
- Hierarchical expansion (workflows show stage runs, groups show docs)
- Context panel (bottom left) with detailed metadata
- Preview pane for document content
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, RichLog, DataTable

from ..activity.sparkline import sparkline
from ..activity.group_picker import GroupPicker
from ..modals import HelpMixin

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


class AgentLogSubscriber:
    """Forwards log content to the activity browser."""

    def __init__(self, browser: "ActivityBrowser"):
        self.browser = browser

    def on_log_content(self, new_content: str) -> None:
        self.browser._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        logger.error(f"Log stream error: {error}")


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
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def format_cost(cost: float) -> str:
    """Format cost in dollars."""
    if not cost or cost == 0:
        return "—"
    if cost < 0.01:
        return f"${cost:.3f}"
    return f"${cost:.2f}"


def format_tokens(tokens: int) -> str:
    """Format token count with K/M abbreviations."""
    if tokens is None or tokens == 0:
        return "—"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)


class ActivityItem:
    """Represents an item in the activity stream - matches original ActivityView."""

    def __init__(
        self,
        item_type: str,  # 'workflow', 'document', 'group', 'synthesis', 'exploration', 'individual_run'
        item_id: int,
        title: str,
        status: str,
        timestamp: datetime,
        cost: float = 0,
        tokens: int = 0,
        children: Optional[List["ActivityItem"]] = None,
        doc_id: Optional[int] = None,
        workflow_run: Optional[Dict] = None,
        individual_run: Optional[Dict] = None,
        depth: int = 0,
    ):
        self.item_type = item_type
        self.item_id = item_id
        self.title = title
        self.status = status
        self.timestamp = timestamp
        self.cost = cost
        self.tokens = tokens
        self.children = children or []
        self.doc_id = doc_id
        self.workflow_run = workflow_run
        self.individual_run = individual_run
        self.depth = depth
        self.expanded = False
        # Progress tracking for running workflows
        self.progress_completed = 0
        self.progress_total = 0
        self.progress_stage = ""
        # These will be set during load
        self._input_tokens = 0
        self._output_tokens = 0
        self._has_workflow_outputs = False
        self._output_count = 0
        self._has_group_children = False
        self._has_doc_children = False
        self.group_type = "batch"
        self.doc_count = 0

    @property
    def status_icon(self) -> str:
        if self.status == "running":
            return "🔄"
        elif self.status == "completed":
            return "✅"
        elif self.status == "failed":
            return "❌"
        elif self.status == "queued":
            return "⏸️"
        elif self.status == "pending":
            return "⏳"
        return "⚪"

    @property
    def type_icon(self) -> str:
        if self.item_type == "workflow":
            return "⚡"
        elif self.item_type == "synthesis":
            return "📝"
        elif self.item_type == "exploration":
            return "◇"
        elif self.item_type == "individual_run":
            return "🤖"
        elif self.item_type == "document":
            return "📄"
        elif self.item_type == "group":
            icons = {
                "initiative": "📋",
                "round": "🔄",
                "batch": "📦",
            }
            return icons.get(self.group_type, "📦")
        return "⚪"


class ActivityBrowser(HelpMixin, Widget):
    """Activity browser matching original ActivityView behavior."""

    HELP_TITLE = "Activity View"
    """Help title for the keybindings modal."""

    class ViewDocument(Message):
        """Request to view a document fullscreen."""
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
        background: $boost;
        padding: 0 1;
        dock: top;
    }

    ActivityBrowser #main-content {
        height: 1fr;
    }

    ActivityBrowser #activity-panel {
        width: 40%;
        height: 100%;
    }

    ActivityBrowser #activity-list-section {
        height: 70%;
    }

    ActivityBrowser #activity-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    ActivityBrowser #activity-table {
        height: 1fr;
    }

    ActivityBrowser #context-section {
        height: 30%;
        border-top: solid $secondary;
    }

    ActivityBrowser #context-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    ActivityBrowser #context-scroll {
        height: 1fr;
    }

    ActivityBrowser #context-content {
        padding: 0 1;
    }

    ActivityBrowser #preview-panel {
        width: 60%;
        height: 100%;
        border-left: solid $primary;
    }

    ActivityBrowser #preview-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    ActivityBrowser #preview-scroll {
        height: 1fr;
    }

    ActivityBrowser #preview-content {
        padding: 0 1;
    }

    ActivityBrowser #preview-log {
        height: 1fr;
        padding: 0 1;
        display: none;
    }

    ActivityBrowser #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
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
        self.activity_items: List[ActivityItem] = []  # Top-level items
        self.flat_items: List[ActivityItem] = []  # Flattened for display
        self.selected_idx: int = 0
        self._zombies_cleaned = False
        self._last_preview_key: Optional[tuple] = None
        # Log streaming
        self.log_stream: Optional[Any] = None
        self.log_subscriber = AgentLogSubscriber(self)
        self.streaming_item_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        """Compose the browser layout."""
        yield Static("Loading...", id="status-bar")

        with Horizontal(id="main-content"):
            with Vertical(id="activity-panel"):
                with Vertical(id="activity-list-section"):
                    yield Static("ACTIVITY", id="activity-header")
                    yield DataTable(id="activity-table", cursor_type="row")

                with Vertical(id="context-section"):
                    yield Static("DETAILS", id="context-header")
                    with ScrollableContainer(id="context-scroll"):
                        yield RichLog(
                            id="context-content",
                            highlight=True,
                            markup=True,
                            wrap=True,
                            auto_scroll=False,
                        )

            with Vertical(id="preview-panel"):
                yield Static("PREVIEW", id="preview-header")
                with ScrollableContainer(id="preview-scroll"):
                    yield RichLog(
                        id="preview-content",
                        highlight=True,
                        markup=True,
                        wrap=True,
                        auto_scroll=False,
                    )
                yield RichLog(id="preview-log", highlight=True, markup=True, wrap=True)

        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Workflows │ [dim]3[/dim] Documents │ "
            "[dim]j/k[/dim] nav │ [dim]Enter[/dim] expand │ [dim]f[/dim] fullscreen │ [dim]?[/dim] help",
            id="help-bar",
        )

        # Group picker overlay
        yield GroupPicker(id="group-picker")

    async def on_mount(self) -> None:
        """Initialize the browser."""
        table = self.query_one("#activity-table", DataTable)
        table.add_column("", width=2)  # Icon
        table.add_column("Time", width=4)
        table.add_column("Title")  # Dynamic width
        table.add_column("ID", width=6)

        await self.load_data()
        table.focus()

        self.set_interval(5.0, self._refresh_data)

    async def load_data(self, update_preview: bool = True) -> None:
        """Load activity data - matches original ActivityView algorithm."""
        self.activity_items = []

        # Clean up zombie workflow runs only once on first load
        if HAS_WORKFLOWS and wf_db and not self._zombies_cleaned:
            try:
                cleaned = wf_db.cleanup_zombie_workflow_runs(max_age_hours=24.0)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} zombie workflow runs")
                self._zombies_cleaned = True
            except Exception as e:
                logger.debug(f"Could not cleanup zombies: {e}")

        # Load document groups first (they contain documents)
        if HAS_GROUPS and groups_db:
            await self._load_groups()

        # Load workflows
        if HAS_WORKFLOWS and wf_db:
            await self._load_workflows()

        # Load recent direct saves (documents not from workflows or groups)
        if HAS_DOCS and doc_db:
            await self._load_direct_saves()

        # Sort: running workflows first (pinned), then by timestamp descending
        def sort_key(item):
            is_running = item.item_type == "workflow" and item.status == "running"
            return (0 if is_running else 1, -item.timestamp.timestamp() if item.timestamp else 0)

        self.activity_items.sort(key=sort_key)

        # Flatten for display
        self._flatten_items()

        # Update UI
        await self._update_table()
        await self._update_status_bar()
        if update_preview:
            await self._update_preview()
            await self._update_context()

    async def _load_groups(self) -> None:
        """Load document groups into activity items."""
        try:
            top_groups = groups_db.list_groups(top_level_only=True)

            for group in top_groups:
                group_id = group["id"]
                created = group.get("created_at")
                if isinstance(created, str):
                    from emdx.utils.datetime import parse_datetime
                    created = parse_datetime(created)
                if not created:
                    created = datetime.now()

                # Count child groups for expansion indicator
                child_groups = groups_db.get_child_groups(group_id)

                item = ActivityItem(
                    item_type="group",
                    item_id=group_id,
                    title=group["name"],
                    status="completed",
                    timestamp=created,
                    cost=group.get("total_cost_usd", 0) or 0,
                    tokens=group.get("total_tokens", 0) or 0,
                )

                # Store group metadata for display
                item.group_type = group.get("group_type", "batch")
                # Use recursive count to include nested groups' docs
                item.doc_count = groups_db.get_recursive_doc_count(group_id)
                item._has_group_children = len(child_groups) > 0 or item.doc_count > 0

                self.activity_items.append(item)

        except Exception as e:
            logger.error(f"Error loading groups: {e}", exc_info=True)

    async def _load_workflows(self) -> None:
        """Load workflow runs into activity items."""
        try:
            runs = wf_db.list_workflow_runs(limit=50)

            for run in runs:
                # Parse timestamp
                started = run.get("started_at")
                if isinstance(started, str):
                    from emdx.utils.datetime import parse_datetime
                    started = parse_datetime(started)
                if not started:
                    started = datetime.now()

                # Skip zombie running workflows (running for > 2 hours)
                if run.get("status") == "running":
                    age_hours = (datetime.now() - started).total_seconds() / 3600
                    if age_hours > 2:
                        continue

                # Get workflow name
                wf_name = "Workflow"
                if workflow_registry:
                    try:
                        wf = workflow_registry.get_workflow(run["workflow_id"])
                        if wf:
                            wf_name = wf.display_name
                    except Exception:
                        pass

                # Get task title from input variables
                task_title = ""
                try:
                    input_vars = run.get("input_variables")
                    if isinstance(input_vars, str):
                        input_vars = json.loads(input_vars)
                    if input_vars:
                        task_title = input_vars.get("task_title", "")
                except Exception:
                    pass

                title = task_title or wf_name

                # Calculate cost - check top-level, then sum from individual runs
                cost = run.get("total_cost_usd", 0) or 0
                if not cost:
                    try:
                        stage_runs = wf_db.list_stage_runs(run["id"])
                        for sr in stage_runs:
                            ind_runs = wf_db.list_individual_runs(sr["id"])
                            for ir in ind_runs:
                                ir_cost = ir.get("cost_usd", 0) or 0
                                cost += ir_cost
                    except Exception:
                        pass

                item = ActivityItem(
                    item_type="workflow",
                    item_id=run["id"],
                    title=title,
                    status=run.get("status", "unknown"),
                    timestamp=started,
                    cost=cost,
                    workflow_run=run,
                )

                # Check if workflow has any outputs and gather stats
                try:
                    stage_runs = wf_db.list_stage_runs(run["id"])
                    has_outputs = False
                    output_doc_id = None
                    output_count = 0
                    total_target = 0
                    total_completed = 0
                    current_stage = ""
                    total_input_tokens = 0
                    total_output_tokens = 0

                    for sr in stage_runs:
                        # Track progress
                        target = sr.get("target_runs", 1)
                        completed = sr.get("runs_completed", 0)
                        total_target += target
                        total_completed += completed
                        # Track current running stage
                        if sr.get("status") == "running":
                            current_stage = sr.get("stage_name", "")
                        # Check synthesis FIRST (prefer over individual outputs)
                        if sr.get("synthesis_doc_id"):
                            output_count += 1
                            has_outputs = True
                            if not output_doc_id:
                                output_doc_id = sr["synthesis_doc_id"]
                        ind_runs = wf_db.list_individual_runs(sr["id"])
                        # Count individual outputs and sum tokens
                        for ir in ind_runs:
                            total_input_tokens += ir.get("input_tokens", 0) or 0
                            total_output_tokens += ir.get("output_tokens", 0) or 0
                            if ir.get("output_doc_id"):
                                output_count += 1
                                has_outputs = True
                                if not output_doc_id:
                                    output_doc_id = ir["output_doc_id"]

                    if has_outputs:
                        item._has_workflow_outputs = True
                        item._output_count = output_count
                    # Store token counts for status bar
                    item._input_tokens = total_input_tokens
                    item._output_tokens = total_output_tokens
                    # Store progress info for running workflows
                    if run.get("status") == "running":
                        item.progress_completed = total_completed
                        item.progress_total = total_target
                        item.progress_stage = current_stage
                    # For completed workflows, set doc_id to the output document
                    if output_doc_id and run.get("status") in ("completed", "failed"):
                        item.doc_id = output_doc_id
                        # Get the output document's timestamp for consistent timezone handling
                        if HAS_DOCS:
                            try:
                                out_doc = doc_db.get_document(output_doc_id)
                                if out_doc:
                                    doc_created = out_doc.get("created_at")
                                    if isinstance(doc_created, str):
                                        from emdx.utils.datetime import parse_datetime
                                        doc_created = parse_datetime(doc_created)
                                    if doc_created:
                                        item.timestamp = doc_created
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"Error checking workflow outputs for run {run['id']}: {e}")

                self.activity_items.append(item)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)

    async def _load_direct_saves(self) -> None:
        """Load documents that weren't created by workflows or added to groups."""
        try:
            # Get documents that are in groups (to exclude them)
            grouped_doc_ids = set()
            if HAS_GROUPS and groups_db:
                try:
                    grouped_doc_ids = groups_db.get_all_grouped_document_ids()
                except Exception as e:
                    logger.debug(f"Error getting grouped doc IDs: {e}")

            # Use efficient single-query function that excludes workflow docs via LEFT JOIN
            docs = list_non_workflow_documents(limit=100, days=7, include_archived=False)

            for doc in docs:
                doc_id = doc["id"]

                # Skip documents that are in groups (they'll show under their group)
                if doc_id in grouped_doc_ids:
                    continue

                created = doc.get("created_at")
                title = doc.get("title", "")

                # Check if this document has children
                children_docs = doc_db.get_children(doc_id, include_archived=False)
                has_children = len(children_docs) > 0

                item = ActivityItem(
                    item_type="document",
                    item_id=doc_id,
                    title=title or "Untitled",
                    status="completed",
                    timestamp=created,
                    doc_id=doc_id,
                )

                # Mark that this document can be expanded
                if has_children:
                    item._has_doc_children = True

                self.activity_items.append(item)

        except Exception as e:
            logger.error(f"Error loading direct saves: {e}", exc_info=True)

    def _flatten_items(self) -> None:
        """Flatten activity items for display, respecting expansion state."""
        self.flat_items = []

        for item in self.activity_items:
            self.flat_items.append(item)
            if item.expanded and item.children:
                for child in item.children:
                    child.depth = 1
                    self.flat_items.append(child)
                    if child.expanded and child.children:
                        for grandchild in child.children:
                            grandchild.depth = 2
                            self.flat_items.append(grandchild)

    async def _update_table(self) -> None:
        """Update the activity table."""
        table = self.query_one("#activity-table", DataTable)
        table.clear()

        for item in self.flat_items:
            # Indentation based on depth
            indent = "  " * item.depth

            # Expand indicator for items that can have children
            has_doc_children = item._has_doc_children
            has_workflow_outputs = item._has_workflow_outputs
            has_group_children = item._has_group_children
            # All completed/failed workflows should be expandable
            is_completed_workflow = (
                item.item_type == "workflow" and
                item.status in ("completed", "failed")
            )
            output_count = item._output_count
            doc_count = item.doc_count
            is_running_workflow = item.item_type == "workflow" and item.status == "running"

            if item.expanded and item.children:
                expand = "▼ "
                badge = ""
            elif is_running_workflow or \
                 (item.item_type == "workflow" and (has_workflow_outputs or is_completed_workflow)) or \
                 (item.item_type == "group" and has_group_children) or \
                 (item.item_type == "document" and has_doc_children):
                expand = "▶ "
                # Show count badge for collapsed items
                if item.item_type == "workflow" and output_count > 0:
                    badge = f" [{output_count}]"
                elif item.item_type == "group" and doc_count > 0:
                    badge = f" [{doc_count}]"
                else:
                    badge = ""
            else:
                expand = "  "
                badge = ""

            # Icon based on status/type
            if item.status in ("running", "failed", "pending", "queued"):
                icon = item.status_icon
            else:
                icon = item.type_icon

            time_str = format_time_ago(item.timestamp)

            # Progress bar for running workflows
            progress_str = ""
            if item.item_type == "workflow" and item.status == "running" and item.progress_total > 0:
                pct = item.progress_completed / item.progress_total
                bar_width = 10
                filled = int(pct * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                progress_str = f" {bar} {item.progress_completed}/{item.progress_total}"

            title = f"{indent}{expand}{item.title[:40]}{progress_str or badge}"

            if item.item_type in ("workflow", "group"):
                id_str = f"#{item.item_id}" if item.item_id else "—"
            else:
                id_str = f"#{item.doc_id}" if item.doc_id else "—"

            table.add_row(icon, time_str, title, id_str)

        # Restore selection
        if self.flat_items and self.selected_idx < len(self.flat_items):
            table.move_cursor(row=self.selected_idx)

    async def _update_status_bar(self) -> None:
        """Update the status bar with current stats - matches original."""
        try:
            status_bar = self.query_one("#status-bar", Static)
        except Exception:
            return

        # Count active workflows
        active = sum(
            1
            for item in self.activity_items
            if item.item_type == "workflow" and item.status == "running"
        )

        # Count docs today
        today = datetime.now().date()
        docs_today = sum(
            1
            for item in self.activity_items
            if item.timestamp and item.timestamp.date() == today
        )

        # Total cost today
        cost_today = sum(
            item.cost
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.cost
        )

        # Count errors (today only)
        errors = sum(
            1
            for item in self.activity_items
            if item.status == "failed"
            and item.timestamp
            and item.timestamp.date() == today
        )

        # Total tokens today (input/output) - from workflows only
        input_tokens_today = sum(
            item._input_tokens or 0
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.item_type == "workflow"
        )
        output_tokens_today = sum(
            item._output_tokens or 0
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.item_type == "workflow"
        )

        # Generate sparkline for the week
        week_data = self._get_week_activity_data()
        spark = sparkline(week_data, width=7)

        # Format status bar
        parts = []
        if active > 0:
            parts.append(f"[green]🟢 {active} Active[/green]")
        else:
            parts.append("[dim]⚪ 0 Active[/dim]")

        # Tokens: in↓ / out↑
        if input_tokens_today > 0 or output_tokens_today > 0:
            parts.append(f"↓{format_tokens(input_tokens_today)} ↑{format_tokens(output_tokens_today)}")

        parts.append(f"📄 {docs_today} today")
        parts.append(format_cost(cost_today))

        if errors > 0:
            parts.append(f"[red]⚠️ {errors}[/red]")

        parts.append(f"[dim]{spark}[/dim]")
        parts.append(datetime.now().strftime("%H:%M"))

        status_bar.update(" │ ".join(parts))

    def _get_week_activity_data(self) -> List[int]:
        """Get activity counts for each day of the past week."""
        today = datetime.now().date()
        counts = []

        for i in range(6, -1, -1):  # 6 days ago to today
            day = today - timedelta(days=i)
            count = sum(
                1
                for item in self.activity_items
                if item.timestamp and item.timestamp.date() == day
            )
            counts.append(count)

        return counts

    async def _refresh_data(self) -> None:
        """Periodic refresh - preserve expansion state."""
        # Remember expanded state
        expanded_ids = {
            (item.item_type, item.item_id)
            for item in self.flat_items
            if item.expanded
        }
        selected_id = None
        if self.flat_items and self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            selected_id = (item.item_type, item.item_id)

        await self.load_data(update_preview=False)

        # Restore expansions
        for item in self.activity_items:
            if (item.item_type, item.item_id) in expanded_ids:
                if item.item_type == "workflow":
                    await self._expand_workflow(item)
                elif item.item_type == "group":
                    await self._expand_group(item)

        self._flatten_items()
        await self._update_table()

        # Restore selection
        if selected_id:
            for i, item in enumerate(self.flat_items):
                if (item.item_type, item.item_id) == selected_id:
                    self.selected_idx = i
                    break

    async def _expand_workflow(self, item: ActivityItem) -> None:
        """Expand a workflow to show stage runs and outputs."""
        if not item.workflow_run or item.expanded:
            return

        run = item.workflow_run
        children = []

        try:
            if HAS_WORKFLOWS and wf_db:
                stage_runs = wf_db.list_stage_runs(run["id"])
                for sr in stage_runs:
                    stage_status = sr.get("status", "pending")
                    ind_runs = wf_db.list_individual_runs(sr["id"])

                    # For running workflows, show individual runs with status
                    if stage_status in ("running", "pending") or run.get("status") == "running":
                        for ir in ind_runs:
                            ir_status = ir.get("status", "pending")
                            run_num = ir.get("run_number", 0)

                            if ir_status == "completed" and ir.get("output_doc_id"):
                                doc = doc_db.get_document(ir["output_doc_id"]) if HAS_DOCS else None
                                title = doc.get("title", f"Run {run_num}")[:25] if doc else f"Run {run_num}"
                            elif ir_status == "running":
                                title = f"Run {run_num} (running...)"
                            elif ir_status == "pending":
                                title = f"Run {run_num} (pending)"
                            elif ir_status == "failed":
                                title = f"Run {run_num} (failed)"
                            else:
                                title = f"Run {run_num}"

                            child = ActivityItem(
                                item_type="individual_run",
                                item_id=ir.get("id"),
                                title=title,
                                status=ir_status,
                                timestamp=item.timestamp,
                                doc_id=ir.get("output_doc_id"),
                                cost=ir.get("cost_usd", 0) or 0,
                                individual_run=ir,
                                depth=1,
                            )
                            children.append(child)
                    else:
                        # Completed: show synthesis first, then outputs
                        if sr.get("synthesis_doc_id"):
                            doc = doc_db.get_document(sr["synthesis_doc_id"]) if HAS_DOCS else None
                            title = doc.get("title", "Synthesis") if doc else "Synthesis"
                            synth = ActivityItem(
                                item_type="synthesis",
                                item_id=sr["synthesis_doc_id"],
                                title=title[:30],
                                status="completed",
                                timestamp=item.timestamp,
                                doc_id=sr["synthesis_doc_id"],
                                depth=1,
                            )
                            children.append(synth)

                            # Individual outputs
                            for ir in ind_runs:
                                if ir.get("output_doc_id") and ir["output_doc_id"] != sr.get("synthesis_doc_id"):
                                    out_doc = doc_db.get_document(ir["output_doc_id"]) if HAS_DOCS else None
                                    out_title = out_doc.get("title", f"Output #{ir['run_number']}")[:25] if out_doc else f"Output #{ir['run_number']}"
                                    out = ActivityItem(
                                        item_type="exploration",
                                        item_id=ir["output_doc_id"],
                                        title=out_title,
                                        status="completed",
                                        timestamp=item.timestamp,
                                        doc_id=ir["output_doc_id"],
                                        individual_run=ir,
                                        depth=1,
                                    )
                                    children.append(out)
                        else:
                            # No synthesis - show outputs directly
                            for ir in ind_runs:
                                ir_status = ir.get("status", "completed")
                                run_num = ir.get("run_number", 0)
                                if ir.get("output_doc_id"):
                                    doc = doc_db.get_document(ir["output_doc_id"]) if HAS_DOCS else None
                                    title = doc.get("title", f"Output #{run_num}")[:25] if doc else f"Output #{run_num}"
                                    child = ActivityItem(
                                        item_type="exploration",
                                        item_id=ir["output_doc_id"],
                                        title=title,
                                        status=ir_status,
                                        timestamp=item.timestamp,
                                        doc_id=ir["output_doc_id"],
                                        individual_run=ir,
                                        depth=1,
                                    )
                                else:
                                    child = ActivityItem(
                                        item_type="individual_run",
                                        item_id=ir.get("id"),
                                        title=f"Run {run_num} ({ir_status})",
                                        status=ir_status,
                                        timestamp=item.timestamp,
                                        individual_run=ir,
                                        depth=1,
                                    )
                                children.append(child)
        except Exception as e:
            logger.error(f"Error expanding workflow: {e}")

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    async def _expand_group(self, item: ActivityItem) -> None:
        """Expand a group to show its documents."""
        if item.expanded:
            return

        children = []
        try:
            if HAS_GROUPS and groups_db:
                # Get child groups first
                child_groups = groups_db.get_child_groups(item.item_id)
                for cg in child_groups:
                    created = cg.get("created_at")
                    if isinstance(created, str):
                        from emdx.utils.datetime import parse_datetime
                        created = parse_datetime(created)

                    child = ActivityItem(
                        item_type="group",
                        item_id=cg["id"],
                        title=cg["name"][:35],
                        status="completed",
                        timestamp=created or item.timestamp,
                        depth=1,
                    )
                    child.group_type = cg.get("group_type", "batch")
                    child.doc_count = groups_db.get_recursive_doc_count(cg["id"])
                    child._has_group_children = child.doc_count > 0
                    children.append(child)

                # Get direct member documents
                members = groups_db.get_group_members(item.item_id)
                for member in members:
                    doc_id = member.get("document_id")
                    if doc_id and HAS_DOCS:
                        doc = doc_db.get_document(doc_id)
                        if doc:
                            child = ActivityItem(
                                item_type="document",
                                item_id=doc_id,
                                title=doc.get("title", "Untitled")[:35],
                                status="completed",
                                timestamp=item.timestamp,
                                doc_id=doc_id,
                                depth=1,
                            )
                            children.append(child)
        except Exception as e:
            logger.error(f"Error expanding group: {e}")

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    async def _expand_document(self, item: ActivityItem) -> None:
        """Expand a document to show its children."""
        if item.expanded or not item._has_doc_children:
            return

        children = []
        try:
            if HAS_DOCS and doc_db:
                child_docs = doc_db.get_children(item.doc_id, include_archived=False)
                for doc in child_docs:
                    created = doc.get("created_at")
                    child = ActivityItem(
                        item_type="document",
                        item_id=doc["id"],
                        title=doc.get("title", "Untitled")[:35],
                        status="completed",
                        timestamp=created or item.timestamp,
                        doc_id=doc["id"],
                        depth=1,
                    )
                    children.append(child)
        except Exception as e:
            logger.error(f"Error expanding document: {e}")

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    def _collapse_item(self, item: ActivityItem) -> None:
        """Collapse an item."""
        item.expanded = False
        item.children = []

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row selection."""
        if event.row_key is not None:
            self.selected_idx = event.cursor_row
            await self._update_preview()
            await self._update_context()

    async def _update_preview(self, force: bool = False) -> None:
        """Update preview pane."""
        from pathlib import Path
        from rich.markup import escape as escape_markup

        try:
            preview = self.query_one("#preview-content", RichLog)
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception:
            return

        def show_markdown():
            preview_scroll.display = True
            preview_log.display = False

        def show_log():
            preview_scroll.display = False
            preview_log.display = True

        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            preview.clear()
            preview.write("[dim]Select an item to preview[/dim]")
            show_markdown()
            header.update("PREVIEW")
            self._last_preview_key = None
            return

        item = self.flat_items[self.selected_idx]
        current_key = (item.item_type, item.item_id, item.status)

        # Skip update if same item and not forced (prevents flickering during refresh)
        # Always update for running items (logs change) or if explicitly forced
        if not force and item.status != "running" and self._last_preview_key == current_key:
            return

        self._last_preview_key = current_key

        # Stop any existing stream
        self._stop_stream()

        # For running workflows or individual runs, show live log
        if item.status == "running" and item.item_type in ("workflow", "individual_run"):
            await self._show_live_log(item)
            return

        # For documents, show content
        preview.clear()
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
                    header.update(f"📄 #{item.doc_id}")

                    if content.strip():
                        from emdx.ui.markdown_config import MarkdownConfig
                        if len(content) > 50000:
                            content = content[:50000] + "\n\n[dim]... (truncated)[/dim]"
                        try:
                            md = MarkdownConfig.create_markdown(content)
                            preview.write(md)
                        except Exception:
                            preview.write(content)
                    else:
                        preview.write("[dim]Empty document[/dim]")
                    show_markdown()
                    return
            except Exception as e:
                logger.debug(f"Error loading preview: {e}")

        # Default
        show_markdown()
        header.update("PREVIEW")
        preview.write(f"[dim]{item.title}[/dim]\n\n[dim]No content available[/dim]")

    async def _show_live_log(self, item: ActivityItem) -> None:
        """Show live log for running workflow or individual run."""
        from pathlib import Path
        from rich.markup import escape as escape_markup

        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready for live log: {e}")
            return

        preview_scroll.display = False
        preview_log.display = True
        preview_log.clear()

        header.update(f"[green]● LIVE[/green] {item.title[:40]}")

        if not HAS_WORKFLOWS or not wf_db:
            preview_log.write("[dim]Workflow system not available[/dim]")
            return

        if not HAS_LOG_STREAM or not LogStream:
            preview_log.write("[dim]Log streaming not available[/dim]")
            return

        try:
            log_path = None

            # For individual runs, get log file from the execution record
            if item.item_type == "individual_run" and item.item_id:
                try:
                    from emdx.models.executions import get_execution
                    ir = wf_db.get_individual_run(item.item_id)
                    if ir and ir.get("agent_execution_id"):
                        exec_record = get_execution(ir["agent_execution_id"])
                        if exec_record and exec_record.log_file:
                            log_path = Path(exec_record.log_file)
                except Exception as e:
                    logger.debug(f"Could not get individual run log: {e}")

            # For workflow runs, find active execution
            elif item.item_type == "workflow" and item.workflow_run:
                run = item.workflow_run
                active_exec = wf_db.get_active_execution_for_run(run["id"])
                if active_exec and active_exec.get("log_file"):
                    log_path = Path(active_exec["log_file"])

            if not log_path:
                preview_log.write(f"[yellow]⏳ Waiting for log...[/yellow]")
                return

            if not log_path.exists():
                preview_log.write(f"[yellow]⏳ Log file pending...[/yellow]")
                return

            # Start streaming
            self.log_stream = LogStream(log_path)
            self.streaming_item_id = item.item_id

            # Show initial content
            initial = self.log_stream.get_initial_content()
            if initial:
                for line in initial.strip().split("\n")[-50:]:
                    preview_log.write(escape_markup(line))
                preview_log.scroll_end(animate=False)

            self.log_stream.subscribe(self.log_subscriber)

        except Exception as e:
            logger.error(f"Error setting up live log: {e}", exc_info=True)
            preview_log.write(f"[red]Error: {e}[/red]")

    def _handle_log_content(self, content: str) -> None:
        """Handle new log content from stream."""
        from rich.markup import escape as escape_markup

        try:
            preview_log = self.query_one("#preview-log", RichLog)
            for line in content.splitlines():
                preview_log.write(escape_markup(line))
            preview_log.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error handling log content: {e}")

    def _stop_stream(self) -> None:
        """Stop any active log stream."""
        if self.log_stream:
            self.log_stream.unsubscribe(self.log_subscriber)
            self.log_stream = None
        self.streaming_item_id = None

    async def _update_context(self) -> None:
        """Update the context panel with details about selected item."""
        try:
            context = self.query_one("#context-content", RichLog)
            header = self.query_one("#context-header", Static)
        except Exception:
            return

        context.clear()

        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            header.update("DETAILS")
            context.write("[dim]Select an item to see details[/dim]")
            return

        item = self.flat_items[self.selected_idx]

        # Workflow run details
        if item.item_type == "workflow" and item.workflow_run:
            await self._show_workflow_context(item, context, header)
        # Document details
        elif item.doc_id:
            await self._show_document_context(item, context, header)
        # Group details
        elif item.item_type == "group":
            await self._show_group_context(item, context, header)
        # Individual run details
        elif item.item_type == "individual_run" or item.individual_run:
            await self._show_individual_run_context(item, context, header)
        else:
            header.update("DETAILS")
            context.write(f"[dim]{item.item_type}: {item.title}[/dim]")

    async def _show_workflow_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show workflow run details in context panel."""
        import re
        import textwrap

        run = item.workflow_run
        if not run:
            return

        status = run.get("status", "unknown")
        status_colors = {"completed": "green", "failed": "red", "running": "yellow"}
        status_color = status_colors.get(status, "white")

        header.update(f"⚡ #{run['id']} [{status_color}]{status}[/{status_color}]")

        # For running workflows, show progress prominently
        if status == "running" and item.progress_total:
            progress_pct = int(100 * item.progress_completed / item.progress_total) if item.progress_total else 0
            content.write(f"[yellow bold]Progress: {item.progress_completed}/{item.progress_total} ({progress_pct}%)[/yellow bold]")
            if item.progress_stage:
                content.write(f"[dim]Current stage: {item.progress_stage}[/dim]")

        # Timing info as compact line
        timing_parts = []
        if run.get("total_execution_time_ms"):
            secs = run["total_execution_time_ms"] / 1000
            timing_parts.append(f"{secs:.1f}s" if secs < 60 else f"{secs/60:.1f}m")
        if run.get("total_tokens_used"):
            timing_parts.append(f"{format_tokens(run['total_tokens_used'])}")
        if item.cost:
            timing_parts.append(format_cost(item.cost))
        if timing_parts:
            content.write(f"[dim]{' · '.join(timing_parts)}[/dim]")

        # Tasks from input variables
        if run.get("input_variables"):
            try:
                vars_data = run["input_variables"]
                if isinstance(vars_data, str):
                    vars_data = json.loads(vars_data)
                tasks = vars_data.get("tasks", [])
                if tasks:
                    content.write("")
                    content.write(f"[bold cyan]─── Tasks ({len(tasks)}) ───[/bold cyan]")
                    wrap_width = 50
                    max_num_width = len(str(len(tasks))) + 2
                    indent = " " * max_num_width
                    for i, task in enumerate(tasks):
                        num_str = f"{i+1}.".rjust(max_num_width - 1) + " "
                        if isinstance(task, int):
                            task_str = f"#{task}"
                            if HAS_DOCS:
                                try:
                                    doc = doc_db.get_document(task)
                                    if doc and doc.get("title"):
                                        task_str = f"#{task}: {doc['title']}"
                                except Exception:
                                    pass
                            wrapped = textwrap.fill(
                                task_str,
                                width=wrap_width,
                                initial_indent=num_str,
                                subsequent_indent=indent,
                            )
                            content.write(f"[cyan]{wrapped}[/cyan]")
                        else:
                            task_str = str(task)
                            wrapped = textwrap.fill(
                                task_str,
                                width=wrap_width,
                                initial_indent=num_str,
                                subsequent_indent=indent,
                            )
                            content.write(wrapped)
            except (json.JSONDecodeError, TypeError):
                pass

        # Stages
        if HAS_WORKFLOWS and wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                content.write("")
                content.write(f"[bold cyan]─── Stages ───[/bold cyan]")
                for sr in stage_runs:
                    icon = {"completed": "[green]✓[/green]", "failed": "[red]✗[/red]", "running": "[yellow]⟳[/yellow]", "pending": "[dim]○[/dim]"}.get(sr["status"], "[dim]○[/dim]")
                    content.write(f"  {icon} {sr['stage_name']} {sr['runs_completed']}/{sr['target_runs']}")

                # Show prompt from first individual run
                for sr in stage_runs:
                    ind_runs = wf_db.list_individual_runs(sr["id"])
                    if ind_runs:
                        first_run = ind_runs[0]
                        prompt = first_run.get("prompt_used", "")
                        if prompt:
                            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", prompt, re.DOTALL)
                            if task_match:
                                task_text = task_match.group(1).strip()
                            else:
                                task_text = prompt.split("\n")[0]

                            content.write("")
                            label = "Current Prompt" if status == "running" else "Prompt"
                            content.write(f"[bold cyan]─── {label} ───[/bold cyan]")
                            wrap_width = 50
                            wrapped = textwrap.fill(task_text, width=wrap_width)
                            for line in wrapped.split("\n"):
                                content.write(f"[dim]{line}[/dim]")
                            break

        # Error if any
        if run.get("error_message"):
            content.write(f"[red]Error: {run['error_message'][:100]}[/red]")

    async def _show_document_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show document metadata in context panel."""
        import re
        import textwrap

        if not HAS_DOCS or not item.doc_id:
            header.update("DOCUMENT")
            return

        try:
            doc = doc_db.get_document(item.doc_id)
            if not doc:
                header.update(f"📄 #{item.doc_id}")
                return

            header.update(f"📄 #{doc['id']}")

            # Get tags for this document
            tags = []
            try:
                from emdx.models.tags import get_document_tags
                tags = get_document_tags(item.doc_id)
            except ImportError:
                pass

            # Check if this doc came from a workflow
            source = doc_db.get_document_source(item.doc_id)
            if source and HAS_WORKFLOWS:
                run_id = source.get("workflow_run_id")
                ind_run_id = source.get("workflow_individual_run_id")

                if run_id:
                    run = wf_db.get_workflow_run(run_id)
                    if run:
                        wf = wf_db.get_workflow(run.get("workflow_id"))
                        wf_name = wf.get("name", "workflow") if wf else "workflow"
                        content.write(f"[dim]Source:[/dim] {wf_name} [cyan]#w{run_id}[/cyan]")

                # Get the prompt that created this doc
                if ind_run_id:
                    ind_run = wf_db.get_individual_run(ind_run_id)
                    if ind_run:
                        # Show cost/time for this specific run
                        meta_parts = []
                        if ind_run.get("cost_usd"):
                            meta_parts.append(format_cost(ind_run["cost_usd"]))
                        if ind_run.get("execution_time_ms"):
                            secs = ind_run["execution_time_ms"] / 1000
                            meta_parts.append(f"{secs:.0f}s" if secs < 60 else f"{secs/60:.1f}m")
                        if ind_run.get("tokens_used"):
                            meta_parts.append(format_tokens(ind_run["tokens_used"]))
                        if meta_parts:
                            content.write(f"[dim]{' · '.join(meta_parts)}[/dim]")

                        # Show the prompt (extract task portion)
                        prompt = ind_run.get("prompt_used", "")
                        if prompt:
                            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", prompt, re.DOTALL)
                            if task_match:
                                task_text = task_match.group(1).strip()
                            else:
                                task_text = prompt.split("\n")[0]

                            content.write("")
                            content.write("[bold cyan]─── Prompt ───[/bold cyan]")
                            wrap_width = 50
                            wrapped = textwrap.fill(task_text, width=wrap_width)
                            for line in wrapped.split("\n"):
                                content.write(f"[dim]{line}[/dim]")

                # Show tags at the end for workflow docs
                if tags:
                    content.write("")
                    content.write(f"[dim]Tags:[/dim] {' '.join(tags)}")
            else:
                # Not from workflow - show richer metadata
                meta_line1 = []
                if doc.get("project"):
                    meta_line1.append(f"[cyan]{doc['project']}[/cyan]")
                if doc.get("created_at"):
                    from emdx.utils.datetime import parse_datetime
                    created_dt = parse_datetime(doc["created_at"])
                    if created_dt:
                        meta_line1.append(f"[dim]{format_time_ago(created_dt)}[/dim]")
                if meta_line1:
                    content.write(" · ".join(meta_line1))

                # Word count and access count
                meta_line2 = []
                doc_content = doc.get("content", "")
                word_count = len(doc_content.split())
                meta_line2.append(f"{word_count} words")
                access_count = doc.get("access_count", 0)
                if access_count and access_count > 1:
                    meta_line2.append(f"{access_count} views")
                content.write(f"[dim]{' · '.join(meta_line2)}[/dim]")

                # Tags
                if tags:
                    content.write(f"[dim]Tags:[/dim] {' '.join(tags)}")

        except Exception as e:
            logger.error(f"Error showing document context: {e}")

    async def _show_group_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show group details in context panel."""
        if not HAS_GROUPS:
            header.update("GROUP")
            return

        try:
            group = groups_db.get_group(item.item_id)
            if not group:
                header.update(f"📦 #{item.item_id}")
                return

            header.update(f"📦 {group['name']}")
            content.write(f"[dim]{group.get('group_type', 'batch')} · {group.get('doc_count', 0)} docs[/dim]")

            if group.get("description"):
                content.write(f"{group['description'][:100]}")

        except Exception as e:
            logger.error(f"Error showing group context: {e}")

    async def _show_individual_run_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show individual run details in context panel."""
        import re
        import textwrap

        run = item.individual_run or item.workflow_run
        if not run:
            header.update("RUN")
            return

        status = run.get("status", item.status or "unknown")
        status_colors = {"completed": "green", "failed": "red", "running": "yellow"}
        status_color = status_colors.get(status, "white")

        run_num = run.get("run_number", "?")
        header.update(f"🤖 Run {run_num} [{status_color}]{status}[/{status_color}]")

        # Stats
        stats_parts = []
        if run.get("execution_time_ms"):
            secs = run["execution_time_ms"] / 1000
            stats_parts.append(f"{secs:.1f}s")
        if run.get("input_tokens") or run.get("output_tokens"):
            stats_parts.append(f"{format_tokens(run.get('input_tokens', 0))}↓ {format_tokens(run.get('output_tokens', 0))}↑")
        if run.get("cost_usd"):
            stats_parts.append(f"${run['cost_usd']:.2f}")
        if stats_parts:
            content.write(f"[dim]{' · '.join(stats_parts)}[/dim]")

        if run.get("error_message"):
            content.write(f"[red]Error: {run['error_message'][:100]}[/red]")

        # Show the prompt (extract task portion)
        prompt = run.get("prompt_used", "")
        if prompt:
            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", prompt, re.DOTALL)
            if task_match:
                task_text = task_match.group(1).strip()
            else:
                task_text = prompt.split("\n")[0]

            content.write("")
            content.write("[bold cyan]─── Prompt ───[/bold cyan]")
            wrap_width = 50
            wrapped = textwrap.fill(task_text, width=wrap_width)
            for line in wrapped.split("\n"):
                content.write(f"[dim]{line}[/dim]")

    # =========================================================================
    # Actions
    # =========================================================================

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#activity-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#activity-table", DataTable)
        table.action_cursor_up()

    async def action_select(self) -> None:
        """Select/expand current item - matches original behavior."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
        elif item.item_type == "group" and not item.expanded and item._has_group_children:
            await self._expand_group(item)
        elif item.item_type == "document" and not item.expanded and item._has_doc_children:
            await self._expand_document(item)
        elif item.expanded:
            self._collapse_item(item)
            self._flatten_items()
            await self._update_table()
        # No action for leaf items - preview is already visible on the right

    async def action_expand(self) -> None:
        """Expand current item."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
        elif item.item_type == "group" and not item.expanded and item._has_group_children:
            await self._expand_group(item)
        elif item.item_type == "document" and not item.expanded and item._has_doc_children:
            await self._expand_document(item)

    async def action_collapse(self) -> None:
        """Collapse current item or go to parent."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if item.expanded:
            self._collapse_item(item)
            self._flatten_items()
            await self._update_table()
        elif item.depth > 0:
            # Navigate to parent
            for idx in range(self.selected_idx - 1, -1, -1):
                if self.flat_items[idx].depth < item.depth:
                    self.selected_idx = idx
                    table = self.query_one("#activity-table", DataTable)
                    table.move_cursor(row=idx)
                    break

    def action_fullscreen(self) -> None:
        """View selected item fullscreen."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return
        item = self.flat_items[self.selected_idx]
        if item.doc_id:
            self.post_message(self.ViewDocument(item.doc_id))

    def action_refresh(self) -> None:
        """Refresh data."""
        import asyncio
        asyncio.create_task(self.load_data())
        self.notify("Refreshed")

    def action_add_to_group(self) -> None:
        """Show group picker to add selected document, group, or workflow to another group."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        picker = self.query_one("#group-picker", GroupPicker)

        # Handle groups - nest under another group
        if item.item_type == "group":
            picker.show(source_group_id=item.item_id)
            return

        # Handle workflows - group all outputs under a parent group
        if item.item_type == "workflow" and item.workflow_run:
            picker.show(workflow_run_id=item.workflow_run.get("id"))
            return

        # Handle documents
        if item.doc_id:
            picker.show(doc_id=item.doc_id)
            return

        self.notify("Select a document, group, or workflow")

    async def action_create_group(self) -> None:
        """Create a new group from the selected document."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if not item.doc_id:
            self.notify("Select a document to create a group from")
            return

        if not HAS_GROUPS or not groups_db:
            self.notify("Groups not available")
            return

        try:
            doc = doc_db.get_document(item.doc_id) if HAS_DOCS else None
            doc_title = doc.get("title", "Untitled") if doc else "Untitled"

            # Create group named after the document
            group_name = f"{doc_title[:30]} Group"
            group_id = groups_db.create_group(
                name=group_name,
                group_type="batch",
            )

            # Add the document to it
            groups_db.add_document_to_group(group_id, item.doc_id, role="primary")

            self.notify(f"Created group '{group_name}'")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            self.notify(f"Error: {e}")

    async def action_create_gist(self) -> None:
        """Create a copy of the currently selected document."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            self.notify("No item selected")
            return

        item = self.flat_items[self.selected_idx]

        if not item.doc_id:
            self.notify("Select a document to gist")
            return

        if not HAS_DOCS or not doc_db:
            self.notify("Documents not available")
            return

        try:
            doc = doc_db.get_document(item.doc_id)
            if not doc:
                self.notify("Document not found")
                return

            title = doc.get("title", "Untitled")
            content = doc.get("content", "")

            from emdx.database.documents import save_document
            from emdx.utils.git import get_git_project

            project = get_git_project()
            new_doc_id = save_document(
                title=f"{title} (copy)",
                content=content,
                project=project,
            )

            self.notify(f"Created gist #{new_doc_id}")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating gist: {e}")
            self.notify(f"Error: {e}")

    async def action_ungroup(self) -> None:
        """Remove selected item from its parent group."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if not HAS_GROUPS or not groups_db:
            self.notify("Groups not available")
            return

        try:
            # Handle ungrouping a group (remove from parent)
            if item.item_type == "group":
                group = groups_db.get_group(item.item_id)
                if not group or not group.get("parent_group_id"):
                    self.notify("Group has no parent")
                    return
                groups_db.update_group(item.item_id, parent_group_id=None)
                self.notify(f"Removed '{group['name']}' from parent")
                await self._refresh_data()
                return

            # Handle ungrouping a document
            if item.doc_id:
                doc_groups = groups_db.get_document_groups(item.doc_id)
                if not doc_groups:
                    self.notify("Document is not in any group")
                    return

                # Remove from all groups
                for group in doc_groups:
                    groups_db.remove_document_from_group(group["id"], item.doc_id)

                group_names = ", ".join(g["name"][:20] for g in doc_groups)
                self.notify(f"Removed from: {group_names}")
                await self._refresh_data()
                return

            self.notify("Select a document or group to ungroup")

        except Exception as e:
            logger.error(f"Error ungrouping: {e}")
            self.notify(f"Error: {e}")

    def action_focus_next(self) -> None:
        """Focus next pane."""
        self.focus_next()

    def action_focus_prev(self) -> None:
        """Focus previous pane."""
        self.focus_previous()

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the table."""
        try:
            table = self.query_one("#activity-table", DataTable)
            table.focus()
        except Exception:
            pass

    # =========================================================================
    # GroupPicker Event Handlers
    # =========================================================================

    async def on_group_picker_group_selected(self, event: GroupPicker.GroupSelected) -> None:
        """Handle group selection from picker."""
        if not HAS_GROUPS or not groups_db:
            return

        try:
            if event.workflow_run_id:
                # Grouping a workflow - find/create group for workflow and nest under selected
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                # Nesting a group under another group
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self.notify(f"Moved group under '{event.group_name}'")
            elif event.doc_id:
                # Adding a document to a group
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self.notify(f"Added to '{event.group_name}'")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self.notify(f"Error: {e}")

        # Refocus the table
        table = self.query_one("#activity-table", DataTable)
        table.focus()

    async def on_group_picker_group_created(self, event: GroupPicker.GroupCreated) -> None:
        """Handle new group creation from picker."""
        if not HAS_GROUPS or not groups_db:
            return

        try:
            if event.workflow_run_id:
                # Grouping a workflow under a new group
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                # Move source group under the new group
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self.notify(f"Created '{event.group_name}' and moved group under it")
            elif event.doc_id:
                # Add document to the new group
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self.notify(f"Created '{event.group_name}' and added document")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self.notify(f"Error: {e}")

        # Refocus the table
        table = self.query_one("#activity-table", DataTable)
        table.focus()

    async def _group_workflow_under(self, workflow_run_id: int, parent_group_id: int, parent_name: str) -> None:
        """Group a workflow's outputs under a parent group.

        Finds or creates a group for the workflow run and nests it under the parent.
        """
        if not HAS_WORKFLOWS or not wf_db:
            return

        # Get workflow run info
        run = wf_db.get_workflow_run(workflow_run_id)
        if not run:
            self.notify("Workflow run not found")
            return

        # Get workflow name from the workflow definition
        workflow_id = run.get("workflow_id")
        workflow = wf_db.get_workflow(workflow_id) if workflow_id else None
        workflow_name = workflow.get("name", "Workflow") if workflow else "Workflow"

        # Check if workflow already has a group
        existing_groups = groups_db.list_groups(workflow_run_id=workflow_run_id)

        if existing_groups:
            # Move existing group(s) under the parent
            for grp in existing_groups:
                if grp.get("parent_group_id") != parent_group_id:
                    groups_db.update_group(grp["id"], parent_group_id=parent_group_id)
            self.notify(f"Moved workflow under '{parent_name}'")
        else:
            # Create a new group for this workflow's outputs
            wf_group_id = groups_db.create_group(
                name=f"{workflow_name} #{workflow_run_id}",
                group_type="batch",
                parent_group_id=parent_group_id,
                workflow_run_id=workflow_run_id,
                created_by="user",
            )

            # Add all workflow output documents to this group
            output_doc_ids = wf_db.get_workflow_output_doc_ids(workflow_run_id)
            added_count = 0
            for doc_id in output_doc_ids:
                try:
                    if groups_db.add_document_to_group(wf_group_id, doc_id, role="member"):
                        added_count += 1
                except Exception as e:
                    logger.warning(f"Failed to add doc {doc_id} to group: {e}")

            if added_count > 0:
                self.notify(f"Grouped {added_count} docs under '{parent_name}'")
            else:
                self.notify(f"Created group under '{parent_name}' (no docs found)")

    def on_group_picker_cancelled(self, event: GroupPicker.Cancelled) -> None:
        """Handle picker cancellation."""
        # Refocus the table
        table = self.query_one("#activity-table", DataTable)
        table.focus()
