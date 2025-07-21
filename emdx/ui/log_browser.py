#!/usr/bin/env python3
"""
Standalone log browser widget for EMDX TUI.

This widget displays execution logs in a dual-pane layout:
- Left pane: Table of recent executions
- Right pane: Log content viewer with selection support
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.commands.claude_execute import format_claude_output
from emdx.models.executions import get_recent_executions, Execution
from .text_areas import SelectionTextArea

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
        self.executions: List[Execution] = []
        self.selection_mode = False
        self.current_execution: Optional[Execution] = None
        self.refresh_timer = None
        self.current_prompt = None
        self.current_tools = None
        
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
                    RichLog(id="log-content", wrap=True, highlight=True, markup=True, auto_scroll=False),
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
        
        # Start auto-refresh timer for log content
        self.set_interval(2.0, self._auto_refresh_log)
        
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
            
            for i, execution in enumerate(self.executions):
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
                
            self.update_status(f"📋 {len(self.executions)} executions | j/k=navigate | s=select | q=back")
            
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
        
        # Add basic metadata
        metadata_lines.append(f"[yellow]Status:[/yellow] {'🔄' if execution.status == 'running' else '✅' if execution.status == 'completed' else '❌'} {execution.status}")
        metadata_lines.append(f"[yellow]Started:[/yellow] {execution.started_at.strftime('%H:%M:%S')}")
        
        if execution.completed_at:
            duration = execution.completed_at - execution.started_at
            minutes = int(duration.total_seconds() // 60)
            seconds = int(duration.total_seconds() % 60)
            metadata_lines.append(f"[yellow]Duration:[/yellow] {minutes}m {seconds}s")
        
        # Add prompt from log file if available
        if self.current_prompt:
            metadata_lines.append("")
            metadata_lines.append("[bold cyan]=== Prompt ===[/bold cyan]")
            metadata_lines.append(self.current_prompt)
        
        # Add tools if available
        if self.current_tools:
            metadata_lines.append("")
            metadata_lines.append("[bold cyan]=== Available Tools ===[/bold cyan]")
            metadata_lines.append(self.current_tools)
        
        return "\n".join(metadata_lines)
    
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
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                except Exception as e:
                    logger.error(f"Error reading log file: {e}")
                    log_content.write(f"❌ Error reading log file: {e}")
                    return
                    
                if content.strip():
                    # Extract prompt and tools from log for display in details panel
                    self.extract_prompt_and_tools(content, execution)
                    
                    # Process lines in reverse order (latest first) and filter out prompt/tools
                    lines = content.splitlines()
                    filtered_lines = []
                    skip_until_line = None
                    
                    for i, line in enumerate(lines):
                        # Skip prompt section
                        if "📝 Prompt being sent to Claude:" in line:
                            skip_until_line = i + 1
                            # Find end of prompt section (look for dashes)
                            while skip_until_line < len(lines):
                                if lines[skip_until_line].strip().startswith("─"):
                                    skip_until_line += 1
                                    break
                                skip_until_line += 1
                            continue
                        
                        # Skip lines within prompt section
                        if skip_until_line and i < skip_until_line:
                            continue
                        
                        # Skip tools line
                        if "📋 Available tools:" in line:
                            continue
                            
                        # Add other lines
                        if skip_until_line and i >= skip_until_line:
                            skip_until_line = None
                        filtered_lines.append(line)
                    
                    # Write lines in reverse order (latest first)
                    for line in reversed(filtered_lines):
                        # Skip header lines and non-JSON lines
                        if (line.startswith('=') or line.startswith('-') or 
                            line.startswith('Version:') or line.startswith('Doc ID:') or 
                            line.startswith('Execution ID:') or line.startswith('Worktree:') or 
                            line.startswith('Started:') or not line.strip()):
                            log_content.write(line)
                        else:
                            # Try to format JSON lines with emojis
                            formatted = format_claude_output(line, time.time())
                            if formatted:
                                log_content.write(formatted)
                            else:
                                log_content.write(line)
                    
                    # Scroll to top to see latest messages
                    log_content.scroll_to(0, 0, animate=False)
                else:
                    log_content.write("[dim](No log content yet)[/dim]")
            else:
                log_content.write(f"❌ Log file not found: {execution.log_file}")
                
        except Exception as e:
            logger.error(f"Error loading execution log: {e}", exc_info=True)
    
    def extract_prompt_and_tools(self, content: str, execution: Execution) -> None:
        """Extract prompt and tools from log content."""
        lines = content.splitlines()
        
        # Reset
        self.current_prompt = None
        self.current_tools = None
        
        # Look for prompt
        for i, line in enumerate(lines):
            if "📝 Prompt being sent to Claude:" in line:
                # Extract prompt content
                prompt_lines = []
                j = i + 1
                # Skip dashes
                while j < len(lines) and lines[j].strip().startswith("─"):
                    j += 1
                # Collect prompt until we hit dashes again
                while j < len(lines) and not lines[j].strip().startswith("─"):
                    prompt_lines.append(lines[j])
                    j += 1
                self.current_prompt = "\n".join(prompt_lines).strip()
            
            # Look for tools
            if "📋 Available tools:" in line:
                # Extract tools from the line
                tools_part = line.split("📋 Available tools:")[-1].strip()
                self.current_tools = tools_part
            
    async def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the execution table."""
        row_idx = event.cursor_row
        if row_idx < len(self.executions):
            execution = self.executions[row_idx]
            self.current_execution = execution
            await self.load_execution_log(execution)
            
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
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
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
            log_widget = RichLog(id="log-content", wrap=True, highlight=True, markup=True, auto_scroll=False)
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
        self.update_status(f"📋 {len(self.executions)} executions | j/k=navigate | s=select | q=back")
        
    async def action_refresh(self) -> None:
        """Refresh the execution list."""
        await self.load_executions()
    
    async def _auto_refresh_log(self) -> None:
        """Auto-refresh the current log content if execution is running."""
        if not self.current_execution or self.selection_mode:
            return
            
        # Check the latest execution status from database
        from emdx.models.executions import get_execution
        latest_execution = get_execution(self.current_execution.id)
        if latest_execution:
            self.current_execution = latest_execution
            
            # Update the execution in the list too
            for i, exec in enumerate(self.executions):
                if exec.id == latest_execution.id:
                    self.executions[i] = latest_execution
                    break
        
        # Only refresh if the execution is still running
        if self.current_execution.status == "running":
            try:
                # Get the latest content from the log file
                log_file = Path(self.current_execution.log_file)
                if log_file.exists():
                    log_content_widget = self.query_one("#log-content", RichLog)
                    
                    # Get current scroll position to restore it
                    current_scroll = log_content_widget.scroll_offset
                    
                    # Read new content
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    if content.strip():
                        # Extract prompt and tools for details panel
                        self.extract_prompt_and_tools(content, self.current_execution)
                        await self.update_details_panel(self.current_execution)
                        
                        # Clear and rewrite content
                        log_content_widget.clear()
                        
                        # Process lines in reverse order (latest first) and filter out prompt/tools
                        lines = content.splitlines()
                        filtered_lines = []
                        skip_until_line = None
                        
                        for i, line in enumerate(lines):
                            # Skip prompt section
                            if "📝 Prompt being sent to Claude:" in line:
                                skip_until_line = i + 1
                                while skip_until_line < len(lines):
                                    if lines[skip_until_line].strip().startswith("─"):
                                        skip_until_line += 1
                                        break
                                    skip_until_line += 1
                                continue
                            
                            # Skip lines within prompt section
                            if skip_until_line and i < skip_until_line:
                                continue
                            
                            # Skip tools line
                            if "📋 Available tools:" in line:
                                continue
                                
                            # Add other lines
                            if skip_until_line and i >= skip_until_line:
                                skip_until_line = None
                            filtered_lines.append(line)
                        
                        # Write lines in reverse order (latest first)
                        for line in reversed(filtered_lines):
                            if (line.startswith('=') or line.startswith('-') or 
                                line.startswith('Version:') or line.startswith('Doc ID:') or 
                                line.startswith('Execution ID:') or line.startswith('Worktree:') or 
                                line.startswith('Started:') or not line.strip()):
                                log_content_widget.write(line)
                            else:
                                formatted = format_claude_output(line, time.time())
                                if formatted:
                                    log_content_widget.write(formatted)
                                else:
                                    log_content_widget.write(line)
                        
                        # Stay at top to see latest messages
                        log_content_widget.scroll_to(0, 0, animate=False)
                        
            except Exception as e:
                logger.debug(f"Error during auto-refresh: {e}")
        
            
    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)
            status.update(text)
        except:
            pass