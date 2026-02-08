"""Activity View - Mission Control for EMDX.

The primary interface for monitoring Claude Code's work:
- Status bar with active count, docs today, cost, errors, sparkline
- Activity stream showing workflows and direct saves
- Preview pane with document content
- Hierarchical drill-in for workflows

Uses Textual's Tree widget for native hierarchy, expand/collapse,
and cursor tracking by node reference — eliminating scroll jumping.
"""

import asyncio
import json
import logging
import re
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, RichLog, Tree

from emdx.utils.datetime_utils import parse_datetime

from .sparkline import sparkline
from .activity_items import ActivityItem as ActivityItemBase
from .activity_data import ActivityDataLoader
from .activity_tree import ActivityTree
from .group_picker import GroupPicker
from ..modals import HelpMixin

logger = logging.getLogger(__name__)


# Import services
try:
    from emdx.workflows import database as wf_db

    HAS_WORKFLOWS = True
except ImportError:
    wf_db = None
    HAS_WORKFLOWS = False

try:
    from emdx.database import documents as doc_db
    from emdx.database import groups as groups_db
    from emdx.services.log_stream import LogStream, LogStreamSubscriber

    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_db = None
    groups_db = None
    HAS_DOCS = False
    HAS_GROUPS = False


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


# Re-export ActivityItem base class from activity_items for type annotations
ActivityItem = ActivityItemBase


class AgentLogSubscriber(LogStreamSubscriber):
    """Forwards log content to the activity view."""

    def __init__(self, view: "ActivityView"):
        self.view = view

    def on_log_content(self, new_content: str) -> None:
        self.view._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        logger.error(f"Log stream error: {error}")


