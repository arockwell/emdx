"""Outcomes view - Zoom 1 showing stage flow and extracted results."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
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


class OutcomesView(Widget):
    """Zoom 1 - shows stage flow and outcomes from a workflow run."""

    class StageSelected(Message):
        """Emitted when user wants to view a stage's logs."""
        def __init__(self, run: Dict[str, Any], stage_name: str) -> None:
            self.run = run
            self.stage_name = stage_name
            super().__init__()

    class IndividualRunSelected(Message):
        """Emitted when user wants to view a specific individual run's logs."""
        def __init__(self, run: Dict[str, Any], stage_name: str, run_number: int) -> None:
            self.run = run
            self.stage_name = stage_name
            self.run_number = run_number
            super().__init__()

    DEFAULT_CSS = """
    OutcomesView {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #outcomes-header {
        height: 2;
        background: $boost;
        padding: 0 1;
    }

    #outcomes-main {
        layout: horizontal;
        height: 1fr;
    }

    #stage-flow-panel {
        width: 40%;
        height: 100%;
        border-right: solid $primary;
    }

    #stage-detail-panel {
        width: 60%;
        height: 100%;
    }

    .panel-header {
        height: 1;
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }

    #stages-table {
        height: 1fr;
    }

    #individual-runs-table {
        height: 50%;
    }

    #artifacts-section {
        height: 50%;
        border-top: solid $surface;
    }

    #artifacts-table {
        height: 1fr;
    }

    #outcomes-footer {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.current_run: Optional[Dict[str, Any]] = None
        self.stage_runs: List[Dict[str, Any]] = []
        self.individual_runs: List[Dict[str, Any]] = []
        self.selected_stage_idx: int = 0
        self.extracted_artifacts: List[Tuple[str, str, str, str]] = []  # (icon, type, id, details)

    def compose(self) -> ComposeResult:
        yield Static("", id="outcomes-header")

        with Horizontal(id="outcomes-main"):
            # Left panel - stage flow
            with Vertical(id="stage-flow-panel"):
                yield Static("STAGE FLOW", classes="panel-header")
                yield DataTable(id="stages-table", cursor_type="row")

            # Right panel - stage detail + artifacts
            with Vertical(id="stage-detail-panel"):
                yield Static("INDIVIDUAL RUNS", classes="panel-header")
                yield DataTable(id="individual-runs-table", cursor_type="row")

                with Vertical(id="artifacts-section"):
                    yield Static("ARTIFACTS", classes="panel-header")
                    yield DataTable(id="artifacts-table", cursor_type="row")

        yield Static("", id="outcomes-footer")

    async def on_mount(self) -> None:
        """Setup tables."""
        # Stages table
        stages = self.query_one("#stages-table", DataTable)
        stages.add_column("", width=2)  # Status icon
        stages.add_column("Stage", width=12)
        stages.add_column("Mode", width=8)
        stages.add_column("Runs", width=6)
        stages.add_column("Time", width=6)

        # Individual runs table
        runs = self.query_one("#individual-runs-table", DataTable)
        runs.add_column("", width=2)  # Status
        runs.add_column("#", width=3)  # Run number
        runs.add_column("Time", width=6)
        runs.add_column("Tokens", width=7)
        runs.add_column("Output", width=20)

        # Artifacts table
        artifacts = self.query_one("#artifacts-table", DataTable)
        artifacts.add_column("", width=2)
        artifacts.add_column("Type", width=6)
        artifacts.add_column("ID", width=8)
        artifacts.add_column("Details", width=30)

        # Focus stages table
        stages.focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail panel when stage selection changes."""
        if event.data_table.id == "stages-table":
            if event.cursor_row is not None and event.cursor_row < len(self.stage_runs):
                self.selected_stage_idx = event.cursor_row
                self.call_later(self._update_individual_runs)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle enter/double-click on a row to drill down to logs."""
        if event.data_table.id == "stages-table":
            # Drill down to stage logs
            if self.current_run and event.cursor_row < len(self.stage_runs):
                stage = self.stage_runs[event.cursor_row]
                self.post_message(self.StageSelected(self.current_run, stage['stage_name']))

        elif event.data_table.id == "individual-runs-table":
            # Drill down to individual run logs
            if self.current_run and event.cursor_row < len(self.individual_runs):
                ind_run = self.individual_runs[event.cursor_row]
                stage = self.stage_runs[self.selected_stage_idx] if self.stage_runs else None
                if stage:
                    self.post_message(self.IndividualRunSelected(
                        self.current_run,
                        stage['stage_name'],
                        ind_run['run_number']
                    ))

    async def show_run(self, run: Dict[str, Any]) -> None:
        """Display outcomes for a workflow run."""
        self.current_run = run
        self.selected_stage_idx = 0

        # Update header
        await self._update_header()

        # Load stage runs from database
        await self._load_stage_runs()

        # Update displays
        await self._update_stages_table()
        await self._update_individual_runs()
        await self._extract_artifacts()
        await self._update_artifacts_table()
        await self._update_footer()

    async def _update_header(self) -> None:
        """Update the header with run info."""
        header = self.query_one("#outcomes-header", Static)

        if not self.current_run:
            header.update("[dim]No run selected[/dim]")
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
                pass

        # Status
        status = run.get('status', 'unknown')
        status_display = {
            'running': '[green]● Running[/green]',
            'completed': '[blue]✓ Completed[/blue]',
            'failed': '[red]✗ Failed[/red]',
            'paused': '[yellow]⏸ Paused[/yellow]',
        }.get(status, f'○ {status}')

        # Time
        time_str = "—"
        if run.get('total_execution_time_ms'):
            secs = run['total_execution_time_ms'] / 1000
            if secs < 60:
                time_str = f"{secs:.0f}s"
            else:
                mins = secs / 60
                time_str = f"{mins:.1f}m"

        # Tokens
        tokens = run.get('total_tokens_used', 0)
        tokens_str = f"{tokens:,}" if isinstance(tokens, int) else "—"

        header.update(
            f"[bold]Run #{run['id']}[/bold]: {wf_name}  "
            f"{status_display}  ⏱ {time_str}  🎫 {tokens_str} tokens"
        )

    async def _load_stage_runs(self) -> None:
        """Load stage runs from database."""
        self.stage_runs = []

        if not self.current_run or not HAS_WORKFLOWS or not wf_db:
            return

        try:
            self.stage_runs = wf_db.list_stage_runs(self.current_run['id'])
        except Exception as e:
            logger.error(f"Error loading stage runs: {e}", exc_info=True)

    async def _update_stages_table(self) -> None:
        """Update the stages table."""
        table = self.query_one("#stages-table", DataTable)
        table.clear()

        if not self.stage_runs:
            # Try to show workflow stages if no runs yet
            if self.current_run and workflow_registry:
                try:
                    wf = workflow_registry.get_workflow(self.current_run['workflow_id'])
                    if wf:
                        for stage in wf.stages:
                            icon = "○"
                            if self.current_run.get('current_stage') == stage.name:
                                icon = "▶"
                            table.add_row(icon, stage.name[:10], stage.mode[:6], "0/1", "—")
                        return
                except Exception:
                    pass

            table.add_row("", "[dim]No stages[/dim]", "", "", "")
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

            # Mode
            mode = sr.get('mode', 'single')
            mode_display = mode[:6]

            # Runs completed / target - for dynamic mode, query actual counts
            if mode == 'dynamic' and sr.get('id'):
                try:
                    counts = wf_db.count_individual_runs(sr['id'])
                    runs_done = counts.get('completed', 0)
                    target = counts.get('total', 0) or sr.get('target_runs', 1)
                except Exception:
                    runs_done = sr.get('runs_completed', 0)
                    target = sr.get('target_runs', 1)
            else:
                runs_done = sr.get('runs_completed', 0)
                target = sr.get('target_runs', 1)
            runs_str = f"{runs_done}/{target}"

            # Time
            time_str = "—"
            if sr.get('execution_time_ms'):
                secs = sr['execution_time_ms'] / 1000
                if secs < 60:
                    time_str = f"{secs:.0f}s"
                else:
                    time_str = f"{secs/60:.1f}m"

            table.add_row(
                icon,
                sr.get('stage_name', '?')[:10],
                mode_display,
                runs_str,
                time_str
            )

        # Select first row
        if self.stage_runs:
            table.move_cursor(row=0)

    async def _update_individual_runs(self) -> None:
        """Update the individual runs table for selected stage."""
        table = self.query_one("#individual-runs-table", DataTable)
        table.clear()

        self.individual_runs = []

        if not self.stage_runs or self.selected_stage_idx >= len(self.stage_runs):
            table.add_row("", "", "[dim]Select a stage[/dim]", "", "")
            return

        stage = self.stage_runs[self.selected_stage_idx]

        if not HAS_WORKFLOWS or not wf_db:
            table.add_row("", "", "[dim]No data[/dim]", "", "")
            return

        try:
            self.individual_runs = wf_db.list_individual_runs(stage['id'])
        except Exception as e:
            logger.error(f"Error loading individual runs: {e}", exc_info=True)
            table.add_row("", "", f"[red]Error: {e}[/red]", "", "")
            return

        if not self.individual_runs:
            # Show placeholder for single-run stages
            status = stage.get('status', 'unknown')
            icon = "✅" if status == 'completed' else ("🔄" if status == 'running' else "⚪")

            time_str = "—"
            if stage.get('execution_time_ms'):
                secs = stage['execution_time_ms'] / 1000
                time_str = f"{secs:.0f}s"

            output = ""
            if stage.get('output_doc_id'):
                output = f"Doc #{stage['output_doc_id']}"

            table.add_row(icon, "1", time_str, str(stage.get('tokens_used', '—')), output)
            return

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
                output = f"[red]{ir['error_message'][:15]}…[/red]"

            table.add_row(
                icon,
                str(ir.get('run_number', '?')),
                time_str,
                str(ir.get('tokens_used', '—')),
                output[:18]
            )

    async def _extract_artifacts(self) -> None:
        """Extract artifacts from run context."""
        self.extracted_artifacts = []

        if not self.current_run:
            return

        try:
            context = self.current_run.get('context_json')
            if isinstance(context, str):
                context = json.loads(context)

            if not context:
                return

            # Combine all stage outputs
            all_output = ""
            for key in sorted(context.keys()):
                if key.endswith('.output'):
                    output = context[key]
                    if isinstance(output, str):
                        all_output += output + "\n"

            # Extract documents
            doc_patterns = [
                (r'Saved as #(\d+):\s*([^\n]+)', lambda m: (m.group(1), m.group(2).strip())),
                (r'Saved as #(\d+)', lambda m: (m.group(1), "Document")),
                (r'Document ID Created: #(\d+)', lambda m: (m.group(1), "Document")),
            ]
            seen_docs = set()
            for pattern, extractor in doc_patterns:
                for match in re.finditer(pattern, all_output, re.IGNORECASE):
                    doc_id, title = extractor(match)
                    if doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        self.extracted_artifacts.append(("📄", "Doc", f"#{doc_id}", title[:28]))

            # Extract PRs
            pr_pattern = r'https://github\.com/([^/]+/[^/]+)/pull/(\d+)'
            seen_prs = set()
            for match in re.finditer(pr_pattern, all_output):
                repo, pr_num = match.groups()
                if pr_num not in seen_prs:
                    seen_prs.add(pr_num)
                    self.extracted_artifacts.append(("🔀", "PR", f"#{pr_num}", f"{repo[:20]}"))

            # Also check stage output_doc_ids
            for sr in self.stage_runs:
                if sr.get('output_doc_id'):
                    doc_id = str(sr['output_doc_id'])
                    if doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        self.extracted_artifacts.append(("📄", "Doc", f"#{doc_id}", f"Stage: {sr['stage_name'][:15]}"))

                if sr.get('synthesis_doc_id'):
                    doc_id = str(sr['synthesis_doc_id'])
                    if doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        self.extracted_artifacts.append(("📝", "Synth", f"#{doc_id}", f"Stage: {sr['stage_name'][:15]}"))

        except Exception as e:
            logger.error(f"Error extracting artifacts: {e}", exc_info=True)

    async def _update_artifacts_table(self) -> None:
        """Update the artifacts table."""
        table = self.query_one("#artifacts-table", DataTable)
        table.clear()

        if not self.extracted_artifacts:
            table.add_row("", "", "[dim]No artifacts[/dim]", "")
            return

        for icon, type_, id_, details in self.extracted_artifacts:
            table.add_row(icon, type_, id_, details)

    async def _update_footer(self) -> None:
        """Update the footer with shortcuts."""
        footer = self.query_one("#outcomes-footer", Static)

        stage_count = len(self.stage_runs)
        artifact_count = len(self.extracted_artifacts)

        footer.update(
            f"{stage_count} stages | {artifact_count} artifacts | "
            "Enter=view logs | Tab=switch panel | z=full logs | Z/Esc=back"
        )

    def get_current_run(self) -> Optional[Dict[str, Any]]:
        """Get the currently displayed run."""
        return self.current_run

    def get_selected_stage(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected stage."""
        if self.stage_runs and self.selected_stage_idx < len(self.stage_runs):
            return self.stage_runs[self.selected_stage_idx]
        return None
