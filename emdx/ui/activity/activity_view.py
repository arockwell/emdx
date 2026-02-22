"""Activity View - Mission Control for EMDX.

Flat table of recent documents and agent executions with a preview pane.
No hierarchy, no groups — just a scannable list sorted by time.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Log, RichLog, Static

from emdx.utils.datetime_utils import parse_datetime

from ..modals import HelpMixin
from .activity_data import TIER_RECENT, TIER_RUNNING, TIER_TASKS, ActivityDataLoader
from .activity_items import ActivityItem as ActivityItemBase
from .activity_table import ActivityTable
from .sparkline import sparkline

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_db

    HAS_DOCS = True
except ImportError:
    doc_db = None  # type: ignore[assignment]
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

    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()

    # If timestamp appears to be in the future, it's likely stored as UTC
    if seconds < -60:
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_local = dt_utc.astimezone().replace(tzinfo=None)
        diff = now - dt_local
        seconds = diff.total_seconds()

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


ActivityItem = ActivityItemBase


class ActivityView(HelpMixin, Widget):
    """Activity View - Mission Control for EMDX."""

    HELP_TITLE = "Activity View"
    """Mission Control — flat table of recent activity."""

    class ViewDocument(Message):
        """Request to view a document fullscreen."""

        def __init__(self, doc_id: int) -> None:
            self.doc_id = doc_id
            super().__init__()

    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "fullscreen", "Open"),
        ("f", "fullscreen", "Fullscreen"),
        ("r", "refresh", "Refresh"),
        ("i", "create_gist", "New Gist"),
        ("x", "dismiss_execution", "Kill/Dismiss"),
        ("d", "mark_done", "Mark Done"),
        ("a", "mark_active", "Mark Active"),
        ("b", "mark_blocked", "Mark Blocked"),
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
        ("question_mark", "show_help", "Help"),
        ("c", "toggle_copy_mode", "Copy Mode"),
        ("R", "jump_running", "Jump Running"),
        ("T", "jump_tasks", "Jump Tasks"),
        ("D", "jump_docs", "Jump Docs"),
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

    #activity-table {
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

    #preview-copy {
        height: 1fr;
        padding: 0 1;
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
        self._fullscreen = False
        self._last_preview_key: tuple[str, int, str] | None = None
        self._preview_raw_content: str = ""
        self._copy_mode = False
        self._zombies_cleaned = False
        self._refresh_in_progress = False
        self._data_loader = ActivityDataLoader()

    def _get_selected_item(self) -> ActivityItem | None:
        """Get the currently selected ActivityItem from the table."""
        try:
            table = self.query_one("#activity-table", ActivityTable)
            return table.get_selected_item()
        except Exception:
            return None

    def compose(self) -> ComposeResult:
        # Status bar
        yield Static("Loading...", id="status-bar")

        # Notification bar (hidden by default)
        yield Static("", id="notification", classes="notification")

        # Main content
        with Horizontal(id="main-content"):
            # Left: Activity table (top) + Context panel (bottom)
            with Vertical(id="activity-panel"):
                # Top: Activity table
                with Vertical(id="activity-list-section"):
                    yield Static("ACTIVITY", id="activity-header")
                    yield ActivityTable(id="activity-table")
                # Bottom: Context panel (document metadata)
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
                    )
                yield Log(
                    id="preview-copy",
                    highlight=True,
                    auto_scroll=False,
                )

    async def on_mount(self) -> None:
        """Initialize the view."""
        table = self.query_one("#activity-table", ActivityTable)

        await self.load_data()
        table.focus()

        # Start refresh timer
        self.set_interval(1.0, self._refresh_data_tick)

    async def load_data(self, update_preview: bool = True) -> None:
        """Load activity data."""
        self.activity_items = await self._data_loader.load_all(
            zombies_cleaned=self._zombies_cleaned,
        )
        self._zombies_cleaned = True

        # Populate table
        table = self.query_one("#activity-table", ActivityTable)
        table.populate(self.activity_items)

        await self._update_status_bar()
        if update_preview:
            await self._update_preview(force=True)
            await self._update_context_panel()

    async def _update_status_bar(self) -> None:
        """Update the status bar with current stats."""
        status_bar = self.query_one("#status-bar", Static)

        active = len([item for item in self.activity_items if item.status == "running"])

        today = datetime.now().date()
        docs_today = len(
            [
                item
                for item in self.activity_items
                if item.timestamp and item.timestamp.date() == today
            ]
        )

        cost_today: float = sum(
            (
                item.cost
                for item in self.activity_items
                if item.timestamp and item.timestamp.date() == today and item.cost
            ),
            0.0,
        )

        errors = len(
            [
                item
                for item in self.activity_items
                if item.status == "failed" and item.timestamp and item.timestamp.date() == today
            ]
        )

        week_data = self._get_week_activity_data()
        spark = sparkline([float(x) for x in week_data], width=7)

        from emdx.ui.themes import get_theme_indicator

        theme_indicator = get_theme_indicator(self.app.theme)

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

        for i in range(6, -1, -1):
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

        self._preview_raw_content = content[:50000] if content else ""

        preview = self.query_one("#preview-content", RichLog)
        preview.clear()

        try:
            if len(content) > 50000:
                content = content[:50000] + "\n\n[dim]... (truncated)[/dim]"
            if content.strip():
                markdown = MarkdownConfig.create_markdown(content)
                preview.write(markdown)
            else:
                preview.write("[dim]Empty document[/dim]")
        except Exception:
            preview.write(content[:50000] if content else "[dim]No content[/dim]")

        if self._copy_mode:
            self._update_copy_widget()

    def _update_copy_widget(self) -> None:
        """Populate the copy-mode Log with raw markdown."""
        try:
            copy_log = self.query_one("#preview-copy", Log)
            copy_log.clear()
            if self._preview_raw_content.strip():
                copy_log.write(self._preview_raw_content)
        except Exception:
            pass

    def action_toggle_copy_mode(self) -> None:
        """Toggle between rendered preview and selectable copy mode."""
        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            copy_log = self.query_one("#preview-copy", Log)
        except Exception:
            return

        self._copy_mode = not self._copy_mode
        if self._copy_mode:
            self._update_copy_widget()
            preview_scroll.display = False
            copy_log.display = True
        else:
            preview_scroll.display = True
            copy_log.display = False

    async def _update_preview(self, force: bool = False) -> None:
        """Update the preview pane with selected item."""
        try:
            preview = self.query_one("#preview-content", RichLog)
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            header = self.query_one("#preview-header", Static)
        except Exception as e:
            logger.debug(f"Preview widgets not ready: {e}")
            return

        def show_markdown() -> None:
            copy_log = self.query_one("#preview-copy", Log)
            if self._copy_mode:
                preview_scroll.display = False
                copy_log.display = True
            else:
                preview_scroll.display = True
                copy_log.display = False

        item = self._get_selected_item()

        if item is None:
            preview.clear()
            preview.write("[dim]Select an item to preview[/dim]")
            show_markdown()
            header.update("PREVIEW")
            self._last_preview_key = None
            return

        current_key = (item.item_type, item.item_id, item.status)

        if not force and item.status != "running" and self._last_preview_key == current_key:
            return

        self._last_preview_key = current_key

        # For documents, show content
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
                    content_stripped = content.lstrip()
                    has_title_header = content_stripped.startswith(
                        f"# {title}"
                    ) or content_stripped.startswith("# ")
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
                        "This document may have been deleted."
                    )
                    show_markdown()
                    header.update(f"⚠️ #{item.doc_id} (missing)")
                    return
            except Exception as e:
                logger.error(f"Error loading document: {e}")

        # For agent executions without doc_id, or tasks
        if item.item_type in ("agent_execution", "task"):
            content, header_text = await item.get_preview_content(doc_db)
            if content:
                self._render_markdown_preview(content)
                show_markdown()
                header.update(header_text)
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

        if item.doc_id:
            await self._show_document_context(item, context_content, context_header)
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
        self._refresh_in_progress = True
        self.run_worker(self._refresh_data(), exclusive=True, group="refresh")

    async def _refresh_data(self) -> None:
        """Periodic refresh of data."""
        try:
            self.activity_items = await self._data_loader.load_all(
                zombies_cleaned=self._zombies_cleaned,
            )
            self._zombies_cleaned = True

            table = self.query_one("#activity-table", ActivityTable)
            table.refresh_items(self.activity_items)

            await self._update_status_bar()
        finally:
            self._refresh_in_progress = False

    # Actions

    def action_cursor_down(self) -> None:
        table = self.query_one("#activity-table", ActivityTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#activity-table", ActivityTable)
        table.action_cursor_up()

    def action_fullscreen(self) -> None:
        """Open document in fullscreen preview modal."""
        item = self._get_selected_item()
        if item is None:
            return

        if item.doc_id:
            from emdx.ui.modals import DocumentPreviewScreen

            self.app.push_screen(DocumentPreviewScreen(item.doc_id))

    async def action_refresh(self) -> None:
        """Manual refresh."""
        await self._refresh_data()

    def action_focus_next(self) -> None:
        """Focus next pane."""
        pass

    def action_focus_prev(self) -> None:
        """Focus previous pane."""
        pass

    def action_jump_running(self) -> None:
        """Jump cursor to the RUNNING section."""
        self._jump_to_section(TIER_RUNNING)

    def action_jump_tasks(self) -> None:
        """Jump cursor to the TASKS section."""
        self._jump_to_section(TIER_TASKS)

    def action_jump_docs(self) -> None:
        """Jump cursor to the DOCS section."""
        self._jump_to_section(TIER_RECENT)

    def _jump_to_section(self, tier: int) -> None:
        """Jump cursor to first item in section, with header scrolled to top."""
        from .activity_table import HEADER_PREFIX

        table = self.query_one("#activity-table", ActivityTable)
        header_key = f"{HEADER_PREFIX}{tier}"

        for i, row in enumerate(table.ordered_rows):
            if str(row.key.value) == header_key:
                # Scroll so the header is at the top
                table.scroll_to(0, i, animate=False)
                # Select the first item after the header
                if i + 1 < table.row_count:
                    table.move_cursor(row=i + 1)
                else:
                    table.move_cursor(row=i)
                return

    async def on_activity_table_item_highlighted(
        self, event: ActivityTable.ItemHighlighted
    ) -> None:
        """Handle table cursor movement."""
        await self._update_preview(force=True)
        await self._update_context_panel()

    def on_activity_table_double_clicked(self, event: ActivityTable.DoubleClicked) -> None:
        """Handle double-click on table row — open fullscreen."""
        self.action_fullscreen()

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

    # Execution management

    async def action_dismiss_execution(self) -> None:
        """Kill or dismiss a stale/running execution."""
        item = self._get_selected_item()
        if item is None:
            self._show_notification("No item selected", is_error=True)
            return

        if item.item_type != "agent_execution":
            # x is a no-op for tasks and documents
            return

        if item.status != "running":
            self._show_notification("Execution is not running", is_error=True)
            return

        try:
            from emdx.models.executions import (
                get_execution,
                update_execution_status,
            )

            execution = get_execution(item.item_id)
            if not execution:
                self._show_notification(f"Execution #{item.item_id} not found", is_error=True)
                return

            if execution.pid:
                try:
                    import psutil

                    proc = psutil.Process(execution.pid)
                    proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            update_execution_status(item.item_id, "failed", exit_code=-6)
            self._show_notification(f"Dismissed execution #{item.item_id}")
            await self._refresh_data()

        except Exception as e:
            logger.error(f"Error dismissing execution: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    # Task status actions

    async def _set_task_status(self, new_status: str) -> None:
        """Change status of the selected task and refresh."""
        item = self._get_selected_item()
        if item is None:
            self._show_notification("No item selected", is_error=True)
            return

        if item.item_type != "task":
            return

        if item.status == new_status:
            return

        try:
            from emdx.models.tasks import update_task

            update_task(item.item_id, status=new_status)
            self._show_notification(f"Task #{item.item_id} → {new_status}")
            await self._refresh_data()
        except Exception as e:
            logger.error(f"Failed to update task: {e}")
            self._show_notification(f"Error: {e}", is_error=True)

    async def action_mark_done(self) -> None:
        """Mark selected task as done."""
        await self._set_task_status("done")

    async def action_mark_active(self) -> None:
        """Mark selected task as active."""
        await self._set_task_status("active")

    async def action_mark_blocked(self) -> None:
        """Mark selected task as blocked."""
        await self._set_task_status("blocked")

    def _show_notification(self, message: str, is_error: bool = False) -> None:
        """Show a notification message."""
        self.notification_is_error = is_error
        self.notification_text = message
        self.notification_visible = True
        self.set_timer(3.0, self._hide_notification)

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select and show a document by its ID."""
        logger.debug(f"select_document_by_id({doc_id}) called")

        table = self.query_one("#activity-table", ActivityTable)

        row_index = table.find_row_by_doc_id(doc_id)
        if row_index is not None:
            logger.debug("Found document row in table")
            table.move_cursor(row=row_index)
            await self._update_preview(force=True)
            return True

        logger.debug("Not in table, trying direct load as fallback")

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
