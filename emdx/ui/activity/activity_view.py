"""Activity View - Mission Control for EMDX.

The primary interface for monitoring Claude Code's work:
- Status bar with active count, docs today, cost, errors, sparkline
- Activity stream showing workflows and direct saves
- Preview pane with document content
- Hierarchical drill-in for workflows
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.markup import escape as escape_markup
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Static, RichLog

from .sparkline import sparkline
from .activity_items import (
    WorkflowItem,
    DocumentItem,
    SynthesisItem,
    IndividualRunItem,
    ExplorationItem,
)
from .group_picker import GroupPicker

logger = logging.getLogger(__name__)


# Import services
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
    from emdx.database.documents import (
        get_workflow_document_ids,
        list_non_workflow_documents,
    )
    from emdx.services.log_stream import LogStream, LogStreamSubscriber

    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_db = None
    groups_db = None
    HAS_DOCS = False
    HAS_GROUPS = False

    def get_workflow_document_ids():
        return set()

    def list_non_workflow_documents(**kwargs):
        return []


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


def format_time_ago(dt: datetime) -> str:
    """Format datetime as relative time."""
    if not dt:
        return "—"

    from datetime import timezone

    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()

    # If timestamp appears to be in the future, it's likely stored as UTC
    # Convert it to local time (documents use UTC, workflows use local)
    if seconds < -60:  # More than 1 minute in "future" = probably UTC
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone().replace(tzinfo=None)
        diff = now - dt_local
        seconds = diff.total_seconds()

    # Handle any remaining future times
    if seconds < 0:
        return "now"

    if seconds < 60:
        return "now"
    if seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins}m"
    if seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h"
    days = int(seconds / 86400)
    return f"{days}d"


class ActivityItem:
    """Represents an item in the activity stream."""

    def __init__(
        self,
        item_type: str,  # 'workflow', 'document', 'error'
        item_id: int,
        title: str,
        status: str,
        timestamp: datetime,
        cost: float = 0,
        tokens: int = 0,
        children: Optional[List["ActivityItem"]] = None,
        doc_id: Optional[int] = None,
        error_message: Optional[str] = None,
        workflow_run: Optional[Dict] = None,
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
        self.error_message = error_message
        self.workflow_run = workflow_run
        self.depth = depth
        self.expanded = False
        # Progress tracking for running workflows
        self.progress_completed = 0  # Runs completed
        self.progress_total = 0  # Total target runs
        self.progress_stage = ""  # Current stage name

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
        else:
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
            # Use group_type-specific icons
            group_type = getattr(self, "group_type", "batch")
            icons = {
                "initiative": "📋",
                "round": "🔄",
                "batch": "📦",
                "session": "💾",
                "custom": "🏷️",
            }
            return icons.get(group_type, "📁")
        else:
            return ""


class AgentLogSubscriber(LogStreamSubscriber):
    """Forwards log content to the activity view."""

    def __init__(self, view: "ActivityView"):
        self.view = view

    def on_log_content(self, new_content: str) -> None:
        self.view._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        logger.error(f"Log stream error: {error}")


class ActivityView(Widget):
    """Mission Control - the primary view for monitoring EMDX activity."""

    class ViewDocument(Message):
        """Request to view a document fullscreen."""

        def __init__(self, doc_id: int) -> None:
            self.doc_id = doc_id
            super().__init__()

    class WorkflowCompleted(Message):
        """Notification that a workflow completed."""

        def __init__(self, workflow_id: int, success: bool) -> None:
            self.workflow_id = workflow_id
            self.success = success
            super().__init__()

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "select", "Select/Expand"),
        ("l", "expand", "Expand"),
        ("h", "collapse", "Collapse"),
        ("f", "fullscreen", "Fullscreen"),
        ("r", "refresh", "Refresh"),
        ("g", "add_to_group", "Add to Group"),
        ("G", "create_group", "Create Group"),
        ("u", "ungroup", "Ungroup"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
    ]

    DEFAULT_CSS = """
    ActivityView {
        layout: vertical;
        height: 100%;
    }

    #status-bar {
        height: 1;
        background: $boost;
        padding: 0 1;
    }

    #main-content {
        height: 1fr;
    }

    #activity-panel {
        width: 45%;
        height: 100%;
    }

    #preview-panel {
        width: 55%;
        height: 100%;
        border-left: solid $primary;
    }

    #activity-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #activity-table {
        height: 1fr;
    }

    #preview-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #preview-scroll {
        height: 1fr;
    }

    #preview-content {
        padding: 0 1;
    }

    #preview-log {
        height: 1fr;
        display: none;
    }

    .notification {
        height: 1;
        background: $success;
        padding: 0 1;
        display: none;
    }

    .notification.error {
        background: $error;
    }

    .notification.visible {
        display: block;
    }
    """

    # Reactive for notification
    notification_text = reactive("")
    notification_visible = reactive(False)
    notification_is_error = reactive(False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.activity_items: List[ActivityItem] = []
        self.flat_items: List[ActivityItem] = []  # Flattened for display
        self.selected_idx: int = 0
        self.log_stream: Optional[LogStream] = None
        self.log_subscriber = AgentLogSubscriber(self)
        self.streaming_item_id: Optional[int] = None
        self._last_workflow_states: Dict[int, str] = {}  # Track for notifications
        self._fullscreen = False
        # Cache to prevent flickering during refresh
        self._last_preview_key: Optional[tuple] = None  # (item_type, item_id, status)
        # Track recently completed workflows for highlight animation
        self._recently_completed: set = set()  # workflow_ids that just finished
        # Flag to only run zombie cleanup once on startup
        self._zombies_cleaned = False

    def compose(self) -> ComposeResult:
        # Status bar
        yield Static("Loading...", id="status-bar")

        # Notification bar (hidden by default)
        yield Static("", id="notification", classes="notification")

        # Main content
        with Horizontal(id="main-content"):
            # Left: Activity stream
            with Vertical(id="activity-panel"):
                yield Static("ACTIVITY", id="activity-header")
                yield DataTable(id="activity-table", cursor_type="row")

            # Right: Preview
            with Vertical(id="preview-panel"):
                yield Static("PREVIEW", id="preview-header")
                with ScrollableContainer(id="preview-scroll"):
                    yield RichLog(id="preview-content", highlight=True, markup=True, wrap=True, auto_scroll=False)
                yield RichLog(id="preview-log", highlight=True, markup=True, wrap=True)

        # Group picker (inline at bottom, hidden by default)
        yield GroupPicker(id="group-picker")

    async def on_mount(self) -> None:
        """Initialize the view."""
        # Setup activity table
        table = self.query_one("#activity-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("", width=2)  # Type icon
        table.add_column("Time", width=5)
        table.add_column("Title", width=30)
        table.add_column("ID", width=6)  # Document/workflow ID
        table.add_column("Cost", width=6)

        await self.load_data()
        table.focus()

        # Start refresh timer
        self.set_interval(5.0, self._refresh_data)

    async def load_data(self, update_preview: bool = True) -> None:
        """Load activity data.

        Args:
            update_preview: Whether to update the preview pane. Set to False during
                           periodic refresh to avoid flickering.
        """
        self.activity_items = []

        # Clean up zombie workflow runs only once on first load
        # Use 24 hours to be conservative - only truly abandoned runs
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
        # Running workflows should always be at the top for visibility
        def sort_key(item):
            is_running = item.item_type == "workflow" and item.status == "running"
            # Running items get priority 0 (will be first after sort)
            # Non-running items get priority 1
            # Within each group, sort by timestamp descending (negate for descending)
            return (0 if is_running else 1, -item.timestamp.timestamp() if item.timestamp else 0)

        self.activity_items.sort(key=sort_key)

        # Flatten for display
        self._flatten_items()

        # Update UI
        await self._update_table()
        await self._update_status_bar()
        if update_preview:
            await self._update_preview(force=True)

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
                # These are likely orphaned processes that didn't clean up
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
                    # Sum cost from individual runs
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
                    title=title[:35],
                    status=run.get("status", "unknown"),
                    timestamp=started,
                    cost=cost,
                    workflow_run=run,
                )

                # Check if workflow has any outputs (for expand indicator)
                # Also capture the primary output doc ID for completed workflows
                # And progress info for running workflows
                try:
                    stage_runs = wf_db.list_stage_runs(run["id"])
                    has_outputs = False
                    output_doc_id = None
                    output_count = 0
                    # Progress tracking for running workflows
                    total_target = 0
                    total_completed = 0
                    current_stage = ""
                    # Token tracking (input/output separately)
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
                        # Count synthesis (add 1 if exists)
                        if sr.get("synthesis_doc_id"):
                            output_count += 1
                            has_outputs = True
                            if not output_doc_id:
                                output_doc_id = sr["synthesis_doc_id"]
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
                    # Also use the output document's timestamp for consistent sorting
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

                # Track for notifications
                old_status = self._last_workflow_states.get(run["id"])
                new_status = run.get("status")
                if old_status == "running" and new_status in ("completed", "failed"):
                    self._notify_workflow_complete(run["id"], new_status == "completed")
                self._last_workflow_states[run["id"]] = new_status

                self.activity_items.append(item)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)

    def _get_workflow_doc_ids(self) -> set:
        """Get all document IDs that were generated by workflows.

        Uses the document_sources bridge table for efficient single-query lookup.
        """
        try:
            return get_workflow_document_ids()
        except Exception as e:
            logger.debug(f"Error getting workflow doc IDs: {e}")
            return set()

    async def _load_groups(self) -> None:
        """Load document groups into activity items."""
        try:
            # Get top-level groups only (those without parents)
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
                    title=group["name"][:35],
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

    async def _load_direct_saves(self) -> None:
        """Load documents that weren't created by workflows or added to groups.

        Uses the document_sources bridge table for efficient single-query filtering.
        """
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
                    title=title[:35] if title else "Untitled",
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
            has_doc_children = getattr(item, '_has_doc_children', False)
            has_workflow_outputs = getattr(item, '_has_workflow_outputs', False)
            has_group_children = getattr(item, '_has_group_children', False)
            # Also treat completed workflows with doc_id as expandable (they have synthesis)
            is_completed_workflow_with_output = (
                item.item_type == "workflow" and
                item.status == "completed" and
                item.doc_id is not None
            )
            # Output count badge for collapsed workflows
            output_count = getattr(item, '_output_count', 0)
            # Doc count for groups
            doc_count = getattr(item, 'doc_count', 0)
            # Running workflows are always expandable (to see individual runs)
            is_running_workflow = item.item_type == "workflow" and item.status == "running"
            if item.expanded and item.children:
                expand = "▼ "
                badge = ""
            elif is_running_workflow or \
                 (item.item_type == "workflow" and (has_workflow_outputs or is_completed_workflow_with_output)) or \
                 (item.item_type == "synthesis" and item.children) or \
                 (item.item_type == "group" and has_group_children) or \
                 has_doc_children:
                expand = "▶ "
                # Show output count badge for collapsed workflows with outputs
                if output_count > 0 and item.item_type == "workflow":
                    badge = f" [{output_count}]"
                # Show doc count badge for groups
                elif doc_count > 0 and item.item_type == "group":
                    badge = f" [{doc_count}]"
                else:
                    badge = ""
            else:
                expand = "  "
                badge = ""

            # Format row
            # Check if this workflow just completed (show sparkle highlight)
            is_recently_completed = (
                item.item_type == "workflow" and
                item.item_id in self._recently_completed
            )
            if is_recently_completed:
                status_icon = "✨"  # Sparkle for recently completed
            else:
                status_icon = item.status_icon
            type_icon = item.type_icon
            time_str = format_time_ago(item.timestamp)

            # For running workflows, show progress bar + stage instead of badge
            progress_str = ""
            if item.item_type == "workflow" and item.status == "running" and item.progress_total > 0:
                # Build mini progress bar using 8ths for accuracy: █████░░░░░ 2/4
                # Use Unicode block elements: █ (full), ▏▎▍▌▋▊▉ (1/8 to 7/8), space (empty)
                # Width=10 gives perfect accuracy for 4 and 5 task workflows
                pct = item.progress_completed / item.progress_total
                bar_width = 10
                filled_exact = pct * bar_width
                filled_full = int(filled_exact)
                remainder = filled_exact - filled_full
                # Partial block characters for the fractional part
                partial_chars = " ▏▎▍▌▋▊▉█"
                partial_idx = int(remainder * 8)
                partial = partial_chars[partial_idx] if partial_idx > 0 else ""
                empty = bar_width - filled_full - (1 if partial else 0)
                bar = "█" * filled_full + partial + "░" * empty
                progress_str = f" {bar} {item.progress_completed}/{item.progress_total}"

            # Truncate title to fit badge/progress within column width (30 chars)
            prefix = f"{indent}{expand}"
            prefix_len = len(prefix)
            # Use progress_str for running, badge for completed
            suffix = progress_str if progress_str else badge
            suffix_len = len(suffix)
            max_title_len = 30 - prefix_len - suffix_len
            truncated_title = item.title[:max_title_len] if len(item.title) > max_title_len else item.title
            title = f"{prefix}{truncated_title}{suffix}"
            # Show document ID or workflow run ID
            # For workflows, always show workflow run ID (not the output doc ID)
            if item.item_type == "workflow" and item.item_id:
                id_str = f"#{item.item_id}"
            elif item.doc_id:
                id_str = f"#{item.doc_id}"
            else:
                id_str = "—"
            cost = format_cost(item.cost) if item.cost else "—"

            table.add_row(status_icon, type_icon, time_str, title, id_str, cost)

        # Restore selection
        if self.flat_items and self.selected_idx < len(self.flat_items):
            table.move_cursor(row=self.selected_idx)

    async def _update_status_bar(self) -> None:
        """Update the status bar with current stats."""
        status_bar = self.query_one("#status-bar", Static)

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

        # Total tokens today (input/output)
        input_tokens_today = sum(
            getattr(item, '_input_tokens', 0) or 0
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.item_type == "workflow"
        )
        output_tokens_today = sum(
            getattr(item, '_output_tokens', 0) or 0
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

    def _render_markdown_preview(self, content: str) -> None:
        """Render markdown content to the preview RichLog."""
        from emdx.ui.markdown_config import MarkdownConfig

        preview = self.query_one("#preview-content", RichLog)
        preview.clear()

        try:
            # Limit preview to first 50000 chars for performance
            if len(content) > 50000:
                content = content[:50000] + "\n\n[dim]... (truncated for preview)[/dim]"
            if content.strip():
                markdown = MarkdownConfig.create_markdown(content)
                preview.write(markdown)
            else:
                preview.write("[dim]Empty document[/dim]")
        except Exception:
            # Fallback to plain text if markdown fails
            preview.write(content[:50000] if content else "[dim]No content[/dim]")

    async def _update_preview(self, force: bool = False) -> None:
        """Update the preview pane with selected item.

        Args:
            force: If True, update even if item hasn't changed (e.g., for user selection changes)
        """
        try:
            preview = self.query_one("#preview-content", RichLog)
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready: {e}")
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
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
                    # Check if content already has a markdown title header (may have leading whitespace)
                    content_stripped = content.lstrip()
                    has_title_header = (
                        content_stripped.startswith(f"# {title}") or
                        content_stripped.startswith("# ")  # Any h1 header counts
                    )
                    if has_title_header:
                        # Content already has a title header, don't duplicate
                        self._render_markdown_preview(content)
                    else:
                        # Content doesn't have title, add it
                        self._render_markdown_preview(f"# {title}\n\n{content}")
                    show_markdown()
                    header.update(f"📄 #{item.doc_id}")
                    return
            except Exception as e:
                logger.error(f"Error loading document: {e}")

        # For workflows, show summary
        if item.item_type == "workflow" and item.workflow_run:
            await self._show_workflow_summary(item)
            return

        # For groups, show summary
        if item.item_type == "group" and HAS_GROUPS:
            await self._show_group_summary(item)
            return

        # Default
        preview.clear()
        preview.write(f"[italic]{item.title}[/italic]")
        show_markdown()

    async def _show_workflow_summary(self, item: ActivityItem) -> None:
        """Show workflow summary in preview."""
        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready for summary: {e}")
            return

        run = item.workflow_run
        if not run:
            return

        status = run.get("status", "unknown")

        # For completed/failed workflows, show the output document content directly
        if status in ("completed", "failed") and HAS_WORKFLOWS and HAS_DOCS:
            try:
                # Get stage runs to find output documents
                stage_runs = wf_db.list_stage_runs(run["id"])
                output_doc_id = None

                # Look for synthesis doc first, then individual outputs
                for sr in stage_runs:
                    if sr.get("synthesis_doc_id"):
                        output_doc_id = sr["synthesis_doc_id"]
                        break

                # If no synthesis, look for individual run outputs
                if not output_doc_id:
                    for sr in stage_runs:
                        ind_runs = wf_db.list_individual_runs(sr["id"])
                        for ir in ind_runs:
                            if ir.get("output_doc_id"):
                                output_doc_id = ir["output_doc_id"]
                                break
                        if output_doc_id:
                            break

                # Show the output document content
                if output_doc_id:
                    doc = doc_db.get_document(output_doc_id)
                    if doc:
                        content = doc.get("content", "")
                        title = doc.get("title", "Untitled")

                        # Add a brief header with workflow info
                        duration_str = ""
                        if run.get("total_execution_time_ms"):
                            secs = run["total_execution_time_ms"] / 1000
                            duration_str = f" • {secs:.0f}s" if secs < 60 else f" • {secs/60:.1f}m"
                        cost_str = f" • {format_cost(item.cost)}" if item.cost else ""

                        header_line = f"*{item.status_icon} {item.title}{duration_str}{cost_str}*\n\n---\n\n"

                        # Check if content already has title
                        content_stripped = content.lstrip()
                        if not content_stripped.startswith("# "):
                            content = f"# {title}\n\n{content}"

                        self._render_markdown_preview(header_line + content)
                        preview_scroll.display = True
                        preview_log.display = False
                        header.update(f"📄 #{output_doc_id} (from w{run['id']})")
                        return
            except Exception as e:
                logger.debug(f"Error loading workflow output: {e}")

        # Fallback: show summary for running workflows or if no output found
        lines = [f"# {item.title}", ""]

        lines.append(f"**Status:** {item.status_icon} {status}")

        if run.get("total_execution_time_ms"):
            secs = run["total_execution_time_ms"] / 1000
            if secs < 60:
                lines.append(f"**Duration:** {secs:.0f}s")
            else:
                lines.append(f"**Duration:** {secs/60:.1f}m")

        if item.cost:
            lines.append(f"**Cost:** {format_cost(item.cost)}")

        # Load children if expanded
        if item.expanded and item.children:
            lines.append("")
            lines.append("## Outputs")
            for child in item.children:
                lines.append(f"- {child.status_icon} {child.title}")

        self._render_markdown_preview("\n".join(lines))
        preview_scroll.display = True
        preview_log.display = False
        header.update(f"⚡ Workflow #{run['id']}")

    async def _show_group_summary(self, item: ActivityItem) -> None:
        """Show group summary in preview."""
        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready for group summary: {e}")
            return

        group_id = item.item_id
        if not group_id:
            return

        try:
            group = groups_db.get_group(group_id)
            if not group:
                return

            lines = [f"# {group['name']}", ""]

            if group.get("description"):
                lines.append(group["description"])
                lines.append("")

            lines.append(f"**Type:** {group.get('group_type', 'batch')}")
            lines.append(f"**Documents:** {group.get('doc_count', 0)}")

            if group.get("total_tokens"):
                lines.append(f"**Total tokens:** {group['total_tokens']:,}")
            if group.get("total_cost_usd"):
                lines.append(f"**Total cost:** ${group['total_cost_usd']:.4f}")

            if group.get("project"):
                lines.append(f"**Project:** {group['project']}")

            # Show child groups if any
            child_groups = groups_db.get_child_groups(group_id)
            if child_groups:
                lines.append("")
                lines.append("## Child Groups")
                for cg in child_groups[:10]:
                    type_icons = {
                        "initiative": "📋",
                        "round": "🔄",
                        "batch": "📦",
                        "session": "💾",
                    }
                    icon = type_icons.get(cg.get("group_type", ""), "📁")
                    lines.append(f"- {icon} #{cg['id']} {cg['name']} ({cg.get('doc_count', 0)} docs)")
                if len(child_groups) > 10:
                    lines.append(f"*... and {len(child_groups) - 10} more*")

            # Show members
            members = groups_db.get_group_members(group_id)
            if members:
                lines.append("")
                lines.append("## Documents")
                for m in members[:15]:
                    role = m.get("role", "member")
                    role_icons = {"primary": "★", "synthesis": "📝", "exploration": "◇", "variant": "≈"}
                    role_icon = role_icons.get(role, "•")
                    lines.append(f"- {role_icon} #{m['id']} {m['title'][:40]} ({role})")
                if len(members) > 15:
                    lines.append(f"*... and {len(members) - 15} more*")

            self._render_markdown_preview("\n".join(lines))
            preview_scroll.display = True
            preview_log.display = False
            header.update(f"{item.type_icon} Group #{group_id}")

        except Exception as e:
            logger.error(f"Error showing group summary: {e}", exc_info=True)

    async def _show_live_log(self, item: ActivityItem) -> None:
        """Show live log for running workflow or individual run."""
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

        header.update(f"[green]● LIVE[/green] {item.title}")

        if not HAS_WORKFLOWS or not wf_db:
            preview_log.write("[dim]Workflow system not available[/dim]")
            return

        try:
            log_path = None

            # For individual runs, get log file from the execution record
            if item.item_type == "individual_run" and item.item_id:
                try:
                    from emdx.models.executions import get_execution
                    # Get the individual run to find its execution ID
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

    def _notify_workflow_complete(self, workflow_id: int, success: bool) -> None:
        """Show notification and play sound for workflow completion."""
        # Track recently completed for highlight effect
        self._recently_completed.add(workflow_id)
        # Clear highlight after 3 seconds
        self.set_timer(3.0, lambda: self._clear_highlight(workflow_id))

        # Play sound
        if success:
            print("\a", end="", flush=True)  # Single bell
        else:
            print("\a\a\a", end="", flush=True)  # Triple bell for error

        # Show notification
        self.notification_is_error = not success
        if success:
            self.notification_text = f"✨ Workflow #{workflow_id} complete"
        else:
            self.notification_text = f"❌ Workflow #{workflow_id} failed"
        self.notification_visible = True

        # Auto-hide after 5 seconds
        self.set_timer(5.0, self._hide_notification)

        # Post message for parent handling
        self.post_message(self.WorkflowCompleted(workflow_id, success))

        # Force preview update if this workflow is currently selected
        # This ensures the preview switches from live log to output document
        if self.flat_items and self.selected_idx < len(self.flat_items):
            selected_item = self.flat_items[self.selected_idx]
            if selected_item.item_type == "workflow" and selected_item.item_id == workflow_id:
                # The item's status will be updated on next refresh, but we need to stop
                # the log stream immediately and trigger preview refresh
                self._stop_stream()
                self._last_preview_key = None  # Force refresh on next update
                self.call_later(lambda: self.run_worker(self._update_preview(force=True)))

    def _clear_highlight(self, workflow_id: int) -> None:
        """Clear the completion highlight for a workflow."""
        self._recently_completed.discard(workflow_id)
        # Refresh table to remove highlight
        self.call_later(self._refresh_table_only)

    async def _refresh_table_only(self) -> None:
        """Refresh just the table display without reloading data."""
        await self._update_table()

    def _hide_notification(self) -> None:
        """Hide the notification bar."""
        self.notification_visible = False

    def watch_notification_visible(self, visible: bool) -> None:
        """React to notification visibility changes."""
        notif = self.query_one("#notification", Static)
        if visible:
            notif.add_class("visible")
            if self.notification_is_error:
                notif.add_class("error")
            else:
                notif.remove_class("error")
            notif.update(self.notification_text)
        else:
            notif.remove_class("visible")

    async def _refresh_data(self) -> None:
        """Periodic refresh of data."""
        # Remember selection and expanded state
        selected_id = None
        if self.flat_items and self.selected_idx < len(self.flat_items):
            item = self.flat_items[self.selected_idx]
            selected_id = (item.item_type, item.item_id)

        # Remember which items were expanded (including nested items like synthesis)
        expanded_ids = set()
        for item in self.activity_items:
            if item.expanded:
                expanded_ids.add((item.item_type, item.item_id))
            # Also check children
            for child in item.children:
                if child.expanded:
                    expanded_ids.add((child.item_type, child.item_id))

        # Load data without updating preview (prevents flicker)
        await self.load_data(update_preview=False)

        # Restore expanded state
        if expanded_ids:
            for item in self.activity_items:
                if (item.item_type, item.item_id) in expanded_ids:
                    # Re-expand this item
                    if item.item_type == "workflow" and not item.expanded:
                        await self._expand_workflow(item)
                    elif item.item_type == "group" and not item.expanded:
                        await self._expand_group(item)
                    elif item.item_type == "document" and not item.expanded:
                        await self._expand_document(item)

            # After re-expanding parents, check if any children need expansion
            for item in self.activity_items:
                for child in item.children:
                    if (child.item_type, child.item_id) in expanded_ids and not child.expanded:
                        if child.item_type == "synthesis" and child.children:
                            child.expanded = True
                        elif child.item_type == "group" and getattr(child, '_has_group_children', False):
                            await self._expand_group(child)

            # Re-flatten after restoring expansions
            self._flatten_items()
            await self._update_table()

        # Restore selection if possible
        if selected_id:
            for idx, item in enumerate(self.flat_items):
                if (item.item_type, item.item_id) == selected_id:
                    self.selected_idx = idx
                    try:
                        table = self.query_one("#activity-table", DataTable)
                        table.move_cursor(row=idx)
                    except Exception:
                        pass
                    break

        # Preview doesn't need updating during refresh unless item changed
        # The cache in _update_preview handles this

    async def _expand_workflow(self, item: ActivityItem) -> None:
        """Expand a workflow to show its stage runs and individual runs.

        Shows:
        - For running workflows: individual runs with their status (running/pending/completed)
        - For completed workflows: synthesis doc (if any) + individual outputs
        """
        if item.item_type != "workflow" or not item.workflow_run:
            return

        if item.expanded:
            return

        run = item.workflow_run
        children = []

        try:
            if HAS_WORKFLOWS and wf_db:
                # Get stage runs
                stage_runs = wf_db.list_stage_runs(run["id"])

                for sr in stage_runs:
                    stage_status = sr.get("status", "pending")
                    target_runs = sr.get("target_runs", 1)
                    runs_completed = sr.get("runs_completed", 0)

                    # Get individual runs for this stage
                    ind_runs = wf_db.list_individual_runs(sr["id"])

                    # For running/pending workflows, show each individual run with status
                    if stage_status in ("running", "pending") or run.get("status") == "running":
                        for ir in ind_runs:
                            ir_status = ir.get("status", "pending")
                            run_num = ir.get("run_number", 0)

                            # Build title based on status
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

                            child_item = ActivityItem(
                                item_type="individual_run",
                                item_id=ir.get("id"),
                                title=title,
                                status=ir_status,
                                timestamp=item.timestamp,
                                doc_id=ir.get("output_doc_id"),
                                cost=ir.get("cost_usd"),
                                depth=1,
                            )
                            children.append(child_item)

                        # If there are more runs expected than records, show pending placeholders
                        if len(ind_runs) < target_runs:
                            for i in range(len(ind_runs) + 1, target_runs + 1):
                                child_item = ActivityItem(
                                    item_type="individual_run",
                                    item_id=None,
                                    title=f"Run {i} (pending)",
                                    status="pending",
                                    timestamp=item.timestamp,
                                    doc_id=None,
                                    depth=1,
                                )
                                children.append(child_item)

                    # For completed workflows, show synthesis + all outputs as flat siblings
                    else:
                        # Show synthesis doc first if available
                        if sr.get("synthesis_doc_id"):
                            doc = doc_db.get_document(sr["synthesis_doc_id"]) if HAS_DOCS else None
                            title = doc.get("title", "Synthesis") if doc else "Synthesis"

                            synth_item = ActivityItem(
                                item_type="synthesis",
                                item_id=sr["synthesis_doc_id"],
                                title=title[:30],
                                status="completed",
                                timestamp=item.timestamp,
                                doc_id=sr["synthesis_doc_id"],
                                cost=sr.get("synthesis_cost_usd"),
                                depth=1,
                            )
                            children.append(synth_item)

                            # Add individual outputs as siblings (flat, not nested)
                            for ir in ind_runs:
                                if ir.get("output_doc_id") and ir["output_doc_id"] != sr.get("synthesis_doc_id"):
                                    out_doc = doc_db.get_document(ir["output_doc_id"]) if HAS_DOCS else None
                                    out_title = out_doc.get("title", f"Output #{ir['run_number']}")[:25] if out_doc else f"Output #{ir['run_number']}"

                                    out_item = ActivityItem(
                                        item_type="exploration",
                                        item_id=ir["output_doc_id"],
                                        title=out_title,
                                        status=ir.get("status", "completed"),
                                        timestamp=item.timestamp,
                                        doc_id=ir["output_doc_id"],
                                        cost=ir.get("cost_usd"),
                                        depth=1,
                                    )
                                    children.append(out_item)

                        # If no synthesis, show individual outputs directly under workflow
                        if not sr.get("synthesis_doc_id"):
                            for ir in ind_runs:
                                if ir.get("output_doc_id"):
                                    doc = doc_db.get_document(ir["output_doc_id"]) if HAS_DOCS else None
                                    title = doc.get("title", f"Output #{ir['run_number']}")[:25] if doc else f"Output #{ir['run_number']}"
                                    child_item = ActivityItem(
                                        item_type="exploration",
                                        item_id=ir["output_doc_id"],
                                        title=title,
                                        status=ir.get("status", "completed"),
                                        timestamp=item.timestamp,
                                        doc_id=ir["output_doc_id"],
                                        cost=ir.get("cost_usd"),
                                        depth=1,
                                    )
                                    children.append(child_item)

        except Exception as e:
            logger.error(f"Error expanding workflow: {e}", exc_info=True)

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    async def _expand_document(self, item: ActivityItem) -> None:
        """Expand a document to show its children."""
        if item.item_type != "document" or not item.doc_id:
            return

        if item.expanded:
            return

        if not getattr(item, '_has_doc_children', False):
            return

        children = []

        try:
            if HAS_DOCS:
                child_docs = doc_db.get_children(item.doc_id, include_archived=False)

                for child_doc in child_docs:
                    # Get relationship type
                    relationship = child_doc.get("relationship", "")
                    rel_icon = {
                        "supersedes": "↑",
                        "exploration": "◇",
                        "variant": "≈",
                    }.get(relationship, "")

                    title = child_doc.get("title", "")[:30]
                    if rel_icon:
                        title = f"{rel_icon} {title}"

                    child_item = ActivityItem(
                        item_type="document",
                        item_id=child_doc["id"],
                        title=title,
                        status="completed",
                        timestamp=item.timestamp,
                        doc_id=child_doc["id"],
                        depth=item.depth + 1,
                    )

                    # Check if this child also has children
                    grandchildren = doc_db.get_children(child_doc["id"], include_archived=False)
                    if grandchildren:
                        child_item._has_doc_children = True

                    children.append(child_item)

        except Exception as e:
            logger.error(f"Error expanding document: {e}", exc_info=True)

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    async def _expand_group(self, item: ActivityItem) -> None:
        """Expand a group to show its child groups and member documents."""
        if item.item_type != "group":
            return

        if item.expanded:
            return

        if not getattr(item, '_has_group_children', False):
            return

        children = []

        try:
            if HAS_GROUPS:
                group_id = item.item_id

                # Load child groups first
                child_groups = groups_db.get_child_groups(group_id)
                for cg in child_groups:
                    if not cg.get("is_active", True):
                        continue

                    # Count grandchildren for expansion indicator
                    grandchildren = groups_db.get_child_groups(cg["id"])

                    child_item = ActivityItem(
                        item_type="group",
                        item_id=cg["id"],
                        title=cg["name"][:35],
                        status="completed",
                        timestamp=item.timestamp,
                        cost=cg.get("total_cost_usd", 0) or 0,
                        tokens=cg.get("total_tokens", 0) or 0,
                        depth=item.depth + 1,
                    )
                    child_item.group_type = cg.get("group_type", "batch")
                    child_item.doc_count = groups_db.get_recursive_doc_count(cg["id"])
                    child_item._has_group_children = len(grandchildren) > 0 or child_item.doc_count > 0

                    children.append(child_item)

                # Load member documents
                members = groups_db.get_group_members(group_id)
                for m in members:
                    role_icons = {
                        "primary": "★",
                        "synthesis": "📝",
                        "exploration": "◇",
                        "variant": "≈",
                    }
                    role_icon = role_icons.get(m.get("role", ""), "")
                    title = m.get("title", "Untitled")[:28]
                    if role_icon:
                        title = f"{role_icon} {title}"

                    child_item = ActivityItem(
                        item_type="document",
                        item_id=m["id"],
                        title=title,
                        status="completed",
                        timestamp=item.timestamp,
                        doc_id=m["id"],
                        depth=item.depth + 1,
                    )

                    # Check if document has children for expansion
                    if HAS_DOCS:
                        grandchildren = doc_db.get_children(m["id"], include_archived=False)
                        if grandchildren:
                            child_item._has_doc_children = True

                    children.append(child_item)

        except Exception as e:
            logger.error(f"Error expanding group: {e}", exc_info=True)

        item.children = children
        item.expanded = True
        self._flatten_items()
        await self._update_table()

    def _collapse_item(self, item: ActivityItem) -> None:
        """Collapse an expanded item."""
        item.expanded = False
        self._flatten_items()

    # Actions

    def action_cursor_down(self) -> None:
        table = self.query_one("#activity-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#activity-table", DataTable)
        table.action_cursor_up()

    async def action_select(self) -> None:
        """Select/expand current item."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        has_doc_children = getattr(item, '_has_doc_children', False)
        has_group_children = getattr(item, '_has_group_children', False)

        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
        elif item.item_type == "group" and not item.expanded and has_group_children:
            await self._expand_group(item)
        elif item.item_type == "document" and not item.expanded and has_doc_children:
            await self._expand_document(item)
        elif item.expanded:
            self._collapse_item(item)
            await self._update_table()
        # No action for leaf items - preview is already visible on the right

    async def action_expand(self) -> None:
        """Expand current item."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
        elif item.item_type == "group" and not item.expanded and getattr(item, '_has_group_children', False):
            await self._expand_group(item)
        elif item.item_type == "document" and not item.expanded and getattr(item, '_has_doc_children', False):
            await self._expand_document(item)
        elif item.item_type == "synthesis" and not item.expanded:
            item.expanded = True
            self._flatten_items()
            await self._update_table()

    async def action_collapse(self) -> None:
        """Collapse current item or go to parent."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if item.expanded:
            self._collapse_item(item)
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
        """Toggle fullscreen preview."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        if item.doc_id:
            self.post_message(self.ViewDocument(item.doc_id))

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_data()  # Use same logic as periodic refresh to preserve state

    def action_focus_next(self) -> None:
        """Focus next pane."""
        # For now, just stay in table
        pass

    def action_focus_prev(self) -> None:
        """Focus previous pane."""
        pass

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row selection change."""
        if event.cursor_row is not None:
            self.selected_idx = event.cursor_row
            await self._update_preview(force=True)  # User changed selection, force update

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key on DataTable)."""
        await self.action_select()

    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        self._stop_stream()

    # Group management actions

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

        self._show_notification("Select a document, group, or workflow", is_error=True)

    async def action_create_group(self) -> None:
        """Create a new group from the selected document."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if not item.doc_id:
            self._show_notification("Select a document to create a group from", is_error=True)
            return

        if not HAS_GROUPS or not groups_db:
            self._show_notification("Groups not available", is_error=True)
            return

        # Get document title for group name
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

            self._show_notification(f"Created group '{group_name}'")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    async def action_ungroup(self) -> None:
        """Remove selected item from its parent group."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]

        if not HAS_GROUPS or not groups_db:
            self._show_notification("Groups not available", is_error=True)
            return

        try:
            # Handle ungrouping a group (remove from parent)
            if item.item_type == "group":
                group = groups_db.get_group(item.item_id)
                if not group or not group.get("parent_group_id"):
                    self._show_notification("Group has no parent", is_error=True)
                    return
                groups_db.update_group(item.item_id, parent_group_id=None)
                self._show_notification(f"Removed '{group['name']}' from parent")
                await self._refresh_data()
                return

            # Handle ungrouping a document
            if item.doc_id:
                doc_groups = groups_db.get_document_groups(item.doc_id)
                if not doc_groups:
                    self._show_notification("Document is not in any group", is_error=True)
                    return

                # Remove from all groups
                for group in doc_groups:
                    groups_db.remove_document_from_group(group["id"], item.doc_id)

                group_names = ", ".join(g["name"][:20] for g in doc_groups)
                self._show_notification(f"Removed from: {group_names}")
                await self._refresh_data()
                return

            self._show_notification("Select a document or group to ungroup", is_error=True)

        except Exception as e:
            logger.error(f"Error ungrouping: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    def _show_notification(self, message: str, is_error: bool = False) -> None:
        """Show a notification message."""
        self.notification_is_error = is_error
        self.notification_text = message
        self.notification_visible = True
        self.set_timer(3.0, self._hide_notification)

    # Group picker message handlers

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
                self._show_notification(f"Moved group under '{event.group_name}'")
            elif event.doc_id:
                # Adding a document to a group
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self._show_notification(f"Added to '{event.group_name}'")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

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
                self._show_notification(f"Created '{event.group_name}' and moved group under it")
            elif event.doc_id:
                # Add document to the new group
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self._show_notification(f"Created '{event.group_name}' and added document")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

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
            self._show_notification("Workflow run not found", is_error=True)
            return

        workflow_name = run.get("workflow_name", "Workflow")

        # Check if workflow already has a group
        existing_groups = groups_db.list_groups(workflow_run_id=workflow_run_id)

        if existing_groups:
            # Move existing group(s) under the parent
            for grp in existing_groups:
                if grp.get("parent_group_id") != parent_group_id:
                    groups_db.update_group(grp["id"], parent_group_id=parent_group_id)
            self._show_notification(f"Moved workflow under '{parent_name}'")
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
            for doc_id in output_doc_ids:
                try:
                    groups_db.add_document_to_group(wf_group_id, doc_id, role="member")
                except Exception:
                    pass  # Already in group

            self._show_notification(f"Grouped workflow under '{parent_name}'")

    def on_group_picker_cancelled(self, event: GroupPicker.Cancelled) -> None:
        """Handle picker cancellation."""
        # Refocus the table
        table = self.query_one("#activity-table", DataTable)
        table.focus()
