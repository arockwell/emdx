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
    from emdx.services.log_stream import LogStream, LogStreamSubscriber

    HAS_DOCS = True
except ImportError:
    doc_db = None
    HAS_DOCS = False


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

    # If datetime is naive (no timezone), assume it's UTC and convert to local
    if dt.tzinfo is None:
        # Assume UTC and convert to local time
        from datetime import timezone
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone()
        dt = dt_local.replace(tzinfo=None)

    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()

    # Handle future times (shouldn't happen but be safe)
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
        elif self.item_type == "document":
            return "📄"
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

    async def on_mount(self) -> None:
        """Initialize the view."""
        # Setup activity table
        table = self.query_one("#activity-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("", width=2)  # Type icon
        table.add_column("Time", width=5)
        table.add_column("Title", width=30)
        table.add_column("Cost", width=6)

        await self.load_data()
        table.focus()

        # Start refresh timer
        self.set_interval(5.0, self._refresh_data)

    async def load_data(self) -> None:
        """Load activity data."""
        self.activity_items = []

        # Clean up zombie workflow runs on first load
        if HAS_WORKFLOWS and wf_db:
            try:
                cleaned = wf_db.cleanup_zombie_workflow_runs(max_age_hours=2.0)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} zombie workflow runs")
            except Exception as e:
                logger.debug(f"Could not cleanup zombies: {e}")

        # Load workflows
        if HAS_WORKFLOWS and wf_db:
            await self._load_workflows()

        # Load recent direct saves (documents not from workflows)
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
        await self._update_preview()

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

                # Calculate cost - check both top-level and context_json
                cost = run.get("total_cost_usd", 0) or 0
                if not cost:
                    # Try to extract from context_json (contains agent execution results)
                    try:
                        ctx = run.get("context_json")
                        if isinstance(ctx, str):
                            ctx = json.loads(ctx)
                        if ctx:
                            # Look for cost in stage outputs (e.g., analyze.output)
                            for key, value in ctx.items():
                                if isinstance(value, str) and "total_cost_usd" in value:
                                    # Parse the __RAW_RESULT_JSON__ from execution logs
                                    match = re.search(r'"total_cost_usd":([0-9.]+)', value)
                                    if match:
                                        cost = float(match.group(1))
                                        break
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
                try:
                    stage_runs = wf_db.list_stage_runs(run["id"])
                    has_outputs = False
                    for sr in stage_runs:
                        if sr.get("synthesis_doc_id"):
                            has_outputs = True
                            break
                        ind_runs = wf_db.list_individual_runs(sr["id"])
                        if any(ir.get("output_doc_id") for ir in ind_runs):
                            has_outputs = True
                            break
                    if has_outputs:
                        item._has_workflow_outputs = True
                except Exception:
                    pass

                # Track for notifications
                old_status = self._last_workflow_states.get(run["id"])
                new_status = run.get("status")
                if old_status == "running" and new_status in ("completed", "failed"):
                    self._notify_workflow_complete(run["id"], new_status == "completed")
                self._last_workflow_states[run["id"]] = new_status

                self.activity_items.append(item)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)

    async def _load_direct_saves(self) -> None:
        """Load documents that weren't created by workflows."""
        try:
            # Get recent documents (top-level only)
            docs = doc_db.list_documents(limit=100, include_archived=False, parent_id=None)

            # Filter to last week
            week_ago = datetime.now() - timedelta(days=7)

            for doc in docs:
                created = doc.get("created_at")
                if isinstance(created, str):
                    from emdx.utils.datetime import parse_datetime
                    created = parse_datetime(created)
                if not created or created < week_ago:
                    continue

                # Skip workflow-generated docs (they have specific title patterns)
                title = doc.get("title", "")
                if any(
                    p in title
                    for p in ["Synthesis", "Workflow Agent Output", "Workflow Output"]
                ):
                    continue

                # Check if this document has children
                children_docs = doc_db.get_children(doc["id"], include_archived=False)
                has_children = len(children_docs) > 0

                item = ActivityItem(
                    item_type="document",
                    item_id=doc["id"],
                    title=title[:35] if title else "Untitled",
                    status="completed",
                    timestamp=created,
                    doc_id=doc["id"],
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
            if item.expanded and item.children:
                expand = "▼ "
            elif (item.item_type == "workflow" and has_workflow_outputs) or \
                 (item.item_type == "synthesis" and item.children) or \
                 has_doc_children:
                expand = "▶ "
            else:
                expand = "  "

            # Format row
            status_icon = item.status_icon
            type_icon = item.type_icon
            time_str = format_time_ago(item.timestamp)
            title = f"{indent}{expand}{item.title}"
            cost = format_cost(item.cost) if item.cost else "—"

            table.add_row(status_icon, type_icon, time_str, title, cost)

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

        # Count errors
        errors = sum(
            1
            for item in self.activity_items
            if item.status == "failed"
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
        from rich.markdown import Markdown as RichMarkdown

        preview = self.query_one("#preview-content", RichLog)
        preview.clear()

        try:
            # Limit preview to first 5000 chars for performance
            if len(content) > 5000:
                content = content[:5000] + "\n\n[dim]... (truncated for preview)[/dim]"
            if content.strip():
                markdown = RichMarkdown(content)
                preview.write(markdown)
            else:
                preview.write("[dim]Empty document[/dim]")
        except Exception:
            # Fallback to plain text if markdown fails
            preview.write(content[:5000] if content else "[dim]No content[/dim]")

    async def _update_preview(self) -> None:
        """Update the preview pane with selected item."""
        try:
            preview = self.query_one("#preview-content", RichLog)
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_log = self.query_one("#preview-log", RichLog)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready: {e}")
            return

        # Stop any existing stream
        self._stop_stream()

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
            return

        item = self.flat_items[self.selected_idx]

        # For running workflows, show live log
        if item.status == "running" and item.item_type == "workflow":
            await self._show_live_log(item)
            return

        # For documents, show content
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
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

        # Build summary
        lines = [f"# {item.title}", ""]

        status = run.get("status", "unknown")
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

    async def _show_live_log(self, item: ActivityItem) -> None:
        """Show live log for running workflow."""
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
            # Find active execution
            run = item.workflow_run
            if not run:
                return

            active_exec = wf_db.get_active_execution_for_run(run["id"])
            if not active_exec or not active_exec.get("log_file"):
                preview_log.write(f"[yellow]⏳ Waiting for log...[/yellow]")
                return

            log_path = Path(active_exec["log_file"])
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

        # Remember which items were expanded
        expanded_ids = set()
        for item in self.activity_items:
            if item.expanded:
                expanded_ids.add((item.item_type, item.item_id))

        await self.load_data()

        # Restore expanded state
        if expanded_ids:
            for item in self.activity_items:
                if (item.item_type, item.item_id) in expanded_ids:
                    # Re-expand this item
                    if item.item_type == "workflow" and not item.expanded:
                        await self._expand_workflow(item)
                    elif item.item_type == "document" and not item.expanded:
                        await self._expand_document(item)

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

    async def _expand_workflow(self, item: ActivityItem) -> None:
        """Expand a workflow to show its outputs."""
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
                    # Get synthesis doc
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
                            depth=1,
                        )

                        # Get exploration children
                        if HAS_DOCS:
                            exploration_docs = doc_db.get_children(
                                sr["synthesis_doc_id"], include_archived=False
                            )
                            for exp_doc in exploration_docs:
                                exp_item = ActivityItem(
                                    item_type="exploration",
                                    item_id=exp_doc["id"],
                                    title=exp_doc.get("title", "")[:25],
                                    status="completed",
                                    timestamp=item.timestamp,
                                    doc_id=exp_doc["id"],
                                    depth=2,
                                )
                                synth_item.children.append(exp_item)

                        children.append(synth_item)

                    # Get individual runs without synthesis
                    ind_runs = wf_db.list_individual_runs(sr["id"])
                    for ir in ind_runs:
                        if ir.get("output_doc_id") and ir["output_doc_id"] != sr.get(
                            "synthesis_doc_id"
                        ):
                            doc = (
                                doc_db.get_document(ir["output_doc_id"])
                                if HAS_DOCS
                                else None
                            )
                            # Skip if this doc is a child of synthesis
                            if doc and doc.get("parent_id"):
                                continue

                            title = doc.get("title", f"Output #{ir['run_number']}") if doc else f"Output #{ir['run_number']}"
                            child_item = ActivityItem(
                                item_type="exploration",
                                item_id=ir["output_doc_id"],
                                title=title[:25],
                                status=ir.get("status", "completed"),
                                timestamp=item.timestamp,
                                doc_id=ir["output_doc_id"],
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

        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
        elif item.item_type == "document" and not item.expanded and has_doc_children:
            await self._expand_document(item)
        elif item.expanded:
            self._collapse_item(item)
            await self._update_table()
        elif item.doc_id:
            # Open document
            self.post_message(self.ViewDocument(item.doc_id))

    async def action_expand(self) -> None:
        """Expand current item."""
        if not self.flat_items or self.selected_idx >= len(self.flat_items):
            return

        item = self.flat_items[self.selected_idx]
        if item.item_type == "workflow" and not item.expanded:
            await self._expand_workflow(item)
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
        await self.load_data()

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
            await self._update_preview()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection (Enter key on DataTable)."""
        await self.action_select()

    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        self._stop_stream()
