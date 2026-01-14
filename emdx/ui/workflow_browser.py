#!/usr/bin/env python3
"""
Workflow browser - view and manage workflow presets and runs.

Presets are the primary view - they represent the actual tasks you run.
Workflows are shown as groupings/categories for presets.
"""

import asyncio
import json
import logging
from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

logger = logging.getLogger(__name__)

# Import workflow components
try:
    from ..workflows.registry import workflow_registry
    from ..workflows import database as wf_db
    from ..workflows.executor import workflow_executor

    logger.info("Successfully imported workflow components")
except Exception as e:
    logger.error(f"Failed to import workflow components: {e}", exc_info=True)
    workflow_registry = None
    wf_db = None


class WorkflowBrowser(Widget):
    """Browser for viewing and managing workflow presets.

    Presets are the primary view - they represent runnable configurations.
    Workflows are shown as groupings.
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "run_preset", "Run"),
        Binding("r", "show_runs", "Runs"),
        Binding("w", "show_workflows", "Workflows"),
        Binding("tab", "cycle_view", "Cycle View"),
    ]

    def __init__(self):
        super().__init__()
        self.presets_by_workflow = {}  # workflow_id -> list of presets
        self.workflows_map = {}  # workflow_id -> workflow
        self.flat_items = []  # Flattened list for table navigation: (type, item)
        self.runs_list = []
        self.current_selection = None  # (type, item) - "preset", "workflow", or "run"
        self.view_mode = "presets"  # "presets", "workflows", or "runs"

    DEFAULT_CSS = """
    WorkflowBrowser {
        layout: vertical;
        height: 100%;
    }

    .workflow-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
    }

    .workflow-content {
        height: 1fr;
    }

    #workflow-sidebar {
        width: 50%;
        height: 100%;
    }

    #workflow-table {
        height: 66%;
    }

    #workflow-details {
        height: 34%;
        border: solid $primary;
        padding: 1;
    }

    #workflow-preview-container {
        width: 50%;
        height: 100%;
    }

    #workflow-preview {
        height: 100%;
        padding: 1;
    }

    #workflow-content {
        height: 100%;
        border: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        """Create UI layout."""
        yield Static("Presets | Enter=Run | r=Runs | w=Workflows", classes="workflow-status", id="workflow-status-bar")

        with Horizontal(classes="workflow-content"):
            # Left sidebar - preset/workflow/run list
            with Vertical(id="workflow-sidebar"):
                yield DataTable(id="workflow-table", cursor_type="row")
                yield Static("", id="workflow-details", markup=True)

            # Right preview - details
            with Vertical(id="workflow-preview-container"):
                with ScrollableContainer(id="workflow-preview"):
                    yield Static("", id="workflow-content", markup=True)

    def on_mount(self) -> None:
        """Set up when mounted."""
        try:
            self.update_status("Loading presets...")
            self.load_presets()
        except Exception as e:
            logger.error(f"Error in WorkflowBrowser.on_mount: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _setup_presets_table(self) -> None:
        """Set up the presets table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=3)  # Indicator column
        table.add_column("Name", width=25)
        table.add_column("Used", width=6)
        table.add_column("Description", width=25)

    def _setup_workflows_table(self) -> None:
        """Set up the workflows table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("ID", width=5)
        table.add_column("Name", width=25)
        table.add_column("Presets", width=8)
        table.add_column("Runs", width=8)

    def _setup_runs_table(self) -> None:
        """Set up the runs table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("Run", width=6)
        table.add_column("Preset", width=15)
        table.add_column("Status", width=12)
        table.add_column("Time", width=10)

    def load_presets(self) -> None:
        """Load presets grouped by workflow."""
        if not workflow_registry or not wf_db:
            self.update_status("Workflow components not available")
            return

        try:
            self._setup_presets_table()
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            # Load all workflows and presets
            workflows = workflow_registry.list_workflows(include_inactive=False)
            self.workflows_map = {wf.id: wf for wf in workflows}

            # Get all presets
            all_presets = wf_db.list_presets()

            # Group presets by workflow
            self.presets_by_workflow = {}
            for preset in all_presets:
                wf_id = preset['workflow_id']
                if wf_id not in self.presets_by_workflow:
                    self.presets_by_workflow[wf_id] = []
                self.presets_by_workflow[wf_id].append(preset)

            # Build flat list and populate table
            self.flat_items = []
            total_presets = 0

            # Sort workflows by total preset usage (most used first)
            workflow_usage = {}
            for wf_id, presets in self.presets_by_workflow.items():
                workflow_usage[wf_id] = sum(p.get('usage_count', 0) for p in presets)

            sorted_workflow_ids = sorted(
                self.presets_by_workflow.keys(),
                key=lambda wf_id: workflow_usage.get(wf_id, 0),
                reverse=True
            )

            for wf_id in sorted_workflow_ids:
                presets = self.presets_by_workflow[wf_id]
                wf = self.workflows_map.get(wf_id)
                if not wf:
                    continue

                # Add workflow header row
                self.flat_items.append(("workflow_header", wf))
                table.add_row(
                    "📁",
                    f"[bold]{wf.display_name}[/bold]",
                    "",
                    f"[dim]{len(presets)} presets[/dim]",
                )

                # Add presets under this workflow
                for preset in presets:
                    self.flat_items.append(("preset", preset))
                    total_presets += 1

                    default_marker = "★" if preset.get('is_default') else " "
                    usage = str(preset.get('usage_count', 0)) + "x"
                    desc = preset.get('description', '')[:25] if preset.get('description') else ""

                    table.add_row(
                        f"  {default_marker}",
                        preset['name'],
                        usage,
                        f"[dim]{desc}[/dim]",
                    )

            # Show workflows with no presets at the bottom (collapsed)
            workflows_without_presets = [
                wf for wf in workflows
                if wf.id not in self.presets_by_workflow
            ]
            if workflows_without_presets:
                self.flat_items.append(("separator", None))
                table.add_row("", "[dim]─── No presets ───[/dim]", "", "")

                for wf in workflows_without_presets[:5]:
                    self.flat_items.append(("workflow_no_presets", wf))
                    table.add_row(
                        "[dim]📄[/dim]",
                        f"[dim]{wf.display_name}[/dim]",
                        "",
                        "[dim]template only[/dim]",
                    )
                if len(workflows_without_presets) > 5:
                    self.flat_items.append(("more", len(workflows_without_presets) - 5))
                    table.add_row("", f"[dim]... +{len(workflows_without_presets) - 5} more[/dim]", "", "")

            self.update_status(f"Presets: {total_presets} | Enter=Run | r=Runs | w=Workflows")
            self.view_mode = "presets"

            # Select first preset if available
            if self.flat_items:
                # Find first actual preset (skip workflow headers)
                for i, (item_type, _) in enumerate(self.flat_items):
                    if item_type == "preset":
                        table.move_cursor(row=i)
                        self._on_item_selected(i)
                        break
                else:
                    table.move_cursor(row=0)
                    self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading presets: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def load_workflows(self) -> None:
        """Load workflows list (template view)."""
        if not workflow_registry:
            self.update_status("Workflow registry not available")
            return

        try:
            self._setup_workflows_table()
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            workflows = workflow_registry.list_workflows(include_inactive=False)
            self.flat_items = []

            for wf in workflows:
                self.flat_items.append(("workflow", wf))

                # Count presets for this workflow
                presets = wf_db.list_presets(workflow_id=wf.id) if wf_db else []

                table.add_row(
                    str(wf.id),
                    wf.display_name,
                    str(len(presets)),
                    str(wf.usage_count),
                )

            self.update_status(f"Workflows: {len(workflows)} | Tab=Presets")
            self.view_mode = "workflows"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def load_runs(self, preset_name: str = None) -> None:
        """Load workflow runs, optionally filtered by preset."""
        if not wf_db:
            self.update_status("Workflow database not available")
            return

        try:
            self._setup_runs_table()
            self.runs_list = wf_db.list_workflow_runs(limit=50)

            # Filter by preset if specified
            if preset_name:
                self.runs_list = [r for r in self.runs_list if r.get('preset_name') == preset_name]

            table = self.query_one("#workflow-table", DataTable)
            table.clear()
            self.flat_items = []

            for run in self.runs_list:
                self.flat_items.append(("run", run))

                # Format status with indicator
                status = run["status"]
                if status == "completed":
                    status = "✓ done"
                elif status == "failed":
                    status = "✗ failed"
                elif status == "running":
                    status = "⟳ running"

                # Format time
                time_str = "-"
                if run.get("total_execution_time_ms"):
                    time_str = f"{run['total_execution_time_ms'] / 1000:.1f}s"

                preset_display = run.get('preset_name') or "[dim]no preset[/dim]"

                table.add_row(
                    f"#{run['id']}",
                    preset_display,
                    status,
                    time_str,
                )

            filter_text = f" ({preset_name})" if preset_name else ""
            self.update_status(f"Runs: {len(self.runs_list)}{filter_text} | Tab=Presets")
            self.view_mode = "runs"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading runs: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _on_item_selected(self, row_index: int) -> None:
        """Handle item selection based on current view."""
        if row_index < 0 or row_index >= len(self.flat_items):
            return

        item_type, item = self.flat_items[row_index]
        self.current_selection = (item_type, item)

        if item_type == "preset":
            self._show_preset_details(item)
        elif item_type in ("workflow_header", "workflow", "workflow_no_presets"):
            self._show_workflow_details(item)
        elif item_type == "run":
            self._show_run_details(item)
        elif item_type == "separator" or item_type == "more":
            # Non-selectable rows - show hint
            details = self.query_one("#workflow-details", Static)
            details.update("[dim]Navigate to a preset or workflow[/dim]")
            preview = self.query_one("#workflow-content", Static)
            preview.update("")

    def _show_preset_details(self, preset: dict) -> None:
        """Show preset details in the panels."""
        wf = self.workflows_map.get(preset['workflow_id'])
        wf_name = wf.display_name if wf else f"Workflow #{preset['workflow_id']}"

        # Update details panel (bottom left)
        details = self.query_one("#workflow-details", Static)
        default_marker = " [green]★ default[/green]" if preset.get('is_default') else ""
        details_text = (
            f"[bold]{preset['display_name']}[/bold]{default_marker}\n"
            f"Workflow: {wf_name}\n"
            f"Used: {preset.get('usage_count', 0)}x"
        )
        details.update(details_text)

        # Update preview panel (right side)
        preview = self.query_one("#workflow-content", Static)
        variables = json.loads(preset['variables_json']) if preset.get('variables_json') else {}

        preview_lines = [
            f"[bold cyan]{preset['display_name']}[/bold cyan]",
            f"[dim]{preset['name']}[/dim]",
            f"Workflow: {wf_name}\n",
        ]

        if preset.get('description'):
            preview_lines.append(f"{preset['description']}\n")

        preview_lines.append("[bold]Variables:[/bold]")
        if variables:
            for k, v in variables.items():
                # Truncate long values
                v_str = str(v)
                if len(v_str) > 50:
                    v_str = v_str[:47] + "..."
                preview_lines.append(f"  [green]{k}[/green]: {v_str}")
        else:
            preview_lines.append("  [dim]No variables defined[/dim]")

        preview_lines.append(f"\n[bold]Usage:[/bold]")
        preview_lines.append(f"  Run count: {preset.get('usage_count', 0)}")
        if preset.get('last_used_at'):
            preview_lines.append(f"  Last used: {preset['last_used_at']}")

        # Show how to run
        preview_lines.append(f"\n[bold]Run with:[/bold]")
        preview_lines.append(f"  [cyan]emdx workflow run {wf.name if wf else 'workflow'} --preset {preset['name']}[/cyan]")

        preview.update("\n".join(preview_lines))

    def _show_workflow_details(self, workflow) -> None:
        """Show workflow details in the panels."""
        # Update details panel
        details = self.query_one("#workflow-details", Static)
        details_text = (
            f"[bold]{workflow.display_name}[/bold]\n"
            f"Category: {workflow.category}\n"
            f"Stages: {len(workflow.stages)} | Runs: {workflow.usage_count}"
        )
        details.update(details_text)

        # Update preview panel
        preview = self.query_one("#workflow-content", Static)
        preview_lines = [
            f"[bold cyan]{workflow.display_name}[/bold cyan]",
            f"[dim]{workflow.name}[/dim]\n",
        ]

        if workflow.description:
            preview_lines.append(f"{workflow.description}\n")

        preview_lines.append("[bold]Stages:[/bold]")
        for i, stage in enumerate(workflow.stages, 1):
            mode_indicator = {
                "single": "1️⃣",
                "parallel": "⏸️",
                "iterative": "🔄",
                "adversarial": "⚔️",
                "dynamic": "🔀",
            }.get(stage.mode.value, "❓")

            preview_lines.append(
                f"  {i}. {mode_indicator} [green]{stage.name}[/green] - {stage.mode.value} x{stage.runs}"
            )

        # Show presets for this workflow
        if wf_db:
            presets = wf_db.list_presets(workflow_id=workflow.id)
            if presets:
                preview_lines.append(f"\n[bold]Presets:[/bold] ({len(presets)})")
                for preset in presets:
                    default_marker = " [green]★[/green]" if preset.get('is_default') else ""
                    preview_lines.append(f"  • {preset['name']}{default_marker}")
            else:
                preview_lines.append(f"\n[dim]No presets - create one with:[/dim]")
                preview_lines.append(f"  [cyan]emdx workflow preset create {workflow.name} <name> --var key=value[/cyan]")

        preview.update("\n".join(preview_lines))

    def _show_run_details(self, run: dict) -> None:
        """Show run details in the panels."""
        status_color = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "blue",
        }.get(run["status"], "white")

        # Update details panel
        details = self.query_one("#workflow-details", Static)
        details_text = (
            f"[bold]Run #{run['id']}[/bold]\n"
            f"Status: [{status_color}]{run['status']}[/{status_color}]\n"
            f"Tokens: {run.get('total_tokens_used', 0)}"
        )
        details.update(details_text)

        # Update preview panel
        preview = self.query_one("#workflow-content", Static)
        wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
        wf_name = wf.display_name if wf else f"Workflow #{run['workflow_id']}"

        preview_lines = [
            f"[bold cyan]Run #{run['id']}[/bold cyan]",
            f"Workflow: {wf_name}",
        ]

        if run.get("preset_name"):
            preview_lines.append(f"Preset: [cyan]{run['preset_name']}[/cyan]")

        preview_lines.append("")
        preview_lines.append(f"Status: [{status_color}]{run['status']}[/{status_color}]")

        if run.get("started_at"):
            preview_lines.append(f"Started: {run['started_at']}")
        if run.get("completed_at"):
            preview_lines.append(f"Completed: {run['completed_at']}")
        if run.get("total_execution_time_ms"):
            preview_lines.append(f"Duration: {run['total_execution_time_ms'] / 1000:.2f}s")

        preview_lines.append(f"\nTokens used: {run.get('total_tokens_used', 0)}")

        if run.get("error_message"):
            preview_lines.append(f"\n[red]Error:[/red] {run['error_message']}")

        # Show input variables
        if run.get("input_variables"):
            variables = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
            if variables:
                preview_lines.append(f"\n[bold]Variables used:[/bold]")
                for k, v in list(variables.items())[:10]:
                    if not k.startswith('_'):
                        v_str = str(v)[:40]
                        preview_lines.append(f"  {k}: {v_str}")

        # Load stage runs
        if wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                preview_lines.append("\n[bold]Stages:[/bold]")
                for sr in stage_runs:
                    status_icon = {
                        "completed": "✓",
                        "failed": "✗",
                        "running": "⟳",
                        "pending": "○",
                    }.get(sr["status"], "?")
                    preview_lines.append(
                        f"  {status_icon} {sr['stage_name']}: {sr['runs_completed']}/{sr['target_runs']}"
                    )

        preview.update("\n".join(preview_lines))

    def update_status(self, message: str) -> None:
        """Update status bar."""
        try:
            status_bar = self.query_one("#workflow-status-bar", Static)
            status_bar.update(message)
        except Exception:
            pass

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row selection changes."""
        if event.cursor_row is not None:
            self._on_item_selected(event.cursor_row)

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#workflow-table", DataTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.query_one("#workflow-table", DataTable)
        table.move_cursor(row=len(self.flat_items) - 1)

    def action_cycle_view(self) -> None:
        """Cycle between presets, workflows, and runs views."""
        if self.view_mode == "presets":
            self.load_runs()
        elif self.view_mode == "runs":
            self.load_workflows()
        else:
            self.load_presets()

    def action_show_runs(self) -> None:
        """Show runs, filtered by current preset if one is selected."""
        if self.current_selection and self.current_selection[0] == "preset":
            preset = self.current_selection[1]
            self.load_runs(preset_name=preset['name'])
        else:
            self.load_runs()

    def action_show_workflows(self) -> None:
        """Show workflows view."""
        self.load_workflows()

    def action_run_preset(self) -> None:
        """Run the selected preset."""
        if not self.current_selection:
            self.update_status("Select a preset to run")
            return

        item_type, item = self.current_selection

        if item_type != "preset":
            self.update_status("Select a preset to run (not a workflow header)")
            return

        preset = item
        wf = self.workflows_map.get(preset['workflow_id'])
        if not wf:
            self.update_status("Workflow not found for preset")
            return

        self.update_status(f"Running: {preset['name']}...")

        # Run workflow with preset asynchronously
        async def run_with_preset():
            try:
                result = await workflow_executor.execute_workflow(
                    workflow_name_or_id=wf.name,
                    preset_name=preset['name'],
                )
                if result.status == "completed":
                    self.update_status(f"✓ Completed - Run #{result.id}")
                else:
                    self.update_status(f"✗ {result.status} - {result.error_message or 'Unknown error'}")
            except Exception as e:
                self.update_status(f"Error: {e}")

        asyncio.create_task(run_with_preset())
