"""Stuck indicator widget for displaying stuck document status.

A simple inline widget that can be used in lists or tables
to indicate when a document is stuck.
"""

import logging
from typing import Optional

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

logger = logging.getLogger(__name__)


class StuckIndicator(Widget):
    """Compact indicator for stuck documents.

    Shows:
    - ⚠️ Stuck (yellow) - document exceeds expected time
    - ❌ Failed (red) - last processing attempt failed
    - Nothing when document is processing normally
    """

    DEFAULT_CSS = """
    StuckIndicator {
        height: 1;
        width: auto;
        min-width: 8;
    }

    StuckIndicator .warning {
        color: $warning;
    }

    StuckIndicator .error {
        color: $error;
    }

    StuckIndicator .dim {
        color: $text-muted;
    }
    """

    # Reactive state
    status = reactive("normal")  # "normal", "stuck", "failed", "processing"
    elapsed_seconds = reactive(0.0)

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)

    def compose(self):
        yield Static("", id="indicator")

    def set_normal(self) -> None:
        """Set indicator to normal state."""
        self.status = "normal"
        self._update_display()

    def set_processing(self, elapsed: float = 0.0) -> None:
        """Set indicator to processing state.

        Args:
            elapsed: Time elapsed in seconds
        """
        self.status = "processing"
        self.elapsed_seconds = elapsed
        self._update_display()

    def set_stuck(self, elapsed: float = 0.0) -> None:
        """Set indicator to stuck state.

        Args:
            elapsed: Time elapsed in seconds
        """
        self.status = "stuck"
        self.elapsed_seconds = elapsed
        self._update_display()

    def set_failed(self, error_message: Optional[str] = None) -> None:
        """Set indicator to failed state.

        Args:
            error_message: Optional error message
        """
        self.status = "failed"
        self._error_message = error_message
        self._update_display()

    def _update_display(self) -> None:
        """Update the indicator display."""
        indicator = self.query_one("#indicator", Static)

        if self.status == "normal":
            indicator.update("")
        elif self.status == "processing":
            elapsed_str = self._format_short_duration(self.elapsed_seconds)
            indicator.update(f"[dim]⟳ {elapsed_str}[/dim]")
        elif self.status == "stuck":
            elapsed_str = self._format_short_duration(self.elapsed_seconds)
            indicator.update(f"[yellow]⚠️ Stuck ({elapsed_str})[/yellow]")
        elif self.status == "failed":
            indicator.update("[red]❌ Failed[/red]")

    def _format_short_duration(self, seconds: float) -> str:
        """Format duration in short form.

        Args:
            seconds: Duration in seconds

        Returns:
            Short string like "1m" or "23s"
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m"
        else:
            return f"{int(seconds // 3600)}h"

    def watch_status(self, status: str) -> None:
        """React to status changes."""
        self._update_display()


class StuckBadge(Widget):
    """A minimal badge version of the stuck indicator.

    Just shows a single character/emoji:
    - ⚠️ for stuck
    - ❌ for failed
    - ⟳ for processing
    - (empty) for normal
    """

    DEFAULT_CSS = """
    StuckBadge {
        height: 1;
        width: 2;
    }
    """

    status = reactive("normal")

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)

    def compose(self):
        yield Static("", id="badge")

    def set_status(self, status: str) -> None:
        """Set the badge status.

        Args:
            status: One of "normal", "processing", "stuck", "failed"
        """
        self.status = status
        self._update_display()

    def _update_display(self) -> None:
        """Update the badge display."""
        badge = self.query_one("#badge", Static)

        if self.status == "normal":
            badge.update("  ")
        elif self.status == "processing":
            badge.update("[dim]⟳[/dim]")
        elif self.status == "stuck":
            badge.update("[yellow]⚠[/yellow]")
        elif self.status == "failed":
            badge.update("[red]✗[/red]")

    def watch_status(self, status: str) -> None:
        """React to status changes."""
        self._update_display()
