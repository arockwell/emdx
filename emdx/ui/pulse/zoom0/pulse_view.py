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


class AgentLogStreamSubscriber(LogStreamSubscriber):
    """Subscriber that forwards log content to the agent log pane."""

    def __init__(self, pulse_view: 'PulseView'):
        self.pulse_view = pulse_view

    def on_log_content(self, new_content: str) -> None:
        """Called when new log content is available."""
        self.pulse_view._handle_agent_stream_content(new_content)

    def on_log_error(self, error: Exception) -> None:
        """Called when log reading encounters an error."""
        logger.error(f"Agent log stream error: {error}")


class PulseView(Widget):
    """Workflow execution observer - shows running and recent workflow runs."""

    BINDINGS = [
        ("tab", "focus_next_panel", "Next Panel"),
        ("shift+tab", "focus_prev_panel", "Prev Panel"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

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

    /* Agent runs panel - top half of RHS */
    #agents-panel {
        height: 50%;
        border-bottom: solid $surface;
    }

    #agents-table {
        height: 1fr;
    }

    /* Agent log panel - bottom half of RHS */
    #agent-log-panel {
        height: 50%;
    }

    #agent-log {
        height: 1fr;
        scrollbar-gutter: stable;
        overflow-x: hidden;
    }

    #agent-log-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, on_selection_changed: Optional[Callable] = None):
        super().__init__()
        self.workflow_runs: List[Dict[str, Any]] = []
        self.on_selection_changed = on_selection_changed
        # Individual agent runs for selected workflow
        self.individual_runs: List[Dict[str, Any]] = []
        self.selected_agent_idx: int = 0
        # Log streaming for selected agent
        self.agent_stream: Optional[LogStream] = None
        self.agent_stream_subscriber = AgentLogStreamSubscriber(self)
        self.streaming_agent_run_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left panel - runs list
            with Vertical(id="runs-panel"):
                yield Static("⚡ WORKFLOW RUNS", classes="pulse-header")
                yield DataTable(id="runs-table", cursor_type="row")
                yield Static("Loading...", id="pulse-summary")

            # Right panel - split into agents list (top) and log viewer (bottom)
            with Vertical(id="preview-panel"):
                # Top half - agent runs list
                with Vertical(id="agents-panel"):
                    yield Static("🤖 AGENTS", classes="pulse-header")
                    yield DataTable(id="agents-table", cursor_type="row")

                # Bottom half - selected agent's log
                with Vertical(id="agent-log-panel"):
                    yield Static("📋 AGENT LOG", classes="pulse-header")
                    yield RichLog(id="agent-log", highlight=True, markup=True, wrap=True)
                    yield Static("", id="agent-log-status")

    async def on_mount(self) -> None:
        """Setup table and load data."""
        # Workflow runs table (left panel)
        table = self.query_one("#runs-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("Run", width=5)
        table.add_column("Workflow", width=16)
        table.add_column("Task", width=20)
        table.add_column("Stage", width=10)
        table.add_column("Time", width=6)

        # Agents table (right panel, top half)
        agents_table = self.query_one("#agents-table", DataTable)
        agents_table.add_column("", width=2)  # Status
        agents_table.add_column("#", width=3)  # Run number
        agents_table.add_column("Time", width=6)
        agents_table.add_column("Tokens", width=7)
        agents_table.add_column("Output", width=16)

        await self.load_data()

        # Focus the table so j/k work immediately
        table.focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update when row selection changes in either table."""
        if event.data_table.id == "runs-table":
            # Workflow run selection changed - load agents for this run
            self.call_later(self._update_agents_panel)
        elif event.data_table.id == "agents-table":
            # Agent selection changed - update log viewer
            if event.cursor_row is not None and event.cursor_row < len(self.individual_runs):
                self.selected_agent_idx = event.cursor_row
                self.call_later(self._update_agent_log)

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
                    except json.JSONDecodeError:
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
                except ValueError:
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
            await self._update_agents_panel()

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

    async def _update_agents_panel(self) -> None:
        """Update the agents panel with individual runs for selected workflow."""
        agents_table = self.query_one("#agents-table", DataTable)
        agents_table.clear()

        run = self.get_selected_run()
        self.individual_runs = []
        self.selected_agent_idx = 0

        if not run:
            agents_table.add_row("", "", "[dim]Select a run[/dim]", "", "")
            await self._update_agent_log()
            return

        if not HAS_WORKFLOWS or not wf_db:
            agents_table.add_row("", "", "[dim]No data[/dim]", "", "")
            await self._update_agent_log()
            return

        try:
            # Get stage runs for this workflow run
            stage_runs = wf_db.list_stage_runs(run['id'])

            # Collect all individual runs from all stages
            for sr in stage_runs:
                ind_runs = wf_db.list_individual_runs(sr['id'])
                self.individual_runs.extend(ind_runs)

            if not self.individual_runs:
                # Single-run workflow - show placeholder
                status = run.get('status', 'unknown')
                icon = "✅" if status == 'completed' else ("🔄" if status == 'running' else "⚪")

                time_str = "—"
                if run.get('total_execution_time_ms'):
                    secs = run['total_execution_time_ms'] / 1000
                    time_str = f"{secs:.0f}s"

                agents_table.add_row(icon, "1", time_str, str(run.get('total_tokens_used', '—')), "")
                await self._update_agent_log()
                return

            # Populate agents table
            for ir in self.individual_runs:
                status = ir.get('status', 'unknown')
                if status == 'running':
                    icon = "🔄"
                elif status == 'completed':
                    icon = "✅"
                elif status == 'failed':
                    icon = "❌"
                else:
                    icon = "⚪"

                # Time
                time_str = "—"
                if ir.get('execution_time_ms'):
                    secs = ir['execution_time_ms'] / 1000
                    time_str = f"{secs:.0f}s"

                # Output
                output = ""
                if ir.get('output_doc_id'):
                    output = f"Doc #{ir['output_doc_id']}"
                elif ir.get('error_message'):
                    output = f"[red]{ir['error_message'][:12]}…[/red]"

                agents_table.add_row(
                    icon,
                    str(ir.get('run_number', '?')),
                    time_str,
                    str(ir.get('tokens_used', '—')),
                    output[:14]
                )

            # Select first row
            if self.individual_runs:
                agents_table.move_cursor(row=0)

            # Update log viewer for first agent
            await self._update_agent_log()

        except Exception as e:
            logger.error(f"Error loading individual runs: {e}", exc_info=True)
            agents_table.add_row("", "", f"[red]Error[/red]", "", "")

    async def _update_agent_log(self) -> None:
        """Update the agent log viewer for the selected agent."""
        agent_log = self.query_one("#agent-log", RichLog)
        status_bar = self.query_one("#agent-log-status", Static)

        # Stop any existing stream if agent changed
        if self.individual_runs and self.selected_agent_idx < len(self.individual_runs):
            selected_run = self.individual_runs[self.selected_agent_idx]
            if selected_run.get('id') != self.streaming_agent_run_id:
                self._stop_agent_stream()

        run = self.get_selected_run()
        if not run:
            agent_log.clear()
            agent_log.write("[dim]No workflow run selected[/dim]")
            status_bar.update("")
            return

        if not self.individual_runs:
            # No individual runs - try to show workflow-level log
            agent_log.clear()
            if run.get('status') == 'running' and HAS_WORKFLOWS and wf_db:
                await self._setup_workflow_stream(run, agent_log, status_bar)
            else:
                # Show context output for completed workflows
                context = run.get('context_json')
                if isinstance(context, str):
                    context = json.loads(context) if context else {}

                if context:
                    output_keys = sorted([k for k in context.keys() if k.endswith('.output')], reverse=True)
                    if output_keys:
                        latest_output = context[output_keys[0]]
                        if isinstance(latest_output, str):
                            for line in latest_output.strip().split('\n')[-30:]:
                                agent_log.write(line)
                        status_bar.update(f"Stage output | {len(output_keys)} stages")
                    else:
                        agent_log.write("[dim]No outputs yet[/dim]")
                        status_bar.update("")
                else:
                    agent_log.write("[dim]No log data[/dim]")
                    status_bar.update("")
            return

        if self.selected_agent_idx >= len(self.individual_runs):
            agent_log.clear()
            agent_log.write("[dim]Select an agent[/dim]")
            status_bar.update("")
            return

        selected = self.individual_runs[self.selected_agent_idx]

        # For running agents: stream from log file
        if selected.get('status') == 'running' and HAS_WORKFLOWS and wf_db:
            await self._setup_agent_stream(selected, agent_log, status_bar)
            return

        # For completed/failed: try to get log from execution record
        agent_log.clear()
        exec_id = selected.get('agent_execution_id')

        if exec_id and wf_db:
            try:
                execution = wf_db.get_agent_execution(exec_id)
                if execution and execution.get('log_file'):
                    log_path = Path(execution['log_file'])
                    if log_path.exists():
                        content = log_path.read_text()
                        lines = content.strip().split('\n')
                        for line in lines[-40:]:
                            agent_log.write(line)
                        status_bar.update(f"Agent #{selected.get('run_number', '?')} log | {len(lines)} lines")
                        return
            except Exception as e:
                logger.error(f"Error reading agent log: {e}")

        # Fallback - show what info we have
        agent_log.write(f"[bold]Agent #{selected.get('run_number', '?')}[/bold]")
        agent_log.write(f"Status: {selected.get('status', '?')}")
        if selected.get('execution_time_ms'):
            agent_log.write(f"Time: {selected['execution_time_ms']/1000:.1f}s")
        if selected.get('output_doc_id'):
            agent_log.write(f"Output: Doc #{selected['output_doc_id']}")
        if selected.get('error_message'):
            agent_log.write(f"[red]Error: {selected['error_message']}[/red]")
        status_bar.update("")

    async def _setup_agent_stream(self, ind_run: Dict[str, Any], agent_log: RichLog, status_bar: Static) -> None:
        """Setup live streaming for a running agent."""
        from datetime import datetime

        exec_id = ind_run.get('agent_execution_id')
        if not exec_id:
            agent_log.clear()
            agent_log.write(f"[yellow]Agent #{ind_run.get('run_number', '?')} running...[/yellow]")
            agent_log.write("[dim]Waiting for log file...[/dim]")
            status_bar.update("[yellow]Starting...[/yellow]")
            return

        # Check if already streaming this agent
        if self.streaming_agent_run_id == ind_run.get('id') and self.agent_stream:
            return

        agent_log.clear()

        try:
            execution = wf_db.get_agent_execution(exec_id)
            if execution and execution.get('log_file'):
                log_path = Path(execution['log_file'])
                if log_path.exists():
                    self._stop_agent_stream()

                    agent_log.write(f"[green]● LIVE[/green] Agent #{ind_run.get('run_number', '?')}")
                    agent_log.write("")

                    self.agent_stream = LogStream(log_path)
                    self.streaming_agent_run_id = ind_run.get('id')

                    # Get initial content
                    initial = self.agent_stream.get_initial_content()
                    if initial:
                        lines = initial.strip().split('\n')
                        for line in lines[-30:]:
                            agent_log.write(line)
                        agent_log.scroll_end(animate=False)

                    self.agent_stream.subscribe(self.agent_stream_subscriber)
                    status_bar.update(f"[green]● LIVE[/green] Agent #{ind_run.get('run_number', '?')}")
                    return
        except Exception as e:
            logger.error(f"Error setting up agent stream: {e}")

        agent_log.write(f"[yellow]Agent #{ind_run.get('run_number', '?')} running...[/yellow]")
        status_bar.update("[yellow]Waiting for log...[/yellow]")

    async def _setup_workflow_stream(self, run: Dict[str, Any], agent_log: RichLog, status_bar: Static) -> None:
        """Setup streaming for workflow-level log (for single-run workflows)."""
        from datetime import datetime

        active_exec = wf_db.get_active_execution_for_run(run['id'])

        if active_exec and active_exec.get('log_file'):
            log_path = Path(active_exec['log_file'])
            if log_path.exists():
                self._stop_agent_stream()

                stage_name = active_exec.get('stage_name', '?')
                agent_log.write(f"[green]● LIVE[/green] [dim]Stage: {stage_name}[/dim]")
                agent_log.write("")

                self.agent_stream = LogStream(log_path)
                self.streaming_agent_run_id = run['id']

                initial = self.agent_stream.get_initial_content()
                if initial:
                    lines = initial.strip().split('\n')
                    for line in lines[-30:]:
                        agent_log.write(line)
                    agent_log.scroll_end(animate=False)

                self.agent_stream.subscribe(self.agent_stream_subscriber)
                status_bar.update(f"[green]● LIVE[/green] streaming {stage_name}")
                return

        # Show elapsed time
        started = run.get('started_at')
        if started:
            if isinstance(started, str):
                started = datetime.fromisoformat(started.replace('Z', '+00:00')).replace(tzinfo=None)
            elapsed = datetime.now() - started
            mins = int(elapsed.total_seconds() // 60)
            secs = int(elapsed.total_seconds() % 60)
            agent_log.write(f"[yellow]⏳ Running for {mins}m {secs}s[/yellow]")
            agent_log.write("[dim]Waiting for log file...[/dim]")
        else:
            agent_log.write("[dim]Starting up...[/dim]")
        status_bar.update("[yellow]Waiting...[/yellow]")

    def _handle_agent_stream_content(self, new_content: str) -> None:
        """Handle new content from the agent log stream."""
        try:
            agent_log = self.query_one("#agent-log", RichLog)
            for line in new_content.splitlines():
                agent_log.write(line)
            agent_log.scroll_end(animate=False)
        except Exception as e:
            logger.error(f"Error handling agent stream content: {e}")

    def _stop_agent_stream(self) -> None:
        """Stop the current agent log stream."""
        if self.agent_stream:
            self.agent_stream.unsubscribe(self.agent_stream_subscriber)
            self.agent_stream = None
        self.streaming_agent_run_id = None

    def get_selected_run(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected workflow run."""
        table = self.query_one("#runs-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.workflow_runs):
            return self.workflow_runs[table.cursor_row]
        return None

    def get_selected_agent_run(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected agent run."""
        if self.individual_runs and self.selected_agent_idx < len(self.individual_runs):
            return self.individual_runs[self.selected_agent_idx]
        return None

    def on_unmount(self) -> None:
        """Clean up when unmounting."""
        self._stop_agent_stream()

    def action_focus_next_panel(self) -> None:
        """Move focus to the next panel (LHS -> RHS agents table)."""
        runs_table = self.query_one("#runs-table", DataTable)
        agents_table = self.query_one("#agents-table", DataTable)

        if runs_table.has_focus:
            # LHS focused -> move to RHS agents table
            agents_table.focus()
        elif agents_table.has_focus:
            # RHS agents table focused -> wrap back to LHS
            runs_table.focus()
        else:
            # Neither focused, focus agents table
            agents_table.focus()

    def action_focus_prev_panel(self) -> None:
        """Move focus to the previous panel."""
        runs_table = self.query_one("#runs-table", DataTable)
        agents_table = self.query_one("#agents-table", DataTable)

        if agents_table.has_focus:
            # RHS focused -> move to LHS
            runs_table.focus()
        elif runs_table.has_focus:
            # LHS focused -> wrap to RHS
            agents_table.focus()
        else:
            # Neither focused, focus runs table
            runs_table.focus()

    def action_cursor_down(self) -> None:
        """Move cursor down in the focused table."""
        runs_table = self.query_one("#runs-table", DataTable)
        agents_table = self.query_one("#agents-table", DataTable)

        if runs_table.has_focus:
            runs_table.action_cursor_down()
        elif agents_table.has_focus:
            agents_table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the focused table."""
        runs_table = self.query_one("#runs-table", DataTable)
        agents_table = self.query_one("#agents-table", DataTable)

        if runs_table.has_focus:
            runs_table.action_cursor_up()
        elif agents_table.has_focus:
            agents_table.action_cursor_up()
