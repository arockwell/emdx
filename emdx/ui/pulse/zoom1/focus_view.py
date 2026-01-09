"""Focus view - Zoom 1 workflow run detail view."""

import json
import logging
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.widgets import DataTable, Static

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


class FocusView(Widget):
    """Zoom 1 - detailed view of a single workflow run."""

    BINDINGS = [
        Binding("tab", "switch_panel", "Switch Panel"),
    ]

    DEFAULT_CSS = """
    FocusView {
        height: 100%;
        width: 100%;
    }

    #focus-container {
        layout: horizontal;
        height: 100%;
        width: 100%;
    }

    #run-info {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
    }

    #stage-list {
        width: 50%;
        height: 100%;
    }

    .focus-header {
        height: 1;
        background: $boost;
        padding: 0 1;
        text-style: bold;
    }

    .run-detail {
        height: auto;
        padding: 1;
    }

    #stages-table {
        height: 1fr;
    }

    #context-preview {
        height: 40%;
        border-top: solid $surface;
    }

    #context-content {
        padding: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.current_run: Optional[Dict[str, Any]] = None
        self.stage_runs: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="focus-container"):
            # Left panel - run info
            with Vertical(id="run-info"):
                yield Static("📋 RUN DETAILS", classes="focus-header")
                yield Static("Select a run to view details", id="run-details", classes="run-detail")
                yield Static("📝 CONTEXT", classes="focus-header")
                with ScrollableContainer(id="context-preview"):
                    yield Static("", id="context-content")

            # Right panel - stage progress
            with Vertical(id="stage-list"):
                yield Static("📊 STAGE PROGRESS", classes="focus-header")
                yield DataTable(id="stages-table", cursor_type="row")

    async def on_mount(self) -> None:
        """Setup the stages table."""
        table = self.query_one("#stages-table", DataTable)
        table.add_column("", width=2)  # Status icon
        table.add_column("Stage", width=15)
        table.add_column("Status", width=10)
        table.add_column("Time", width=8)
        table.add_column("Tokens", width=8)

    async def show_run(self, run: Dict[str, Any]) -> None:
        """Display details for a workflow run."""
        self.current_run = run
        await self._update_run_details()
        await self._update_stages()
        await self._update_context()

    async def _update_run_details(self) -> None:
        """Update the run details panel."""
        details = self.query_one("#run-details", Static)

        if not self.current_run:
            details.update("[dim]No run selected[/dim]")
            return

        run = self.current_run

        # Get workflow name
        wf_name = "Unknown"
        if workflow_registry:
            try:
                wf = workflow_registry.get_workflow(run['workflow_id'])
                if wf:
                    wf_name = wf.display_name
            except Exception:
                wf_name = f"Workflow #{run['workflow_id']}"

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
        task_id = "—"
        try:
            input_vars = run.get('input_variables')
            if isinstance(input_vars, str):
                input_vars = json.loads(input_vars)
            if input_vars:
                task_title = input_vars.get('task_title', '—')
                task_id = str(input_vars.get('task_id', '—'))
        except Exception:
            pass

        # Time info
        time_str = "—"
        if run.get('total_execution_time_ms'):
            secs = run['total_execution_time_ms'] / 1000
            if secs < 60:
                time_str = f"{secs:.1f}s"
            else:
                mins = secs / 60
                time_str = f"{mins:.1f}m"

        # Build details text
        text = f"""[bold]Run #{run['id']}[/bold]

Workflow: {wf_name}
Status: {status_display}
Stage: {run.get('current_stage', '—')}

[dim]Task:[/dim] #{task_id}
{task_title[:50]}

[dim]Time:[/dim] {time_str}
[dim]Tokens:[/dim] {run.get('total_tokens_used', '—')}"""

        if run.get('error_message'):
            text += f"\n\n[red]Error:[/red] {run['error_message'][:100]}"

        details.update(text)

    async def _update_stages(self) -> None:
        """Update the stages table."""
        table = self.query_one("#stages-table", DataTable)
        table.clear()

        if not self.current_run or not HAS_WORKFLOWS or not wf_db:
            return

        try:
            self.stage_runs = wf_db.list_stage_runs(self.current_run['id'])

            if not self.stage_runs:
                # Show workflow stages without runs
                wf = workflow_registry.get_workflow(self.current_run['workflow_id']) if workflow_registry else None
                if wf:
                    for stage in wf.stages:
                        icon = "○"
                        if self.current_run.get('current_stage') == stage.name:
                            icon = "▶"
                        table.add_row(icon, stage.name, "[dim]pending[/dim]", "—", "—")
                return

            for sr in self.stage_runs:
                status = sr.get('status', 'unknown')
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
                if sr.get('execution_time_ms'):
                    secs = sr['execution_time_ms'] / 1000
                    time_str = f"{secs:.0f}s"

                # Tokens
                tokens = str(sr.get('tokens_used', '—'))

                table.add_row(
                    icon,
                    sr.get('stage_name', '?')[:13],
                    status[:8],
                    time_str,
                    tokens
                )

        except Exception as e:
            logger.error(f"Error loading stage runs: {e}", exc_info=True)

    async def _update_context(self) -> None:
        """Update the context preview."""
        content = self.query_one("#context-content", Static)

        if not self.current_run:
            content.update("")
            return

        try:
            context = self.current_run.get('context_json')
            if isinstance(context, str):
                context = json.loads(context)

            if not context:
                content.update("[dim]No context data[/dim]")
                return

            # Show key context variables
            lines = []
            for key, value in context.items():
                if key.startswith('_'):
                    continue  # Skip internal vars
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "…"
                lines.append(f"[cyan]{key}:[/cyan] {value}")

            content.update("\n".join(lines[:10]) if lines else "[dim]Empty context[/dim]")

        except Exception as e:
            content.update(f"[red]Error: {e}[/red]")

    def action_switch_panel(self) -> None:
        """Switch focus between panels."""
        # For now, just a placeholder
        pass

    def get_selected_stage(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected stage run."""
        table = self.query_one("#stages-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.stage_runs):
            return self.stage_runs[table.cursor_row]
        return None

    def get_current_run(self) -> Optional[Dict[str, Any]]:
        """Get the currently displayed run."""
        return self.current_run
