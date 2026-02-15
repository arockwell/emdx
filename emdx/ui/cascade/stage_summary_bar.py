"""Stage summary bar widget for cascade browser."""

from typing import Any

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from emdx.services.cascade_service import get_cascade_stats

from .constants import STAGE_EMOJI, STAGES


class StageSummaryBar(Widget):
    """Compact bar showing all stages with counts and current selection."""

    DEFAULT_CSS = """
    StageSummaryBar {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    StageSummaryBar #stage-bar {
        height: 1;
        text-align: center;
    }

    StageSummaryBar #stage-detail {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    current_stage = reactive("idea")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.stats: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="stage-bar")
        yield Static("", id="stage-detail")

    def refresh_stats(self) -> None:
        """Refresh stage statistics."""
        self.stats = get_cascade_stats()
        self._update_display()

    def _update_display(self) -> None:
        """Update the display."""
        bar = self.query_one("#stage-bar", Static)
        detail = self.query_one("#stage-detail", Static)

        # Build stage bar with arrows
        parts = []
        for stage in STAGES:
            count = self.stats.get(stage, 0)
            emoji = STAGE_EMOJI.get(stage, "")

            if stage == self.current_stage:
                # Highlighted current stage
                parts.append(f"[bold reverse] {emoji} {stage.upper()} ({count}) [/]")
            elif count > 0:
                parts.append(f"[bold]{emoji} {stage}[/bold] ({count})")
            else:
                parts.append(f"[dim]{emoji} {stage} (0)[/dim]")

        bar.update(" \u2192 ".join(parts))

        # Show detail for current stage
        count = self.stats.get(self.current_stage, 0)
        if count > 0:
            detail.update(f"[bold]\u2190 h[/bold] prev stage \u2502 [bold]l \u2192[/bold] next stage \u2502 {count} document{'s' if count != 1 else ''} at {self.current_stage}")  # noqa: E501
        else:
            detail.update(f"[bold]\u2190 h[/bold] prev stage \u2502 [bold]l \u2192[/bold] next stage \u2502 No documents at {self.current_stage}")  # noqa: E501