class ActivityView(HelpMixin, Widget):
    """Activity View - Mission Control for EMDX."""

    HELP_TITLE = "Activity View"
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
        ("i", "create_gist", "New Gist"),
        ("u", "ungroup", "Ungroup"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
        ("a", "mark_read", "Mark Read"),
        ("question_mark", "show_help", "Help"),
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
        width: 40%;
        height: 100%;
    }

    #activity-list-section {
        height: 70%;
    }

    #context-section {
        height: 30%;
        border-top: solid $secondary;
    }

    #context-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #context-scroll {
        height: 1fr;
    }

    #context-content {
        padding: 0 1;
    }

    #preview-panel {
        width: 60%;
        height: 100%;
        border-left: solid $primary;
    }

    #activity-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #activity-tree {
        height: 1fr;
        scrollbar-size: 1 1;
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
        self.log_stream: Optional[LogStream] = None
        self.log_subscriber = AgentLogSubscriber(self)
        self.streaming_item_id: Optional[int] = None
        self._fullscreen = False
        # Cache to prevent flickering during refresh
        self._last_preview_key: Optional[tuple] = None  # (item_type, item_id, status)
        # Track recently completed workflows for highlight animation
        self._recently_completed: set = set()  # workflow_ids that just finished
        # Flag to only run zombie cleanup once on startup
        self._zombies_cleaned = False
        # Reentrance guard: prevents overlapping async refreshes
        self._refresh_in_progress = False
        # Data loader (owns DB queries and workflow state tracking)
        self._data_loader = ActivityDataLoader()
        self._data_loader.on_workflow_complete = self._notify_workflow_complete

    def _get_selected_item(self) -> Optional[ActivityItem]:
        """Get the currently selected ActivityItem from the tree."""
        try:
            tree = self.query_one("#activity-tree", ActivityTree)
            node = tree.cursor_node
            return node.data if node else None
        except Exception:
            return None

    def compose(self) -> ComposeResult:
        # Status bar
        yield Static("Loading...", id="status-bar")

        # Notification bar (hidden by default)
        yield Static("", id="notification", classes="notification")

        # Main content
        with Horizontal(id="main-content"):
            # Left: Activity stream (top) + Context panel (bottom)
            with Vertical(id="activity-panel"):
                # Top: Activity list
                with Vertical(id="activity-list-section"):
                    yield Static("ACTIVITY", id="activity-header")
                    yield ActivityTree("Activity", id="activity-tree")
                # Bottom: Context panel (workflow details or doc metadata)
                with Vertical(id="context-section"):
                    yield Static("DETAILS", id="context-header")
                    with ScrollableContainer(id="context-scroll"):
                        yield RichLog(id="context-content", highlight=True, markup=True, wrap=True, auto_scroll=False)

            # Right: Preview (document content)
            with Vertical(id="preview-panel"):
                yield Static("PREVIEW", id="preview-header")
                with ScrollableContainer(id="preview-scroll"):
                    yield RichLog(id="preview-content", highlight=True, markup=True, wrap=True, auto_scroll=False)
                yield RichLog(id="preview-log", highlight=True, markup=True, wrap=True)

        # Group picker (inline at bottom, hidden by default)
        yield GroupPicker(id="group-picker")

    async def on_mount(self) -> None:
        """Initialize the view."""
        tree = self.query_one("#activity-tree", ActivityTree)
        # Share recently_completed set so tree can use it for sparkle icon
        tree._recently_completed = self._recently_completed

        await self.load_data()
        tree.focus()

        # Start refresh timer
        self.set_interval(1.0, self._refresh_data)

    async def load_data(self, update_preview: bool = True) -> None:
        """Load activity data."""
        self.activity_items = await self._data_loader.load_all(
            zombies_cleaned=self._zombies_cleaned,
        )
        self._zombies_cleaned = True

        # Populate tree
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.populate_from_items(self.activity_items)

        await self._update_status_bar()
        if update_preview:
            await self._update_preview(force=True)
            await self._update_context_panel()

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
            getattr(item, 'input_tokens', 0) or 0
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.item_type == "workflow"
        )
        output_tokens_today = sum(
            getattr(item, 'output_tokens', 0) or 0
            for item in self.activity_items
            if item.timestamp
            and item.timestamp.date() == today
            and item.item_type == "workflow"
        )

        # Generate sparkline for the week
        week_data = self._get_week_activity_data()
        spark = sparkline(week_data, width=7)

        # Get theme indicator
        from emdx.ui.themes import get_theme_indicator
        theme_indicator = get_theme_indicator(self.app.theme)

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
        parts.append(f"[dim]{theme_indicator}[/dim]")

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
        """Update the preview pane with selected item."""
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

        item = self._get_selected_item()

        if item is None:
            preview.clear()
            preview.write("[dim]Select an item to preview[/dim]")
            show_markdown()
            header.update("PREVIEW")
            self._last_preview_key = None
            return

        current_key = (item.item_type, item.item_id, item.status)

        # Skip update if same item and not forced (prevents flickering during refresh)
        # Always update for running items (logs change) or if explicitly forced
        if not force and item.status != "running" and self._last_preview_key == current_key:
            return

        self._last_preview_key = current_key

        # Stop any existing stream
        self._stop_stream()

        # For running workflows, individual runs, or agent executions, show live log
        if item.status == "running" and item.item_type in ("workflow", "individual_run", "agent_execution"):
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
                        self._render_markdown_preview(content)
                    else:
                        self._render_markdown_preview(f"# {title}\n\n{content}")
                    show_markdown()
                    header.update(f"📄 #{item.doc_id}")
                    return
                else:
                    self._render_markdown_preview(
                        f"# {item.title}\n\n"
                        f"*Document #{item.doc_id} not found*\n\n"
                        "This document may have been deleted or the database may be out of sync."
                    )
                    show_markdown()
                    header.update(f"⚠️ #{item.doc_id} (missing)")
                    return
            except Exception as e:
                logger.error(f"Error loading document: {e}")

        # For agent executions without doc_id, use the item's preview method
        if item.item_type == "agent_execution":
            content, header_text = await item.get_preview_content(wf_db, doc_db)
            if content:
                self._render_markdown_preview(content)
                show_markdown()
                header.update(header_text)
                return

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

    async def _update_context_panel(self) -> None:
        """Update the context panel with details about selected item."""
        try:
            context_content = self.query_one("#context-content", RichLog)
            context_header = self.query_one("#context-header", Static)
        except Exception as e:
            logger.debug(f"Context panel not ready: {e}")
            return

        context_content.clear()

        item = self._get_selected_item()
        if item is None:
            context_header.update("DETAILS")
            context_content.write("[dim]Select an item to see details[/dim]")
            return

        # Workflow run details
        if item.item_type == "workflow" and item.workflow_run:
            await self._show_workflow_context(item, context_content, context_header)
        # Document details
        elif item.doc_id:
            await self._show_document_context(item, context_content, context_header)
        # Group details
        elif item.item_type == "group":
            await self._show_group_context(item, context_content, context_header)
        # Individual run details
        elif item.item_type == "individual_run" or getattr(item, 'individual_run', None):
            await self._show_individual_run_context(item, context_content, context_header)
        # Mail message details
        elif item.item_type == "mail":
            context_header.update(f"📧 #{item.item_id}")
            context_content.write(f"[bold]From:[/bold] @{item.sender}")
            context_content.write(f"[bold]To:[/bold] @{item.recipient}")
            context_content.write(f"[bold]Status:[/bold] {'read' if item.is_read else '[yellow]unread[/yellow]'}")
            if item.comment_count:
                context_content.write(f"[bold]Replies:[/bold] {item.comment_count}")
            if item.url:
                context_content.write(f"[dim]{item.url}[/dim]")
        else:
            context_header.update("DETAILS")
            context_content.write(f"[dim]{item.item_type}: {item.title}[/dim]")

    async def _show_workflow_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show workflow run details in context panel."""
        run = item.workflow_run
        if not run:
            return

        status = run.get("status", "unknown")
        status_colors = {"completed": "green", "failed": "red", "running": "yellow"}
        status_color = status_colors.get(status, "white")

        header.update(f"⚡ #{run['id']} [{status_color}]{status}[/{status_color}]")

        # For running workflows, show progress prominently
        if status == "running" and item.progress_total:
            if getattr(item, '_is_synthesizing', False):
                content.write(f"[magenta bold]🔮 Synthesizing...[/magenta bold]")
                content.write(f"[dim]Combining outputs from {item.progress_completed} runs[/dim]")
            else:
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
                    try:
                        context_section = self.query_one("#context-section")
                        wrap_width = max(context_section.size.width - 4, 40)
                    except Exception:
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
                    icon = {"completed": "[green]✓[/green]", "failed": "[red]✗[/red]", "running": "[yellow]⟳[/yellow]", "synthesizing": "[magenta]🔮[/magenta]", "pending": "[dim]○[/dim]"}.get(sr["status"], "[dim]○[/dim]")
                    stage_suffix = " 🔮 Synthesizing..." if sr["status"] == "synthesizing" else f" {sr['runs_completed']}/{sr['target_runs']}"
                    content.write(f"  {icon} {sr['stage_name']}{stage_suffix}")

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
                        try:
                            context_section = self.query_one("#context-section")
                            wrap_width = max(context_section.size.width - 4, 40)
                        except Exception:
                            wrap_width = 50

                        wrapped = textwrap.fill(task_text, width=wrap_width)
                        for line in wrapped.split("\n"):
                            content.write(f"[dim]{line}[/dim]")
                        break

        if run.get("error_message"):
            content.write(f"[red]Error: {run['error_message'][:100]}[/red]")

    async def _show_document_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show document metadata in context panel."""
        if not HAS_DOCS or not item.doc_id:
            header.update("DOCUMENT")
            return

        try:
            doc = doc_db.get_document(item.doc_id)
            if not doc:
                header.update(f"📄 #{item.doc_id}")
                return

            header.update(f"📄 #{doc['id']}")

            try:
                from emdx.models.tags import get_document_tags
                tags = get_document_tags(item.doc_id)
            except ImportError:
                tags = []

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

                if ind_run_id:
                    ind_run = wf_db.get_individual_run(ind_run_id)
                    if ind_run:
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

                        prompt = ind_run.get("prompt_used", "")
                        if prompt:
                            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", prompt, re.DOTALL)
                            if task_match:
                                task_text = task_match.group(1).strip()
                            else:
                                task_text = prompt.split("\n")[0]

                            content.write("")
                            content.write("[bold cyan]─── Prompt ───[/bold cyan]")
                            try:
                                context_section = self.query_one("#context-section")
                                wrap_width = max(context_section.size.width - 4, 40)
                            except Exception:
                                wrap_width = 50

                            wrapped = textwrap.fill(task_text, width=wrap_width)
                            for line in wrapped.split("\n"):
                                content.write(f"[dim]{line}[/dim]")

                if tags:
                    content.write("")
                    content.write(f"[dim]Tags:[/dim] {' '.join(tags)}")
            else:
                meta_line1 = []
                if doc.get("project"):
                    meta_line1.append(f"[cyan]{doc['project']}[/cyan]")
                if doc.get("created_at"):
                    created_dt = parse_datetime(doc["created_at"])
                    if created_dt:
                        meta_line1.append(f"[dim]{format_time_ago(created_dt)}[/dim]")
                if meta_line1:
                    content.write(" · ".join(meta_line1))

                meta_line2 = []
                doc_content = doc.get("content", "")
                word_count = len(doc_content.split())
                meta_line2.append(f"{word_count} words")
                access_count = doc.get("access_count", 0)
                if access_count and access_count > 1:
                    meta_line2.append(f"{access_count} views")
                content.write(f"[dim]{' · '.join(meta_line2)}[/dim]")

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
        run = getattr(item, 'individual_run', None) or getattr(item, 'workflow_run', None)
        if not run:
            header.update("RUN")
            return

        status = run.get("status", item.status or "unknown")
        status_colors = {"completed": "green", "failed": "red", "running": "yellow"}
        status_color = status_colors.get(status, "white")

        run_num = run.get("run_number", "?")
        header.update(f"🤖 Run {run_num} [{status_color}]{status}[/{status_color}]")

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

        prompt = run.get("prompt_used", "")
        if prompt:
            task_match = re.search(r"## Task\s*\n(.+?)(?=\n## |\Z)", prompt, re.DOTALL)
            if task_match:
                task_text = task_match.group(1).strip()
            else:
                task_text = prompt.split("\n")[0]

            content.write("")
            content.write("[bold cyan]─── Prompt ───[/bold cyan]")
            try:
                context_section = self.query_one("#context-section")
                wrap_width = max(context_section.size.width - 4, 40)
            except Exception:
                wrap_width = 50

            wrapped = textwrap.fill(task_text, width=wrap_width)
            for line in wrapped.split("\n"):
                content.write(f"[dim]{line}[/dim]")

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
                stage_runs = wf_db.list_stage_runs(run["id"])
                output_doc_id = None

                for sr in stage_runs:
                    if sr.get("synthesis_doc_id"):
                        output_doc_id = sr["synthesis_doc_id"]
                        break

                if not output_doc_id:
                    for sr in stage_runs:
                        ind_runs = wf_db.list_individual_runs(sr["id"])
                        for ir in ind_runs:
                            if ir.get("output_doc_id"):
                                output_doc_id = ir["output_doc_id"]
                                break
                        if output_doc_id:
                            break

                if output_doc_id:
                    doc = doc_db.get_document(output_doc_id)
                    if doc:
                        content = doc.get("content", "")
                        title = doc.get("title", "Untitled")

                        duration_str = ""
                        if run.get("total_execution_time_ms"):
                            secs = run["total_execution_time_ms"] / 1000
                            duration_str = f" • {secs:.0f}s" if secs < 60 else f" • {secs/60:.1f}m"
                        cost_str = f" • {format_cost(item.cost)}" if item.cost else ""

                        header_line = f"*{item.status_icon} {item.title}{duration_str}{cost_str}*\n\n---\n\n"

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

        # Show children from expanded tree node
        if item.children:
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

            if item.item_type == "agent_execution":
                log_file = getattr(item, 'log_file', None)
                if log_file:
                    log_path = Path(log_file)

            elif item.item_type == "individual_run" and item.item_id:
                try:
                    from emdx.models.executions import get_execution
                    from emdx.database.connection import db_connection

                    ir = wf_db.get_individual_run(item.item_id)
                    if ir:
                        if ir.get("agent_execution_id"):
                            exec_record = get_execution(ir["agent_execution_id"])
                            if exec_record and exec_record.log_file:
                                log_path = Path(exec_record.log_file)

                        if not log_path:
                            with db_connection.get_connection() as conn:
                                cursor = conn.execute(
                                    """
                                    SELECT log_file FROM executions
                                    WHERE doc_title LIKE ?
                                    AND status = 'running'
                                    ORDER BY id DESC LIMIT 1
                                    """,
                                    (f"Workflow Agent Run #{item.item_id}%",),
                                )
                                row = cursor.fetchone()
                                if row and row['log_file']:
                                    log_path = Path(row['log_file'])
                except Exception as e:
                    logger.debug(f"Could not get individual run log: {e}")

            elif item.item_type == "workflow" and getattr(item, 'workflow_run', None):
                run = item.workflow_run
                active_exec = wf_db.get_active_execution_for_run(run["id"])
                if active_exec and active_exec.get("log_file"):
                    log_path = Path(active_exec["log_file"])

            if not log_path:
                preview_log.write(f"[yellow]⏳ Waiting for log...[/yellow]")
                preview_log.write(f"[dim]item_type={item.item_type}, has workflow_run={getattr(item, 'workflow_run', None) is not None}[/dim]")
                return

            if not log_path.exists():
                preview_log.write(f"[yellow]⏳ Log file pending: {log_path}[/yellow]")
                return

            preview_log.write(f"[green]● Streaming from: {log_path.name}[/green]")
            self.log_stream = LogStream(log_path)
            self.streaming_item_id = item.item_id

            initial = self.log_stream.get_initial_content()
            if initial:
                from emdx.ui.live_log_writer import LiveLogWriter
                writer = LiveLogWriter(preview_log, auto_scroll=True)
                from emdx.utils.stream_json_parser import parse_and_format_live_logs
                formatted = parse_and_format_live_logs(initial)
                for line in formatted[-50:]:
                    preview_log.write(line)
                preview_log.scroll_end(animate=False)

            self.log_stream.subscribe(self.log_subscriber)

        except Exception as e:
            logger.error(f"Error setting up live log: {e}", exc_info=True)
            preview_log.write(f"[red]Error: {e}[/red]")

    def _handle_log_content(self, content: str) -> None:
        """Handle new log content from stream - LIVE LOGS formatted."""
        def update_ui():
            try:
                from emdx.ui.live_log_writer import LiveLogWriter

                preview_log = self.query_one("#preview-log", RichLog)
                writer = LiveLogWriter(preview_log, auto_scroll=True)
                writer.write(content)
            except Exception as e:
                logger.error(f"Error handling log content: {e}")

        self.app.call_from_thread(update_ui)

    def _stop_stream(self) -> None:
        """Stop any active log stream."""
        if self.log_stream:
            self.log_stream.unsubscribe(self.log_subscriber)
            self.log_stream = None
        self.streaming_item_id = None

    def _notify_workflow_complete(self, workflow_id: int, success: bool) -> None:
        """Show notification and play sound for workflow completion."""
        self._recently_completed.add(workflow_id)
        self.set_timer(3.0, lambda: self._clear_highlight(workflow_id))

        if success:
            print("\a", end="", flush=True)
        else:
            print("\a\a\a", end="", flush=True)

        self.notification_is_error = not success
        if success:
            self.notification_text = f"✨ Workflow #{workflow_id} complete"
        else:
            self.notification_text = f"❌ Workflow #{workflow_id} failed"
        self.notification_visible = True

        self.set_timer(5.0, self._hide_notification)

        self.post_message(self.WorkflowCompleted(workflow_id, success))

        # Force preview update if this workflow is currently selected
        item = self._get_selected_item()
        if item and item.item_type == "workflow" and item.item_id == workflow_id:
            self._stop_stream()
            self._last_preview_key = None
            self.call_later(lambda: self.run_worker(self._update_preview(force=True)))

    def _clear_highlight(self, workflow_id: int) -> None:
        """Clear the completion highlight for a workflow."""
        self._recently_completed.discard(workflow_id)
        # Refresh tree labels to remove highlight
        self.call_later(self._refresh_labels_only)

    async def _refresh_labels_only(self) -> None:
        """Refresh just the tree labels without reloading data."""
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.refresh_from_items(self.activity_items)

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
        """Periodic refresh of data.

        With Tree widget, this is dramatically simpler:
        1. Load fresh items from DB
        2. Call refresh_from_items() which diffs and updates labels in-place
        3. Tree preserves cursor position and scroll natively
        """
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True

        try:
            self.activity_items = await self._data_loader.load_all(
                zombies_cleaned=self._zombies_cleaned,
            )
            self._zombies_cleaned = True

            tree = self.query_one("#activity-tree", ActivityTree)
            tree.refresh_from_items(self.activity_items)

            await self._update_status_bar()
        finally:
            self._refresh_in_progress = False

    # Actions

    def action_cursor_down(self) -> None:
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.action_cursor_down()

    def action_cursor_up(self) -> None:
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.action_cursor_up()

    async def action_select(self) -> None:
        """Select/expand current item."""
        item = self._get_selected_item()
        if item is None:
            return

        tree = self.query_one("#activity-tree", ActivityTree)
        node = tree.cursor_node
        if node is None:
            return

        if node.is_expanded:
            node.collapse()
        elif item.can_expand():
            # Load children before expanding
            try:
                item.children = await item.load_children(wf_db, doc_db)
                item.expanded = True
                # Add children to tree node
                node.remove_children()
                tree._add_children(node, item.children)
                node.expand()
            except Exception as e:
                logger.error(f"Error expanding {item.item_type} #{item.item_id}: {e}", exc_info=True)

    async def action_expand(self) -> None:
        """Expand current item."""
        item = self._get_selected_item()
        if item is None:
            return

        tree = self.query_one("#activity-tree", ActivityTree)
        node = tree.cursor_node
        if node is None or node.is_expanded:
            return

        if item.can_expand():
            try:
                item.children = await item.load_children(wf_db, doc_db)
                item.expanded = True
                node.remove_children()
                tree._add_children(node, item.children)
                node.expand()
            except Exception as e:
                logger.error(f"Error expanding {item.item_type} #{item.item_id}: {e}", exc_info=True)

    async def action_collapse(self) -> None:
        """Collapse current item or go to parent."""
        tree = self.query_one("#activity-tree", ActivityTree)
        node = tree.cursor_node
        if node is None:
            return

        if node.is_expanded:
            node.collapse()
            if node.data:
                node.data.expanded = False
        elif node.parent and node.parent != tree.root:
            # Navigate to parent
            tree.move_cursor(node.parent)

    def action_fullscreen(self) -> None:
        """Toggle fullscreen preview."""
        item = self._get_selected_item()
        if item is None:
            return

        if item.doc_id:
            self.post_message(self.ViewDocument(item.doc_id))

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_data()

    async def action_mark_read(self) -> None:
        """Mark selected mail message as read."""
        item = self._get_selected_item()
        if item is None:
            return
        if item.item_type != "mail":
            return

        from emdx.services.mail_service import get_mail_service
        service = get_mail_service()
        success = await asyncio.to_thread(service.mark_read, item.item_id)
        if success:
            item.is_read = True
            # Update the tree node label
            tree = self.query_one("#activity-tree", ActivityTree)
            node = tree.cursor_node
            if node:
                node.set_label(tree._make_label(item))
            await self._update_context_panel()

    def action_focus_next(self) -> None:
        """Focus next pane."""
        pass

    def action_focus_prev(self) -> None:
        """Focus previous pane."""
        pass

    async def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        """Handle tree cursor movement."""
        await self._update_preview(force=True)
        await self._update_context_panel()

    async def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection (Enter key)."""
        await self.action_select()

    async def on_tree_node_expanded(self, event: Tree.NodeExpanded) -> None:
        """Handle lazy child loading when a node is expanded."""
        node = event.node
        item = node.data
        if item is None:
            return

        # If node already has children in the tree, skip
        if len(list(node.children)) > 0:
            return

        # Load children from DB
        if item.can_expand():
            try:
                item.children = await item.load_children(wf_db, doc_db)
                item.expanded = True
                tree = self.query_one("#activity-tree", ActivityTree)
                tree._add_children(node, item.children)
            except Exception as e:
                logger.error(f"Error loading children for {item.item_type} #{item.item_id}: {e}", exc_info=True)

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        """Track collapse state on the item."""
        if event.node.data:
            event.node.data.expanded = False

    def on_unmount(self) -> None:
        """Cleanup on unmount."""
        self._stop_stream()

    # Gist/quick document creation

    async def action_create_gist(self) -> None:
        """Create a copy of the currently selected document."""
        item = self._get_selected_item()
        if item is None:
            self._show_notification("No item selected", is_error=True)
            return

        if not item.doc_id:
            self._show_notification("Select a document to gist", is_error=True)
            return

        if not HAS_DOCS or not doc_db:
            self._show_notification("Documents not available", is_error=True)
            return

        try:
            doc = doc_db.get_document(item.doc_id)
            if not doc:
                self._show_notification("Document not found", is_error=True)
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

            self._show_notification(f"Created gist #{new_doc_id}")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating gist: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    # Group management actions

    def action_add_to_group(self) -> None:
        """Show group picker to add selected document, group, or workflow to another group."""
        item = self._get_selected_item()
        if item is None:
            return

        picker = self.query_one("#group-picker", GroupPicker)

        if item.item_type == "group":
            picker.show(source_group_id=item.item_id)
            return

        if item.item_type == "workflow" and item.workflow_run:
            picker.show(workflow_run_id=item.workflow_run.get("id"))
            return

        if item.doc_id:
            picker.show(doc_id=item.doc_id)
            return

        self._show_notification("Select a document, group, or workflow", is_error=True)

    async def action_create_group(self) -> None:
        """Create a new group from the selected document."""
        item = self._get_selected_item()
        if item is None:
            return

        if not item.doc_id:
            self._show_notification("Select a document to create a group from", is_error=True)
            return

        if not HAS_GROUPS or not groups_db:
            self._show_notification("Groups not available", is_error=True)
            return

        try:
            doc = doc_db.get_document(item.doc_id) if HAS_DOCS else None
            doc_title = doc.get("title", "Untitled") if doc else "Untitled"

            group_name = f"{doc_title[:30]} Group"
            group_id = groups_db.create_group(
                name=group_name,
                group_type="batch",
            )

            groups_db.add_document_to_group(group_id, item.doc_id, role="primary")

            self._show_notification(f"Created group '{group_name}'")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    async def action_ungroup(self) -> None:
        """Remove selected item from its parent group."""
        item = self._get_selected_item()
        if item is None:
            return

        if not HAS_GROUPS or not groups_db:
            self._show_notification("Groups not available", is_error=True)
            return

        try:
            if item.item_type == "group":
                group = groups_db.get_group(item.item_id)
                if not group or not group.get("parent_group_id"):
                    self._show_notification("Group has no parent", is_error=True)
                    return
                groups_db.update_group(item.item_id, parent_group_id=None)
                self._show_notification(f"Removed '{group['name']}' from parent")
                await self._refresh_data()
                return

            if item.doc_id:
                doc_groups = groups_db.get_document_groups(item.doc_id)
                if not doc_groups:
                    self._show_notification("Document is not in any group", is_error=True)
                    return

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
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self._show_notification(f"Moved group under '{event.group_name}'")
            elif event.doc_id:
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self._show_notification(f"Added to '{event.group_name}'")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

        tree = self.query_one("#activity-tree", ActivityTree)
        tree.focus()

    async def on_group_picker_group_created(self, event: GroupPicker.GroupCreated) -> None:
        """Handle new group creation from picker."""
        if not HAS_GROUPS or not groups_db:
            return

        try:
            if event.workflow_run_id:
                await self._group_workflow_under(event.workflow_run_id, event.group_id, event.group_name)
            elif event.source_group_id:
                groups_db.update_group(event.source_group_id, parent_group_id=event.group_id)
                self._show_notification(f"Created '{event.group_name}' and moved group under it")
            elif event.doc_id:
                groups_db.add_document_to_group(event.group_id, event.doc_id)
                self._show_notification(f"Created '{event.group_name}' and added document")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Error in group operation: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

        tree = self.query_one("#activity-tree", ActivityTree)
        tree.focus()

    async def _group_workflow_under(self, workflow_run_id: int, parent_group_id: int, parent_name: str) -> None:
        """Group a workflow's outputs under a parent group."""
        if not HAS_WORKFLOWS or not wf_db:
            return

        run = wf_db.get_workflow_run(workflow_run_id)
        if not run:
            self._show_notification("Workflow run not found", is_error=True)
            return

        workflow_id = run.get("workflow_id")
        workflow = wf_db.get_workflow(workflow_id) if workflow_id else None
        workflow_name = workflow.get("name", "Workflow") if workflow else "Workflow"

        existing_groups = groups_db.list_groups(workflow_run_id=workflow_run_id)

        if existing_groups:
            for grp in existing_groups:
                if grp.get("parent_group_id") != parent_group_id:
                    groups_db.update_group(grp["id"], parent_group_id=parent_group_id)
            self._show_notification(f"Moved workflow under '{parent_name}'")
        else:
            wf_group_id = groups_db.create_group(
                name=f"{workflow_name} #{workflow_run_id}",
                group_type="batch",
                parent_group_id=parent_group_id,
                workflow_run_id=workflow_run_id,
                created_by="user",
            )

            output_doc_ids = wf_db.get_workflow_output_doc_ids(workflow_run_id)
            added_count = 0
            for doc_id in output_doc_ids:
                try:
                    if groups_db.add_document_to_group(wf_group_id, doc_id, role="member"):
                        added_count += 1
                except Exception as e:
                    logger.warning(f"Failed to add doc {doc_id} to group: {e}")

            if added_count > 0:
                self._show_notification(f"Grouped {added_count} docs under '{parent_name}'")
            else:
                self._show_notification(f"Created group under '{parent_name}' (no docs found)")

    def on_group_picker_cancelled(self, event: GroupPicker.Cancelled) -> None:
        """Handle picker cancellation."""
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.focus()

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select and show a document by its ID.

        Walks tree nodes to find the document. If inside a collapsed
        workflow, expands it first, then selects the document node.
        """
        logger.debug(f"select_document_by_id({doc_id}) called")

        tree = self.query_one("#activity-tree", ActivityTree)

        # First check if already visible in tree
        node = tree.find_node_by_doc_id(doc_id)
        if node:
            logger.debug(f"Found document node directly in tree")
            tree.move_cursor(node)
            tree.scroll_to_node(node)
            await self._update_preview(force=True)
            return True

        logger.debug("Not visible in tree, checking if doc is inside a collapsed workflow...")

        # Check if any workflow has this doc_id and expand it
        for top_node in tree.root.children:
            if top_node.data and top_node.data.item_type == "workflow":
                if getattr(top_node.data, 'doc_id', None) == doc_id:
                    logger.debug(f"Found workflow with doc_id={doc_id}, expanding...")
                    # Load children and expand
                    item = top_node.data
                    try:
                        item.children = await item.load_children(wf_db, doc_db)
                        item.expanded = True
                        top_node.remove_children()
                        tree._add_children(top_node, item.children)
                        top_node.expand()
                    except Exception as e:
                        logger.error(f"Error expanding workflow: {e}")

                    # Now search again
                    node = tree.find_node_by_doc_id(doc_id)
                    if node:
                        logger.debug(f"Found doc node after expanding workflow")
                        tree.move_cursor(node)
                        tree.scroll_to_node(node)
                        await self._update_preview(force=True)
                        return True
                    logger.debug("Doc NOT found after expand - unexpected!")
                    break

        logger.debug("Not found via workflow parent, trying direct load as fallback")

        # Fallback - just show doc in preview
        if HAS_DOCS and doc_db:
            doc = doc_db.get_document(doc_id)
            if doc:
                content = doc.get("content", "")
                title = doc.get("title", "Untitled")
                self._render_markdown_preview(f"# {title}\n\n{content}")
                header = self.query_one("#preview-header", Static)
                header.update(f"📄 #{doc_id}")
                self._show_notification(f"Showing: {title[:40]}")
                return True

        self._show_notification(f"Document #{doc_id} not found", is_error=True)
        return False
