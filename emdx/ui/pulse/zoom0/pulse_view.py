"""Pulse view - workflow execution observer for zoom 0."""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Static, RichLog, Markdown

from emdx.services.log_stream import LogStream, LogStreamSubscriber
from emdx.utils.datetime_utils import parse_datetime

logger = logging.getLogger(__name__)


def format_tokens(tokens: int) -> str:
    """Format token count with K/M abbreviations."""
    if tokens is None or tokens == 0:
        return "—"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)


def format_cost(cost: float) -> str:
    """Format cost in dollars with appropriate precision."""
    if not cost or cost == 0:
        return "—"
    if cost < 0.01:
        return f"${cost:.3f}"
    if cost < 1.00:
        return f"${cost:.2f}"
    return f"${cost:.2f}"


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

    class ViewDocument(Message):
        """Message to request viewing a document."""
        def __init__(self, doc_id: int) -> None:
            self.doc_id = doc_id
            super().__init__()

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

    #agent-doc {
        height: 1fr;
        scrollbar-gutter: stable;
        padding: 0 1;
        display: none;
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

                # Bottom half - selected agent's log OR document content
                with Vertical(id="agent-log-panel"):
                    yield Static("📋 AGENT OUTPUT", classes="pulse-header")
                    # Two widgets - we show one or the other
                    yield RichLog(id="agent-log", highlight=True, markup=True, wrap=True)
                    yield Markdown("", id="agent-doc")
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
        agents_table.add_column("Time", width=5)
        agents_table.add_column("In", width=5)  # Input tokens
        agents_table.add_column("Out", width=5)  # Output tokens
        agents_table.add_column("Cost", width=6)  # Estimated cost
        agents_table.add_column("Output", width=10)

        # Hide doc widget initially (we'll show it when needed)
        self.query_one("#agent-doc").display = False

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
                started_dt = parse_datetime(started)
                if not started_dt:
                    return False
                # Remove timezone for comparison with local time
                if started_dt.tzinfo is not None:
                    started_dt = started_dt.replace(tzinfo=None)
                now = datetime.now()
                return (now - started_dt) < timedelta(minutes=minutes)

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
            agents_table.add_row("", "", "[dim]Select a run[/dim]", "", "", "", "")
            await self._update_agent_log()
            return

        if not HAS_WORKFLOWS or not wf_db:
            agents_table.add_row("", "", "[dim]No data[/dim]", "", "", "", "")
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
                elif run.get('started_at'):
                    # Calculate from timestamps as fallback
                    try:
                        from datetime import datetime
                        started = run['started_at']
                        if isinstance(started, str):
                            started = datetime.fromisoformat(started)
                        # Use completed_at if available, otherwise use current time (for running)
                        if run.get('completed_at'):
                            completed = run['completed_at']
                            if isinstance(completed, str):
                                completed = datetime.fromisoformat(completed)
                        else:
                            completed = datetime.now()
                        secs = (completed - started).total_seconds()
                        time_str = f"{secs:.0f}s"
                    except (ValueError, TypeError):
                        pass

                agents_table.add_row(icon, "1", time_str, "—", "—", "—", "")
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

                # Time - use execution_time_ms if available, otherwise calculate from timestamps
                time_str = "—"
                if ir.get('execution_time_ms'):
                    secs = ir['execution_time_ms'] / 1000
                    time_str = f"{secs:.0f}s"
                elif ir.get('started_at'):
                    # Calculate from timestamps as fallback
                    try:
                        from datetime import datetime
                        started = ir['started_at']
                        # Handle both string and datetime objects
                        if isinstance(started, str):
                            started = datetime.fromisoformat(started)
                        # Use completed_at if available, otherwise use current time (for running)
                        if ir.get('completed_at'):
                            completed = ir['completed_at']
                            if isinstance(completed, str):
                                completed = datetime.fromisoformat(completed)
                        else:
                            completed = datetime.now()
                        secs = (completed - started).total_seconds()
                        time_str = f"{secs:.0f}s"
                    except (ValueError, TypeError):
                        pass

                # Output
                output = ""
                if ir.get('output_doc_id'):
                    output = f"Doc #{ir['output_doc_id']}"
                elif status == 'running':
                    output = "● LIVE"
                elif ir.get('error_message'):
                    output = ir['error_message'][:12] + "…"

                # Token and cost display - show "..." for running agents
                if status == 'running':
                    in_str = "..."
                    out_str = "..."
                    cost_str = "..."
                else:
                    in_str = format_tokens(ir.get('input_tokens'))
                    out_str = format_tokens(ir.get('output_tokens'))
                    cost_str = format_cost(ir.get('cost_usd'))

                agents_table.add_row(
                    icon,
                    str(ir.get('run_number', '?')),
                    time_str,
                    in_str,
                    out_str,
                    cost_str,
                    output[:10]
                )

            # Select first row
            if self.individual_runs:
                agents_table.move_cursor(row=0)
                logger.info(f"Selected first agent, individual_runs[0]={self.individual_runs[0]}")

            # Update log viewer for first agent
            logger.info(f"Calling _update_agent_log with selected_agent_idx={self.selected_agent_idx}")
            await self._update_agent_log()

        except Exception as e:
            logger.error(f"Error loading individual runs: {e}", exc_info=True)
            agents_table.add_row("", "", f"[red]Error[/red]", "", "", "", "")

    async def _update_agent_log(self) -> None:
        """Update the agent output panel for the selected agent.

        Shows either:
        - Document content (for completed agents with output)
        - Log stream (for running agents)
        - Basic info (for agents without output)
        """
        # Debug to file - at the very start
        from pathlib import Path
        debug_log = Path.home() / ".emdx" / "pulse_debug.log"
        def dbg_early(msg):
            with open(debug_log, "a") as f:
                f.write(f"{msg}\n")

        dbg_early(f"_update_agent_log called: individual_runs={len(self.individual_runs)}, selected_idx={self.selected_agent_idx}")

        agent_log = self.query_one("#agent-log", RichLog)
        agent_doc = self.query_one("#agent-doc", Markdown)
        status_bar = self.query_one("#agent-log-status", Static)

        # Stop any existing stream
        self._stop_agent_stream()

        # Helper to show log widget
        def show_log():
            agent_log.display = True
            agent_doc.display = False

        # Helper to show doc widget
        def show_doc():
            agent_log.display = False
            agent_doc.display = True

        agent_log.clear()

        # No individual runs selected
        if not self.individual_runs or self.selected_agent_idx >= len(self.individual_runs):
            show_log()
            agent_log.write("[dim]Select an agent[/dim]")
            status_bar.update("")
            return

        selected = self.individual_runs[self.selected_agent_idx]
        agent_status = selected.get('status', '?')
        output_doc_id = selected.get('output_doc_id')

        # Completed agent with document -> show document in Static widget
        dbg_early(f"status={agent_status}, output_doc_id={output_doc_id}")
        if agent_status == 'completed' and output_doc_id:
            try:
                from emdx.models import documents as doc_model
                import re

                # First, load the log document
                doc = doc_model.get_document(output_doc_id)

                # Check if this is a workflow log (not the actual output)
                # If so, try to find the real output by parsing the log for saved doc IDs
                if doc and doc.get('title', '').startswith('Workflow Agent Output'):
                    dbg_early(f"Doc #{output_doc_id} is a workflow log, searching for actual output...")
                    content = doc.get('content', '')

                    # Strip ANSI codes and look for saved document pattern
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    clean_content = ansi_escape.sub('', content)

                    # Find "Saved as #123" patterns
                    matches = re.findall(r'Saved as #(\d+)', clean_content, re.IGNORECASE)
                    for doc_id_str in reversed(matches):
                        doc_id = int(doc_id_str)
                        if doc_id > 0:
                            actual_doc = doc_model.get_document(doc_id)
                            if actual_doc:
                                doc = actual_doc
                                dbg_early(f"Found actual output: #{doc_id} - {actual_doc.get('title')}")
                                break

                dbg_early(f"Showing doc: {doc.get('title') if doc else 'None'}")
                if doc:
                    # Use Markdown widget for nice formatting
                    show_doc()

                    # Build document display with markdown header
                    agent_num = selected.get('run_number', '?')
                    time_str = f"{selected['execution_time_ms']/1000:.0f}s" if selected.get('execution_time_ms') else "—"
                    in_tokens = format_tokens(selected.get('input_tokens'))
                    out_tokens = format_tokens(selected.get('output_tokens'))
                    cost_str = format_cost(selected.get('cost_usd'))

                    header = f"## ✓ Agent #{agent_num}\n"
                    header += f"*Time: {time_str} | In: {in_tokens} | Out: {out_tokens} | Cost: {cost_str}*\n\n"
                    header += f"### 📄 {doc.get('title', 'Untitled')}\n\n"

                    content = doc.get('content', '')
                    agent_doc.update(header + content)

                    # Scroll to top
                    agent_doc.scroll_home(animate=False)

                    dbg_early(f"Content set in Markdown widget")
                    status_bar.update(f"Doc #{doc.get('id', output_doc_id)} | Enter=open full doc")
                    return
            except Exception as e:
                dbg_early(f"Error loading document: {e}")
                logger.error(f"Error loading document: {e}")
                # Fall through to show log view with error

        # Show log view for running/failed/no-doc agents
        show_log()

        agent_num = selected.get('run_number', '?')
        time_str = f"{selected['execution_time_ms']/1000:.0f}s" if selected.get('execution_time_ms') else "—"
        in_tokens = format_tokens(selected.get('input_tokens'))
        out_tokens = format_tokens(selected.get('output_tokens'))
        cost_str = format_cost(selected.get('cost_usd'))

        if agent_status == 'completed':
            agent_log.write(f"[bold green]━━━ Agent #{agent_num} ✓ ━━━[/bold green]")
        elif agent_status == 'failed':
            agent_log.write(f"[bold red]━━━ Agent #{agent_num} ✗ ━━━[/bold red]")
        elif agent_status == 'running':
            agent_log.write(f"[bold yellow]━━━ Agent #{agent_num} ⟳ ━━━[/bold yellow]")
        else:
            agent_log.write(f"[bold]━━━ Agent #{agent_num} ━━━[/bold]")

        agent_log.write(f"[dim]Time: {time_str} | In: {in_tokens} | Out: {out_tokens} | Cost: {cost_str}[/dim]")
        agent_log.write("")

        # Show error if present
        if selected.get('error_message'):
            agent_log.write(f"[red]Error: {selected['error_message']}[/red]")
            agent_log.write("")

        # For running agents, set up live log streaming
        if agent_status == 'running':
            dbg_early(f"Setting up agent stream for running agent #{agent_num}")
            await self._setup_agent_stream(selected, agent_log, status_bar)
        else:
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
            if not execution:
                agent_log.write(f"[yellow]Agent #{ind_run.get('run_number', '?')} starting...[/yellow]")
                agent_log.write(f"[dim]exec_id={exec_id} not found yet[/dim]")
                status_bar.update("[yellow]Starting...[/yellow]")
                return

            log_file = execution.get('log_file')
            if not log_file:
                agent_log.write(f"[yellow]Agent #{ind_run.get('run_number', '?')} starting...[/yellow]")
                agent_log.write("[dim]No log file assigned yet[/dim]")
                status_bar.update("[yellow]Initializing...[/yellow]")
                return

            log_path = Path(log_file)
            if not log_path.exists():
                agent_log.write(f"[yellow]Agent #{ind_run.get('run_number', '?')} starting...[/yellow]")
                agent_log.write(f"[dim]Waiting for: {log_path.name}[/dim]")
                status_bar.update("[yellow]Log pending...[/yellow]")
                return

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
        except Exception as e:
            logger.error(f"Error setting up agent stream: {e}", exc_info=True)
            agent_log.write(f"[red]Error loading log: {e}[/red]")
            status_bar.update("[red]Error[/red]")

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
        started_dt = parse_datetime(started) if started else None
        if started_dt:
            # Remove timezone for comparison with local time
            if started_dt.tzinfo is not None:
                started_dt = started_dt.replace(tzinfo=None)
            from datetime import datetime
            elapsed = datetime.now() - started_dt
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

    def action_open_document(self) -> None:
        """Open the output document for the selected agent run."""
        # Check if agents table is focused - if so, use selected agent's doc
        agents_table = self.query_one("#agents-table", DataTable)
        if agents_table.has_focus:
            agent_run = self.get_selected_agent_run()
            if agent_run and agent_run.get('output_doc_id'):
                self.post_message(self.ViewDocument(agent_run['output_doc_id']))
                return

        # Otherwise check the workflow run for output docs
        run = self.get_selected_run()
        if run:
            # Try to get output from the workflow run
            # Check for output_doc_ids in the run context or stages
            if HAS_WORKFLOWS and wf_db:
                stage_runs = wf_db.list_stage_runs(run['id'])
                for sr in stage_runs:
                    if sr.get('output_doc_id'):
                        self.post_message(self.ViewDocument(sr['output_doc_id']))
                        return
                    if sr.get('synthesis_doc_id'):
                        self.post_message(self.ViewDocument(sr['synthesis_doc_id']))
                        return
