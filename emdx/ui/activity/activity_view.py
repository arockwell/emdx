"""Activity View - Document Browser for EMDX.

Flat table of recent documents with a preview pane.
No hierarchy, no groups — just a scannable list sorted by time.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Log, RichLog, Static

from ..modals import HelpMixin
from .activity_data import ActivityDataLoader
from .activity_items import ActivityItem as ActivityItemBase
from .activity_table import ActivityTable
from .sparkline import sparkline

logger = logging.getLogger(__name__)

try:
    from emdx.database import documents as doc_db

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
    """Activity View - Document Browser for EMDX."""

    HELP_TITLE = "Activity View"
    """Document browser — flat table of recent documents."""

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
        ("tab", "focus_next", "Next Pane"),
        ("shift+tab", "focus_prev", "Prev Pane"),
        ("question_mark", "show_help", "Help"),
        ("c", "toggle_copy_mode", "Copy Mode"),
        ("w", "cycle_doc_type_filter", "Filter Docs"),
        ("z", "toggle_zoom", "Zoom"),
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

    /* ── Top band: list + sidebar ─────────────────────── */

    #activity-panel {
        height: 40%;
        width: 100%;
    }

    /* Wide (>=120 cols, default): list 70%, sidebar 30% */
    #activity-list-section {
        width: 70%;
    }

    #context-section {
        width: 30%;
        border-left: solid $secondary;
    }

    /* Narrow (<120 cols): sidebar hidden, list fills band */
    #activity-panel.sidebar-hidden #context-section {
        display: none;
    }

    #activity-panel.sidebar-hidden #activity-list-section {
        width: 100%;
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

    /* ── Bottom pane: content preview ─────────────────── */

    #preview-panel {
        height: 60%;
        width: 100%;
        border-top: solid $primary;
    }

    /* ── Zoom: content full-screen (list hidden) ──────── */
    #activity-panel.zoom-content {
        display: none;
    }

    #preview-panel.zoom-content {
        height: 100%;
        border-top: none;
    }

    /* ── Zoom: list full-screen (content hidden) ──────── */
    #preview-panel.zoom-list {
        display: none;
    }

    #activity-panel.zoom-list {
        height: 100%;
    }

    /* ── Backward-compat aliases (existing zoom classes) ─ */
    #activity-panel.zoom-hidden {
        display: none;
    }

    #preview-panel.zoom-full {
        height: 100%;
        border-top: none;
    }

    /* ── Table and headers ────────────────────────────── */

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

    /* ── Notification bar ─────────────────────────────── */

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

    # Doc type filter cycle order
    DOC_TYPE_FILTERS = ("user", "wiki", "all")
    DOC_TYPE_FILTER_LABELS = {
        "user": "📄 User Docs",
        "wiki": "📚 Wiki Only",
        "all": "🔀 All Docs",
    }

    # Reactive for notification
    notification_text = reactive("")
    notification_visible = reactive(False)
    notification_is_error = reactive(False)
    doc_type_filter: reactive[str] = reactive("user")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.activity_items: list[ActivityItem] = []
        self._fullscreen = False
        self._last_preview_key: tuple[str, int, str] | None = None
        self._preview_raw_content: str = ""
        self._copy_mode = False
        self._refresh_in_progress = False
        self._data_loader = ActivityDataLoader()
        self._zoomed: bool = False
        self._sidebar_visible: bool = True

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
        with Vertical(id="main-content"):
            # Top band: Activity table (left) + Context panel (right)
            with Horizontal(id="activity-panel"):
                # Left: Activity table
                with Vertical(id="activity-list-section"):
                    yield Static("DOCUMENTS", id="activity-header")
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

    # Width threshold for showing/hiding sidebar
    SIDEBAR_WIDTH_THRESHOLD = 120

    async def on_mount(self) -> None:
        """Initialize the view."""
        table = self.query_one("#activity-table", ActivityTable)

        # Apply initial sidebar visibility based on current width
        self._update_sidebar_visibility()

        await self.load_data()
        table.focus()

        # Start refresh timer
        self.set_interval(1.0, self._refresh_data_tick)

    def on_resize(self, event: events.Resize) -> None:
        """Toggle sidebar visibility based on terminal width."""
        self._update_sidebar_visibility()

    def _update_sidebar_visibility(self) -> None:
        """Show/hide sidebar based on current width."""
        try:
            panel = self.query_one("#activity-panel")
        except Exception:
            return
        was_visible = self._sidebar_visible
        if self.size.width < self.SIDEBAR_WIDTH_THRESHOLD:
            panel.add_class("sidebar-hidden")
            self._sidebar_visible = False
        else:
            panel.remove_class("sidebar-hidden")
            self._sidebar_visible = True
        # Re-render preview if sidebar visibility changed (preamble toggle)
        if was_visible != self._sidebar_visible:
            self._last_preview_key = None  # force re-render
            self.run_worker(self._update_preview(force=True), exclusive=True)

    async def load_data(self, update_preview: bool = True) -> None:
        """Load activity data."""
        self.activity_items = await self._data_loader.load_all(
            doc_type_filter=self.doc_type_filter,
        )

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

        week_data = self._get_week_activity_data()
        spark = sparkline([float(x) for x in week_data], width=7)

        from emdx.ui.themes import get_theme_indicator

        theme_indicator = get_theme_indicator(self.app.theme)

        parts = []
        parts.append(f"📄 {docs_today} today")
        parts.append(format_cost(cost_today))

        parts.append(f"[dim]{spark}[/dim]")

        filter_label = self.DOC_TYPE_FILTER_LABELS.get(self.doc_type_filter, "All")
        parts.append(f"[dim]{filter_label}[/dim]")

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

    def _build_metadata_preamble(self, item: ActivityItem) -> str:
        """Build a Rich markup string of document metadata for the preview preamble.

        Used when the sidebar is hidden (narrow mode) to show metadata
        inline above the document content.
        """
        from .activity_items import DocumentItem

        lines: list[str] = []

        if isinstance(item, DocumentItem):
            # Line 1: type badge + project + age
            parts: list[str] = []
            if item.doc_type == "wiki":
                parts.append("[bold magenta]wiki[/bold magenta]")
            if item.project:
                parts.append(f"[cyan]{item.project}[/cyan]")
            parts.append(f"[dim]{format_time_ago(item.timestamp)}[/dim]")
            lines.append(" · ".join(parts))

            # Line 2: stats
            stats: list[str] = []
            if item.word_count:
                stats.append(f"{item.word_count:,} words")
            if item.access_count > 1:
                stats.append(f"{item.access_count} views")
            if stats:
                lines.append(f"[dim]{' · '.join(stats)}[/dim]")

            # Tags
            if item.tags:
                lines.append(f"[dim]Tags:[/dim] {' '.join(item.tags)}")

        return "\n".join(lines)

    def _render_markdown_preview(
        self,
        content: str,
        title: str = "Untitled",
        metadata_preamble: str = "",
    ) -> None:
        """Render markdown content to the preview RichLog.

        Args:
            content: Markdown content to render.
            title: Document title.
            metadata_preamble: Optional metadata block to prepend when sidebar
                is hidden (narrow mode). Written as Rich markup before the
                markdown body.
        """
        from emdx.ui.link_helpers import linkify_richlog
        from emdx.ui.markdown_config import render_markdown_to_richlog

        preview = self.query_one("#preview-content", RichLog)

        if metadata_preamble:
            # Write preamble as Rich markup, then separator, then markdown
            preview.clear()
            for line in metadata_preamble.splitlines():
                preview.write(line)
            preview.write("[dim]───[/dim]")
            # Render markdown after preamble (append mode — don't clear)
            self._preview_raw_content = render_markdown_to_richlog(
                preview, content, title, clear=False
            )
        else:
            self._preview_raw_content = render_markdown_to_richlog(preview, content, title)

        # Post-process URLs after the RichLog has rendered its content
        if "http" in content:
            self.call_after_refresh(linkify_richlog, preview)

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

        if not force and self._last_preview_key == current_key:
            return

        self._last_preview_key = current_key

        # Build metadata preamble if sidebar is hidden
        preamble = ""
        if not self._sidebar_visible:
            preamble = self._build_metadata_preamble(item)

        # Show document content
        if item.doc_id and HAS_DOCS:
            try:
                doc = doc_db.get_document(item.doc_id)
                if doc:
                    content = doc.get("content", "")
                    title = doc.get("title", "Untitled")
                    self._render_markdown_preview(content, title, metadata_preamble=preamble)
                    show_markdown()
                    header.update(f"📄 #{item.doc_id}")
                    return
                else:
                    self._render_markdown_preview(
                        f"*Document #{item.doc_id} not found*\n\n"
                        "This document may have been deleted.",
                        item.title,
                    )
                    show_markdown()
                    header.update(f"⚠️ #{item.doc_id} (missing)")
                    return
            except Exception as e:
                logger.error(f"Error loading document: {e}")

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
            context_content.write(f"[dim]{item.title}[/dim]")

    async def _show_document_context(
        self, item: ActivityItem, content: RichLog, header: Static
    ) -> None:
        """Show document metadata in context panel.

        Uses data already loaded on the DocumentItem to avoid re-fetching.
        Falls back to DB lookup for linked documents (knowledge graph).
        """
        if not HAS_DOCS or not item.doc_id:
            header.update("DOCUMENT")
            return

        try:
            from .activity_items import DocumentItem

            header.update(f"📄 #{item.doc_id}")

            # Line 1: type badge + project + age
            meta_line1: list[str] = []
            if isinstance(item, DocumentItem):
                if item.doc_type == "wiki":
                    meta_line1.append("[bold magenta]wiki[/bold magenta]")
                if item.project:
                    meta_line1.append(f"[cyan]{item.project}[/cyan]")
            meta_line1.append(f"[dim]{format_time_ago(item.timestamp)}[/dim]")
            content.write(" · ".join(meta_line1))

            # Line 2: word count + access count + timestamps
            if isinstance(item, DocumentItem):
                meta_line2: list[str] = []
                if item.word_count:
                    meta_line2.append(f"{item.word_count:,} words")
                if item.access_count > 1:
                    meta_line2.append(f"{item.access_count} views")
                if item.updated_at:
                    meta_line2.append(f"Updated {format_time_ago(item.updated_at)}")
                if meta_line2:
                    content.write(f"[dim]{' · '.join(meta_line2)}[/dim]")

                # Tags
                if item.tags:
                    content.write(f"[dim]Tags:[/dim] {' '.join(item.tags)}")

            # Linked documents (knowledge graph)
            try:
                from emdx.database.document_links import get_links_for_document

                links = get_links_for_document(item.doc_id)
                if links:
                    content.write("")
                    content.write("[bold]Related:[/bold]")
                    for link in links[:5]:
                        if link["source_doc_id"] == item.doc_id:
                            other_id = link["target_doc_id"]
                            other_title = link["target_title"]
                        else:
                            other_id = link["source_doc_id"]
                            other_title = link["source_title"]
                        score = link.get("similarity_score", 0)
                        title_trunc = (other_title or "")[:40]
                        line = Text("  ")
                        click_style = Style(
                            bold=True,
                            underline=True,
                            color="bright_cyan",
                            meta={"@click": f"app.select_doc({other_id})"},
                        )
                        line.append(f"#{other_id}", style=click_style)
                        line.append(f" {title_trunc}")
                        if score:
                            line.append(f" {int(score * 100)}%", style="dim")
                        content.write(line)
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"Error loading linked docs: {e}")

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
                doc_type_filter=self.doc_type_filter,
            )

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

    def action_toggle_zoom(self) -> None:
        """Cycle zoom: normal -> content full-screen -> list full-screen -> normal."""
        activity_panel = self.query_one("#activity-panel")
        preview_panel = self.query_one("#preview-panel")

        if not self._zoomed:
            # Normal -> zoom content (list hidden, preview full)
            self._zoomed = True
            activity_panel.add_class("zoom-content")
            preview_panel.add_class("zoom-content")
            self.query_one("#preview-content", RichLog).focus()
        elif activity_panel.has_class("zoom-content"):
            # Zoom content -> zoom list (preview hidden, list full)
            activity_panel.remove_class("zoom-content")
            preview_panel.remove_class("zoom-content")
            activity_panel.add_class("zoom-list")
            preview_panel.add_class("zoom-list")
            self.query_one("#activity-table", ActivityTable).focus()
        else:
            # Zoom list -> normal
            self._zoomed = False
            activity_panel.remove_class("zoom-list")
            preview_panel.remove_class("zoom-list")
            self.query_one("#activity-table", ActivityTable).focus()

    def action_focus_next(self) -> None:
        """Focus next pane."""
        pass

    def action_focus_prev(self) -> None:
        """Focus previous pane."""
        pass

    async def action_cycle_doc_type_filter(self) -> None:
        """Cycle document type filter: user -> wiki -> all -> user."""
        current_idx = self.DOC_TYPE_FILTERS.index(self.doc_type_filter)
        next_idx = (current_idx + 1) % len(self.DOC_TYPE_FILTERS)
        self.doc_type_filter = self.DOC_TYPE_FILTERS[next_idx]
        label = self.DOC_TYPE_FILTER_LABELS[self.doc_type_filter]
        self._show_notification(f"Filter: {label}")
        await self.load_data()

    async def on_activity_table_item_highlighted(
        self, event: ActivityTable.ItemHighlighted
    ) -> None:
        """Handle table cursor movement."""
        await self._update_preview(force=True)
        await self._update_context_panel()

    def on_activity_table_enter_pressed(self, event: ActivityTable.EnterPressed) -> None:
        """Handle Enter key on table row — open fullscreen."""
        self.action_fullscreen()

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
                self._render_markdown_preview(content, title)
                header = self.query_one("#preview-header", Static)
                header.update(f"📄 #{doc_id}")
                self._show_notification(f"Showing: {title[:40]}")
                return True

        self._show_notification(f"Document #{doc_id} not found", is_error=True)
        return False
