#!/usr/bin/env python3
"""
Standalone log browser widget for EMDX TUI.

This widget displays execution logs in a dual-pane layout:
- Left pane: Table of recent executions
- Right pane: Log content viewer with selection support

The LogBrowser uses mixins for separation of concerns:
- LogBrowserDisplayMixin: Display formatting and status updates
- LogBrowserFilteringMixin: Log content filtering and noise reduction
- LogBrowserNavigationMixin: Cursor navigation and selection mode
"""

import logging
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.services.execution_service import Execution, get_recent_executions
from emdx.services.log_stream import LogStream, LogStreamSubscriber

from .log_browser_display import LogBrowserDisplayMixin
from .log_browser_filtering import LogBrowserFilteringMixin
from .log_browser_navigation import LogBrowserHost, LogBrowserNavigationMixin
from .modals import HelpMixin

logger = logging.getLogger(__name__)


class LogBrowserSubscriber(LogStreamSubscriber):
    """Internal subscriber for LogBrowser to handle stream events."""

    def __init__(self, log_browser):
        self.log_browser = log_browser

    def on_log_content(self, new_content: str) -> None:
        """Delegate to LogBrowser."""
        self.log_browser._handle_log_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        """Delegate to LogBrowser."""
        self.log_browser._handle_log_error(error)


