#!/usr/bin/env python3
"""
Workflow browser - task-driven workflow execution interface.

The primary view shows workflows (execution patterns) with their modes.
Tasks are provided at runtime - the key question is "What tasks do I want
to run through this workflow?"

Presets are a secondary feature for saving common configurations.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Input, Static

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
    """Browser for viewing and running workflows with task input.

    Task-driven model:
    - Workflows define HOW to execute (parallel, iterative, etc.)
    - Tasks define WHAT to execute (provided at runtime via --task)
    - Presets save common variable configurations
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "run_workflow", "Run"),
        Binding("t", "add_task", "Add Task"),
        Binding("T", "clear_tasks", "Clear Tasks"),
        Binding("p", "show_presets", "Presets"),
        Binding("r", "show_runs", "Runs"),
        Binding("tab", "cycle_view", "Cycle View"),
        Binding("escape", "cancel_input", "Cancel", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.workflows_list = []  # List of workflow configs
        self.presets_by_workflow = {}  # workflow_id -> list of presets
        self.flat_items = []  # Flattened list for table navigation: (type, item)
        self.runs_list = []
        self.current_selection = None  # (type, item)
        self.view_mode = "workflows"  # "workflows", "presets", or "runs"

        # Task input state
        self.pending_tasks: List[str] = []  # Tasks ready to run
        self.task_input_active = False

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
        height: 50%;
    }

    #task-panel {
        height: 16%;
        border: solid $secondary;
        padding: 0 1;
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

    #task-input {
        dock: top;
        display: none;
        margin: 0 1;
    }

    #task-input.visible {
        display: block;
    }

    .task-count {
        color: $success;
    }

    .mode-indicator {
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create UI layout."""
        yield Static(
            "Workflows | Enter=Run | t=Add Task | p=Presets | r=Runs",
            classes="workflow-status",
            id="workflow-status-bar"
        )

        # Task input (hidden by default)
        yield Input(
            placeholder="Enter task (string or doc ID), press Enter to add...",
            id="task-input"
        )

        with Horizontal(classes="workflow-content"):
            # Left sidebar - workflow/preset/run list + task panel
            with Vertical(id="workflow-sidebar"):
                yield DataTable(id="workflow-table", cursor_type="row")
                yield Static("", id="task-panel", markup=True)
                yield Static("", id="workflow-details", markup=True)

            # Right preview - details
            with Vertical(id="workflow-preview-container"):
                with ScrollableContainer(id="workflow-preview"):
                    yield Static("", id="workflow-content", markup=True)

    def on_mount(self) -> None:
        """Set up when mounted."""
        try:
            self.update_status("Loading workflows...")
            self.load_workflows()
            self._update_task_panel()
        except Exception as e:
            logger.error(f"Error in WorkflowBrowser.on_mount: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _setup_workflows_table(self) -> None:
        """Set up the workflows table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=3)  # Mode indicator
        table.add_column("Name", width=22)
        table.add_column("Mode", width=12)
        table.add_column("Task", width=5)  # Supports {{task}}?
        table.add_column("Runs", width=6)

    def _setup_presets_table(self) -> None:
        """Set up the presets table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=3)  # Indicator column
        table.add_column("Name", width=25)
        table.add_column("Used", width=6)
        table.add_column("Description", width=25)

    def _setup_runs_table(self) -> None:
        """Set up the runs table columns."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear(columns=True)
        table.add_column("Run", width=6)
        table.add_column("Workflow", width=15)
        table.add_column("Tasks", width=6)
        table.add_column("Status", width=10)
        table.add_column("Time", width=8)

    def _get_primary_execution_mode(self, workflow) -> Tuple[str, str]:
        """Get the primary execution mode and icon for a workflow.

        Returns (mode_name, icon).
        """
        if not workflow.stages:
            return ("none", "?")

        # Check stages for the primary mode
        mode_counts = {}
        for stage in workflow.stages:
            mode = stage.mode.value
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

        # Get most common mode (or first if tie)
        primary_mode = max(mode_counts.keys(), key=lambda m: mode_counts[m])

        mode_icons = {
            "single": ("single", "1"),
            "parallel": ("parallel", "||"),
            "iterative": ("iterative", "=>"),
            "adversarial": ("adversarial", "vs"),
            "dynamic": ("dynamic", "*"),
        }

        return mode_icons.get(primary_mode, (primary_mode, "?"))

    def _workflow_supports_tasks(self, workflow) -> bool:
        """Check if workflow has {{task}} in any stage prompt."""
        for stage in workflow.stages:
            if stage.prompt and "{{task}}" in stage.prompt:
                return True
            if stage.prompts:
                for p in stage.prompts:
                    if "{{task}}" in p:
                        return True
        return False

    def load_workflows(self) -> None:
        """Load workflows list (primary view)."""
        if not workflow_registry:
            self.update_status("Workflow registry not available")
            return

        try:
            self._setup_workflows_table()
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            workflows = workflow_registry.list_workflows(include_inactive=False)
            self.workflows_list = workflows
            self.flat_items = []

            # Sort by usage (most used first)
            workflows = sorted(workflows, key=lambda w: w.usage_count, reverse=True)

            for wf in workflows:
                self.flat_items.append(("workflow", wf))

                mode_name, mode_icon = self._get_primary_execution_mode(wf)
                supports_tasks = self._workflow_supports_tasks(wf)

                # Visual indicators
                task_indicator = "[green]Yes[/green]" if supports_tasks else "[dim]-[/dim]"

                # Mode with color coding
                mode_colors = {
                    "parallel": "cyan",
                    "iterative": "yellow",
                    "adversarial": "red",
                    "dynamic": "magenta",
                    "single": "dim",
                }
                mode_color = mode_colors.get(mode_name, "white")
                mode_display = f"[{mode_color}]{mode_name}[/{mode_color}]"

                table.add_row(
                    mode_icon,
                    wf.display_name[:22],
                    mode_display,
                    task_indicator,
                    str(wf.usage_count),
                )

            task_count = len(self.pending_tasks)
            task_info = f" | {task_count} tasks" if task_count > 0 else ""
            self.update_status(f"Workflows: {len(workflows)}{task_info} | Enter=Run | t=Add Task | p=Presets")
            self.view_mode = "workflows"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading workflows: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def load_presets(self, workflow_id: int = None) -> None:
        """Load presets, optionally filtered by workflow."""
        if not workflow_registry or not wf_db:
            self.update_status("Workflow components not available")
            return

        try:
            self._setup_presets_table()
            table = self.query_one("#workflow-table", DataTable)
            table.clear()

            # Get workflows for grouping
            workflows = workflow_registry.list_workflows(include_inactive=False)
            workflows_map = {wf.id: wf for wf in workflows}

            # Get all presets
            all_presets = wf_db.list_presets(workflow_id=workflow_id)

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

            # Sort workflows by total preset usage
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
                wf = workflows_map.get(wf_id)
                if not wf:
                    continue

                # Add workflow header row
                self.flat_items.append(("workflow_header", wf))
                table.add_row(
                    "[bold cyan]>[/bold cyan]",
                    f"[bold]{wf.display_name}[/bold]",
                    "",
                    f"[dim]{len(presets)} presets[/dim]",
                )

                # Add presets under this workflow
                for preset in presets:
                    self.flat_items.append(("preset", preset))
                    total_presets += 1

                    default_marker = "[green]*[/green]" if preset.get('is_default') else " "
                    usage = str(preset.get('usage_count', 0)) + "x"
                    desc = preset.get('description', '')[:25] if preset.get('description') else ""

                    table.add_row(
                        f"  {default_marker}",
                        preset['name'],
                        usage,
                        f"[dim]{desc}[/dim]",
                    )

            filter_text = ""
            if workflow_id:
                wf = workflows_map.get(workflow_id)
                if wf:
                    filter_text = f" ({wf.display_name})"

            self.update_status(f"Presets: {total_presets}{filter_text} | Enter=Select | Tab=Workflows")
            self.view_mode = "presets"

            if self.flat_items:
                # Select first preset
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

    def load_runs(self, workflow_id: int = None) -> None:
        """Load workflow runs, optionally filtered by workflow."""
        if not wf_db:
            self.update_status("Workflow database not available")
            return

        try:
            self._setup_runs_table()
            self.runs_list = wf_db.list_workflow_runs(limit=50)

            # Filter by workflow if specified
            if workflow_id:
                self.runs_list = [r for r in self.runs_list if r.get('workflow_id') == workflow_id]

            table = self.query_one("#workflow-table", DataTable)
            table.clear()
            self.flat_items = []

            for run in self.runs_list:
                self.flat_items.append(("run", run))

                # Get workflow name
                wf = workflow_registry.get_workflow(run["workflow_id"]) if workflow_registry else None
                wf_name = wf.display_name[:15] if wf else f"#{run['workflow_id']}"

                # Get task count from input variables
                task_count = "-"
                if run.get("input_variables"):
                    try:
                        vars_data = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                        tasks = vars_data.get('tasks', [])
                        if tasks:
                            task_count = str(len(tasks))
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Format status with indicator
                status = run["status"]
                if status == "completed":
                    status = "[green]done[/green]"
                elif status == "failed":
                    status = "[red]failed[/red]"
                elif status == "running":
                    status = "[yellow]running[/yellow]"

                # Format time
                time_str = "-"
                if run.get("total_execution_time_ms"):
                    time_str = f"{run['total_execution_time_ms'] / 1000:.1f}s"

                table.add_row(
                    f"#{run['id']}",
                    wf_name,
                    task_count,
                    status,
                    time_str,
                )

            filter_text = ""
            if workflow_id and workflow_registry:
                wf = workflow_registry.get_workflow(workflow_id)
                if wf:
                    filter_text = f" ({wf.display_name})"

            self.update_status(f"Runs: {len(self.runs_list)}{filter_text} | Tab=Workflows")
            self.view_mode = "runs"

            if self.flat_items:
                table.move_cursor(row=0)
                self._on_item_selected(0)

        except Exception as e:
            logger.error(f"Error loading runs: {e}", exc_info=True)
            self.update_status(f"Error: {e}")

    def _update_task_panel(self) -> None:
        """Update the task panel showing pending tasks."""
        panel = self.query_one("#task-panel", Static)

        if not self.pending_tasks:
            panel.update(
                "[dim]No tasks queued[/dim]\n"
                "[dim]Press [bold]t[/bold] to add tasks (strings or doc IDs)[/dim]"
            )
            return

        lines = [f"[bold green]{len(self.pending_tasks)} tasks ready:[/bold green]"]

        # Show up to 3 tasks with truncation
        for i, task in enumerate(self.pending_tasks[:3]):
            task_display = str(task)
            if len(task_display) > 40:
                task_display = task_display[:37] + "..."
            lines.append(f"  {i+1}. {task_display}")

        if len(self.pending_tasks) > 3:
            lines.append(f"  [dim]... +{len(self.pending_tasks) - 3} more[/dim]")

        lines.append("[dim]Press [bold]T[/bold] to clear | [bold]Enter[/bold] to run[/dim]")

        panel.update("\n".join(lines))

    def _on_item_selected(self, row_index: int) -> None:
        """Handle item selection based on current view."""
        if row_index < 0 or row_index >= len(self.flat_items):
            return

        item_type, item = self.flat_items[row_index]
        self.current_selection = (item_type, item)

        if item_type == "workflow":
            self._show_workflow_details(item)
        elif item_type == "preset":
            self._show_preset_details(item)
        elif item_type == "workflow_header":
            self._show_workflow_details(item)
        elif item_type == "run":
            self._show_run_details(item)
        else:
            # Non-selectable rows
            details = self.query_one("#workflow-details", Static)
            details.update("[dim]Navigate to an item[/dim]")
            preview = self.query_one("#workflow-content", Static)
            preview.update("")

    def _show_workflow_details(self, workflow) -> None:
        """Show workflow details with task-driven focus."""
        supports_tasks = self._workflow_supports_tasks(workflow)
        mode_name, mode_icon = self._get_primary_execution_mode(workflow)

        # Update details panel (bottom left)
        details = self.query_one("#workflow-details", Static)

        task_support = "[green]Supports tasks[/green]" if supports_tasks else "[dim]No task variable[/dim]"

        details_text = (
            f"[bold]{workflow.display_name}[/bold]\n"
            f"Mode: [cyan]{mode_name}[/cyan] | Stages: {len(workflow.stages)}\n"
            f"{task_support}"
        )
        details.update(details_text)

        # Update preview panel (right side)
        preview = self.query_one("#workflow-content", Static)
        preview_lines = [
            f"[bold cyan]{workflow.display_name}[/bold cyan]",
            f"[dim]{workflow.name}[/dim]\n",
        ]

        if workflow.description:
            preview_lines.append(f"{workflow.description}\n")

        # Execution pattern section
        preview_lines.append("[bold]Execution Pattern:[/bold]")

        mode_descriptions = {
            "single": "Run once, get one result",
            "parallel": "Run N times simultaneously, then synthesize",
            "iterative": "Run N times sequentially, each building on previous",
            "adversarial": "Advocate -> Critic -> Synthesizer pattern",
            "dynamic": "Discover items at runtime, process each in parallel",
        }

        preview_lines.append(f"  Primary mode: [cyan]{mode_name}[/cyan]")
        preview_lines.append(f"  [dim]{mode_descriptions.get(mode_name, '')}[/dim]\n")

        # Stages section
        preview_lines.append("[bold]Stages:[/bold]")
        for i, stage in enumerate(workflow.stages, 1):
            mode_indicator = {
                "single": "1",
                "parallel": "||",
                "iterative": "=>",
                "adversarial": "vs",
                "dynamic": "*",
            }.get(stage.mode.value, "?")

            has_task = "{{task}}" in (stage.prompt or "")
            task_badge = " [green][task][/green]" if has_task else ""

            preview_lines.append(
                f"  {i}. [{mode_indicator}] [green]{stage.name}[/green] - {stage.mode.value} x{stage.runs}{task_badge}"
            )

        # Run preview section
        if self.pending_tasks:
            preview_lines.append(f"\n[bold yellow]Run Preview:[/bold yellow]")
            task_count = len(self.pending_tasks)

            if mode_name == "parallel":
                max_concurrent = workflow.stages[0].max_concurrent if workflow.stages else 5
                preview_lines.append(f"  Will run {task_count} tasks in parallel (max {max_concurrent} concurrent)")
            elif mode_name == "iterative":
                preview_lines.append(f"  Will run {task_count} tasks sequentially")
            elif mode_name == "dynamic":
                preview_lines.append(f"  Will discover items from tasks and process each")
            else:
                preview_lines.append(f"  Will run with {task_count} tasks")

            # Show estimated token usage hint
            preview_lines.append(f"  [dim]Estimated: ~{task_count * len(workflow.stages)} API calls[/dim]")

        # How to run section
        preview_lines.append(f"\n[bold]Run with CLI:[/bold]")
        if self.pending_tasks:
            task_args = " ".join(f'--task "{t}"' for t in self.pending_tasks[:2])
            if len(self.pending_tasks) > 2:
                task_args += " ..."
            preview_lines.append(f"  [cyan]emdx workflow run {workflow.name} {task_args}[/cyan]")
        else:
            preview_lines.append(f"  [cyan]emdx workflow run {workflow.name} --task \"your task\"[/cyan]")

        # Show presets if available
        if wf_db:
            presets = wf_db.list_presets(workflow_id=workflow.id)
            if presets:
                preview_lines.append(f"\n[bold]Saved Presets:[/bold] ({len(presets)})")
                for preset in presets[:3]:
                    default_marker = " [green]*[/green]" if preset.get('is_default') else ""
                    preview_lines.append(f"  - {preset['name']}{default_marker}")
                if len(presets) > 3:
                    preview_lines.append(f"  [dim]... +{len(presets) - 3} more (press p)[/dim]")

        preview.update("\n".join(preview_lines))

    def _show_preset_details(self, preset: dict) -> None:
        """Show preset details in the panels."""
        wf = None
        if workflow_registry:
            wf = workflow_registry.get_workflow(preset['workflow_id'])
        wf_name = wf.display_name if wf else f"Workflow #{preset['workflow_id']}"

        # Update details panel (bottom left)
        details = self.query_one("#workflow-details", Static)
        default_marker = " [green]* default[/green]" if preset.get('is_default') else ""
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

        preview_lines.append("[bold]Saved Variables:[/bold]")
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
        if wf:
            preview_lines.append(f"  [cyan]emdx workflow run {wf.name} --preset {preset['name']}[/cyan]")
            if self.pending_tasks:
                task_count = len(self.pending_tasks)
                preview_lines.append(f"  [dim]+ {task_count} pending tasks[/dim]")

        preview.update("\n".join(preview_lines))

    def _show_run_details(self, run: dict) -> None:
        """Show run details with task information."""
        status_color = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "blue",
        }.get(run["status"], "white")

        # Update details panel
        details = self.query_one("#workflow-details", Static)

        # Extract task info
        task_info = ""
        if run.get("input_variables"):
            try:
                vars_data = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                tasks = vars_data.get('tasks', [])
                if tasks:
                    task_info = f"\nTasks: {len(tasks)}"
            except (json.JSONDecodeError, TypeError):
                pass

        details_text = (
            f"[bold]Run #{run['id']}[/bold]\n"
            f"Status: [{status_color}]{run['status']}[/{status_color}]{task_info}\n"
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

        # Show tasks that were run
        if run.get("input_variables"):
            try:
                variables = json.loads(run["input_variables"]) if isinstance(run["input_variables"], str) else run["input_variables"]
                tasks = variables.get('tasks', [])
                if tasks:
                    preview_lines.append(f"\n[bold]Tasks ({len(tasks)}):[/bold]")
                    for i, task in enumerate(tasks[:5]):
                        task_str = str(task)[:50]
                        if len(str(task)) > 50:
                            task_str += "..."
                        preview_lines.append(f"  {i+1}. {task_str}")
                    if len(tasks) > 5:
                        preview_lines.append(f"  [dim]... +{len(tasks) - 5} more[/dim]")

                # Show other variables
                other_vars = {k: v for k, v in variables.items() if k != 'tasks' and not k.startswith('_')}
                if other_vars:
                    preview_lines.append(f"\n[bold]Variables:[/bold]")
                    for k, v in list(other_vars.items())[:5]:
                        v_str = str(v)[:40]
                        preview_lines.append(f"  {k}: {v_str}")
            except (json.JSONDecodeError, TypeError):
                pass

        # Load stage runs
        if wf_db:
            stage_runs = wf_db.list_stage_runs(run["id"])
            if stage_runs:
                preview_lines.append("\n[bold]Stages:[/bold]")
                for sr in stage_runs:
                    status_icon = {
                        "completed": "[green]OK[/green]",
                        "failed": "[red]X[/red]",
                        "running": "[yellow]...[/yellow]",
                        "pending": "[dim]o[/dim]",
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle task input submission."""
        if event.input.id == "task-input":
            task_value = event.value.strip()
            if task_value:
                # Try to parse as doc ID, otherwise use as string
                try:
                    task = int(task_value)
                except ValueError:
                    task = task_value

                self.pending_tasks.append(task)
                self._update_task_panel()

                # Update status
                self.update_status(f"Added task. {len(self.pending_tasks)} tasks ready.")

            # Clear and hide input
            event.input.value = ""
            event.input.remove_class("visible")
            event.input.display = False
            self.task_input_active = False

            # Refocus table
            table = self.query_one("#workflow-table", DataTable)
            table.focus()

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
        """Cycle between workflows, presets, and runs views."""
        if self.view_mode == "workflows":
            self.load_runs()
        elif self.view_mode == "runs":
            self.load_presets()
        else:
            self.load_workflows()

    def action_show_presets(self) -> None:
        """Show presets, filtered by current workflow if selected."""
        workflow_id = None
        if self.current_selection and self.current_selection[0] == "workflow":
            workflow_id = self.current_selection[1].id
        self.load_presets(workflow_id=workflow_id)

    def action_show_runs(self) -> None:
        """Show runs, filtered by current workflow if selected."""
        workflow_id = None
        if self.current_selection and self.current_selection[0] == "workflow":
            workflow_id = self.current_selection[1].id
        self.load_runs(workflow_id=workflow_id)

    def action_add_task(self) -> None:
        """Show task input for adding a new task."""
        task_input = self.query_one("#task-input", Input)
        task_input.display = True
        task_input.add_class("visible")
        task_input.focus()
        self.task_input_active = True
        self.update_status("Enter task (string or doc ID), press Enter to add, Escape to cancel")

    def action_clear_tasks(self) -> None:
        """Clear all pending tasks."""
        self.pending_tasks = []
        self._update_task_panel()
        self.update_status("Tasks cleared")

    def action_cancel_input(self) -> None:
        """Cancel task input."""
        if self.task_input_active:
            task_input = self.query_one("#task-input", Input)
            task_input.value = ""
            task_input.remove_class("visible")
            task_input.display = False
            self.task_input_active = False

            table = self.query_one("#workflow-table", DataTable)
            table.focus()

            task_count = len(self.pending_tasks)
            task_info = f" | {task_count} tasks" if task_count > 0 else ""
            self.update_status(f"Workflows: {len(self.workflows_list)}{task_info} | Enter=Run | t=Add Task")

    def action_run_workflow(self) -> None:
        """Run the selected workflow with pending tasks."""
        if not self.current_selection:
            self.update_status("Select a workflow to run")
            return

        item_type, item = self.current_selection

        # Determine what to run
        workflow = None
        preset = None

        if item_type == "workflow":
            workflow = item
        elif item_type == "workflow_header":
            workflow = item
        elif item_type == "preset":
            preset = item
            if workflow_registry:
                workflow = workflow_registry.get_workflow(preset['workflow_id'])

        if not workflow:
            self.update_status("Select a workflow or preset to run")
            return

        # Check if workflow supports tasks but none provided
        supports_tasks = self._workflow_supports_tasks(workflow)
        if supports_tasks and not self.pending_tasks:
            self.update_status("This workflow needs tasks. Press 't' to add tasks first.")
            return

        # Build run message
        task_info = f" with {len(self.pending_tasks)} tasks" if self.pending_tasks else ""
        preset_info = f" (preset: {preset['name']})" if preset else ""
        self.update_status(f"Running: {workflow.display_name}{preset_info}{task_info}...")

        # Run workflow asynchronously
        async def run_workflow():
            try:
                variables = {}
                if self.pending_tasks:
                    variables['tasks'] = self.pending_tasks.copy()

                result = await workflow_executor.execute_workflow(
                    workflow_name_or_id=workflow.name,
                    preset_name=preset['name'] if preset else None,
                    input_variables=variables if variables else None,
                )

                if result.status == "completed":
                    self.update_status(f"Completed - Run #{result.id} | {result.total_tokens_used} tokens")
                    # Clear tasks after successful run
                    self.pending_tasks = []
                    self._update_task_panel()
                else:
                    self.update_status(f"Failed - {result.error_message or 'Unknown error'}")
            except Exception as e:
                self.update_status(f"Error: {e}")

        asyncio.create_task(run_workflow())
