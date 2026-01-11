"""Log content writer - handles writing content to RichLog with line numbers."""

from textual.widgets import RichLog


class LogContentWriter:
    """Handles writing log content to a RichLog widget with line numbering."""

    def __init__(self, log_output: RichLog):
        self.log_output = log_output
        self.line_count = 0

    def write_content(self, content: str) -> None:
        """Write content to the log output with line numbers."""
        for line in content.splitlines():
            self.line_count += 1
            self.log_output.write(f"[dim]{self.line_count:5}[/dim] {line}")

    def write_raw(self, content: str) -> None:
        """Write content without line numbers."""
        self.log_output.write(content)
        self.line_count += 1

    def write_header(self, header: str) -> None:
        """Write a styled header section."""
        self.log_output.write(f"\n[bold cyan]═══ {header} ═══[/bold cyan]\n")
        self.line_count += 2

    def write_error(self, message: str) -> None:
        """Write an error message."""
        self.log_output.write(f"[red]Error: {message}[/red]")
        self.line_count += 1

    def write_info(self, message: str) -> None:
        """Write an info/dim message."""
        self.log_output.write(f"[dim]{message}[/dim]")
        self.line_count += 1

    def clear(self) -> None:
        """Clear the log output and reset line count."""
        self.log_output.clear()
        self.line_count = 0

    def scroll_end(self, animate: bool = False) -> None:
        """Scroll to the end of the log."""
        self.log_output.scroll_end(animate=animate)
