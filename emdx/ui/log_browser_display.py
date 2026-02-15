#!/usr/bin/env python3
"""
Display mixin for LogBrowser.

Handles log content display, formatting, and status updates.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual.widgets import RichLog, Static

if TYPE_CHECKING:
    from emdx.services.execution_service import Execution

logger = logging.getLogger(__name__)


class LogBrowserDisplayMixin:
    """Mixin class for log display functionality in LogBrowser.

    Expects to be mixed into a Widget subclass with query_one, is_live_mode,
    and _filter_log_content methods available.
    """

    def format_execution_metadata(self, execution: "Execution") -> str:
        """Format execution metadata for details panel display."""
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

    async def update_details_panel(self, execution: "Execution") -> None:
        """Update the details panel with execution metadata."""
        try:
            details_panel = self.query_one("#log-details", RichLog)  # type: ignore[attr-defined]
            details_panel.clear()

            # Format and display metadata
            metadata_content = self.format_execution_metadata(execution)
            details_panel.write(metadata_content)

        except Exception as e:
            logger.error(f"Error updating details panel: {e}", exc_info=True)

    def _handle_log_content(self, new_content: str) -> None:
        """Handle new log content from stream."""
        try:
            if new_content:
                filtered_content = self._filter_log_content(new_content)  # type: ignore[attr-defined]
                if filtered_content.strip():
                    log_content = self.query_one("#log-content", RichLog)  # type: ignore[attr-defined]
                    log_content.write(filtered_content)

                    # Auto-scroll to bottom in live mode
                    if self.is_live_mode:  # type: ignore[attr-defined]
                        log_content.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error displaying new log content: {e}")

    def _handle_log_error(self, error: Exception) -> None:
        """Handle log streaming errors."""
        try:
            log_content = self.query_one("#log-content", RichLog)  # type: ignore[attr-defined]
            error_msg = f"❌ Log streaming error: {error}"
            log_content.write(error_msg)
            logger.error(f"Log streaming error: {error}")
        except Exception:
            pass

    def update_status(self, text: str) -> None:
        """Update the status bar."""
        try:
            status = self.query_one(".log-status", Static)  # type: ignore[attr-defined]
            status.update(text)
        except Exception:
            pass
