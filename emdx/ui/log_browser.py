#!/usr/bin/env python3
"""
Standalone log browser widget for EMDX TUI.

This widget displays execution logs in a dual-pane layout:
- Left pane: Table of recent executions
- Right pane: Log content viewer with selection support
"""

import logging
import time
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.models.executions import Execution, get_recent_executions
from emdx.services.log_stream import LogStream, LogStreamSubscriber

from .text_areas import SelectionTextArea
from .log_parser import LogParser, LogEntry

logger = logging.getLogger(__name__)


class LogBrowserHost:
    """Host implementation for LogBrowser to work with SelectionTextArea."""

    def __init__(self, log_browser):
        self.log_browser = log_browser

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (called by SelectionTextArea)."""
        # Exit selection mode
        try:
            import asyncio
            asyncio.create_task(self.log_browser.exit_selection_mode())
        except Exception as e:
            logger.error(f"Error exiting selection mode: {e}")


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


class LogBrowser(Widget):
    """Log browser widget for viewing execution logs with event-driven streaming."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("s", "selection_mode", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "toggle_live", "Live Mode"),
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
        border-top: heavy gray;
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

    def format_execution_metadata(self, execution: Execution) -> str:
        """Format execution metadata for details panel display."""
        from pathlib import Path

        metadata_lines = []

        # Add worktree information if available (just the last part)
        if execution.working_dir:
            worktree_name = Path(execution.working_dir).name
            metadata_lines.append(f"[yellow]Worktree:[/yellow] {worktree_name}")

        # Add log file (just filename)
        log_filename = Path(execution.log_file).name
        metadata_lines.append(f"[yellow]Log:[/yellow] {log_filename}")

        # Add timing information
        metadata_lines.append("")
        metadata_lines.append(
            f"[yellow]Started:[/yellow] {execution.started_at.strftime('%H:%M:%S')}"
        )

        if execution.completed_at:
            metadata_lines.append(
                f"[yellow]Completed:[/yellow] {execution.completed_at.strftime('%H:%M:%S')}"
            )
            # Calculate duration
            duration = execution.completed_at - execution.started_at
            minutes = int(duration.total_seconds() // 60)
            seconds = int(duration.total_seconds() % 60)
            metadata_lines.append(f"[yellow]Duration:[/yellow] {minutes}m {seconds}s")

        # Add status
        status_icon = {
            'running': '🔄',
            'completed': '✅',
            'failed': '❌'
        }.get(execution.status, '❓')
        metadata_lines.append(f"[yellow]Status:[/yellow] {status_icon} {execution.status}")

        return "\n".join(metadata_lines)

    def _is_wrapper_noise(self, line: str) -> bool:
        """Check if a line is wrapper orchestration noise that should be filtered out."""
        if not line.strip():
            return False

        # Common wrapper patterns to filter out
        wrapper_patterns = [
            "🔄 Wrapper script started",
            "📋 Command:",
            "🚀 Starting Claude process...",
            "✅ Claude process finished",
            "📊 Updating execution status",
            "✅ Database updated successfully",
            "🔧 Background process started with PID:",
            "📄 Output is being written to this log file",
            "🔄 Wrapper will update status on completion",
            "📝 Prompt being sent to Claude:",
            "────────────────────────────────────────────────────────────",
        ]

        # Check for exact matches or patterns that start lines
        for pattern in wrapper_patterns:
            if pattern in line:
                return True

        # Filter out execution metadata lines
        if any(line.startswith(prefix) for prefix in [
            "⚡ Execution type:",
            "📋 Available tools:",
            "🔧 Background process",
            "📄 Output is being",
        ]):
            return True

        return False

    async def update_details_panel(self, execution: Execution) -> None:
        """Update the details panel with execution metadata."""
        try:
            details_panel = self.query_one("#log-details", RichLog)
            details_panel.clear()

            # Format and display metadata
            metadata_content = self.format_execution_metadata(execution)
            details_panel.write(metadata_content)

        except Exception as e:
            logger.error(f"Error updating details panel: {e}", exc_info=True)

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

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#log-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#log-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#log-table", DataTable)
        table.cursor_coordinate = (0, 0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.query_one("#log-table", DataTable)
        if self.executions:
            table.cursor_coordinate = (len(self.executions) - 1, 0)

    async def action_selection_mode(self) -> None:
        """Enter text selection mode."""
        if self.selection_mode:
            return

        self.selection_mode = True

        # Get current log content by re-reading the file
        # This is more reliable than trying to extract from RichLog
        content = ""
        try:
            table = self.query_one("#log-table", DataTable)
            row_idx = table.cursor_row
            if row_idx < len(self.executions):
                execution = self.executions[row_idx]
                log_file = Path(execution.log_file)
                if log_file.exists():
                    with open(log_file, encoding='utf-8', errors='replace') as f:
                        content = f.read()
        except Exception as e:
            logger.error(f"Error reading log for selection: {e}")
            content = "Error reading log content"

        # Replace log viewer with selection text area
        preview_container = self.query_one("#log-preview", ScrollableContainer)
        log_widget = self.query_one("#log-content", RichLog)
        await log_widget.remove()

        # Create LogBrowserHost instance for SelectionTextArea
        host = LogBrowserHost(self)
        selection_area = SelectionTextArea(
            host,
            content,
            id="log-selection",
            read_only=True
        )
        await preview_container.mount(selection_area)
        selection_area.focus()

        self.update_status("Selection Mode | Enter=copy | ESC=cancel")

    async def exit_selection_mode(self) -> None:
        """Exit selection mode and restore log viewer."""
        if not self.selection_mode:
            return

        self.selection_mode = False

        # Remove selection area and restore RichLog
        try:
            preview_container = self.query_one("#log-preview", ScrollableContainer)
            selection_area = self.query_one("#log-selection", SelectionTextArea)
            await selection_area.remove()

            # Re-mount RichLog widget with markup support
            log_widget = RichLog(id="log-content", wrap=True, highlight=True, markup=True,
                                 auto_scroll=False)
            await preview_container.mount(log_widget)

            # Reload the current execution's log
            table = self.query_one("#log-table", DataTable)
            row_idx = table.cursor_row
            if row_idx < len(self.executions):
                execution = self.executions[row_idx]
                await self.load_execution_log(execution)

            # Focus back to table
            table.focus()

        except Exception as e:
            logger.error(f"Error exiting selection mode: {e}")

        # Restore normal status
        status_text = (
            f"📋 {len(self.executions)} executions | "
            "j/k=navigate | s=select | q=back"
        )
        self.update_status(status_text)

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

    # Stream event handlers (called by LogBrowserSubscriber)
    def _handle_log_content(self, new_content: str) -> None:
        """Handle new log content from stream."""
        try:
            if new_content:
                filtered_content = self._filter_log_content(new_content)
                if filtered_content.strip():
                    log_content = self.query_one("#log-content", RichLog)
                    log_content.write(filtered_content)
                    
                    # Auto-scroll to bottom in live mode
                    if self.is_live_mode:
                        log_content.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error displaying new log content: {e}")

    def _handle_log_error(self, error: Exception) -> None:
        """Handle log streaming errors."""
        try:
            log_content = self.query_one("#log-content", RichLog)
            error_msg = f"❌ Log streaming error: {error}"
            log_content.write(error_msg)
            logger.error(f"Log streaming error: {error}")
        except Exception:
            pass

    def _filter_log_content(self, content: str) -> str:
        """Apply filtering to new content (without header formatting)."""
        lines = content.splitlines()
        filtered_lines = []
        
        for line in lines:
            # Skip wrapper orchestration messages
            if self._is_wrapper_noise(line):
                continue
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def _format_initial_content(self, content: str, execution: Execution) -> str:
        """Apply same filtering and formatting logic as current LogBrowser."""
        if not content.strip():
            return ""
        
        # Simple header - just the execution info
        lines = [f"[bold]Execution #{execution.id}[/bold] - {execution.doc_title}", ""]
        
        # Split content into header and log lines
        content_lines = content.splitlines()
        header_lines = []
        log_lines = []
        in_header = True

        for line in content_lines:
            if in_header and (
                line.startswith('=') or line.startswith('Version:') or
                line.startswith('Doc ID:') or line.startswith('Execution ID:') or
                line.startswith('Worktree:') or line.startswith('Started:') or
                line.startswith('Build ID:') or line.startswith('-')
            ):
                header_lines.append(line)
            else:
                in_header = False
                log_lines.append(line)

        # Extract prompt and filter out wrapper noise
        filtered_lines = []
        prompt_content = []
        in_prompt = False

        for line in log_lines:
            # Detect prompt section
            if "📝 Prompt being sent to Claude:" in line:
                in_prompt = True
                continue
            elif line.strip() == "─" * 60:
                if in_prompt:
                    in_prompt = False
                    continue
            elif in_prompt:
                prompt_content.append(line)
                continue

            # Skip wrapper orchestration messages
            if self._is_wrapper_noise(line):
                continue
            filtered_lines.append(line)

        # Show prompt first if we found one
        if prompt_content:
            lines.append("[bold blue]Prompt:[/bold blue]")
            for prompt_line in prompt_content:
                if prompt_line.strip():
                    lines.append(prompt_line)
            lines.append("")
            lines.append("[bold blue]Claude Response:[/bold blue]")

        # Add the filtered log content
        lines.extend(filtered_lines)
        
        return '\n'.join(lines)

    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)
            status.update(text)
        except Exception:
            pass

