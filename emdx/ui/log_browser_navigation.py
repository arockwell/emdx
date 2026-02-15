#!/usr/bin/env python3
"""
Navigation mixin for LogBrowser.

Handles cursor navigation and selection mode for log content.
"""

import logging
from pathlib import Path
from typing import Any

from textual.containers import ScrollableContainer
from textual.widgets import DataTable, RichLog

from .text_areas import SelectionTextArea

logger = logging.getLogger(__name__)


class LogBrowserHost:
    """Host implementation for LogBrowser to work with SelectionTextArea."""

    def __init__(self, log_browser: Any) -> None:
        self.log_browser = log_browser

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (called by SelectionTextArea)."""
        # Exit selection mode
        try:
            import asyncio
            asyncio.create_task(self.log_browser.exit_selection_mode())
        except Exception as e:
            logger.error(f"Error exiting selection mode: {e}")


class LogBrowserNavigationMixin:
    """Mixin class for navigation functionality in LogBrowser."""

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
        table.cursor_coordinate = (0, 0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
        if self.executions:  # type: ignore[attr-defined]
            table.cursor_coordinate = (len(self.executions) - 1, 0)  # type: ignore[attr-defined]

    async def action_selection_mode(self) -> None:
        """Enter text selection mode."""
        if self.selection_mode:  # type: ignore[has-type]
            return

        self.selection_mode = True  # type: ignore[attr-defined]

        # Get current log content by re-reading the file
        # This is more reliable than trying to extract from RichLog
        content = ""
        try:
            table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
            row_idx = table.cursor_row
            if row_idx < len(self.executions):  # type: ignore[attr-defined]
                execution = self.executions[row_idx]  # type: ignore[attr-defined]
                log_file = Path(execution.log_file)
                if log_file.exists():
                    with open(log_file, encoding='utf-8', errors='replace') as f:
                        content = f.read()
        except Exception as e:
            logger.error(f"Error reading log for selection: {e}")
            content = "Error reading log content"

        # Replace log viewer with selection text area
        preview_container = self.query_one("#log-preview", ScrollableContainer)  # type: ignore[attr-defined]
        log_widget = self.query_one("#log-content", RichLog)  # type: ignore[attr-defined]
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

        self.update_status("Selection Mode | Enter=copy | ESC=cancel")  # type: ignore[attr-defined]

    async def exit_selection_mode(self) -> None:
        """Exit selection mode and restore log viewer."""
        if not self.selection_mode:  # type: ignore[attr-defined]
            return

        self.selection_mode = False  # type: ignore[attr-defined]

        # Remove selection area and restore RichLog
        try:
            preview_container = self.query_one("#log-preview", ScrollableContainer)  # type: ignore[attr-defined]
            selection_area = self.query_one("#log-selection", SelectionTextArea)  # type: ignore[attr-defined]
            await selection_area.remove()

            # Re-mount RichLog widget with markup support
            log_widget = RichLog(id="log-content", wrap=True, highlight=True, markup=True,
                                 auto_scroll=False)
            await preview_container.mount(log_widget)

            # Reload the current execution's log
            table = self.query_one("#log-table", DataTable)  # type: ignore[attr-defined]
            row_idx = table.cursor_row
            if row_idx < len(self.executions):  # type: ignore[attr-defined]
                execution = self.executions[row_idx]  # type: ignore[attr-defined]
                await self.load_execution_log(execution)  # type: ignore[attr-defined]

            # Focus back to table
            table.focus()

        except Exception as e:
            logger.error(f"Error exiting selection mode: {e}")

        # Restore normal status
        status_text = (
            f"📋 {len(self.executions)} executions | "  # type: ignore[attr-defined]
            "j/k=navigate | s=select | q=back"
        )
        self.update_status(status_text)  # type: ignore[attr-defined]
