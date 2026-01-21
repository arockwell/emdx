"""Log content writer - handles writing content to RichLog with line numbers.

LIVE LOGS: Delegates to LiveLogWriter for proper timestamp and tool formatting.
"""

from textual.widgets import RichLog


class LogContentWriter:
    """Handles writing log content to a RichLog widget with line numbering.

    LIVE LOGS: Delegates to LiveLogWriter for stream-json parsing and formatting.
    """

    def __init__(self, log_output: RichLog):
        from emdx.ui.live_log_writer import LiveLogWriter

        self.log_output = log_output
        self.line_count = 0
        # Use LiveLogWriter with line numbers enabled
        self._writer = LiveLogWriter(log_output, show_line_numbers=True, auto_scroll=False)

    def write_content(self, content: str) -> None:
        """Write content to the log output with LIVE LOGS formatting.

        Delegates to LiveLogWriter for stream-json parsing and formatting.
        """
        self._writer.write(content)
        self.line_count = self._writer.line_count

    def write_raw(self, content: str) -> None:
        """Write content without parsing."""
        self._writer.write_raw(content)
        self.line_count = self._writer.line_count

    def write_header(self, header: str) -> None:
        """Write a styled header section."""
        self._writer.write_header(header)
        self.line_count = self._writer.line_count

    def write_error(self, message: str) -> None:
        """Write an error message."""
        self._writer.write_error(message)
        self.line_count = self._writer.line_count

    def write_info(self, message: str) -> None:
        """Write an info/dim message."""
        self._writer.write_info(message)
        self.line_count = self._writer.line_count

    def clear(self) -> None:
        """Clear the log output and reset line count."""
        self._writer.clear()
        self.line_count = 0

    def scroll_end(self, animate: bool = False) -> None:
        """Scroll to the end of the log."""
        self._writer.scroll_end(animate=animate)
