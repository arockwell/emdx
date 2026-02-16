"""Activity View - Mission Control for EMDX.

The primary interface for monitoring Claude Code's work:
- Status bar with active count, docs today, cost, errors, sparkline
- Activity stream showing cascades, agents, groups, and direct saves
- Preview pane with document content
- Hierarchical drill-in for groups and cascade runs

Uses Textual's Tree widget for native hierarchy, expand/collapse,
and cursor tracking by node reference — eliminating scroll jumping.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static, Tree

from emdx.utils.datetime_utils import parse_datetime

from ..modals import HelpMixin
from .activity_data import ActivityDataLoader
from .activity_items import ActivityItem as ActivityItemBase
from .activity_tree import ActivityTree
from .group_picker import GroupPicker
from .sparkline import sparkline

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_db
    from emdx.services import group_service as groups_db
    from emdx.services.log_stream import LogStream, LogStreamSubscriber

    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_db = None  # type: ignore[assignment]
    groups_db = None  # type: ignore[assignment]
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
        return "just now"

    if seconds < 10:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s"
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

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "fullscreen", "Open"),
        ("l", "expand", "Expand"),
        ("h", "collapse", "Collapse"),
        ("f", "fullscreen", "Fullscreen"),
        ("r", "refresh", "Refresh"),
        ("g", "add_to_group", "Add to Group"),
        ("G", "create_group", "Create Group"),
        ("i", "create_gist", "New Gist"),
        ("u", "ungroup", "Ungroup"),
        ("x", "dismiss_execution", "Kill/Dismiss"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.activity_items: list[ActivityItem] = []
        self.log_stream: LogStream | None = None
        self.log_subscriber = AgentLogSubscriber(self)
        self.streaming_item_id: int | None = None
        self._fullscreen = False
        # Cache to prevent flickering during refresh
        self._last_preview_key: tuple | None = None  # (item_type, item_id, status)
        # Flag to only run zombie cleanup once on startup
        self._zombies_cleaned = False
        # Reentrance guard: prevents overlapping async refreshes
        self._refresh_in_progress = False
        # Data loader (owns DB queries)
        self._data_loader = ActivityDataLoader()

    def _get_selected_item(self) -> ActivityItem | None:
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
                        yield RichLog(
                            id="context-content",
                            highlight=True,
                            markup=True,
                            wrap=True,
                            auto_scroll=False,
                        )  # noqa: E501

            # Right: Preview (document content)
            with Vertical(id="preview-panel"):
                yield Static("PREVIEW", id="preview-header")
                with ScrollableContainer(id="preview-scroll"):
                    yield RichLog(
                        id="preview-content",
                        highlight=True,
                        markup=True,
                        wrap=True,
                        auto_scroll=False,
                    )  # noqa: E501
                yield RichLog(id="preview-log", highlight=True, markup=True, wrap=True)

        # Group picker (inline at bottom, hidden by default)
        yield GroupPicker(id="group-picker")

    async def on_mount(self) -> None:
        """Initialize the view."""
        tree = self.query_one("#activity-tree", ActivityTree)

        await self.load_data()
        tree.focus()

        # Start refresh timer (sync wrapper dispatches to async via run_worker)
        self.set_interval(1.0, self._refresh_data_tick)

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

        # Count active items (running agents)
        active = len([item for item in self.activity_items if item.status == "running"])

        # Count docs today
        today = datetime.now().date()
        docs_today = len(
            [
                item
                for item in self.activity_items
                if item.timestamp and item.timestamp.date() == today
            ]
        )

        # Total cost today
        cost_today: float = sum(
            (
                item.cost
                for item in self.activity_items
                if item.timestamp and item.timestamp.date() == today and item.cost
            ),
            0.0,
        )

        # Count errors (today only)
        errors = len(
            [
                item
                for item in self.activity_items
                if item.status == "failed" and item.timestamp and item.timestamp.date() == today
            ]
        )

        # Generate sparkline for the week
        week_data = self._get_week_activity_data()
        spark = sparkline([float(x) for x in week_data], width=7)

        # Get theme indicator
        from emdx.ui.themes import get_theme_indicator

        theme_indicator = get_theme_indicator(self.app.theme)

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
        parts.append(f"[dim]{theme_indicator}[/dim]")

        status_bar.update(" │ ".join(parts))

    def _get_week_activity_data(self) -> list[int]:
        """Get activity counts for each day of the past week."""
        today = datetime.now().date()
        counts = []

        for i in range(6, -1, -1):  # 6 days ago to today
            day = today - timedelta(days=i)
            count = len(
                [
                    item
                    for item in self.activity_items
                    if item.timestamp and item.timestamp.date() == day
                ]
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

        def show_markdown() -> None:
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

        # For running agent executions, show live log
        if item.status == "running" and item.item_type == "agent_execution":
            await self._show_live_log(item)
            return

        # For documents, show content
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
                    # Check if content already has a markdown title header (may have leading whitespace)  # noqa: E501
                    content_stripped = content.lstrip()
                    has_title_header = (
                        content_stripped.startswith(f"# {title}")
                        or content_stripped.startswith("# ")  # Any h1 header counts
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
            content, header_text = await item.get_preview_content(doc_db)
            if content:
                self._render_markdown_preview(content)
                show_markdown()
                header.update(header_text)
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

        # Document details
        if item.doc_id:
            await self._show_document_context(item, context_content, context_header)
        # Group details
        elif item.item_type == "group":
            await self._show_group_context(item, context_content, context_header)
        else:
            context_header.update("DETAILS")
            context_content.write(f"[dim]{item.item_type}: {item.title}[/dim]")

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
                from emdx.services.tag_service import get_document_tags

                tags = get_document_tags(item.doc_id)
            except ImportError:
                tags = []

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
            content.write(
                f"[dim]{group.get('group_type', 'batch')} · {group.get('doc_count', 0)} docs[/dim]"
            )  # noqa: E501

            desc = group.get("description")
            if desc:
                content.write(f"{desc[:100]}")

        except Exception as e:
            logger.error(f"Error showing group context: {e}")

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

            desc = group.get("description")
            if desc:
                lines.append(desc)
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
                    lines.append(
                        f"- {icon} #{cg['id']} {cg['name']} ({cg.get('doc_count', 0)} docs)"
                    )  # noqa: E501
                if len(child_groups) > 10:
                    lines.append(f"*... and {len(child_groups) - 10} more*")

            members = groups_db.get_group_members(group_id)
            if members:
                lines.append("")
                lines.append("## Documents")
                for m in members[:15]:
                    role = m.get("role", "member")
                    role_icons = {
                        "primary": "★",
                        "synthesis": "📝",
                        "exploration": "◇",
                        "variant": "≈",
                    }  # noqa: E501
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
        """Show live log for running agent execution."""
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

        try:
            log_path = None

            if item.item_type == "agent_execution":
                log_file = getattr(item, "log_file", None)
                if log_file:
                    log_path = Path(log_file)

            if not log_path:
                preview_log.write("[yellow]⏳ Waiting for log...[/yellow]")
                preview_log.write(f"[dim]item_type={item.item_type}[/dim]")
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

                LiveLogWriter(preview_log, auto_scroll=True)
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

        def update_ui() -> None:
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

    def _refresh_data_tick(self) -> None:
        """Sync callback for set_interval — dispatches to async refresh."""
        if self._refresh_in_progress:
            return
        # Set flag here (sync) to prevent the next tick from cancelling
        # the worker via exclusive=True before the coroutine starts.
        self._refresh_in_progress = True
        self.run_worker(self._refresh_data(), exclusive=True, group="refresh")

    async def _refresh_data(self) -> None:
        """Periodic refresh of data.

        With Tree widget, this is dramatically simpler:
        1. Load fresh items from DB
        2. Call refresh_from_items() which diffs and updates labels in-place
        3. Tree preserves cursor position and scroll natively
        """
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
                item.children = await item.load_children(doc_db)
                item.expanded = True
                # Add children to tree node
                node.remove_children()
                tree.add_activity_children(node, item.children)
                node.expand()
            except Exception as e:
                logger.error(
                    f"Error expanding {item.item_type} #{item.item_id}: {e}", exc_info=True
                )  # noqa: E501

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
                item.children = await item.load_children(doc_db)
                item.expanded = True
                node.remove_children()
                tree.add_activity_children(node, item.children)
                node.expand()
            except Exception as e:
                logger.error(
                    f"Error expanding {item.item_type} #{item.item_id}: {e}", exc_info=True
                )  # noqa: E501

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
        """Open document in fullscreen preview modal."""
        item = self._get_selected_item()
        if item is None:
            return

        if item.doc_id:
            from emdx.ui.modals import DocumentPreviewModal

            self.app.push_screen(DocumentPreviewModal(item.doc_id))

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_data()

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
        """Handle tree node selection (Enter key) — open fullscreen."""
        self.action_fullscreen()

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
                item.children = await item.load_children(doc_db)
                item.expanded = True
                tree = self.query_one("#activity-tree", ActivityTree)
                tree.add_activity_children(node, item.children)
            except Exception as e:
                logger.error(
                    f"Error loading children for {item.item_type} #{item.item_id}: {e}",
                    exc_info=True,
                )  # noqa: E501

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

            from emdx.utils.git import get_git_project

            project = get_git_project()
            new_doc_id = doc_db.save_document(
                title=f"{title} (copy)",
                content=content,
                project=project,
            )

            self._show_notification(f"Created gist #{new_doc_id}")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error creating gist: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    # Execution management actions

    async def action_dismiss_execution(self) -> None:
        """Kill or dismiss a stale/running execution."""
        item = self._get_selected_item()
        if item is None:
            self._show_notification("No item selected", is_error=True)
            return

        if item.item_type != "agent_execution":
            self._show_notification("Can only dismiss executions", is_error=True)
            return

        if item.status != "running":
            self._show_notification("Execution is not running", is_error=True)
            return

        try:
            from emdx.models.executions import get_execution, update_execution_status

            execution = get_execution(item.item_id)
            if not execution:
                self._show_notification(f"Execution #{item.item_id} not found", is_error=True)
                return

            # Try to kill the process if it has a PID
            if execution.pid:
                try:
                    import psutil

                    proc = psutil.Process(execution.pid)
                    proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # Process already gone or can't access

            # Mark as failed
            update_execution_status(item.item_id, "failed", exit_code=-6)
            self._show_notification(f"Dismissed execution #{item.item_id}")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error dismissing execution: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    # Group management actions

    def action_add_to_group(self) -> None:
        """Show group picker to add selected document or group to another group."""
        item = self._get_selected_item()
        if item is None:
            return

        picker = self.query_one("#group-picker", GroupPicker)

        if item.item_type == "group":
            picker.show(source_group_id=item.item_id)
            return

        if item.doc_id:
            picker.show(doc_id=item.doc_id)
            return

        self._show_notification("Select a document or group", is_error=True)

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
            if event.source_group_id:
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
            if event.source_group_id:
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

    def on_group_picker_cancelled(self, event: GroupPicker.Cancelled) -> None:
        """Handle picker cancellation."""
        tree = self.query_one("#activity-tree", ActivityTree)
        tree.focus()

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select and show a document by its ID."""
        logger.debug(f"select_document_by_id({doc_id}) called")

        tree = self.query_one("#activity-tree", ActivityTree)

        # First check if already visible in tree
        node = tree.find_node_by_doc_id(doc_id)
        if node:
            logger.debug("Found document node directly in tree")
            tree.move_cursor(node)
            tree.scroll_to_node(node)
            await self._update_preview(force=True)
            return True

        logger.debug("Not visible in tree, trying direct load as fallback")

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
