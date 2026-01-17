#!/usr/bin/env python3
"""
Workflow browser - template-focused workflow launcher.

Primary view shows workflow templates with their stage pipelines visually.
Secondary view shows recent runs with links to outputs.

Mental model:
- Workflows are execution patterns (templates)
- Tasks are provided at runtime
- Runs show history with links to outputs
"""

import asyncio
import json
import logging
import re
import textwrap
from typing import List, Optional, Tuple

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static

from .modals import HelpMixin

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


# Mode icons and colors for visual pipeline display
MODE_INFO = {
    "single": {"icon": "•", "color": "dim", "name": "single"},
    "parallel": {"icon": "||", "color": "cyan", "name": "parallel"},
    "iterative": {"icon": "⟳", "color": "yellow", "name": "iterative"},
    "adversarial": {"icon": "⚔", "color": "red", "name": "adversarial"},
    "dynamic": {"icon": "◈", "color": "magenta", "name": "dynamic"},
}


class WorkflowBrowser(HelpMixin, Widget):
    """Template-focused workflow browser.

    Shows workflow patterns with visual stage pipelines.
    Tasks are provided at runtime via CLI or task input.
    """

    HELP_TITLE = "Workflow Browser"
    HELP_CATEGORIES = {
        "run_workflow": "Actions",
        "add_task": "Tasks",
        "clear_tasks": "Tasks",
        "toggle_runs": "View",
        "view_outputs": "Actions",
        "cancel_input": "Other",
    }

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "run_workflow", "Run"),
        Binding("t", "add_task", "Add Task"),
        Binding("T", "clear_tasks", "Clear Tasks"),
        Binding("r", "toggle_runs", "Toggle Runs"),
        Binding("o", "view_outputs", "View Outputs"),
        Binding("question_mark", "show_help", "Help"),
        Binding("escape", "cancel_input", "Cancel", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.workflows_list = []
        self.runs_list = []
        self.flat_items = []  # (type, item) for navigation
        self.current_selection = None
        self.view_mode = "templates"  # "templates" or "runs"
        self.pending_tasks: List[str] = []
        self.task_input_active = False

    DEFAULT_CSS = """
    WorkflowBrowser {
        layout: vertical;
        height: 100%;
    }

    .status-bar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }

    .main-content {
        height: 1fr;
    }

    #left-panel {
        width: 40%;
        height: 100%;
    }

    #workflow-table {
        height: 60%;
    }

    #task-panel {
        height: 40%;
        border-top: solid $secondary;
        padding: 1;
    }

    #right-panel {
        width: 60%;
        height: 100%;
        border-left: solid $primary;
    }

    #preview-scroll {
        height: 100%;
        overflow-y: auto;
    }

    #preview-content {
        padding: 1;
        width: 100%;
    }

    #task-input {
        dock: top;
        display: none;
        margin: 0 1;
    }

    #task-input.visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        """Create UI layout."""
        yield Static(
            "Templates | Enter=Run | t=Task | r=Runs",
            classes="status-bar",
            id="status-bar"
        )

        yield Input(
            placeholder="Enter task (string or doc ID)...",
            id="task-input"
        )

        with Horizontal(classes="main-content"):
            with Vertical(id="left-panel"):
                yield DataTable(id="workflow-table", cursor_type="row")
                yield Static("", id="task-panel", markup=True)

            with Vertical(id="right-panel"):
                with ScrollableContainer(id="preview-scroll"):
                    yield Static("", id="preview-content", markup=True)

    def on_mount(self) -> None:
        """Initialize the browser."""
        try:
            self.load_templates()
            self._update_task_panel()
        except Exception as e:
            logger.error(f"Error mounting workflow browser: {e}", exc_info=True)
            self._update_status(f"Error: {e}")

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the workflow table."""
        try:
            table = self.query_one("#workflow-table", DataTable)
            if table:
                table.focus()
        except Exception:
            # Widget not mounted yet
            pass

    def _update_status(self, message: str) -> None:
        """Update status bar."""
        try:
            self.query_one("#status-bar", Static).update(message)
        except Exception:
            pass

    def _get_preview_width(self) -> int:
        """Get the available width for preview content."""
        try:
            panel = self.query_one("#right-panel")
            # Subtract padding (1 on each side) and border (1)
            return max(panel.size.width - 4, 40)
        except Exception:
            return 80  # Fallback

    def _box_top(self, title: str, style: str = "bold") -> str:
        """Generate box top line: ┌─ Title ───────┐"""
        width = self._get_preview_width()
        title_part = f"─ {title} "
        # width - 2 for ┌ and ┐, then subtract title_part length
        dashes = "─" * max(width - len(title_part) - 2, 4)
        return f"[{style}]┌{title_part}{dashes}┐[/{style}]"

    def _box_line(self, content: str, style: str = "bold") -> str:
        """Generate box content line: │ content      │"""
        width = self._get_preview_width()
        # Strip markup to calculate visible length
        visible_content = re.sub(r'\[/?[^\]]+\]', '', content)
        padding = max(width - len(visible_content) - 4, 0)
        return f"[{style}]│[/{style}] {content}{' ' * padding} [{style}]│[/{style}]"

    def _box_bottom(self, style: str = "bold") -> str:
        """Generate box bottom line: └───────────────┘"""
        width = self._get_preview_width()
        return f"[{style}]└{'─' * (width - 2)}┘[/{style}]"

    def _wrap_text(self, text: str, indent: int = 0) -> List[str]:
        """Wrap text to fit preview width."""
        width = self._get_preview_width() - 6 - indent  # Account for box borders and indent
        return textwrap.wrap(text, width=max(width, 20))

    def _get_pipeline_str(self, workflow) -> str:
        """Get visual pipeline string for a workflow's stages.

        Example: "|| → ∑" for parallel with synthesis
        """
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

    def load_templates(self) -> None:
        """Load workflow templates (primary view)."""
        if not workflow_registry:
            self._update_status("Workflow registry not available")
            return

        try:
            table = self.query_one("#workflow-table", DataTable)
            table.clear(columns=True)
            table.add_column("Pipeline", width=12)
            table.add_column("Name", width=24)
            table.add_column("Task", width=5)
            table.add_column("Uses", width=5)

            workflows = workflow_registry.list_workflows(include_inactive=False)
            # Sort by usage
            workflows = sorted(workflows, key=lambda w: w.usage_count, reverse=True)
            self.workflows_list = workflows
            self.flat_items = []

            for wf in workflows:
                self.flat_items.append(("workflow", wf))

                pipeline = self._get_pipeline_str(wf)
                supports_tasks = self._workflow_supports_tasks(wf)
                task_indicator = "[green]✓[/green]" if supports_tasks else "[dim]-[/dim]"

                table.add_row(
                    pipeline,
                    wf.display_name[:24],
                    task_indicator,
                    str(wf.usage_count),
                )

            task_count = len(self.pending_tasks)
            task_info = f" [{task_count} tasks]" if task_count > 0 else ""
            self._update_status(f"Templates ({len(workflows)}){task_info} | Enter=Run | t=Task | r=Runs")
            self.view_mode = "templates"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading templates: {e}", exc_info=True)
            self._update_status(f"Error: {e}")

    def load_runs(self) -> None:
        """Load recent runs with output links."""
        if not wf_db:
            self._update_status("Database not available")
            return

        try:
            table = self.query_one("#workflow-table", DataTable)
            table.clear(columns=True)
            table.add_column("ID", width=6)
            table.add_column("Workflow", width=18)
            table.add_column("Tasks", width=6)
            table.add_column("Status", width=10)
            table.add_column("Output", width=6)

            self.runs_list = wf_db.list_workflow_runs(limit=30)
            self.flat_items = []

            for run in self.runs_list:
                self.flat_items.append(("run", run))

                # Get workflow name
                wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
                wf_name = wf.display_name[:18] if wf else f"#{run['workflow_id']}"

                # Get task count
                task_count = "-"
                if run.get("input_variables"):
                    try:
                        vars_data = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                        tasks = vars_data.get('tasks', [])
                        if tasks:
                            task_count = str(len(tasks))
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Format status
                status = run["status"]
                status_display = {
                    "completed": "[green]done[/green]",
                    "failed": "[red]fail[/red]",
                    "running": "[yellow]run[/yellow]",
                    "pending": "[dim]...[/dim]",
                }.get(status, status)

                # Output doc indicator
                output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []
                output_indicator = f"[cyan]{len(output_ids)}[/cyan]" if output_ids else "[dim]-[/dim]"

                table.add_row(
                    f"#{run['id']}",
                    wf_name,
                    task_count,
                    status_display,
                    output_indicator,
                )

            self._update_status(f"Runs ({len(self.runs_list)}) | o=View Outputs | Tab=Templates")
            self.view_mode = "runs"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading runs: {e}", exc_info=True)
            self._update_status(f"Error: {e}")

    def _update_task_panel(self) -> None:
        """Update the task panel."""
        panel = self.query_one("#task-panel", Static)

        lines = ["[bold]Tasks to Run[/bold]"]

        if not self.pending_tasks:
            lines.append("")
            lines.append("[dim]No tasks queued[/dim]")
            lines.append("[dim]Press t to add tasks[/dim]")
            lines.append("")
            lines.append("[dim]Tasks can be:[/dim]")
            lines.append("[dim]  • Text strings[/dim]")
            lines.append("[dim]  • Document IDs (numbers)[/dim]")
        else:
            lines.append(f"[green]{len(self.pending_tasks)} ready[/green]")
            lines.append("")

            for i, task in enumerate(self.pending_tasks[:5]):
                task_str = str(task)
                if len(task_str) > 35:
                    task_str = task_str[:32] + "..."
                # Show doc ID indicator
                if isinstance(task, int):
                    lines.append(f"  {i+1}. [cyan]doc:{task}[/cyan]")
                else:
                    lines.append(f"  {i+1}. {task_str}")

            if len(self.pending_tasks) > 5:
                lines.append(f"  [dim]+{len(self.pending_tasks) - 5} more[/dim]")

            lines.append("")
            lines.append("[dim]T=Clear | Enter=Run[/dim]")

        panel.update("\n".join(lines))

    def _on_item_selected(self, row_index: int) -> None:
        """Handle item selection."""
        if row_index < 0 or row_index >= len(self.flat_items):
            return

        item_type, item = self.flat_items[row_index]
        self.current_selection = (item_type, item)

        if item_type == "workflow":
            self._show_template_preview(item)
        elif item_type == "run":
            self._show_run_preview(item)

    def _show_template_preview(self, workflow) -> None:
        """Show workflow template preview with boxed pipeline."""
        preview = self.query_one("#preview-content", Static)

        lines = [
            f"[bold cyan]{workflow.display_name}[/bold cyan]",
            f"[dim]{workflow.name}[/dim]",
        ]

        if workflow.description:
            lines.append("")
            for wrapped_line in self._wrap_text(workflow.description):
                lines.append(wrapped_line)

        lines.append("")

        # Pipeline box
        lines.append(self._box_top("Pipeline"))
        for i, stage in enumerate(workflow.stages):
            mode = stage.mode.value
            info = MODE_INFO.get(mode, {"icon": "?", "color": "white", "name": mode})

            # Check if stage uses {{task}}
            has_task = "{{task}}" in (stage.prompt or "")
            task_badge = " [green]◆[/green]" if has_task else ""

            # Stage line with mode icon
            mode_display = f"[{info['color']}]{info['icon']:>2}[/{info['color']}]"
            lines.append(self._box_line(f"{mode_display} [bold]{stage.name}[/bold]{task_badge}"))
            lines.append(self._box_line(f"    [dim]{info['name']} × {stage.runs}[/dim]"))
        lines.append(self._box_bottom())
        lines.append("")

        # Status / action prompt
        supports_tasks = self._workflow_supports_tasks(workflow)
        if supports_tasks:
            if self.pending_tasks:
                lines.append(self._box_top("Ready", "bold green"))
                lines.append(self._box_line(f"{len(self.pending_tasks)} tasks queued", "bold green"))
                lines.append(self._box_line("[dim]Press Enter to run[/dim]", "bold green"))
                lines.append(self._box_bottom("bold green"))
            else:
                lines.append(self._box_top("Needs Tasks", "yellow"))
                lines.append(self._box_line("This workflow requires task input", "yellow"))
                lines.append(self._box_line("[dim]Press t to add tasks[/dim]", "yellow"))
                lines.append(self._box_bottom("yellow"))
        else:
            lines.append("[dim]Static workflow (no task input needed)[/dim]")

        # CLI hint
        lines.append("")
        lines.append("[dim]CLI:[/dim]")
        if self.pending_tasks:
            task_args = " ".join(f'-t "{t}"' for t in self.pending_tasks[:2])
            if len(self.pending_tasks) > 2:
                task_args += " ..."
            lines.append(f"[dim]  emdx workflow run {workflow.name} {task_args}[/dim]")
        else:
            lines.append(f"[dim]  emdx workflow run {workflow.name} -t \"task\"[/dim]")

        preview.update("\n".join(lines))

    def _show_run_preview(self, run: dict) -> None:
        """Show run preview with boxed sections."""
        preview = self.query_one("#preview-content", Static)

        # Get workflow info
        wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
        wf_name = wf.display_name if wf else f"Workflow #{run['workflow_id']}"

        status_colors = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
        }
        status_color = status_colors.get(run["status"], "white")

        lines = []

        # Header
        lines.append(f"[bold cyan]Run #{run['id']}[/bold cyan]  [{status_color}]{run['status']}[/{status_color}]")
        lines.append(f"[dim]{wf_name}[/dim]")
        lines.append("")

        # Timing info (compact)
        timing_parts = []
        if run.get("total_execution_time_ms"):
            secs = run['total_execution_time_ms'] / 1000
            timing_parts.append(f"{secs:.1f}s")
        if run.get("total_tokens_used"):
            timing_parts.append(f"{run['total_tokens_used']:,} tokens")
        if timing_parts:
            lines.append(f"[dim]{' · '.join(timing_parts)}[/dim]")
            lines.append("")

        # Tasks box
        if run.get("input_variables"):
            try:
                vars_data = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                tasks = vars_data.get('tasks', [])
                if tasks:
                    lines.append(self._box_top(f"Tasks ({len(tasks)})"))
                    wrap_width = self._get_preview_width() - 8  # Account for box + number prefix
                    for i, task in enumerate(tasks):
                        task_str = str(task)
                        if isinstance(task, int):
                            # Doc ID - show on one line
                            lines.append(self._box_line(f"{i+1}. [cyan]doc:{task}[/cyan]"))
                        else:
                            # String task - wrap at word boundaries
                            wrapped = textwrap.wrap(task_str, width=max(wrap_width, 30))
                            for j, line in enumerate(wrapped):
                                if j == 0:
                                    lines.append(self._box_line(f"{i+1}. {line}"))
                                else:
                                    lines.append(self._box_line(f"   {line}"))
                    lines.append(self._box_bottom())
                    lines.append("")
            except (json.JSONDecodeError, TypeError):
                pass

        # Stages box
        if wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                lines.append(self._box_top("Stages"))
                for sr in stage_runs:
                    icon = {
                        "completed": "[green]✓[/green]",
                        "failed": "[red]✗[/red]",
                        "running": "[yellow]⟳[/yellow]",
                    }.get(sr["status"], "[dim]○[/dim]")
                    # For running stages, get real-time count from individual runs
                    if sr["status"] == "running":
                        counts = wf_db.count_individual_runs(sr["id"])
                        completed = counts.get("completed", 0)
                        total = counts.get("total", sr["target_runs"])
                        progress = f"{completed}/{total}"
                    else:
                        progress = f"{sr['runs_completed']}/{sr['target_runs']}"
                    lines.append(self._box_line(f"{icon} {sr['stage_name']:<20} {progress}"))
                lines.append(self._box_bottom())
                lines.append("")

        # Outputs box
        output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []
        if output_ids:
            lines.append(self._box_top(f"Outputs ({len(output_ids)})"))
            lines.append(self._box_line("[dim]Press o to view in document browser[/dim]"))
            for doc_id in output_ids:
                lines.append(self._box_line(f"[cyan]doc:{doc_id}[/cyan]"))
            lines.append(self._box_bottom())
        else:
            lines.append("[dim]No outputs yet[/dim]")

        # Error (if any)
        if run.get("error_message"):
            lines.append("")
            lines.append(self._box_top("Error", "bold red"))
            for line in self._wrap_text(run["error_message"]):
                lines.append(self._box_line(line, "bold red"))
            lines.append(self._box_bottom("bold red"))

        preview.update("\n".join(lines))

    # Navigation actions
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row selection."""
        if event.cursor_row is not None:
            self._on_item_selected(event.cursor_row)

    def action_cursor_down(self) -> None:
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one("#workflow-table", DataTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#workflow-table", DataTable)
        table.move_cursor(row=len(self.flat_items) - 1)

    # View actions
    def action_toggle_runs(self) -> None:
        """Toggle between templates and runs view."""
        if self.view_mode == "templates":
            self.load_runs()
        else:
            self.load_templates()

    def action_view_outputs(self) -> None:
        """Navigate to outputs for current run."""
        if not self.current_selection or self.current_selection[0] != "run":
            self._update_status("Select a run to view outputs")
            return

        run = self.current_selection[1]
        output_ids = json.loads(run.get("output_doc_ids", "[]")) if run.get("output_doc_ids") else []

        if not output_ids:
            self._update_status("No outputs for this run")
            return

        # Navigate to document browser and view first output
        first_doc_id = output_ids[0]

        async def go_to_document():
            if hasattr(self.app, "switch_browser"):
                await self.app.switch_browser("document")
                # Try to select the document
                doc_browser = self.app.browsers.get("document") if hasattr(self.app, "browsers") else None
                if doc_browser and hasattr(doc_browser, "select_document_by_id"):
                    await doc_browser.select_document_by_id(first_doc_id)

        asyncio.create_task(go_to_document())

    # Task input actions
    def action_add_task(self) -> None:
        """Show task input."""
        task_input = self.query_one("#task-input", Input)
        task_input.display = True
        task_input.add_class("visible")
        task_input.focus()
        self.task_input_active = True
        self._update_status("Enter task, press Enter to add")

    def action_clear_tasks(self) -> None:
        """Clear pending tasks."""
        self.pending_tasks = []
        self._update_task_panel()
        self._update_status("Tasks cleared")

    def action_cancel_input(self) -> None:
        """Cancel task input."""
        if self.task_input_active:
            task_input = self.query_one("#task-input", Input)
            task_input.value = ""
            task_input.remove_class("visible")
            task_input.display = False
            self.task_input_active = False
            self.query_one("#workflow-table", DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle task input submission."""
        if event.input.id == "task-input":
            task_value = event.value.strip()
            if task_value:
                # Try as doc ID first
                try:
                    task = int(task_value)
                except ValueError:
                    task = task_value

                self.pending_tasks.append(task)
                self._update_task_panel()
                self._update_status(f"Added task ({len(self.pending_tasks)} total)")

            event.input.value = ""
            event.input.remove_class("visible")
            event.input.display = False
            self.task_input_active = False
            self.query_one("#workflow-table", DataTable).focus()

    # Run action
    def action_run_workflow(self) -> None:
        """Run selected workflow with pending tasks."""
        if not self.current_selection:
            self._update_status("Select a workflow")
            return

        item_type, item = self.current_selection

        if item_type != "workflow":
            self._update_status("Select a workflow template to run")
            return

        workflow = item

        # Check if tasks needed
        if self._workflow_supports_tasks(workflow) and not self.pending_tasks:
            self._update_status("Add tasks first (press t)")
            return

        task_info = f" with {len(self.pending_tasks)} tasks" if self.pending_tasks else ""
        self._update_status(f"Running {workflow.display_name}{task_info}...")

        async def run():
            try:
                variables = {}
                if self.pending_tasks:
                    variables['tasks'] = self.pending_tasks.copy()

                result = await workflow_executor.execute_workflow(
                    workflow_name_or_id=workflow.name,
                    input_variables=variables if variables else None,
                )

                if result.status == "completed":
                    self._update_status(f"Done! Run #{result.id} ({result.total_tokens_used:,} tokens)")
                    self.pending_tasks = []
                    self._update_task_panel()
                else:
                    self._update_status(f"Failed: {result.error_message or 'Unknown'}")
            except Exception as e:
                self._update_status(f"Error: {e}")

        asyncio.create_task(run())
