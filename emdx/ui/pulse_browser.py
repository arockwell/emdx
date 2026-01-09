"""Pulse+Zoom browser - workflow execution observer."""

import logging
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from .pulse.zoom1.outcomes_view import OutcomesView

logger = logging.getLogger(__name__)


class PulseBrowser(Widget):
    """Three-level zoom browser for observing workflow executions."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("z", "zoom_in", "Zoom In", priority=True),
        Binding("Z", "zoom_out", "Zoom Out", priority=True),
        Binding("enter", "zoom_in", "Select"),
        Binding("escape", "zoom_out", "Back", priority=True),
        Binding("0", "goto_zoom0", "Overview", priority=True),
        Binding("1", "goto_zoom1", "Focus", priority=True),
        Binding("2", "goto_zoom2", "Deep", priority=True),
        Binding("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    PulseBrowser {
        layout: vertical;
        height: 100%;
    }

    .zoom-container {
        height: 1fr;
    }

    #pulse-status {
        dock: bottom;
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    """

    zoom_level = reactive(0)

    def __init__(self):
        super().__init__()

        # Views
        self.pulse_view = None     # Zoom 0 - run list + preview
        self.outcomes_view = None  # Zoom 1 - extracted outcomes
        self.log_view = None       # Zoom 2 - full logs

        # Track selected run for zoom transitions
        self.selected_run: Optional[Dict[str, Any]] = None

        # Track selected stage for drill-down to logs
        self.selected_stage_name: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="zoom0", classes="zoom-container")
        yield Vertical(id="zoom1", classes="zoom-container")
        yield Vertical(id="zoom2", classes="zoom-container")
        yield Static("", id="pulse-status")

    async def on_mount(self) -> None:
        """Initialize the browser."""
        logger.info("PulseBrowser mounted")

        # Hide zoom 1 and 2 initially
        self.query_one("#zoom1").display = False
        self.query_one("#zoom2").display = False

        # Mount PulseView into zoom0 (run list + preview)
        from .pulse.zoom0.pulse_view import PulseView
        self.pulse_view = PulseView()
        await self.query_one("#zoom0").mount(self.pulse_view)

        # Mount OutcomesView into zoom1 (extracted results)
        from .pulse.zoom1.outcomes_view import OutcomesView
        self.outcomes_view = OutcomesView()
        await self.query_one("#zoom1").mount(self.outcomes_view)

        # Mount LogView into zoom2 (full logs)
        from .pulse.zoom2.log_view import LogView
        self.log_view = LogView()
        await self.query_one("#zoom2").mount(self.log_view)

        self._update_status()

    def on_outcomes_view_stage_selected(self, event: OutcomesView.StageSelected) -> None:
        """Handle stage selection from OutcomesView - drill down to stage logs."""
        logger.info(f"Stage selected: {event.stage_name}")
        self.selected_run = event.run
        self.selected_stage_name = event.stage_name
        self.zoom_level = 2

    def on_outcomes_view_individual_run_selected(self, event: OutcomesView.IndividualRunSelected) -> None:
        """Handle individual run selection - drill down to that specific run's logs."""
        logger.info(f"Individual run selected: {event.stage_name} run #{event.run_number}")
        self.selected_run = event.run
        self.selected_stage_name = event.stage_name
        # For now, just show the stage logs - we could filter further by run_number
        self.zoom_level = 2

    def watch_zoom_level(self, old_level: int, new_level: int) -> None:
        """React to zoom level changes."""
        logger.info(f"Zoom level changed: {old_level} -> {new_level}")

        # Hide all containers, show only current
        for i in range(3):
            container = self.query_one(f"#zoom{i}")
            container.display = (i == new_level)

        # Load data for new zoom level
        if new_level == 1 and self.outcomes_view and self.selected_run:
            self.call_later(lambda: self._show_run_outcomes())
        elif new_level == 2 and self.log_view and self.selected_run:
            self.call_later(lambda: self._show_run_logs())

        self._update_status()

    async def _show_run_outcomes(self) -> None:
        """Show outcomes for selected run."""
        if self.outcomes_view and self.selected_run:
            await self.outcomes_view.show_run(self.selected_run)

    async def _show_run_logs(self) -> None:
        """Show logs for selected run."""
        if self.log_view and self.selected_run:
            await self.log_view.load_workflow_run(
                self.selected_run,
                stage_name=self.selected_stage_name
            )

    def _update_status(self) -> None:
        """Update status bar."""
        zoom_names = ["Runs", "Outcomes", "Logs"]

        # Get quick stats
        stats_text = ""
        if self.pulse_view and hasattr(self.pulse_view, 'workflow_runs'):
            running = sum(1 for r in self.pulse_view.workflow_runs if r.get('status') == 'running')
            stats_text = f"Running: {running}"

        # Context-aware shortcuts
        if self.zoom_level == 0:
            shortcuts = "z/Enter=outcomes | r=refresh | q=back"
        elif self.zoom_level == 1:
            shortcuts = "z/Enter=full logs | Z/Esc=back | q=back"
        else:
            shortcuts = "Z/Esc=back | l=live | g/G=top/bottom | q=back"

        status_text = f"Zoom {self.zoom_level}: {zoom_names[self.zoom_level]} | {stats_text} | {shortcuts}"

        try:
            self.query_one("#pulse-status", Static).update(status_text)
        except Exception:
            pass

    def _get_selected_run(self) -> Optional[Dict[str, Any]]:
        """Get currently selected workflow run from pulse view."""
        if self.pulse_view:
            return self.pulse_view.get_selected_run()
        return None

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        if self.zoom_level == 0 and self.pulse_view:
            try:
                from textual.widgets import DataTable
                table = self.pulse_view.query_one("#runs-table", DataTable)
                table.action_cursor_down()
            except Exception as e:
                logger.error(f"Error in cursor_down: {e}")
        elif self.zoom_level == 1 and self.outcomes_view:
            try:
                from textual.widgets import DataTable
                # Try artifacts table first, then stages
                for table_id in ["#artifacts-table", "#stages-table"]:
                    try:
                        table = self.outcomes_view.query_one(table_id, DataTable)
                        if table.has_focus:
                            table.action_cursor_down()
                            return
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error in cursor_down: {e}")
        elif self.zoom_level == 2 and self.log_view:
            self.log_view.action_scroll_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self.zoom_level == 0 and self.pulse_view:
            try:
                from textual.widgets import DataTable
                table = self.pulse_view.query_one("#runs-table", DataTable)
                table.action_cursor_up()
            except Exception as e:
                logger.error(f"Error in cursor_up: {e}")
        elif self.zoom_level == 1 and self.outcomes_view:
            try:
                from textual.widgets import DataTable
                for table_id in ["#artifacts-table", "#stages-table"]:
                    try:
                        table = self.outcomes_view.query_one(table_id, DataTable)
                        if table.has_focus:
                            table.action_cursor_up()
                            return
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error in cursor_up: {e}")
        elif self.zoom_level == 2 and self.log_view:
            self.log_view.action_scroll_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        if self.zoom_level == 2 and self.log_view:
            self.log_view.action_scroll_home()

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        if self.zoom_level == 2 and self.log_view:
            self.log_view.action_scroll_end()

    def action_zoom_in(self) -> None:
        """Zoom in to more detail."""
        if self.zoom_level == 0:
            self.selected_run = self._get_selected_run()
            self.selected_stage_name = None  # Clear stage filter
            if self.selected_run:
                self.zoom_level = 1
            else:
                logger.info("No run selected")
        elif self.zoom_level == 1:
            # z from zoom1 shows ALL logs (no stage filter)
            # Enter on a stage shows just that stage's logs (via message handler)
            self.selected_stage_name = None
            self.zoom_level = 2

    def action_zoom_out(self) -> None:
        """Zoom out to less detail."""
        if self.zoom_level > 0:
            self.zoom_level -= 1

    def action_goto_zoom0(self) -> None:
        """Jump to zoom level 0."""
        self.zoom_level = 0

    def action_goto_zoom1(self) -> None:
        """Jump to zoom level 1."""
        if not self.selected_run:
            self.selected_run = self._get_selected_run()
        if self.selected_run:
            self.zoom_level = 1

    def action_goto_zoom2(self) -> None:
        """Jump to zoom level 2."""
        if not self.selected_run:
            self.selected_run = self._get_selected_run()
        if self.selected_run:
            self.zoom_level = 2

    async def action_refresh(self) -> None:
        """Refresh current view."""
        if self.zoom_level == 0 and self.pulse_view:
            await self.pulse_view.load_data()
        elif self.zoom_level == 1 and self.outcomes_view and self.selected_run:
            await self.outcomes_view.show_run(self.selected_run)
        elif self.zoom_level == 2 and self.log_view and self.selected_run:
            await self.log_view.load_workflow_run(self.selected_run)
        self._update_status()
