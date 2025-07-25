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

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.models.executions import Execution, get_recent_executions

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


class LogBrowser(Widget):
    """Log browser widget for viewing execution logs."""

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
        self.live_mode = False
        self.refresh_timer = None
        self.last_log_size = 0

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
        self.stop_live_refresh()

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
        """Load and display the log content for the selected execution."""
        try:
            # Update details panel with execution metadata
            await self.update_details_panel(execution)

            log_content = self.query_one("#log-content", RichLog)
            log_content.clear()

            # Read log file content
            log_file = Path(execution.log_file)
            if log_file.exists():
                # Store file size for live refresh detection
                self.last_log_size = log_file.stat().st_size

                try:
                    with open(log_file, encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception as e:
                    logger.error(f"Error reading log file: {e}")
                    log_content.write(f"❌ Error reading log file: {e}")
                    return

                if content.strip():
                    # Simple header - just the execution info
                    header_text = f"[bold]Execution #{execution.id}[/bold] - {execution.doc_title}"
                    log_content.write(header_text)
                    log_content.write("")

                    # Split content into header and log lines
                    lines = content.splitlines()
                    header_lines = []
                    log_lines = []
                    in_header = True

                    for line in lines:
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
                        log_content.write("[bold blue]Prompt:[/bold blue]")
                        for prompt_line in prompt_content:
                            if prompt_line.strip():
                                log_content.write(prompt_line)
                        log_content.write("")
                        log_content.write("[bold blue]Claude Response:[/bold blue]")

                    # Show logs in chronological order (oldest first, newest last)
                    last_timestamp = None
                    for line in filtered_lines:
                        if not line.strip():
                            log_content.write(line)
                        else:
                            # Parse timestamp from log line if available
                            parsed_timestamp = parse_log_timestamp(line)
                            if parsed_timestamp:
                                last_timestamp = parsed_timestamp

                            # Use parsed timestamp or last known timestamp, fallback to current time
                            timestamp_to_use = parsed_timestamp or last_timestamp or time.time()

                            # Try to format JSON lines with emojis
                            formatted = format_claude_output(line, timestamp_to_use)
                            if formatted:
                                log_content.write(formatted)
                            else:
                                log_content.write(line)

                    # In live mode, scroll to bottom to see newest logs
                    # In normal mode, stay at top
                    if self.live_mode:
                        # Scroll to bottom
                        log_content.scroll_end(animate=False)
                    else:
                        # Stay at top
                        log_content.scroll_to(0, 0, animate=False)
                else:
                    log_content.write("[dim](No log content yet)[/dim]")
            else:
                log_content.write(f"❌ Log file not found: {execution.log_file}")

        except Exception as e:
            logger.error(f"Error loading execution log: {e}", exc_info=True)

    async def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the execution table."""
        row_idx = event.cursor_row
        if row_idx < len(self.executions):
            execution = self.executions[row_idx]
            await self.load_execution_log(execution)

            # Update status to show live mode hint for running executions
            if self.live_mode:
                self.update_status("🔴 LIVE MODE | l=toggle off | Auto-refresh every 1s")
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
        """Toggle live mode for auto-refreshing logs."""
        self.live_mode = not self.live_mode

        if self.live_mode:
            # Start auto-refresh timer
            self.start_live_refresh()
            self.update_status("🔴 LIVE MODE | l=toggle off | Auto-refresh every 1s")
        else:
            # Stop auto-refresh
            self.stop_live_refresh()
            # Refresh status based on current state
            if self.selection_mode:
                self.update_status("Selection Mode | Enter=copy | ESC=cancel")
            else:
                status_text = (
                f"📋 {len(self.executions)} executions | "
                "j/k=navigate | s=select | l=live | q=back"
            )
            self.update_status(status_text)

        # Reload current log with new ordering
        table = self.query_one("#log-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < len(self.executions):
            execution = self.executions[row_idx]
            await self.load_execution_log(execution)

    def start_live_refresh(self) -> None:
        """Start the auto-refresh timer for live mode."""
        if self.refresh_timer:
            self.refresh_timer.stop()

        # Refresh every 1 second
        self.refresh_timer = self.set_timer(1.0, self.live_refresh_log)

    def stop_live_refresh(self) -> None:
        """Stop the auto-refresh timer."""
        if self.refresh_timer:
            self.refresh_timer.stop()
            self.refresh_timer = None

    async def live_refresh_log(self) -> None:
        """Refresh the current log in live mode."""
        if not self.live_mode:
            return

        # Get current execution
        table = self.query_one("#log-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < len(self.executions):
            execution = self.executions[row_idx]

            # Check if file has grown
            log_file = Path(execution.log_file)
            if log_file.exists():
                current_size = log_file.stat().st_size
                if current_size != self.last_log_size:
                    self.last_log_size = current_size
                    await self.load_execution_log(execution)

        # Schedule next refresh
        if self.live_mode:
            self.refresh_timer = self.set_timer(1.0, self.live_refresh_log)


    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)
            status.update(text)
        except Exception:
            pass

