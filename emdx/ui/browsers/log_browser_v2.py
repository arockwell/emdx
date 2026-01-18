"""
LogBrowserV2 - Panel-based log browser demonstrating the new architecture.

This browser shows execution logs using the reusable panel components,
achieving the same functionality as LogBrowser in ~100 lines of code.

Features:
- ListPanel for execution list with vim navigation
- PreviewPanel for log content viewing
- Live mode with log streaming
- Log content filtering
"""

import logging
from pathlib import Path
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget

from emdx.models.executions import Execution, get_recent_executions
from emdx.services.log_stream import LogStream, LogStreamSubscriber

from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
)

logger = logging.getLogger(__name__)


class LogBrowserV2(Widget):
    """Panel-based log browser for viewing execution logs.

    Uses ListPanel and PreviewPanel for a clean, maintainable implementation.
    """

    DEFAULT_CSS = """
    LogBrowserV2 {
        layout: horizontal;
        height: 100%;
    }

    LogBrowserV2 #log-list {
        width: 40%;
        min-width: 40;
    }

    LogBrowserV2 #log-preview {
        width: 60%;
        min-width: 50;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("l", "toggle_live", "Live Mode", show=True),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executions: list[Execution] = []
        self.current_stream: Optional[LogStream] = None
        self.is_live_mode = False
        self._stream_subscriber = _LogStreamHandler(self)

    def compose(self) -> ComposeResult:
        """Compose the browser layout with panels."""
        yield ListPanel(
            columns=[
                ColumnDef("", width=3),  # Status emoji
                ColumnDef("Execution", width=50),
            ],
            config=ListPanelConfig(
                show_search=True,
                search_placeholder="Search executions...",
                status_format="{filtered}/{total} executions",
            ),
            show_status=True,
            id="log-list",
        )

        yield PreviewPanel(
            config=PreviewPanelConfig(
                enable_editing=False,
                enable_selection=True,
                markdown_rendering=False,  # Log content is plain text
                empty_message="Select an execution to view logs",
            ),
            id="log-preview",
        )

    async def on_mount(self) -> None:
        """Load executions on mount."""
        await self._load_executions()

    async def on_unmount(self) -> None:
        """Clean up stream on unmount."""
        self._cleanup_stream()

    async def _load_executions(self) -> None:
        """Load recent executions into the list."""
        self.executions = get_recent_executions(limit=50)

        items = [
            ListItem(
                id=ex.id,
                values=[
                    {"running": "🔄", "completed": "✅", "failed": "❌"}.get(ex.status, "❓"),
                    f"#{ex.id} - {ex.doc_title[:44]}{'...' if len(ex.doc_title) > 44 else ''}",
                ],
                data={"execution": ex},
            )
            for ex in self.executions
        ]

        list_panel = self.query_one("#log-list", ListPanel)
        list_panel.set_items(items)

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Load log content when execution is selected."""
        execution = event.item.data["execution"]
        await self._load_log_content(execution)

    async def _load_log_content(self, execution: Execution) -> None:
        """Load and display log content for an execution."""
        self._cleanup_stream()

        preview = self.query_one("#log-preview", PreviewPanel)
        log_path = Path(execution.log_file)

        if not log_path.exists():
            await preview.show_content(f"Log file not found: {log_path}")
            return

        # Create stream and get initial content
        self.current_stream = LogStream(log_path)
        content = self.current_stream.get_initial_content()

        # Format content with header and filtering
        formatted = self._format_log_content(execution, content)
        await preview.show_content(formatted, title=f"Execution #{execution.id}")

        # Enable live streaming if in live mode
        if self.is_live_mode:
            self.current_stream.subscribe(self._stream_subscriber)

    def _format_log_content(self, execution: Execution, content: str) -> str:
        """Format log content with header and noise filtering."""
        lines = [f"Execution #{execution.id} - {execution.doc_title}", ""]

        # Filter wrapper noise from content
        for line in content.splitlines():
            if not self._is_wrapper_noise(line):
                lines.append(line)

        return "\n".join(lines)

    def _is_wrapper_noise(self, line: str) -> bool:
        """Check if a line is orchestration noise to filter out."""
        noise_patterns = [
            "Wrapper script started", "Command:", "Starting Claude",
            "Claude process finished", "Updating execution status",
            "Database updated", "Background process started",
            "Output is being written", "Wrapper will update",
            "Prompt being sent", "────────",
        ]
        return any(p in line for p in noise_patterns)

    def _handle_new_content(self, content: str) -> None:
        """Handle streaming log content updates."""
        if not content.strip():
            return

        # Filter and append to preview
        filtered = "\n".join(
            line for line in content.splitlines()
            if not self._is_wrapper_noise(line)
        )

        if filtered.strip():
            try:
                preview = self.query_one("#log-preview", PreviewPanel)
                # For streaming, we append by re-showing with new content
                current = preview.get_content()
                import asyncio
                asyncio.create_task(preview.show_content(current + "\n" + filtered))
            except Exception as e:
                logger.debug(f"Error updating preview: {e}")

    def _cleanup_stream(self) -> None:
        """Clean up current log stream."""
        if self.current_stream:
            self.current_stream.unsubscribe(self._stream_subscriber)
            self.current_stream = None

    async def action_refresh(self) -> None:
        """Refresh the execution list."""
        await self._load_executions()

    async def action_toggle_live(self) -> None:
        """Toggle live streaming mode."""
        self.is_live_mode = not self.is_live_mode

        if self.current_stream:
            if self.is_live_mode:
                self.current_stream.subscribe(self._stream_subscriber)
                self.notify("Live mode ON")
            else:
                self.current_stream.unsubscribe(self._stream_subscriber)
                self.notify("Live mode OFF")


class _LogStreamHandler(LogStreamSubscriber):
    """Internal handler for log stream events."""

    def __init__(self, browser: LogBrowserV2):
        self.browser = browser

    def on_log_content(self, new_content: str) -> None:
        self.browser._handle_new_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        logger.error(f"Log stream error: {error}")
