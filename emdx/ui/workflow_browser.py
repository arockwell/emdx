#!/usr/bin/env python3
"""
Workflow browser - view and manage workflow definitions and runs.
"""

import asyncio
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
    """Browser for viewing and managing workflows."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("r", "run_workflow", "Run"),
        Binding("s", "show_runs", "Show Runs"),
        Binding("tab", "toggle_view", "Toggle View"),
    ]

    def __init__(self):
        super().__init__()
        self.workflows_list = []
        self.runs_list = []
        self.current_workflow_id = None
        self.view_mode = "workflows"  # "workflows" or "runs"

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
        yield Static("Workflow Browser [w=workflows, r=runs]", classes="workflow-status", id="workflow-status-bar")

        with Horizontal(classes="workflow-content"):
            # Left sidebar - workflow/run list
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
            self.update_status("Loading workflows...")

            # Set up table for workflows
            self._setup_workflows_table()
            self.load_workflows()

        except Exception as e:
            logger.error(f"Error in WorkflowBrowser.on_mount: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _setup_workflows_table(self) -> None:
        """Set up the workflows table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("ID", width=5)
        table.add_column("Name", width=20)
        table.add_column("Category", width=12)
        table.add_column("Stages", width=8)
        table.add_column("Runs", width=8)

    def _setup_runs_table(self) -> None:
        """Set up the runs table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("Run", width=6)
        table.add_column("Workflow", width=15)
        table.add_column("Status", width=12)
        table.add_column("Stage", width=12)
        table.add_column("Time", width=10)

    def load_workflows(self) -> None:
        """Load workflows from registry."""
        if not workflow_registry:
            self.update_status("Workflow registry not available")
            return

        try:
            self.workflows_list = workflow_registry.list_workflows(include_inactive=True)
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            for wf in self.workflows_list:
                builtin_marker = "🏛️ " if wf.is_builtin else ""
                table.add_row(
                    str(wf.id),
                    f"{builtin_marker}{wf.display_name}",
                    wf.category,
                    str(len(wf.stages)),
                    str(wf.usage_count),
                )

            self.update_status(f"Workflows: {len(self.workflows_list)} | Tab to toggle view | r to run")
            self.view_mode = "workflows"

            # Select first row if available
            if self.workflows_list:
                table.move_cursor(row=0)
                self._on_workflow_selected(0)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def load_runs(self, workflow_id: int = None) -> None:
        """Load workflow runs."""
        if not wf_db:
            self.update_status("Workflow database not available")
            return

        try:
            self._setup_runs_table()
            self.runs_list = wf_db.list_workflow_runs(workflow_id=workflow_id, limit=50)
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            for run in self.runs_list:
                # Get workflow name
                wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
                wf_name = wf.display_name[:12] if wf else f"#{run['workflow_id']}"

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

                table.add_row(
                    f"#{run['id']}",
                    wf_name,
                    status,
                    run.get("current_stage") or "-",
                    time_str,
                )

            filter_text = f" (workflow #{workflow_id})" if workflow_id else ""
            self.update_status(f"Runs: {len(self.runs_list)}{filter_text} | Tab to toggle view")
            self.view_mode = "runs"

            # Select first row if available
            if self.runs_list:
                table.move_cursor(row=0)
                self._on_run_selected(0)

        except Exception as e:
            logger.error(f"Error loading runs: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _on_workflow_selected(self, row_index: int) -> None:
        """Handle workflow selection."""
        if row_index < 0 or row_index >= len(self.workflows_list):
            return

        workflow = self.workflows_list[row_index]
        self.current_workflow_id = workflow.id

        # Update details panel
        details = self.query_one("#workflow-details", Static)
        details_text = (
            f"[bold]{workflow.display_name}[/bold]\n"
            f"Category: {workflow.category}\n"
            f"Stages: {len(workflow.stages)} | Runs: {workflow.usage_count}"
        )
        details.update(details_text)

        # Update preview panel with stage details
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
            }.get(stage.mode.value, "❓")

            strategy = f" ({stage.iteration_strategy})" if stage.iteration_strategy else ""
            preview_lines.append(
                f"  {i}. {mode_indicator} [green]{stage.name}[/green] - {stage.mode.value} x{stage.runs}{strategy}"
            )

        preview_lines.append(f"\n[bold]Statistics:[/bold]")
        if workflow.usage_count > 0:
            success_rate = workflow.success_count / workflow.usage_count * 100
            preview_lines.append(f"  Success rate: {success_rate:.1f}%")
        preview_lines.append(f"  Total runs: {workflow.usage_count}")
        if workflow.last_used_at:
            preview_lines.append(f"  Last used: {workflow.last_used_at}")

        preview.update("\n".join(preview_lines))

    def _on_run_selected(self, row_index: int) -> None:
        """Handle run selection."""
        if row_index < 0 or row_index >= len(self.runs_list):
            return

        run = self.runs_list[row_index]

        # Update details panel
        details = self.query_one("#workflow-details", Static)
        status_color = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "blue",
        }.get(run["status"], "white")

        details_text = (
            f"[bold]Run #{run['id']}[/bold]\n"
            f"Status: [{status_color}]{run['status']}[/{status_color}]\n"
            f"Tokens: {run.get('total_tokens_used', 0)}"
        )
        details.update(details_text)

        # Update preview with run details
        preview = self.query_one("#workflow-content", Static)

        # Get workflow info
        wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
        wf_name = wf.display_name if wf else f"Workflow #{run['workflow_id']}"

        preview_lines = [
            f"[bold cyan]Run #{run['id']}[/bold cyan]",
            f"Workflow: {wf_name}\n",
            f"Status: [{status_color}]{run['status']}[/{status_color}]",
            f"Current stage: {run.get('current_stage') or '-'}",
        ]

        if run.get("started_at"):
            preview_lines.append(f"Started: {run['started_at']}")
        if run.get("completed_at"):
            preview_lines.append(f"Completed: {run['completed_at']}")
        if run.get("total_execution_time_ms"):
            preview_lines.append(f"Duration: {run['total_execution_time_ms'] / 1000:.2f}s")

        preview_lines.append(f"\nTokens used: {run.get('total_tokens_used', 0)}")

        if run.get("error_message"):
            preview_lines.append(f"\n[red]Error:[/red] {run['error_message']}")

        # Load stage runs
        if wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                preview_lines.append("\n[bold]Stage Progress:[/bold]")
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
            if self.view_mode == "workflows":
                self._on_workflow_selected(event.cursor_row)
            else:
                self._on_run_selected(event.cursor_row)

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
        if self.view_mode == "workflows":
            table.move_cursor(row=len(self.workflows_list) - 1)
        else:
            table.move_cursor(row=len(self.runs_list) - 1)

    def action_toggle_view(self) -> None:
        """Toggle between workflows and runs view."""
        if self.view_mode == "workflows":
            self.load_runs()
        else:
            self._setup_workflows_table()
            self.load_workflows()

    def action_show_runs(self) -> None:
        """Show runs for the selected workflow."""
        if self.view_mode == "workflows" and self.current_workflow_id:
            self.load_runs(workflow_id=self.current_workflow_id)

    def action_run_workflow(self) -> None:
        """Run the selected workflow."""
        if self.view_mode != "workflows" or not self.current_workflow_id:
            self.update_status("Select a workflow to run")
            return

        workflow = workflow_registry.get_workflow(self.current_workflow_id)
        if not workflow:
            self.update_status("Workflow not found")
            return

        self.update_status(f"Running workflow: {workflow.display_name}...")

        # Run workflow asynchronously
        async def run_workflow():
            try:
                result = await workflow_executor.execute_workflow(
                    workflow_name_or_id=workflow.name
                )
                if result.status == "completed":
                    self.update_status(f"✓ Workflow completed - Run #{result.id}")
                else:
                    self.update_status(f"✗ Workflow {result.status} - {result.error_message}")
            except Exception as e:
                self.update_status(f"Error: {e}")

        asyncio.create_task(run_workflow())
