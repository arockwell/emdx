"""Pulse view - workflow execution observer for zoom 0."""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import DataTable, Static, RichLog

from emdx.services.log_stream import LogStream, LogStreamSubscriber

logger = logging.getLogger(__name__)

# Import workflow components
try:
    from emdx.workflows import database as wf_db
    from emdx.workflows.registry import workflow_registry
    HAS_WORKFLOWS = True
except ImportError:
    wf_db = None
    workflow_registry = None
    HAS_WORKFLOWS = False


class PreviewStreamSubscriber(LogStreamSubscriber):
    """Subscriber that forwards log content to the preview pane."""

    def __init__(self, pulse_view: 'PulseView'):
        self.pulse_view = pulse_view

    def on_log_content(self, new_content: str) -> None:
        """Called when new log content is available."""
        self.pulse_view._handle_stream_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        """Called when log reading encounters an error."""
        logger.error(f"Preview stream error: {error}")


class PulseView(Widget):
    """Workflow execution observer - shows running and recent workflow runs."""

    DEFAULT_CSS = """
    PulseView {
        layout: horizontal;
        height: 100%;
    }

    #runs-panel {
        width: 55%;
        height: 100%;
    }

    #preview-panel {
        width: 45%;
        height: 100%;
        border-left: solid $primary;
    }

    .pulse-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    #runs-table {
        height: 1fr;
    }

    #pulse-summary {
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    #preview-content {
        height: 1fr;
        padding: 0 1;
    }

    #preview-header {
        height: auto;
        max-height: 6;
        padding: 0;
    }

    #preview-log {
        height: 1fr;
        scrollbar-gutter: stable;
        overflow-x: hidden;
    }

    #preview-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, on_selection_changed: Optional[Callable] = None):
        super().__init__()
        self.workflow_runs: List[Dict[str, Any]] = []
        self.on_selection_changed = on_selection_changed
        # Log streaming
        self.current_stream: Optional[LogStream] = None
        self.stream_subscriber = PreviewStreamSubscriber(self)
        self.streaming_run_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left panel - runs list
            with Vertical(id="runs-panel"):
                yield Static("⚡ WORKFLOW RUNS", classes="pulse-header")
                yield DataTable(id="runs-table", cursor_type="row")
                yield Static("Loading...", id="pulse-summary")

            # Right panel - preview with streaming log
            with Vertical(id="preview-panel"):
                yield Static("📋 PREVIEW", classes="pulse-header")
                yield Static("", id="preview-header")
                yield RichLog(id="preview-log", highlight=True, markup=True, wrap=True)
                yield Static("", id="preview-status")

    async def on_mount(self) -> None:
        """Setup table and load data."""
        table = self.query_one("#runs-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("Run", width=5)
        table.add_column("Workflow", width=16)
        table.add_column("Task", width=20)
        table.add_column("Stage", width=10)
        table.add_column("Time", width=6)

        await self.load_data()

        # Focus the table so j/k work immediately
        table.focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update preview when row selection changes."""
        self.call_later(self._update_preview)

    async def load_data(self) -> None:
        """Load workflow runs."""
        if not HAS_WORKFLOWS or not wf_db:
            self._show_no_workflows()
            return

        try:
            # Get all recent runs
            all_runs = wf_db.list_workflow_runs(limit=50)

            from datetime import datetime, timedelta

            # Filter out stale runs (no context AND old = orphaned/crashed)
            def has_context(r):
                context = r.get('context_json')
                if not context or context == '{}':
                    return False
                if isinstance(context, str):
                    try:
                        context = json.loads(context)
                    except:
                        return False
                return len(context) > 0

            def is_recent(r, minutes=30):
                """Check if run started within the last N minutes."""
                started = r.get('started_at')
                if not started:
                    return False
                try:
                    if isinstance(started, str):
                        started = datetime.fromisoformat(started.replace('Z', '+00:00')).replace(tzinfo=None)
                    now = datetime.now()
                    return (now - started) < timedelta(minutes=minutes)
                except:
                    return False

            # Running: show if has context OR is recent (might still be starting up)
            running = [r for r in all_runs if r.get('status') == 'running' and (has_context(r) or is_recent(r))]
            completed = [r for r in all_runs if r.get('status') == 'completed']
            failed_with_data = [r for r in all_runs if r.get('status') == 'failed' and has_context(r)]
            paused = [r for r in all_runs if r.get('status') == 'paused']

            # Combine: running first, then paused, completed, failed with data
            others = paused + completed + failed_with_data

            # Combine: running first, then others (already sorted by id desc)
            self.workflow_runs = (running + others)[:30]

            await self._update_runs_table()
            await self._update_summary()
            await self._update_preview()

        except Exception as e:
            logger.error(f"Error loading workflow runs: {e}", exc_info=True)
            summary = self.query_one("#pulse-summary", Static)
            summary.update(f"[red]Error: {e}[/red]")

    def _show_no_workflows(self) -> None:
        """Show message when workflow system unavailable."""
        table = self.query_one("#runs-table", DataTable)
        table.clear()
        table.add_row("", "", "[dim]Workflow system not available[/dim]", "", "", "")
        summary = self.query_one("#pulse-summary", Static)
        summary.update("[dim]Import emdx.workflows to enable[/dim]")

    async def _update_runs_table(self) -> None:
        """Update the runs table."""
        table = self.query_one("#runs-table", DataTable)
        table.clear()

        if not self.workflow_runs:
            table.add_row("", "", "[dim]No workflow runs yet[/dim]", "", "", "")
            return

        for run in self.workflow_runs:
            # Status icon - use clear emojis
            status = run.get('status', 'unknown')
            if status == 'running':
                icon = "🔄"
            elif status == 'completed':
                icon = "✅"
            elif status == 'failed':
                icon = "❌"
            elif status == 'paused':
                icon = "⏸️"
            else:
                icon = "⚪"

            # Run ID
            run_id = f"#{run['id']}"

            # Workflow name
            wf_name = "?"
            if workflow_registry:
                try:
                    wf = workflow_registry.get_workflow(run['workflow_id'])
                    if wf:
                        wf_name = wf.display_name[:14]
                except Exception:
                    wf_name = f"wf#{run['workflow_id']}"

            # Task info from input_variables
            task_title = "—"
            try:
                input_vars = run.get('input_variables')
                if isinstance(input_vars, str):
                    input_vars = json.loads(input_vars)
                if input_vars and isinstance(input_vars, dict):
                    task_title = input_vars.get('task_title', '—')[:18]
            except Exception:
                pass

            # Current stage
            stage = run.get('current_stage', '—') or '—'
            if len(stage) > 8:
                stage = stage[:8] + "…"

            # Time
            time_str = "—"
            if run.get('total_execution_time_ms'):
                secs = run['total_execution_time_ms'] / 1000
                if secs < 60:
                    time_str = f"{secs:.0f}s"
                else:
                    mins = secs / 60
                    time_str = f"{mins:.1f}m"
            elif status == 'running':
                time_str = "…"

            table.add_row(icon, run_id, wf_name, task_title, stage, time_str)

        # Select first row
        if self.workflow_runs:
            table.move_cursor(row=0)

    async def _update_summary(self) -> None:
        """Update the summary line."""
        summary = self.query_one("#pulse-summary", Static)

        running = sum(1 for r in self.workflow_runs if r.get('status') == 'running')
        completed = sum(1 for r in self.workflow_runs if r.get('status') == 'completed')
        failed = sum(1 for r in self.workflow_runs if r.get('status') == 'failed')

        text = f"Running: {running} | Done: {completed} | Failed: {failed} | Total: {len(self.workflow_runs)}"
        summary.update(text)

    async def _update_preview(self) -> None:
        """Update the preview panel with selected run's log - streaming for running workflows."""
        header = self.query_one("#preview-header", Static)
        preview_log = self.query_one("#preview-log", RichLog)
        status_bar = self.query_one("#preview-status", Static)
        run = self.get_selected_run()

        # Stop any existing stream if we switched runs
        if run and run['id'] != self.streaming_run_id:
            self._stop_stream()

        if not run:
            header.update("[dim]No run selected[/dim]")
            preview_log.clear()
            status_bar.update("")
            return

        try:
            # Get workflow name
            wf_name = "Unknown"
            if workflow_registry:
                try:
                    wf = workflow_registry.get_workflow(run['workflow_id'])
                    if wf:
                        wf_name = wf.display_name
                except Exception:
                    pass

            # Status with color
            status = run.get('status', 'unknown')
            status_display = {
                'running': '[green]● Running[/green]',
                'completed': '[blue]✓ Completed[/blue]',
                'failed': '[red]✗ Failed[/red]',
                'paused': '[yellow]⏸ Paused[/yellow]',
            }.get(status, f'○ {status}')

            # Task info
            task_title = "—"
            try:
                input_vars = run.get('input_variables')
                if isinstance(input_vars, str):
                    input_vars = json.loads(input_vars)
                if input_vars:
                    task_title = input_vars.get('task_title', '—')
            except Exception:
                pass

            # Update header
            header.update(
                f"[bold]Run #{run['id']}[/bold] - {wf_name}\n"
                f"Status: {status_display}  Stage: {run.get('current_stage', '—')}\n"
                f"Task: {task_title[:50]}"
            )

            # For RUNNING workflows: try to stream from the active log file
            if status == 'running' and HAS_WORKFLOWS and wf_db:
                await self._setup_live_stream(run, preview_log, status_bar)
                return

            # For completed/failed: show context output
            preview_log.clear()
            context = run.get('context_json')
            if isinstance(context, str):
                context = json.loads(context) if context else {}

            if context:
                # Find the most recent stage output
                output_keys = sorted([k for k in context.keys() if k.endswith('.output')], reverse=True)
                if output_keys:
                    latest_key = output_keys[0]
                    stage_name = latest_key.replace('.output', '')
                    preview_log.write(f"[dim]─── Stage: {stage_name} ───[/dim]")
                    latest_output = context[latest_key]
                    if isinstance(latest_output, str):
                        for line in latest_output.strip().split('\n')[-50:]:
                            preview_log.write(line)
                    else:
                        preview_log.write("[dim]No text output[/dim]")
                    status_bar.update(f"Showing last stage output | {len(output_keys)} stages completed")
                else:
                    preview_log.write("[dim]No stage outputs yet[/dim]")
                    status_bar.update("")
            else:
                preview_log.write("[dim]No context data[/dim]")
                status_bar.update("")

        except Exception as e:
            logger.error(f"Error updating preview: {e}", exc_info=True)
            preview_log.clear()
            preview_log.write(f"[red]Error: {e}[/red]")

    async def _setup_live_stream(self, run: Dict[str, Any], preview_log: RichLog, status_bar: Static) -> None:
        """Setup live streaming from the active execution's log file."""
        from datetime import datetime

        # Check if we're already streaming this run
        if self.streaming_run_id == run['id'] and self.current_stream:
            return  # Already streaming

        preview_log.clear()

        # Try to get the active execution
        active_exec = wf_db.get_active_execution_for_run(run['id'])

        if active_exec and active_exec.get('log_file'):
            log_path = Path(active_exec['log_file'])
            if log_path.exists():
                # Setup streaming
                self._stop_stream()  # Clean up any previous stream

                stage_name = active_exec.get('stage_name', '?')
                preview_log.write(f"[green]● LIVE[/green] [dim]Stage: {stage_name}[/dim]")
                preview_log.write("")

                self.current_stream = LogStream(log_path)
                self.streaming_run_id = run['id']

                # Get initial content
                initial = self.current_stream.get_initial_content()
                if initial:
                    # Show last 40 lines
                    lines = initial.strip().split('\n')
                    for line in lines[-40:]:
                        preview_log.write(line)
                    preview_log.scroll_end(animate=False)

                # Subscribe for live updates
                self.current_stream.subscribe(self.stream_subscriber)
                status_bar.update(f"[green]● LIVE[/green] streaming from {stage_name} | l=toggle")
                return

        # No active log file - show elapsed time
        started = run.get('started_at')
        if started:
            if isinstance(started, str):
                started = datetime.fromisoformat(started.replace('Z', '+00:00')).replace(tzinfo=None)
            elapsed = datetime.now() - started
            mins = int(elapsed.total_seconds() // 60)
            secs = int(elapsed.total_seconds() % 60)
            preview_log.write(f"[yellow]⏳ Running for {mins}m {secs}s[/yellow]")
            preview_log.write("")
            preview_log.write("[dim]Waiting for agent to start writing logs...[/dim]")
            preview_log.write("[dim]Stream will begin when execution starts.[/dim]")
        else:
            preview_log.write("[dim]Starting up...[/dim]")

        status_bar.update("[yellow]Waiting for log file...[/yellow]")

    def _handle_stream_content(self, new_content: str) -> None:
        """Handle new content from the log stream."""
        try:
            preview_log = self.query_one("#preview-log", RichLog)
            for line in new_content.splitlines():
                preview_log.write(line)
            preview_log.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error handling stream content: {e}")

    def _stop_stream(self) -> None:
        """Stop the current log stream."""
        if self.current_stream:
            self.current_stream.unsubscribe(self.stream_subscriber)
            self.current_stream = None
        self.streaming_run_id = None

    def get_selected_run(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected workflow run."""
        table = self.query_one("#runs-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.workflow_runs):
            return self.workflow_runs[table.cursor_row]
        return None

    def on_unmount(self) -> None:
        """Clean up when unmounting."""
        self._stop_stream()
