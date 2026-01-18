"""
WorkflowBrowser - Workflow browser using the panel-based architecture.

A simplified reimplementation of WorkflowBrowser using ListPanel and PreviewPanel
for template listing and run history.

Features:
- ListPanel with vim navigation for workflows/runs
- PreviewPanel for workflow details and stage info
- Toggle between templates (workflows) and runs views
- Task input for workflows requiring tasks
- Same functionality as original in ~200 lines
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Input, Static

from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
    SimpleStatusBar,
    InputPanel,
    InputMode,
)

logger = logging.getLogger(__name__)

# Import workflow components
try:
    from ...workflows.registry import workflow_registry
    from ...workflows import database as wf_db
    from ...workflows.executor import workflow_executor
except Exception as e:
    logger.error(f"Failed to import workflow components: {e}")
    workflow_registry = None
    wf_db = None
    workflow_executor = None

# Mode icons for visual pipeline display
MODE_INFO = {
    "single": {"icon": "1", "color": "dim"},
    "parallel": {"icon": "||", "color": "cyan"},
    "iterative": {"icon": "→", "color": "yellow"},
    "adversarial": {"icon": "⚔", "color": "red"},
    "dynamic": {"icon": "*", "color": "magenta"},
}


class WorkflowBrowser(Widget):
    """Workflow browser using panel components.

    A simplified workflow browser that displays templates with visual
    pipeline stages and run history using the reusable panel system.
    """

    DEFAULT_CSS = """
    WorkflowBrowser {
        layout: vertical;
        height: 100%;
    }

    WorkflowBrowser #workflow-main {
        height: 1fr;
    }

    WorkflowBrowser #workflow-list {
        width: 45%;
        min-width: 40;
    }

    WorkflowBrowser #workflow-preview {
        width: 55%;
        min-width: 40;
        border-left: solid $primary;
    }

    WorkflowBrowser #workflow-status {
        dock: bottom;
    }

    WorkflowBrowser #task-input-panel {
        dock: top;
    }

    WorkflowBrowser #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("r", "toggle_runs", "Toggle Runs", show=True),
        Binding("t", "add_task", "Add Task", show=True),
        Binding("T", "clear_tasks", "Clear Tasks", show=True),
        Binding("enter", "run_workflow", "Run", show=True),
        Binding("o", "view_outputs", "View Outputs"),
        Binding("R", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.view_mode = "templates"  # "templates" or "runs"
        self.pending_tasks: List[Union[str, int]] = []
        self.workflow_data: List[Any] = []
        self.run_data: List[Dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield InputPanel(
            mode=InputMode.PROMPT,
            overlay=True,
            id="task-input-panel",
        )
        with Horizontal(id="workflow-main"):
            yield ListPanel(
                columns=[
                    ColumnDef("Pipeline", width=12),
                    ColumnDef("Name", width=24),
                    ColumnDef("T", width=2),  # Task indicator
                    ColumnDef("#", width=4),  # Usage count
                ],
                config=ListPanelConfig(
                    show_search=True,
                    search_placeholder="Search workflows...",
                    status_format="{filtered}/{total}",
                ),
                show_status=True,
                id="workflow-list",
            )
            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=False,
                    empty_message="Select a workflow to see details",
                    markdown_rendering=False,
                ),
                id="workflow-preview",
            )
        yield SimpleStatusBar(id="workflow-status")
        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Workflows │ [dim]3[/dim] Documents │ "
            "[dim]j/k[/dim] nav │ [dim]Enter[/dim] run │ [dim]t[/dim] add task │ [dim]r[/dim] toggle runs │ [dim]?[/dim] help",
            id="help-bar",
        )

    async def on_mount(self) -> None:
        # Configure task input panel
        input_panel = self.query_one("#task-input-panel", InputPanel)
        input_panel.set_mode_config(
            InputMode.PROMPT,
            label="Task:",
            placeholder="Enter task (string or doc ID)...",
            hints="Enter=add | Esc=cancel",
        )
        await self._load_templates()
        self._update_status()

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    async def _load_templates(self) -> None:
        """Load workflow templates into the list."""
        if not workflow_registry:
            return

        try:
            workflows = workflow_registry.list_workflows(include_inactive=False)
            workflows = sorted(workflows, key=lambda w: w.usage_count, reverse=True)
            self.workflow_data = workflows

            items = [self._workflow_to_item(wf) for wf in workflows]
            self.query_one("#workflow-list", ListPanel).set_items(items)
            self.view_mode = "templates"
        except Exception as e:
            logger.error(f"Error loading templates: {e}", exc_info=True)

    async def _load_runs(self) -> None:
        """Load recent workflow runs into the list."""
        if not wf_db:
            return

        try:
            # Reconfigure columns for runs view
            list_panel = self.query_one("#workflow-list", ListPanel)

            self.run_data = wf_db.list_workflow_runs(limit=30)
            items = [self._run_to_item(run) for run in self.run_data]
            list_panel.set_items(items)
            self.view_mode = "runs"
        except Exception as e:
            logger.error(f"Error loading runs: {e}", exc_info=True)

    def _workflow_to_item(self, wf) -> ListItem:
        """Convert a workflow to a ListItem."""
        pipeline = self._get_pipeline_str(wf)
        supports_tasks = self._workflow_supports_tasks(wf)
        task_ind = "[green]✓[/green]" if supports_tasks else "[dim]-[/dim]"

        return ListItem(
            id=wf.name,
            values=[pipeline, wf.display_name[:24], task_ind, str(wf.usage_count)],
            data={"workflow": wf, "type": "workflow"},
        )

    def _run_to_item(self, run: Dict[str, Any]) -> ListItem:
        """Convert a run dict to a ListItem."""
        wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
        wf_name = wf.display_name[:18] if wf else f"#{run['workflow_id']}"

        # Status display
        status = run["status"]
        status_display = {
            "completed": "[green]done[/green]",
            "failed": "[red]fail[/red]",
            "running": "[yellow]run[/yellow]",
            "pending": "[dim]...[/dim]",
        }.get(status, status[:6])

        # Output count
        output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []
        output_ind = f"[cyan]{len(output_ids)}[/cyan]" if output_ids else "[dim]-[/dim]"

        return ListItem(
            id=run["id"],
            values=[f"#{run['id']}", wf_name[:16], status_display, output_ind],
            data={"run": run, "type": "run"},
        )

    def _get_pipeline_str(self, workflow) -> str:
        """Get visual pipeline string for workflow stages."""
        if not workflow.stages:
            return "[dim]empty[/dim]"

        parts = []
        for stage in workflow.stages:
            mode = stage.mode.value
            info = MODE_INFO.get(mode, {"icon": "?", "color": "white"})
            parts.append(f"[{info['color']}]{info['icon']}[/{info['color']}]")

        return " → ".join(parts)

    def _workflow_supports_tasks(self, workflow) -> bool:
        """Check if workflow has {{task}} in any prompt."""
        for stage in workflow.stages:
            if stage.prompt and "{{task}}" in stage.prompt:
                return True
            if stage.prompts:
                for p in stage.prompts:
                    if "{{task}}" in p:
                        return True
        return False

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Update preview when item is selected."""
        item = event.item
        if not item.data:
            return

        preview = self.query_one("#workflow-preview", PreviewPanel)
        item_type = item.data.get("type")

        if item_type == "workflow":
            content = self._format_workflow_detail(item.data["workflow"])
            await preview.show_content(content, render_markdown=False)
        elif item_type == "run":
            content = self._format_run_detail(item.data["run"])
            await preview.show_content(content, render_markdown=False)

    async def on_list_panel_item_activated(self, event: ListPanel.ItemActivated) -> None:
        """Handle Enter on item - run workflow or view run."""
        item = event.item
        if item.data and item.data.get("type") == "workflow":
            await self._run_selected_workflow()

    async def on_input_panel_input_submitted(self, event: InputPanel.InputSubmitted) -> None:
        """Handle task input submission."""
        value = event.value.strip()
        if value:
            # Try as doc ID first
            try:
                task = int(value)
            except ValueError:
                task = value

            self.pending_tasks.append(task)
            self._update_status()
            self.notify(f"Added task ({len(self.pending_tasks)} total)")

    # -------------------------------------------------------------------------
    # Preview Formatting
    # -------------------------------------------------------------------------

    def _format_workflow_detail(self, workflow) -> str:
        """Format workflow details for preview."""
        lines = [
            f"[bold cyan]{workflow.display_name}[/bold cyan]",
            f"[dim]{workflow.name}[/dim]",
        ]

        if workflow.description:
            lines.extend(["", workflow.description[:200]])

        lines.extend(["", "[bold]Pipeline[/bold]"])
        for i, stage in enumerate(workflow.stages):
            mode = stage.mode.value
            info = MODE_INFO.get(mode, {"icon": "?", "color": "white"})
            has_task = "{{task}}" in (stage.prompt or "")
            task_badge = " [green]◆[/green]" if has_task else ""
            lines.append(
                f"  [{info['color']}]{info['icon']:>2}[/{info['color']}] "
                f"[bold]{stage.name}[/bold]{task_badge} ({mode} × {stage.runs})"
            )

        # Status section
        supports_tasks = self._workflow_supports_tasks(workflow)
        lines.append("")
        if supports_tasks:
            if self.pending_tasks:
                lines.append(f"[green]Ready:[/green] {len(self.pending_tasks)} tasks queued")
                lines.append("[dim]Press Enter to run[/dim]")
            else:
                lines.append("[yellow]Needs Tasks:[/yellow] This workflow requires task input")
                lines.append("[dim]Press t to add tasks[/dim]")
        else:
            lines.append("[dim]Static workflow (no task input needed)[/dim]")

        # CLI hint
        lines.extend(["", "[dim]CLI:[/dim]"])
        if self.pending_tasks:
            task_args = " ".join(f'-t "{t}"' for t in self.pending_tasks[:2])
            if len(self.pending_tasks) > 2:
                task_args += " ..."
            lines.append(f"[dim]  emdx workflow run {workflow.name} {task_args}[/dim]")
        else:
            lines.append(f"[dim]  emdx workflow run {workflow.name} -t \"task\"[/dim]")

        return "\n".join(lines)

    def _format_run_detail(self, run: Dict[str, Any]) -> str:
        """Format run details for preview."""
        wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
        wf_name = wf.display_name if wf else f"Workflow #{run['workflow_id']}"

        status_colors = {"completed": "green", "failed": "red", "running": "yellow"}
        status_color = status_colors.get(run["status"], "white")

        lines = [
            f"[bold cyan]Run #{run['id']}[/bold cyan]  [{status_color}]{run['status']}[/{status_color}]",
            f"[dim]{wf_name}[/dim]",
            "",
        ]

        # Timing
        if run.get("total_execution_time_ms"):
            secs = run["total_execution_time_ms"] / 1000
            lines.append(f"[dim]Duration: {secs:.1f}s[/dim]")
        if run.get("total_tokens_used"):
            lines.append(f"[dim]Tokens: {run['total_tokens_used']:,}[/dim]")

        # Tasks
        if run.get("input_variables"):
            try:
                vars_data = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                tasks = vars_data.get("tasks", [])
                if tasks:
                    lines.extend(["", f"[bold]Tasks ({len(tasks)})[/bold]"])
                    for i, task in enumerate(tasks[:5]):
                        if isinstance(task, int):
                            lines.append(f"  {i+1}. [cyan]doc:{task}[/cyan]")
                        else:
                            task_str = str(task)[:40]
                            lines.append(f"  {i+1}. {task_str}")
                    if len(tasks) > 5:
                        lines.append(f"  [dim]+{len(tasks) - 5} more[/dim]")
            except (json.JSONDecodeError, TypeError):
                pass

        # Stages
        if wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                lines.extend(["", "[bold]Stages[/bold]"])
                for sr in stage_runs:
                    icon = {
                        "completed": "[green]✓[/green]",
                        "failed": "[red]✗[/red]",
                        "running": "[yellow]⟳[/yellow]",
                    }.get(sr["status"], "[dim]○[/dim]")
                    progress = f"{sr['runs_completed']}/{sr['target_runs']}"
                    lines.append(f"  {icon} {sr['stage_name']:<20} {progress}")

        # Outputs
        output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []
        if output_ids:
            lines.extend(["", f"[bold]Outputs ({len(output_ids)})[/bold]"])
            lines.append("[dim]Press o to view in document browser[/dim]")
            for doc_id in output_ids[:3]:
                lines.append(f"  [cyan]doc:{doc_id}[/cyan]")
            if len(output_ids) > 3:
                lines.append(f"  [dim]+{len(output_ids) - 3} more[/dim]")

        # Error
        if run.get("error_message"):
            lines.extend(["", f"[red]Error:[/red] {run['error_message'][:100]}"])

        return "\n".join(lines)

    def _update_status(self) -> None:
        """Update status bar."""
        status = self.query_one("#workflow-status", SimpleStatusBar)
        task_info = f" [{len(self.pending_tasks)} tasks]" if self.pending_tasks else ""

        if self.view_mode == "templates":
            status.set(f"Templates{task_info} | Enter=Run | t=Task | r=Runs | T=Clear")
        else:
            status.set("Runs | o=View Outputs | r=Templates")

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    async def action_toggle_runs(self) -> None:
        """Toggle between templates and runs view."""
        if self.view_mode == "templates":
            await self._load_runs()
        else:
            await self._load_templates()
        self._update_status()

    def action_add_task(self) -> None:
        """Show task input."""
        input_panel = self.query_one("#task-input-panel", InputPanel)
        input_panel.show(mode=InputMode.PROMPT)

    def action_clear_tasks(self) -> None:
        """Clear pending tasks."""
        self.pending_tasks = []
        self._update_status()
        self.notify("Tasks cleared")

    async def action_run_workflow(self) -> None:
        """Run selected workflow."""
        await self._run_selected_workflow()

    async def _run_selected_workflow(self) -> None:
        """Execute the currently selected workflow."""
        if self.view_mode != "templates":
            self.notify("Select a workflow template to run")
            return

        list_panel = self.query_one("#workflow-list", ListPanel)
        item = list_panel.get_selected_item()

        if not item or not item.data or item.data.get("type") != "workflow":
            self.notify("Select a workflow")
            return

        workflow = item.data["workflow"]

        if self._workflow_supports_tasks(workflow) and not self.pending_tasks:
            self.notify("Add tasks first (press t)")
            return

        if not workflow_executor:
            self.notify("Workflow executor not available")
            return

        task_info = f" with {len(self.pending_tasks)} tasks" if self.pending_tasks else ""
        self.notify(f"Running {workflow.display_name}{task_info}...")

        try:
            variables = {}
            if self.pending_tasks:
                variables["tasks"] = self.pending_tasks.copy()

            result = await workflow_executor.execute_workflow(
                workflow_name_or_id=workflow.name,
                input_variables=variables if variables else None,
            )

            if result.status == "completed":
                self.notify(f"Done! Run #{result.id} ({result.total_tokens_used:,} tokens)")
                self.pending_tasks = []
                self._update_status()
            else:
                self.notify(f"Failed: {result.error_message or 'Unknown'}")
        except Exception as e:
            self.notify(f"Error: {e}")

    async def action_view_outputs(self) -> None:
        """Navigate to outputs for current run."""
        if self.view_mode != "runs":
            self.notify("Select a run to view outputs")
            return

        list_panel = self.query_one("#workflow-list", ListPanel)
        item = list_panel.get_selected_item()

        if not item or not item.data or item.data.get("type") != "run":
            self.notify("Select a run")
            return

        run = item.data["run"]
        output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []

        if not output_ids:
            self.notify("No outputs for this run")
            return

        first_doc_id = output_ids[0]

        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")
            doc_browser = self.app.browsers.get("document") if hasattr(self.app, "browsers") else None
            if doc_browser and hasattr(doc_browser, "select_document_by_id"):
                await doc_browser.select_document_by_id(first_doc_id)

    async def action_refresh(self) -> None:
        """Refresh current view."""
        if self.view_mode == "templates":
            await self._load_templates()
        else:
            await self._load_runs()
        self._update_status()
        self.notify("Refreshed")
