"""Timeline view - horizontal time-based task visualization for zoom 0."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from emdx.models import tasks
from emdx.models.executions import get_recent_executions, Execution

logger = logging.getLogger(__name__)

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


class TimelineBar(Static):
    """A horizontal bar representing a task/execution on the timeline."""

    DEFAULT_CSS = """
    TimelineBar {
        height: 1;
        min-width: 3;
    }

    TimelineBar.running {
        background: $success;
    }

    TimelineBar.completed {
        background: $primary;
    }

    TimelineBar.failed {
        background: $error;
    }

    TimelineBar.selected {
        border: tall $accent;
    }
    """

    def __init__(self, label: str, status: str, width: int):
        bar_char = "█" * max(width, 1)
        super().__init__(bar_char)
        self.add_class(status)


class TimelineSwimlane(Widget):
    """A single swimlane (row) in the timeline."""

    DEFAULT_CSS = """
    TimelineSwimlane {
        layout: horizontal;
        height: 2;
        margin-bottom: 1;
    }

    .swimlane-label {
        width: 20;
        padding: 0 1;
        text-align: right;
    }

    .swimlane-track {
        width: 1fr;
        height: 1;
        background: $surface;
    }
    """

    def __init__(self, label: str, item_id: int):
        super().__init__()
        self.label = label
        self.item_id = item_id
        self.bars: List[TimelineBar] = []

    def compose(self) -> ComposeResult:
        yield Static(self.label[:18], classes="swimlane-label")
        yield Horizontal(classes="swimlane-track", id=f"track-{self.item_id}")

    def add_bar(self, bar: TimelineBar) -> None:
        """Add a bar to this swimlane."""
        track = self.query_one(f"#track-{self.item_id}", Horizontal)
        track.mount(bar)
        self.bars.append(bar)


class TimelineView(Widget):
    """Timeline view showing tasks and executions over time."""

    BINDINGS = [
        Binding("j", "move_down", "Down"),
        Binding("k", "move_up", "Up"),
        Binding("h", "scroll_left", "Earlier"),
        Binding("l", "scroll_right", "Later"),
        Binding("t", "toggle_timespan", "Timespan"),
    ]

    DEFAULT_CSS = """
    TimelineView {
        layout: vertical;
        height: 100%;
    }

    .timeline-header {
        height: 1;
        background: $boost;
        padding: 0 1;
    }

    .timeline-axis {
        height: 1;
        padding: 0 21;
        color: $text-muted;
    }

    .timeline-content {
        height: 1fr;
    }

    .timeline-legend {
        height: 1;
        dock: bottom;
        padding: 0 1;
        color: $text-muted;
    }
    """

    timespan_hours = reactive(8)  # 4, 8, or 24 hours
    selected_index = reactive(0)

    def __init__(self):
        super().__init__()
        self.executions: List[Execution] = []
        self.swimlanes: List[TimelineSwimlane] = []

    def compose(self) -> ComposeResult:
        yield Static("📊 TIMELINE", classes="timeline-header")
        yield Static(self._make_axis(), classes="timeline-axis", id="axis")
        with ScrollableContainer(classes="timeline-content", id="content"):
            yield Static("[dim]Loading...[/dim]")
        yield Static(
            "████ running  ████ completed  ████ failed  |  t=timespan  h/l=scroll  j/k=select",
            classes="timeline-legend"
        )

    def _make_axis(self) -> str:
        """Generate the time axis string."""
        now = datetime.now()
        hours = self.timespan_hours

        # Create markers
        markers = []
        for i in range(0, hours + 1, max(1, hours // 8)):
            time = now - timedelta(hours=hours - i)
            markers.append(time.strftime("%H:%M"))

        # Distribute markers across ~60 chars
        width = 60
        spacing = width // len(markers)
        axis = ""
        for i, marker in enumerate(markers):
            if i == 0:
                axis = marker
            else:
                padding = spacing - len(marker)
                axis += " " * padding + marker

        return axis

    async def on_mount(self) -> None:
        """Load initial data."""
        await self.load_data()

    async def load_data(self) -> None:
        """Load executions and build timeline."""
        try:
            self.executions = get_recent_executions(limit=30)

            content = self.query_one("#content", ScrollableContainer)

            # Clear existing swimlanes
            for child in list(content.children):
                child.remove()
            self.swimlanes.clear()

            if not self.executions:
                await content.mount(Static("[dim]No recent executions[/dim]"))
                return

            # Group by doc_id to create swimlanes
            by_doc: Dict[int, List[Execution]] = {}
            for ex in self.executions:
                if ex.doc_id not in by_doc:
                    by_doc[ex.doc_id] = []
                by_doc[ex.doc_id].append(ex)

            # Create swimlanes
            for doc_id, execs in list(by_doc.items())[:15]:  # Limit to 15 rows
                title = execs[0].doc_title[:18] if execs else f"Doc #{doc_id}"
                swimlane = TimelineSwimlane(title, doc_id)
                self.swimlanes.append(swimlane)
                await content.mount(swimlane)

                # Add bars for each execution
                for ex in execs:
                    width = self._calc_bar_width(ex)
                    if width > 0:
                        bar = TimelineBar(ex.doc_title, ex.status, width)
                        swimlane.add_bar(bar)

            # Update axis
            axis = self.query_one("#axis", Static)
            axis.update(self._make_axis())

        except Exception as e:
            logger.error(f"Error loading timeline data: {e}", exc_info=True)

    def _calc_bar_width(self, execution: Execution) -> int:
        """Calculate bar width based on execution duration."""
        now = datetime.now(execution.started_at.tzinfo)
        timespan = timedelta(hours=self.timespan_hours)

        # Check if execution is within our timespan
        if execution.started_at < now - timespan:
            return 0

        # Calculate width (1 char = ~1% of timespan)
        if execution.completed_at:
            duration = (execution.completed_at - execution.started_at).total_seconds()
        else:
            # Running - extends to now
            duration = (now - execution.started_at).total_seconds()

        # Convert to chars (60 chars = full timespan)
        total_seconds = timespan.total_seconds()
        width = int((duration / total_seconds) * 60)
        return max(1, min(width, 60))

    def action_move_down(self) -> None:
        """Move selection down."""
        if self.selected_index < len(self.swimlanes) - 1:
            self.selected_index += 1

    def action_move_up(self) -> None:
        """Move selection up."""
        if self.selected_index > 0:
            self.selected_index -= 1

    def action_scroll_left(self) -> None:
        """Scroll timeline earlier (not implemented yet)."""
        pass

    def action_scroll_right(self) -> None:
        """Scroll timeline later (not implemented yet)."""
        pass

    def action_toggle_timespan(self) -> None:
        """Toggle between 4h, 8h, 24h timespan."""
        spans = [4, 8, 24]
        current_idx = spans.index(self.timespan_hours) if self.timespan_hours in spans else 0
        self.timespan_hours = spans[(current_idx + 1) % len(spans)]
        # Trigger reload
        self.call_later(self.load_data)

    def watch_timespan_hours(self, old: int, new: int) -> None:
        """React to timespan changes."""
        logger.info(f"Timespan changed: {old}h -> {new}h")