class LogBrowser(
    HelpMixin,
    LogBrowserDisplayMixin,
    LogBrowserFilteringMixin,
    LogBrowserNavigationMixin,
    Widget
):
    """Log browser widget for viewing execution logs with event-driven streaming.

    This class combines functionality from multiple mixins:
    - LogBrowserDisplayMixin: format_execution_metadata, update_details_panel,
      _handle_log_content, _handle_log_error, update_status
    - LogBrowserFilteringMixin: _is_wrapper_noise, _filter_log_content,
      _format_initial_content
    - LogBrowserNavigationMixin: action_cursor_*, action_selection_mode,
      exit_selection_mode
    """

    HELP_TITLE = "Log Browser"
    HELP_CATEGORIES = {
        "toggle_live": "View",
    }

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("s", "selection_mode", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "toggle_live", "Live Mode"),
        Binding("question_mark", "show_help", "Help"),
        # Note: 'q' key is handled by BrowserContainer to switch back to document browser
    ]

    DEFAULT_CSS = """
    LogBrowser {
        layout: vertical;
        height: 100%;
    }

    .log-browser-content {
        layout: horizontal;
        height: 1fr;
    }

    #log-sidebar {
        width: 1fr;
        min-width: 50;
        height: 100%;
        layout: vertical;
    }

    #log-table-container {
        min-height: 15;
    }

    #log-details-container {
        min-height: 8;
        border-top: heavy $primary;
    }

    #log-table {
        width: 100%;
        border-right: solid $primary;
    }

    #log-preview-container {
        width: 1fr;
        min-width: 40;
        padding: 0 1;
    }

    #log-content {
        padding: 1;
    }

    .log-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executions: list[Execution] = []
        self.selection_mode = False
        self.current_stream: Optional[LogStream] = None
        self.is_live_mode = False
        self.stream_subscriber = LogBrowserSubscriber(self)

    def compose(self) -> ComposeResult:
        """Compose the log browser layout."""
        with Horizontal(classes="log-browser-content"):
            # Left sidebar (50% width) - contains table + details
            with Vertical(id="log-sidebar") as sidebar:
                # Apply direct styles for precise control
                sidebar.styles.width = "1fr"
                sidebar.styles.min_width = 50
                sidebar.styles.height = "100%"

                # Table container (2/3 of sidebar height)
                with Vertical(id="log-table-container") as table_container:
                    table_container.styles.height = "66%"
                    table_container.styles.min_height = 15
                    table_container.styles.padding = 0

                    table = DataTable(id="log-table")
                    table.cursor_type = "row"
                    table.show_header = True
                    yield table

                # Details container (1/3 of sidebar height)
                with Vertical(id="log-details-container") as details_container:
                    details_container.styles.height = "34%"
                    details_container.styles.min_height = 8
                    details_container.styles.padding = 0
                    details_container.styles.border_top = ("heavy", "gray")

                    yield RichLog(
                        id="log-details",
                        wrap=True,
                        markup=True,
                        auto_scroll=False
                    )

            # Right preview panel (50% width) - equal split
            with Vertical(id="log-preview-container") as preview_container:
                preview_container.styles.width = "1fr"
                preview_container.styles.min_width = 40
                preview_container.styles.padding = (0, 1)

                yield ScrollableContainer(
                    RichLog(id="log-content", wrap=True, highlight=True, markup=True,
                            auto_scroll=False),
                    id="log-preview"
                )

        # Status bar
        yield Static("Loading executions...", classes="log-status")

    async def on_mount(self) -> None:
        """Initialize the log browser."""
        logger.info("📋 LogBrowser mounted")

        # Set up the table
        table = self.query_one("#log-table", DataTable)
        table.add_column("", width=3)  # Status emoji column, no header
        table.add_column("Title", width=50)

        # Focus the table
        table.focus()

        # Load executions
        await self.load_executions()

    async def on_focus(self) -> None:
        """Refresh executions when the log browser gains focus."""
        logger.info("📋 LogBrowser focused - refreshing executions")
        await self.load_executions()

    async def on_unmount(self) -> None:
        """Clean up when unmounting."""
        logger.info("📋 LogBrowser unmounting")
        if self.current_stream:
            self.current_stream.unsubscribe(self.stream_subscriber)

    async def load_executions(self) -> None:
        """Load recent executions from the database."""
        try:
            self.executions = get_recent_executions(limit=50)

            if not self.executions:
                self.update_status("No executions found")
                return

            # Populate the table
            table = self.query_one("#log-table", DataTable)
            table.clear()

            for execution in self.executions:
                status_icon = {
                    'running': '🔄',
                    'completed': '✅',
                    'failed': '❌'
                }.get(execution.status, '❓')

                # Format title with ID prefix
                title_with_id = f"#{execution.id} - {execution.doc_title}"
                # Truncate if needed
                if len(title_with_id) > 47:
                    title_with_id = title_with_id[:44] + "..."

                table.add_row(
                    status_icon,
                    title_with_id
                )

            status_text = (
                f"📋 {len(self.executions)} executions | "
                "j/k=navigate | s=select | l=live | q=back"
            )
            self.update_status(status_text)

            # Load first execution if available
            if self.executions:
                await self.load_execution_log(self.executions[0])

        except Exception as e:
            logger.error(f"Error loading executions: {e}", exc_info=True)
            self.update_status(f"Error loading executions: {e}")

    async def load_execution_log(self, execution: Execution) -> None:
        """Load and display the log content using event-driven streaming."""
        try:
            # Update details panel with execution metadata
            await self.update_details_panel(execution)

            log_content = self.query_one("#log-content", RichLog)
            log_content.clear()

            # Stop current stream if any
            if self.current_stream:
                self.current_stream.unsubscribe(self.stream_subscriber)

            # Create new stream for this execution
            log_file = Path(execution.log_file)
            self.current_stream = LogStream(log_file)

            # Get initial content
            initial_content = self.current_stream.get_initial_content()

            if initial_content.strip():
                formatted_content = self._format_initial_content(initial_content, execution)
                for line in formatted_content.splitlines():
                    log_content.write(line)

                # Scroll position based on live mode
                if self.is_live_mode:
                    log_content.scroll_end(animate=False)
                else:
                    log_content.scroll_to(0, 0, animate=False)
            else:
                log_content.write("[dim](No log content yet)[/dim]")

            # Enable live streaming if in live mode
            if self.is_live_mode:
                self.current_stream.subscribe(self.stream_subscriber)

        except Exception as e:
            logger.error(f"Error loading execution log: {e}", exc_info=True)

    async def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the execution table."""
        row_idx = event.cursor_row
        if row_idx < len(self.executions):
            execution = self.executions[row_idx]
            await self.load_execution_log(execution)

            # Update status to show live mode hint for running executions
            if self.is_live_mode:
                self.update_status("🔴 LIVE MODE | l=toggle off | Event-driven streaming")
            elif execution.status == 'running' and not self.selection_mode:
                self.update_status("📋 Execution running | Press 'l' for live mode | q=back")

    async def action_refresh(self) -> None:
        """Refresh the execution list."""
        await self.load_executions()

    async def action_toggle_live(self) -> None:
        """Toggle live mode using event-driven streaming."""
        self.is_live_mode = not self.is_live_mode

        if self.is_live_mode:
            # Enable live streaming if we have a current stream
            if self.current_stream:
                self.current_stream.subscribe(self.stream_subscriber)
            self.update_status("🔴 LIVE MODE | l=toggle off | Event-driven streaming")
        else:
            # Disable live streaming
            if self.current_stream:
                self.current_stream.unsubscribe(self.stream_subscriber)
            self.update_status("📋 Live mode off | l=toggle on | q=back")
