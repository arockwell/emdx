"""Centralized LIVE LOGS writer for all UI components.

This module provides a single, reusable utility for writing live log content
to RichLog widgets with proper stream-json parsing, timestamps, and formatting.

USAGE:
    from emdx.ui.live_log_writer import LiveLogWriter

    writer = LiveLogWriter(rich_log_widget)
    writer.write(content)  # Parses stream-json and formats with timestamps

This replaces scattered log handling code across:
- activity_view.py
- pulse_view.py
- log_content_writer.py
- work_browser.py
"""

import logging

from textual.widgets import RichLog

from emdx.ui.link_helpers import linkify_text
from emdx.utils.stream_json_parser import parse_and_format_live_logs

logger = logging.getLogger(__name__)


class LiveLogWriter:
    """Unified LIVE LOGS writer with stream-json parsing and formatting.

    This class handles all the complexity of parsing Claude's stream-json
    output format and displaying it with proper timestamps, tool info,
    and styling.

    Features:
    - Parses stream-json format from Claude CLI
    - Extracts and displays timestamps from StructuredLogger entries
    - Shows tool calls with names and input summaries
    - Handles text, status, and result events with appropriate styling
    - Optional line numbering
    - Auto-scrolling support
    """

    def __init__(
        self,
        log_output: RichLog,
        show_line_numbers: bool = False,
        auto_scroll: bool = True,
    ):
        """Initialize the live log writer.

        Args:
            log_output: The RichLog widget to write to
            show_line_numbers: Whether to prefix lines with numbers
            auto_scroll: Whether to auto-scroll to end after writes
        """
        self.log_output = log_output
        self.show_line_numbers = show_line_numbers
        self.auto_scroll = auto_scroll
        self.line_count = 0

    def write(self, content: str) -> None:
        """Write content with LIVE LOGS formatting.

        Parses stream-json format and displays with timestamps, tool info,
        and styling. This is the main method for live log streaming.

        Args:
            content: Raw log content (stream-json or plain text)
        """
        try:
            formatted_lines = parse_and_format_live_logs(content)
            for line in formatted_lines:
                self._write_line(line)

            if self.auto_scroll:
                self.log_output.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error writing live log content: {e}")
            # Fallback to raw content
            for line in content.splitlines():
                self._write_line(line)

    def write_raw(self, content: str) -> None:
        """Write content without parsing (for non-stream-json content).

        Args:
            content: Content to write as-is
        """
        for line in content.splitlines():
            self._write_line(line)

        if self.auto_scroll:
            self.log_output.scroll_end(animate=False)

    def write_status(self, message: str) -> None:
        """Write a status message with styling.

        Args:
            message: Status message to display
        """
        self._write_line(f"[bold blue]{message}[/bold blue]")

    def write_error(self, message: str) -> None:
        """Write an error message with styling.

        Args:
            message: Error message to display
        """
        self._write_line(f"[red]Error: {message}[/red]")

    def write_info(self, message: str) -> None:
        """Write an info message with dim styling.

        Args:
            message: Info message to display
        """
        self._write_line(f"[dim]{message}[/dim]")

    def write_header(self, header: str) -> None:
        """Write a styled header section.

        Args:
            header: Header text to display
        """
        self._write_line("")
        self._write_line(f"[bold cyan]═══ {header} ═══[/bold cyan]")
        self._write_line("")

    def clear(self) -> None:
        """Clear the log output and reset line count."""
        self.log_output.clear()
        self.line_count = 0

    def scroll_end(self, animate: bool = False) -> None:
        """Scroll to the end of the log.

        Args:
            animate: Whether to animate the scroll
        """
        self.log_output.scroll_end(animate=animate)

    def _write_line(self, line: str) -> None:
        """Write a single line with optional line numbering.

        Args:
            line: The line to write
        """
        self.line_count += 1
        if "http" in line:
            from rich.text import Text

            content = linkify_text(line)
            if self.show_line_numbers:
                prefix = Text.from_markup(f"[dim]{self.line_count:5}[/dim] ")
                prefix.append_text(content)
                self.log_output.write(prefix)
            else:
                self.log_output.write(content)
        elif self.show_line_numbers:
            self.log_output.write(f"[dim]{self.line_count:5}[/dim] {line}")
        else:
            self.log_output.write(line)
