"""Log view - Zoom 2 full-screen log viewer with streaming."""

import logging
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, RichLog

from emdx.models.executions import Execution, get_execution, get_recent_executions
from emdx.services.log_stream import LogStream, LogStreamSubscriber

from .log_content_writer import LogContentWriter
from .workflow_log_loader import WorkflowLogLoader

logger = logging.getLogger(__name__)


class LogViewSubscriber(LogStreamSubscriber):
    """Subscriber that forwards log content to the LogView."""

    def __init__(self, log_view: 'LogView'):
        self.log_view = log_view

    def on_log_content(self, new_content: str) -> None:
        """Called when new log content is available."""
        self.log_view._handle_new_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        """Called when log reading encounters an error."""
        self.log_view._handle_error(error)


class LogView(Widget):
    """Full-screen log viewer for Zoom 2."""

    BINDINGS = [
        Binding("j", "scroll_down", "Scroll Down"),
        Binding("k", "scroll_up", "Scroll Up"),
        Binding("g", "scroll_home", "Top"),
        Binding("G", "scroll_end", "Bottom"),
        Binding("l", "toggle_live", "Toggle Live"),
        Binding("slash", "search", "Search"),
        Binding("n", "next_match", "Next Match"),
        Binding("N", "prev_match", "Prev Match"),
    ]

    DEFAULT_CSS = """
    LogView {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #log-header {
        height: 1;
        background: $boost;
        padding: 0 1;
    }

    #log-output {
        height: 1fr;
        scrollbar-gutter: stable;
    }

    #log-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    is_live = reactive(True)
    search_query = reactive("")

    def __init__(self):
        super().__init__()
        self.current_execution: Optional[Execution] = None
        self.current_stream: Optional[LogStream] = None
        self.subscriber = LogViewSubscriber(self)
        self._writer: Optional[LogContentWriter] = None
        self._workflow_loader: Optional[WorkflowLogLoader] = None

    def compose(self) -> ComposeResult:
        yield Static("📜 LOG VIEWER", id="log-header")
        yield RichLog(id="log-output", highlight=True, markup=True, wrap=True)
        yield Static("", id="log-status")

    @property
    def writer(self) -> LogContentWriter:
        """Get the content writer, creating it if needed."""
        if self._writer is None:
            log_output = self.query_one("#log-output", RichLog)
            self._writer = LogContentWriter(log_output)
        return self._writer

    @property
    def workflow_loader(self) -> WorkflowLogLoader:
        """Get the workflow loader, creating it if needed."""
        if self._workflow_loader is None:
            self._workflow_loader = WorkflowLogLoader(self.writer)
        return self._workflow_loader

    async def on_mount(self) -> None:
        """Initialize the log viewer."""
        self._update_status()

    async def load_execution(self, exec_id: int) -> None:
        """Load logs for a specific execution."""
        try:
            execution = get_execution(str(exec_id))
            if not execution:
                self._show_error(f"Execution #{exec_id} not found")
                return

            await self._load_execution_logs(execution)

        except Exception as e:
            logger.error(f"Error loading execution {exec_id}: {e}", exc_info=True)
            self._show_error(str(e))

    async def load_latest(self) -> None:
        """Load the most recent execution's logs."""
        try:
            executions = get_recent_executions(limit=1)
            if executions:
                await self._load_execution_logs(executions[0])
            else:
                self._show_message("No executions found")
        except Exception as e:
            logger.error(f"Error loading latest execution: {e}", exc_info=True)
            self._show_error(str(e))

    async def load_workflow_run(
        self, run: Dict[str, Any], stage_name: Optional[str] = None
    ) -> None:
        """Load logs from a workflow run's context or individual execution logs."""
        # Stop current stream if any
        self._stop_stream()
        self.current_execution = None

        # Update header
        header = self.query_one("#log-header", Static)
        status = run.get('status', 'unknown')
        status_icon = WorkflowLogLoader._get_status_icon(status)
        header.update(f"📜 {status_icon} Run #{run['id']} - {stage_name or 'All Stages'}")

        # Load via workflow loader
        await self.workflow_loader.load_workflow_run(run, stage_name)
        self._update_status()

    async def _load_execution_logs(self, execution: Execution) -> None:
        """Load logs from an execution."""
        # Stop current stream if any
        self._stop_stream()

        self.current_execution = execution
        self.writer.clear()

        # Update header
        self._update_header_for_execution(execution)

        # Check if log file exists
        log_path = execution.log_path
        if not log_path.exists():
            self._show_message(f"Log file not found: {log_path}")
            return

        # Create stream and get initial content
        self.current_stream = LogStream(log_path)
        initial_content = self.current_stream.get_initial_content()

        if initial_content:
            self.writer.write_content(initial_content)

        # Subscribe for live updates if in live mode and execution is running
        if self.is_live and execution.is_running:
            self.current_stream.subscribe(self.subscriber)

        self._update_status()

    def _stop_stream(self) -> None:
        """Stop and clean up the current stream."""
        if self.current_stream:
            self.current_stream.unsubscribe(self.subscriber)
            self.current_stream = None

    def _update_header_for_execution(self, execution: Execution) -> None:
        """Update header for an execution."""
        header = self.query_one("#log-header", Static)
        status_icon = (
            "🔄" if execution.is_running
            else ("✅" if execution.status == 'completed' else "❌")
        )
        header.update(f"📜 {status_icon} {execution.doc_title} (#{execution.id})")

    def _handle_new_content(self, new_content: str) -> None:
        """Handle new content from the log stream."""
        if new_content:
            self.writer.write_content(new_content)
            self._update_status()

            # Auto-scroll to bottom if in live mode
            if self.is_live:
                self.writer.scroll_end(animate=False)

    def _handle_error(self, error: Exception) -> None:
        """Handle an error from the log stream."""
        logger.error(f"Log stream error: {error}")
        self.writer.write_error(str(error))

    def _show_error(self, message: str) -> None:
        """Show an error message."""
        self.writer.clear()
        self.writer.write_error(message)
        self._update_status()

    def _show_message(self, message: str) -> None:
        """Show an info message."""
        self.writer.clear()
        self.writer.write_info(message)
        self._update_status()

    def _update_status(self) -> None:
        """Update the status bar."""
        status = self.query_one("#log-status", Static)

        parts = []

        # Execution info
        if self.current_execution:
            parts.append(f"Exec #{self.current_execution.id}")
            parts.append(self.current_execution.status)

        # Line count
        parts.append(f"{self.writer.line_count} lines")

        # Live mode indicator
        if self.is_live:
            parts.append("[green]● LIVE[/green]")
        else:
            parts.append("[yellow]⏸ PAUSED[/yellow]")

        # Shortcuts
        parts.append("l=toggle live | g/G=top/bottom | /=search")

        status.update(" | ".join(parts))

    def action_scroll_down(self) -> None:
        """Scroll down."""
        log_output = self.query_one("#log-output", RichLog)
        log_output.scroll_down()

    def action_scroll_up(self) -> None:
        """Scroll up."""
        log_output = self.query_one("#log-output", RichLog)
        log_output.scroll_up()

    def action_scroll_home(self) -> None:
        """Scroll to top."""
        log_output = self.query_one("#log-output", RichLog)
        log_output.scroll_home()

    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        log_output = self.query_one("#log-output", RichLog)
        log_output.scroll_end()

    def action_toggle_live(self) -> None:
        """Toggle live mode."""
        self.is_live = not self.is_live

        if self.current_stream and self.current_execution:
            if self.is_live and self.current_execution.is_running:
                self.current_stream.subscribe(self.subscriber)
            else:
                self.current_stream.unsubscribe(self.subscriber)

        self._update_status()

    def action_search(self) -> None:
        """Start search (placeholder)."""
        # TODO: Implement search input
        pass

    def action_next_match(self) -> None:
        """Go to next search match (placeholder)."""
        pass

    def action_prev_match(self) -> None:
        """Go to previous search match (placeholder)."""
        pass

    def watch_is_live(self, old: bool, new: bool) -> None:
        """React to live mode changes."""
        logger.info(f"Live mode: {old} -> {new}")

    def clear(self) -> None:
        """Clear the log viewer."""
        self._stop_stream()
        self.current_execution = None
        self.writer.clear()

        header = self.query_one("#log-header", Static)
        header.update("📜 LOG VIEWER")

        self._update_status()

    def on_unmount(self) -> None:
        """Clean up when unmounting."""
        self._stop_stream()
