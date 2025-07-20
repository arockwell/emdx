#!/usr/bin/env python3
"""
Standalone log browser widget for EMDX TUI.

This widget displays execution logs in a dual-pane layout:
- Left pane: Table of recent executions
- Right pane: Log content viewer with selection support
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, RichLog, Static

from emdx.models.executions import get_recent_executions, Execution

logger = logging.getLogger(__name__)


class LogSelectionTextArea(Static):
    """Text area for selecting and copying log content."""
    
    def __init__(self, log_browser, content: str, *args, **kwargs):
        super().__init__(content, *args, **kwargs)
        self.log_browser = log_browser
        self.can_focus = True
        
    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.log_browser.exit_selection_mode()
            event.stop()
        elif event.key == "enter":
            # Copy selection to clipboard
            try:
                # For now, copy entire content
                # TODO: Implement actual text selection
                subprocess.run(["pbcopy"], input=self.renderable.encode(), check=True)
                logger.info("Copied log content to clipboard")
            except Exception as e:
                logger.error(f"Failed to copy to clipboard: {e}")
            self.log_browser.exit_selection_mode()
            event.stop()


class LogBrowser(Widget):
    """Log browser widget for viewing execution logs."""
    
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("s", "selection_mode", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Back"),
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
    
    #log-table {
        width: 40%;
        min-width: 50;
        border-right: solid $primary;
    }
    
    #log-preview {
        width: 60%;
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
            # Execution list table
            table = DataTable(id="log-table")
            table.cursor_type = "row"
            table.show_header = True
            yield table
            
            # Log content preview
            yield ScrollableContainer(
                RichLog(id="log-content"),
                id="log-preview"
            )
            
        # Status bar
        yield Static("Loading executions...", classes="log-status")
        
    async def on_mount(self) -> None:
        """Initialize the log browser."""
        logger.info("📋 LogBrowser mounted")
        
        # Set up the table
        table = self.query_one("#log-table", DataTable)
        table.add_column("#", width=4)
        table.add_column("Status", width=10)
        table.add_column("Document", width=25)
        table.add_column("Started", width=8)
        
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
                
                table.add_row(
                    f"{i+1}",
                    f"{status_icon} {execution.status}",
                    execution.doc_title[:25] + "..." if len(execution.doc_title) > 25 else execution.doc_title,
                    execution.started_at.strftime("%H:%M")
                )
                
            self.update_status(f"📋 {len(self.executions)} executions | j/k=navigate | s=select | q=back")
            
            # Load first execution if available
            if self.executions:
                await self.load_execution_log(self.executions[0])
                
        except Exception as e:
            logger.error(f"Error loading executions: {e}", exc_info=True)
            self.update_status(f"Error loading executions: {e}")
            
    async def load_execution_log(self, execution: Execution) -> None:
        """Load and display the log content for the selected execution."""
        try:
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
                    # Add execution header
                    header = Text()
                    header.append(f"📋 Execution: {execution.doc_title}\n", style="bold cyan")
                    header.append(f"📅 Started: {execution.started_at}\n")
                    header.append(f"📊 Status: {execution.status}\n")
                    if execution.completed_at:
                        header.append(f"⏱️  Completed: {execution.completed_at}\n")
                    header.append(f"📁 Working Dir: {execution.working_dir}\n")
                    header.append(f"📄 Log File: {execution.log_file}\n")
                    header.append("─" * 60 + "\n", style="dim")
                    
                    log_content.write(header)
                    log_content.write(content)
                else:
                    log_content.write("⚠️ Log file is empty")
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
        
        # Get current log content
        log_widget = self.query_one("#log-content", RichLog)
        # Extract text content (simplified for now)
        content = "\n".join(str(line) for line in log_widget._lines)
        
        # Replace log viewer with selection text area
        preview_container = self.query_one("#log-preview", ScrollableContainer)
        await log_widget.remove()
        
        selection_area = LogSelectionTextArea(self, content, id="log-selection")
        await preview_container.mount(selection_area)
        selection_area.focus()
        
        self.update_status("Selection Mode | Enter=copy | ESC=cancel")
        
    def exit_selection_mode(self) -> None:
        """Exit selection mode and restore log viewer."""
        if not self.selection_mode:
            return
            
        self.selection_mode = False
        
        # Restore normal status
        self.update_status(f"📋 {len(self.executions)} executions | j/k=navigate | s=select | q=back")
        
        # We'll restore the log view on next mount
        # For now, just refresh
        self.refresh()
        
    async def action_refresh(self) -> None:
        """Refresh the execution list."""
        await self.load_executions()
        
    def action_quit(self) -> None:
        """Return to document browser."""
        # The container will handle the actual switching
        # We don't actually quit here - let the container handle 'q' key
        pass
            
    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)
            status.update(text)
        except:
            pass