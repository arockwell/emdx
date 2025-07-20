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
        table.add_column("#", width=6)
        table.add_column("Title", width=45)
        
        # Focus the table
        table.focus()
        
        # Load executions
        await self.load_executions()
        
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
                
                # Combine ID and status in a compact format
                id_with_status = f"{status_icon}{execution.id}"
                
                table.add_row(
                    id_with_status,
                    execution.doc_title[:40] + "..." if len(execution.doc_title) > 40 else execution.doc_title
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
        try:
            # Try to get version info, fallback to default if not available
            from emdx import __version__
            version = __version__
        except:
            version = "0.6.0"
        
        try:
            from emdx import __build_id__
            build_id = __build_id__
        except:
            build_id = "unknown"
        
        # Build metadata sections
        metadata_lines = [
            "[bold cyan]=== EMDX Claude Execution ===[/bold cyan]",
            f"[yellow]Version:[/yellow] {version}",
            f"[yellow]Build ID:[/yellow] {build_id}",
            f"[yellow]Doc ID:[/yellow] {execution.doc_id if hasattr(execution, 'doc_id') else 'N/A'}",
            f"[yellow]Execution ID:[/yellow] {execution.id}",
            ""
        ]
        
        # Add worktree information if available
        if execution.working_dir:
            metadata_lines.extend([
                f"[yellow]Worktree:[/yellow] {execution.working_dir}",
                ""
            ])
        
        # Add timing information
        started_str = execution.started_at.strftime('%Y-%m-%d %H:%M:%S')
        metadata_lines.append(f"[yellow]Started:[/yellow] {started_str}")
        
        if execution.completed_at:
            completed_str = execution.completed_at.strftime('%Y-%m-%d %H:%M:%S')
            metadata_lines.append(f"[yellow]Completed:[/yellow] {completed_str}")
        
        # Add status and exit code
        status_icon = {
            'running': '🔄',
            'completed': '✅',
            'failed': '❌'
        }.get(execution.status, '❓')
        
        metadata_lines.extend([
            "",
            f"[yellow]Status:[/yellow] {status_icon} {execution.status}",
        ])
        
        # Add file paths
        metadata_lines.extend([
            "",
            f"[yellow]Log File:[/yellow] {execution.log_file}",
        ])
        
        metadata_lines.append("[bold cyan]" + "=" * 50 + "[/bold cyan]")
        
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
                    # Add execution header with rich formatting
                    log_content.write("[bold cyan]=== Execution {} ===[/bold cyan]".format(execution.id))
                    log_content.write("[yellow]Document:[/yellow] {}".format(execution.doc_title))
                    log_content.write("[yellow]Status:[/yellow] {}".format(execution.status))
                    log_content.write("[yellow]Started:[/yellow] {}".format(
                        execution.started_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')))
                    if execution.completed_at:
                        log_content.write("[yellow]Completed:[/yellow] {}".format(
                            execution.completed_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')))
                    log_content.write("[yellow]Working Dir:[/yellow] {}".format(execution.working_dir))
                    log_content.write("[yellow]Log File:[/yellow] {}".format(execution.log_file))
                    log_content.write("[bold cyan]=== Log Output ===[/bold cyan]")
                    log_content.write("")
                    
                    # Process log content to format JSON lines with emojis
                    for line in content.splitlines():
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
                    
                    # Scroll to top so users see the beginning of the log
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
        
            
    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)
            status.update(text)
        except:
            pass