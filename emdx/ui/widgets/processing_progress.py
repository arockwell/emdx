"""Processing progress widget for cascade stage transitions.

Shows real-time progress during cascade processing:
- Animated spinner
- Elapsed time counter
- ETA based on historical data
- Progress bar
- Optional output preview
"""

import logging
from typing import Optional

from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal

logger = logging.getLogger(__name__)


class ProcessingProgress(Widget):
    """Widget showing progress of an active cascade stage transition.

    Displays:
    ┌─────────────────────────────────────────┐
    │ ⟳ Processing: idea → prompt            │
    │ Elapsed: 1m 23s │ ETA: ~2m 30s         │
    │ ████████░░░░░░░░░░░░ 40%               │
    └─────────────────────────────────────────┘
    """

    DEFAULT_CSS = """
    ProcessingProgress {
        height: auto;
        min-height: 4;
        max-height: 6;
        background: $surface;
        border: solid $accent;
        padding: 0 1;
        display: none;
    }

    ProcessingProgress.active {
        display: block;
    }

    ProcessingProgress #progress-header {
        height: 1;
        width: 100%;
    }

    ProcessingProgress #progress-timing {
        height: 1;
        width: 100%;
        color: $text-muted;
    }

    ProcessingProgress #progress-bar {
        height: 1;
        width: 100%;
    }

    ProcessingProgress #progress-output {
        height: 1;
        width: 100%;
        color: $text-muted;
    }

    ProcessingProgress.stuck {
        border: solid $warning;
    }

    ProcessingProgress.stuck #progress-header {
        color: $warning;
    }
    """

    # Reactive properties
    is_processing = reactive(False)
    from_stage = reactive("")
    to_stage = reactive("")
    elapsed_seconds = reactive(0.0)
    estimated_total = reactive(0.0)
    is_stuck = reactive(False)
    output_preview = reactive("")
    doc_id = reactive(0)

    # Spinner frames for animation
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(
        self,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self._timer: Optional[Timer] = None
        self._spinner_idx = 0

    def compose(self):
        yield Static("", id="progress-header")
        yield Static("", id="progress-timing")
        yield Static("", id="progress-bar")
        yield Static("", id="progress-output")

    def start_processing(
        self,
        doc_id: int,
        from_stage: str,
        to_stage: str,
        estimated_seconds: Optional[float] = None,
    ) -> None:
        """Start showing progress for a processing operation.

        Args:
            doc_id: The document being processed
            from_stage: The source stage
            to_stage: The target stage
            estimated_seconds: Optional estimated total time
        """
        self.doc_id = doc_id
        self.from_stage = from_stage
        self.to_stage = to_stage
        self.elapsed_seconds = 0.0
        self.estimated_total = estimated_seconds or 0.0
        self.is_stuck = False
        self.output_preview = ""
        self.is_processing = True

        # Start the timer for updates
        self._timer = self.set_interval(1.0, self._tick)
        self.add_class("active")
        self._update_display()

    def stop_processing(self, success: bool = True) -> None:
        """Stop showing progress.

        Args:
            success: Whether the processing completed successfully
        """
        if self._timer:
            self._timer.stop()
            self._timer = None

        self.is_processing = False
        self.remove_class("active")
        self.remove_class("stuck")

    def set_output_preview(self, text: str) -> None:
        """Set the output preview text.

        Args:
            text: The preview text (typically last line of output)
        """
        # Truncate to reasonable length
        if len(text) > 60:
            text = text[:57] + "..."
        self.output_preview = text
        self._update_display()

    def mark_stuck(self, is_stuck: bool = True) -> None:
        """Mark the processing as stuck.

        Args:
            is_stuck: Whether the processing is stuck
        """
        self.is_stuck = is_stuck
        if is_stuck:
            self.add_class("stuck")
        else:
            self.remove_class("stuck")
        self._update_display()

    def _tick(self) -> None:
        """Called every second to update elapsed time."""
        self.elapsed_seconds += 1.0
        self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_FRAMES)

        # Check if stuck (exceeded estimated time by 2x)
        if self.estimated_total > 0 and not self.is_stuck:
            if self.elapsed_seconds > self.estimated_total * 2:
                self.mark_stuck(True)

        self._update_display()

    def _update_display(self) -> None:
        """Update all display elements."""
        header = self.query_one("#progress-header", Static)
        timing = self.query_one("#progress-timing", Static)
        bar = self.query_one("#progress-bar", Static)
        output = self.query_one("#progress-output", Static)

        if not self.is_processing:
            header.update("")
            timing.update("")
            bar.update("")
            output.update("")
            return

        # Header with spinner
        spinner = self.SPINNER_FRAMES[self._spinner_idx]
        if self.is_stuck:
            header.update(
                f"[yellow]⚠️ Stuck: {self.from_stage} → {self.to_stage}[/yellow] "
                f"[dim](doc #{self.doc_id})[/dim]"
            )
        else:
            header.update(
                f"[cyan]{spinner}[/cyan] Processing: "
                f"[bold]{self.from_stage}[/bold] → [bold]{self.to_stage}[/bold] "
                f"[dim](doc #{self.doc_id})[/dim]"
            )

        # Timing info
        elapsed_str = self._format_duration(self.elapsed_seconds)
        if self.estimated_total > 0:
            remaining = max(0, self.estimated_total - self.elapsed_seconds)
            if remaining > 0:
                eta_str = f"~{self._format_duration(remaining)}"
            else:
                eta_str = "[yellow]exceeded[/yellow]"
            timing.update(f"Elapsed: [bold]{elapsed_str}[/bold] │ ETA: {eta_str}")
        else:
            timing.update(f"Elapsed: [bold]{elapsed_str}[/bold] │ ETA: [dim]unknown[/dim]")

        # Progress bar
        bar_width = 30
        if self.estimated_total > 0:
            progress = min(1.0, self.elapsed_seconds / self.estimated_total)
            filled = int(bar_width * progress)
            empty = bar_width - filled
            pct = int(progress * 100)

            if self.is_stuck:
                bar_str = f"[yellow]{'█' * filled}{'░' * empty}[/yellow] {pct}%"
            elif progress >= 0.8:
                bar_str = f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim] {pct}%"
            else:
                bar_str = f"[cyan]{'█' * filled}[/cyan][dim]{'░' * empty}[/dim] {pct}%"
            bar.update(bar_str)
        else:
            # Indeterminate progress animation
            pos = int(self._spinner_idx / 2) % (bar_width - 3)
            bar_str = (
                "[dim]" + "░" * pos + "[/dim]"
                "[cyan]███[/cyan]"
                "[dim]" + "░" * (bar_width - pos - 3) + "[/dim]"
            )
            bar.update(bar_str)

        # Output preview
        if self.output_preview:
            output.update(f"[dim]{self.output_preview}[/dim]")
        else:
            output.update("")

    def _format_duration(self, seconds: float) -> str:
        """Format a duration in human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable string like "1m 23s"
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            if secs > 0:
                return f"{minutes}m {secs}s"
            return f"{minutes}m"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def watch_is_processing(self, is_processing: bool) -> None:
        """React to processing state changes."""
        if is_processing:
            self.add_class("active")
        else:
            self.remove_class("active")
            self.remove_class("stuck")
