"""Preview panel for cascade browser - document and execution log display."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from textual.containers import ScrollableContainer
from textual.widgets import RichLog, Static

from emdx.services.cascade_service import get_document, get_document_children
from emdx.services.execution_service import get_execution, update_execution_status

from .constants import STAGE_EMOJI

logger = logging.getLogger(__name__)


class PreviewPanel:
    """Handles preview rendering for the CascadeView.

    This is a helper class (not a widget) that manages the preview pane
    content within CascadeView's compose tree.
    """

    def __init__(self, view: 'CascadeView'):
        self.view = view
        self.log_stream: Optional['LogStream'] = None
        self._log_subscriber = None
        self._selected_exec: Optional[Dict[str, Any]] = None

    def show_document(self, doc_id: int) -> None:
        """Show document content in preview pane."""
        self.stop_log_stream()

        try:
            header = self.view.query_one("#pv-preview-header", Static)
            preview_scroll = self.view.query_one("#pv-preview-scroll", ScrollableContainer)
            preview_content = self.view.query_one("#pv-preview-content", RichLog)
            preview_log = self.view.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        # Show scroll view, hide log view
        preview_scroll.display = True
        preview_log.display = False

        preview_content.clear()

        doc = get_document(doc_id)
        if not doc:
            header.update("[bold]Preview[/bold]")
            preview_content.write("[dim]Document not found[/dim]")
            return

        header.update(f"[bold]#{doc_id}[/bold] {doc.get('title', '')[:40]}")

        # Show document content
        content = doc.get("content", "")
        if content:
            for line in content.split("\n")[:100]:
                preview_content.write(line)
        else:
            preview_content.write("[dim]No content[/dim]")

    def show_execution(self, exec_data: Dict[str, Any]) -> None:
        """Show execution log in preview pane - live if running."""
        self.stop_log_stream()
        self._selected_exec = exec_data

        try:
            header = self.view.query_one("#pv-preview-header", Static)
            preview_scroll = self.view.query_one("#pv-preview-scroll", ScrollableContainer)
            preview_content = self.view.query_one("#pv-preview-content", RichLog)
            preview_log = self.view.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        exec_id = exec_data.get("exec_id")
        status = exec_data.get("status", "")
        is_running = status == "running"

        # Get log file path and check for zombie processes
        exec_record = get_execution(exec_id) if exec_id else None
        log_file = exec_record.log_file if exec_record else None

        # Check for zombie (process died but status still "running")
        if exec_record and exec_record.is_zombie:
            # Auto-fix: mark as failed
            update_execution_status(exec_id, 'failed', -1)
            is_running = False
            status = "failed"
            exec_data["status"] = "failed"  # Update local data too

        if is_running and log_file:
            log_path = Path(log_file)
            if log_path.exists():
                # Show live log
                header.update(f"[green]\u25cf LIVE[/green] [bold]#{exec_id}[/bold]")
                preview_scroll.display = False
                preview_log.display = True
                preview_log.clear()
                self._start_log_stream(log_path, preview_log)
            else:
                # Log file doesn't exist - execution is stale/orphaned
                # Auto-fix: mark as failed
                update_execution_status(exec_id, 'failed', -1)
                header.update(f"[red]\u25cf STALE[/red] [bold]#{exec_id}[/bold]")
                preview_scroll.display = False
                preview_log.display = True
                preview_log.clear()
                preview_log.write("[red]Execution was stale - automatically marked as failed[/red]")
                preview_log.write(f"[dim]Log file not found: {log_file}[/dim]")
                preview_log.write("")
                preview_log.write("[yellow]The process died without completing.[/yellow]")
        else:
            # Show static log content
            header.update(f"[bold]#{exec_id}[/bold] {exec_data.get('doc_title', '')[:30]}")
            preview_scroll.display = False
            preview_log.display = True
            preview_log.clear()

            if log_file:
                log_path = Path(log_file)
                if log_path.exists():
                    content = log_path.read_text()
                    from emdx.ui.live_log_writer import LiveLogWriter
                    writer = LiveLogWriter(preview_log, auto_scroll=False)
                    writer.write(content)
                else:
                    preview_log.write("[dim]Log file not found[/dim]")
            else:
                preview_log.write("[dim]No log file[/dim]")

    def _start_log_stream(self, log_path: Path, preview_log: RichLog) -> None:
        """Start streaming a log file to the preview."""
        from emdx.services.log_stream import LogStream
        from emdx.ui.live_log_writer import LiveLogWriter
        from emdx.utils.stream_json_parser import parse_and_format_live_logs

        self.log_stream = LogStream(log_path)

        # Show initial content
        initial = self.log_stream.get_initial_content()
        if initial:
            formatted = parse_and_format_live_logs(initial)
            for line in formatted[-50:]:
                preview_log.write(line)
            preview_log.scroll_end(animate=False)

        # Subscribe for updates
        view = self.view

        class LogSubscriber:
            def __init__(self, log_widget: RichLog):
                self.log_widget = log_widget

            def on_log_content(self, content: str) -> None:
                def update():
                    writer = LiveLogWriter(self.log_widget, auto_scroll=True)
                    writer.write(content)
                    self.log_widget.refresh()
                try:
                    view.app.call_from_thread(update)
                except Exception as e:
                    logger.error(f"call_from_thread failed: {e}")

            def on_log_error(self, error: Exception) -> None:
                logger.error(f"LogSubscriber.on_log_error: {error}")

        self._log_subscriber = LogSubscriber(preview_log)
        self.log_stream.subscribe(self._log_subscriber)

    def stop_log_stream(self) -> None:
        """Stop any active log stream."""
        if self.log_stream and self._log_subscriber:
            self.log_stream.unsubscribe(self._log_subscriber)
        self.log_stream = None
