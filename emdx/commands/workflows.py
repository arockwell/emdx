"""Workflow management commands for EMDX."""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import typer
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from ..workflows import database as wf_db
from ..workflows.base import ExecutionMode, WorkflowConfig, WorkflowRun
from ..workflows.executor import workflow_executor
from ..workflows.registry import workflow_registry
from ..utils.text_formatting import truncate_title, truncate_description
from ..utils.output import console

app = typer.Typer(help="Manage and run EMDX workflows")


def create_worktree_for_workflow(base_branch: str = "main") -> tuple[str, str]:
    """Create a unique git worktree for a workflow run.

    Args:
        base_branch: Branch to base the worktree on

    Returns:
        Tuple of (worktree_path, branch_name)
    """
    import random
    import os

    # Get the repo root
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True
    )
    repo_root = result.stdout.strip()

    # Create unique branch and worktree names with timestamp + random + pid
    timestamp = int(time.time())
    random_suffix = random.randint(1000, 9999)
    pid = os.getpid()
    unique_id = f"{timestamp}-{pid}-{random_suffix}"
    branch_name = f"workflow-{unique_id}"
    worktree_dir = Path(repo_root).parent / f"emdx-workflow-{unique_id}"

    # Create the worktree
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_branch],
        capture_output=True, text=True, check=True
    )

    return str(worktree_dir), branch_name


def cleanup_worktree(worktree_path: str):
    """Clean up a workflow worktree after completion.

    Args:
        worktree_path: Path to the worktree to clean up
    """
    try:
        # Remove the worktree
        subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"],
            capture_output=True, text=True
        )
    except Exception as e:
        console.print(f"[yellow]Warning: Could not clean up worktree {worktree_path}: {e}[/yellow]")


@app.command("list")
def list_workflows(
    category: Optional[str] = typer.Option(
        None,
        "--category",
        "-c",
        help="Filter by category: analysis, planning, implementation, review, custom",
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json, simple"
    ),
    all: bool = typer.Option(False, "--all", "-a", help="Include inactive workflows"),
):
    """List all available workflows."""
    try:
        workflows = workflow_registry.list_workflows(
            category=category, include_inactive=all
        )

        if format == "json":
            output = []
            for wf in workflows:
                output.append(
                    {
                        "id": wf.id,
                        "name": wf.name,
                        "display_name": wf.display_name,
                        "description": wf.description,
                        "category": wf.category,
                        "stages": len(wf.stages),
                        "usage_count": wf.usage_count,
                        "is_builtin": wf.is_builtin,
                    }
                )
            console.print(json.dumps(output, indent=2, default=str))
        elif format == "simple":
            for wf in workflows:
                status = "" if wf.is_active else " [INACTIVE]"
                console.print(f"{wf.name}: {wf.description or 'No description'}{status}")
        else:
            if not workflows:
                console.print("[yellow]No workflows found[/yellow]")
                return

            table = Table(
                title="EMDX Workflows", show_header=True, header_style="bold magenta"
            )
            table.add_column("ID", style="cyan", no_wrap=True, width=4)
            table.add_column("Name", style="green", no_wrap=True)
            table.add_column("Category", style="yellow")
            table.add_column("Stages", justify="center", style="blue")
            table.add_column("Description", style="white")
            table.add_column("Usage", justify="right", style="cyan")
            table.add_column("Status", style="red")

            for wf in workflows:
                # Format stages summary
                stages_summary = str(len(wf.stages))

                # Format status
                status = "✓" if wf.is_active else "✗"
                if wf.is_builtin:
                    status += " 🏛️"

                description = truncate_description(wf.description or "")

                table.add_row(
                    str(wf.id),
                    wf.display_name,
                    wf.category,
                    stages_summary,
                    description,
                    str(wf.usage_count),
                    status,
                )

            console.print(table)
            console.print("\n[dim]Status: ✓=active ✗=inactive 🏛️=builtin[/dim]")

    except Exception as e:
        console.print(f"[red]Error listing workflows: {e}[/red]")
        raise typer.Exit(1)


@app.command("show")
def show_workflow(
    workflow_name: str = typer.Argument(..., help="Workflow name or ID"),
):
    """Show detailed information about a workflow."""
    try:
        # Try to parse as ID first
        try:
            workflow_id = int(workflow_name)
            workflow = workflow_registry.get_workflow(workflow_id)
        except ValueError:
            workflow = workflow_registry.get_workflow(workflow_name)

        if not workflow:
            console.print(f"[red]Workflow not found: {workflow_name}[/red]")
            raise typer.Exit(1)

        # Display workflow info
        console.print(
            Panel(
                f"[bold]{workflow.display_name}[/bold]\n"
                f"[dim]Name: {workflow.name}[/dim]\n\n"
                f"{workflow.description or 'No description'}",
                title=f"Workflow #{workflow.id}",
                border_style="cyan",
            )
        )

        # Display stages
        console.print("\n[bold]Stages:[/bold]")
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("#", style="cyan", width=3)
        table.add_column("Name", style="green")
        table.add_column("Mode", style="yellow")
        table.add_column("Runs", justify="center", style="magenta")
        table.add_column("Strategy", style="blue")

        for i, stage in enumerate(workflow.stages, 1):
            strategy = stage.iteration_strategy or "-"
            table.add_row(
                str(i), stage.name, stage.mode.value, str(stage.runs), strategy
            )

        console.print(table)

        # Display stats
        console.print("\n[bold]Statistics:[/bold]")
        success_rate = (
            (workflow.success_count / workflow.usage_count * 100)
            if workflow.usage_count > 0
            else 0
        )
        console.print(f"  Total runs: {workflow.usage_count}")
        console.print(f"  Success rate: {success_rate:.1f}%")
        if workflow.last_used_at:
            console.print(f"  Last used: {workflow.last_used_at}")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error showing workflow: {e}[/red]")
        raise typer.Exit(1)


@app.command("run")
def run_workflow(
    workflow_name: str = typer.Argument(..., help="Workflow name or ID"),
    doc_id: Optional[int] = typer.Option(
        None, "--doc", "-d", help="Input document ID"
    ),
    task: Optional[List[str]] = typer.Option(
        None, "--task", "-t", help="Task to run (string or doc ID). Can be specified multiple times."
    ),
    title: Optional[str] = typer.Option(
        None, "--title", help="Custom title for this run (shown in Activity view)"
    ),
    vars: Optional[List[str]] = typer.Option(
        None, "--var", "-v", help="Variables as key=value pairs (override preset)"
    ),
    preset: Optional[str] = typer.Option(
        None, "--preset", "-p", help="Preset name to use for variables"
    ),
    save_as: Optional[str] = typer.Option(
        None,
        "--save-as",
        help="Save this run's variables as a new preset with this name",
    ),
    background: bool = typer.Option(
        False,
        "--background/--foreground",
        help="Run in background (default: foreground)",
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree/--no-worktree",
        help="Create isolated git worktree for this run (recommended for parallel runs)",
    ),
    base_branch: str = typer.Option(
        "main",
        "--base-branch",
        help="Base branch for worktree (only used with --worktree)",
    ),
    keep_worktree: bool = typer.Option(
        False,
        "--keep-worktree",
        help="Don't cleanup worktree after completion (for debugging)",
    ),
    discover: Optional[str] = typer.Option(
        None,
        "--discover",
        help="Override discovery command for dynamic stages (outputs items one per line)",
    ),
    max_concurrent: Optional[int] = typer.Option(
        None,
        "-j",
        "--jobs",
        "-P",
        "--parallel",
        "--max-concurrent",
        help="Override max concurrent executions for parallel/dynamic stages",
    ),
):
    """Run a workflow.

    Use --worktree (-w) when running multiple workflows in parallel to avoid
    git conflicts. Each workflow will get its own isolated worktree.

    Examples:
        # Run multiple tasks in parallel with a workflow
        emdx workflow run task_parallel -t "Analyze auth module" -t "Review tests" -t "Check docs"

        # Use document IDs as tasks (from previous analysis)
        emdx workflow run parallel_fix -t 5182 -t 5183 -t 5184

        # Specify a custom title for the Activity view
        emdx workflow run task_parallel -t "Task 1" -t "Task 2" --title "My Analysis Run"

        # Use worktree isolation for parallel runs that modify files
        emdx workflow run parallel_fix -t "Add type hints" -t "Fix imports" --worktree

        # Specify base branch for worktree
        emdx workflow run parallel_fix -t "Fix bug" --worktree --base-branch develop

        # Limit concurrent executions
        emdx workflow run task_parallel -t "Task 1" -t "Task 2" -t "Task 3" -j 2

        # Use a preset with custom variable overrides
        emdx workflow run task_parallel --preset security_audit --var depth=deep

        # Save current run variables as a new preset
        emdx workflow run task_parallel -t "Review code" --var topic=Performance --save-as perf_review
    """
    worktree_path = None

    try:
        # Try to parse as ID first
        try:
            workflow_id = int(workflow_name)
            workflow = workflow_registry.get_workflow(workflow_id)
        except ValueError:
            workflow = workflow_registry.get_workflow(workflow_name)

        if not workflow:
            console.print(f"[red]Workflow not found: {workflow_name}[/red]")
            raise typer.Exit(1)

        # Parse variables
        variables = {}
        if vars:
            for var in vars:
                if "=" in var:
                    key, value = var.split("=", 1)
                    variables[key.strip()] = value.strip()

        # Parse tasks (can be strings or doc IDs)
        if task:
            tasks = []
            for t in task:
                try:
                    tasks.append(int(t))  # Try as doc ID
                except ValueError:
                    tasks.append(t)  # Use as string
            variables['tasks'] = tasks

        # Create worktree if requested
        worktree_branch = None
        working_dir = None

        if worktree:
            try:
                worktree_path, worktree_branch = create_worktree_for_workflow(base_branch)
                working_dir = worktree_path
                console.print(f"[cyan]Created worktree:[/cyan] {worktree_path}")
                console.print(f"  Branch: {worktree_branch}")
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Failed to create worktree: {e.stderr}[/red]")
                raise typer.Exit(1)

        # Add discovery and max_concurrent overrides to variables
        if discover:
            variables['_discovery_override'] = discover
        if max_concurrent:
            variables['_max_concurrent_override'] = max_concurrent
        variables['base_branch'] = base_branch

        # Store title in input_variables (used by Activity view)
        if title:
            variables['task_title'] = title

        console.print(f"[cyan]Starting workflow:[/cyan] {workflow.display_name}")
        if title:
            console.print(f"  Title: {title}")
        console.print(f"  Stages: {len(workflow.stages)}")
        if doc_id:
            console.print(f"  Input document: #{doc_id}")
        if task:
            console.print(f"  Tasks: {len(task)} task(s)")
        if preset:
            console.print(f"  Preset: {preset}")
        if discover:
            console.print(f"  Discovery command: {discover}")
        if max_concurrent:
            console.print(f"  Max concurrent: {max_concurrent}")
        if variables and any(not k.startswith('_') and k != 'tasks' for k in variables):
            user_vars = {k: v for k, v in variables.items() if not k.startswith('_') and k != 'tasks'}
            if user_vars:
                console.print(f"  Variables: {user_vars}")
        if working_dir:
            console.print(f"  Working dir: {working_dir}")
        if save_as:
            console.print(f"  Will save as preset: {save_as}")

        try:
            # Run workflow
            result = asyncio.run(
                workflow_executor.execute_workflow(
                    workflow_name_or_id=workflow.name,
                    input_doc_id=doc_id,
                    input_variables=variables if variables else None,
                    preset_name=preset,
                    working_dir=working_dir,
                )
            )

            # Display results
            if result.status == "completed":
                console.print(f"\n[green]✓ Workflow completed successfully[/green]")
                console.print(f"  Run ID: #{result.id}")
                console.print(f"  Tokens used: {result.total_tokens_used}")
                console.print(
                    f"  Execution time: {result.total_execution_time_ms / 1000:.2f}s"
                )
                if result.output_doc_ids:
                    console.print(f"  Output documents: {result.output_doc_ids}")

                # Save as preset if requested
                if save_as:
                    try:
                        preset_id = wf_db.create_preset_from_run(
                            run_id=result.id,
                            name=save_as,
                            display_name=save_as.replace("_", " ").replace("-", " ").title(),
                            description=f"Created from run #{result.id}",
                            created_by="cli",
                        )
                        console.print(f"  [green]✓ Saved as preset '{save_as}' (ID: {preset_id})[/green]")
                    except Exception as e:
                        console.print(f"  [yellow]⚠ Failed to save preset: {e}[/yellow]")
            else:
                console.print(f"\n[red]✗ Workflow failed[/red]")
                console.print(f"  Run ID: #{result.id}")
                console.print(f"  Status: {result.status}")
                if result.error_message:
                    console.print(f"  Error: {result.error_message}")
                raise typer.Exit(1)

        finally:
            # Cleanup worktree unless told to keep it
            if worktree_path and not keep_worktree:
                console.print(f"[dim]Cleaning up worktree: {worktree_path}[/dim]")
                cleanup_worktree(worktree_path)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error running workflow: {e}[/red]")
        # Try to cleanup worktree on error
        if worktree_path and not keep_worktree:
            cleanup_worktree(worktree_path)
        raise typer.Exit(1)


@app.command("runs")
def list_runs(
    workflow_name: Optional[str] = typer.Option(
        None, "--workflow", "-w", help="Filter by workflow name or ID"
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status: pending, running, completed, failed, cancelled",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum runs to show"),
):
    """List workflow runs."""
    try:
        # Resolve workflow ID if name provided
        workflow_id = None
        if workflow_name:
            try:
                workflow_id = int(workflow_name)
            except ValueError:
                wf = workflow_registry.get_workflow(workflow_name)
                if wf:
                    workflow_id = wf.id
                else:
                    console.print(f"[red]Workflow not found: {workflow_name}[/red]")
                    raise typer.Exit(1)

        runs = wf_db.list_workflow_runs(
            workflow_id=workflow_id, status=status, limit=limit
        )

        if not runs:
            console.print("[yellow]No workflow runs found[/yellow]")
            return

        table = Table(
            title="Workflow Runs", show_header=True, header_style="bold magenta"
        )
        table.add_column("Run ID", style="cyan", width=8)
        table.add_column("Workflow", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Stage", style="blue")
        table.add_column("Tokens", justify="right", style="magenta")
        table.add_column("Duration", justify="right", style="cyan")
        table.add_column("Started", style="dim")

        for run in runs:
            # Get workflow name
            wf = workflow_registry.get_workflow(run["workflow_id"])
            wf_name = wf.display_name if wf else f"#{run['workflow_id']}"

            # Format status with color
            status_display = run["status"]
            if run["status"] == "completed":
                status_display = "[green]✓ completed[/green]"
            elif run["status"] == "failed":
                status_display = "[red]✗ failed[/red]"
            elif run["status"] == "running":
                status_display = "[yellow]⟳ running[/yellow]"
            elif run["status"] == "cancelled":
                status_display = "[dim]⊘ cancelled[/dim]"

            # Format duration
            duration = "-"
            if run.get("total_execution_time_ms"):
                duration = f"{run['total_execution_time_ms'] / 1000:.1f}s"

            # Format started time
            started = str(run.get("started_at", ""))[:16] if run.get("started_at") else "-"

            table.add_row(
                f"#{run['id']}",
                wf_name,
                status_display,
                run.get("current_stage") or "-",
                str(run.get("total_tokens_used", 0)),
                duration,
                started,
            )

        console.print(table)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error listing runs: {e}[/red]")
        raise typer.Exit(1)


@app.command("status")
def show_run_status(
    run_id: int = typer.Argument(..., help="Workflow run ID"),
):
    """Show detailed status of a workflow run."""
    try:
        run = wf_db.get_workflow_run(run_id)
        if not run:
            console.print(f"[red]Workflow run not found: #{run_id}[/red]")
            raise typer.Exit(1)

        workflow = workflow_registry.get_workflow(run["workflow_id"])
        wf_name = workflow.display_name if workflow else f"Workflow #{run['workflow_id']}"

        # Display run info
        status_color = {
            "completed": "green",
            "failed": "red",
            "running": "yellow",
            "pending": "blue",
            "cancelled": "dim",
        }.get(run["status"], "white")

        console.print(
            Panel(
                f"[bold]{wf_name}[/bold]\n"
                f"Status: [{status_color}]{run['status']}[/{status_color}]\n"
                f"Current stage: {run.get('current_stage') or '-'}",
                title=f"Workflow Run #{run_id}",
                border_style="cyan",
            )
        )

        # Display stage runs
        stage_runs = wf_db.list_stage_runs(run_id)
        if stage_runs:
            console.print("\n[bold]Stage Progress:[/bold]")
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Stage", style="green")
            table.add_column("Mode", style="yellow")
            table.add_column("Progress", style="cyan")
            table.add_column("Status", style="magenta")
            table.add_column("Tokens", justify="right")
            table.add_column("Duration", justify="right")

            for stage in stage_runs:
                progress = f"{stage['runs_completed']}/{stage['target_runs']}"
                duration = (
                    f"{stage['execution_time_ms'] / 1000:.1f}s"
                    if stage.get("execution_time_ms")
                    else "-"
                )

                status_display = stage["status"]
                if stage["status"] == "completed":
                    status_display = "[green]✓[/green]"
                elif stage["status"] == "failed":
                    status_display = "[red]✗[/red]"
                elif stage["status"] == "running":
                    status_display = "[yellow]⟳[/yellow]"

                table.add_row(
                    stage["stage_name"],
                    stage["mode"],
                    progress,
                    status_display,
                    str(stage.get("tokens_used", 0)),
                    duration,
                )

            console.print(table)

        # Display error if failed
        if run.get("error_message"):
            console.print(f"\n[red]Error:[/red] {run['error_message']}")

        # Display output documents
        if run.get("output_doc_ids"):
            output_ids = json.loads(run["output_doc_ids"])
            if output_ids:
                console.print(f"\n[bold]Output Documents:[/bold] {output_ids}")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error showing run status: {e}[/red]")
        raise typer.Exit(1)


@app.command("create")
def create_workflow(
    name: str = typer.Argument(..., help="Unique workflow name"),
    display_name: str = typer.Option(..., "--display-name", "-n", help="Display name"),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Workflow description"
    ),
    category: str = typer.Option(
        "custom",
        "--category",
        "-c",
        help="Category: analysis, planning, implementation, review, custom",
    ),
    from_file: Optional[str] = typer.Option(
        None, "--file", "-f", help="Load definition from JSON file"
    ),
):
    """Create a new workflow."""
    try:
        # Load definition from file or create minimal
        if from_file:
            import json
            from pathlib import Path

            file_path = Path(from_file)
            if not file_path.exists():
                console.print(f"[red]File not found: {from_file}[/red]")
                raise typer.Exit(1)

            with open(file_path) as f:
                definition = json.load(f)
                stages = definition.get("stages", [])
                variables = definition.get("variables", {})
        else:
            # Create a minimal single-stage workflow
            console.print(
                "[yellow]Creating minimal workflow. Use --file to provide full definition.[/yellow]"
            )
            stages = [{"name": "main", "mode": "single", "runs": 1}]
            variables = {}

        workflow = workflow_registry.create_workflow(
            name=name,
            display_name=display_name,
            stages=stages,
            variables=variables,
            description=description,
            category=category,
        )

        console.print(f"[green]✓ Created workflow: {workflow.display_name}[/green]")
        console.print(f"  ID: #{workflow.id}")
        console.print(f"  Stages: {len(workflow.stages)}")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error creating workflow: {e}[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_workflow(
    workflow_name: str = typer.Argument(..., help="Workflow name or ID"),
    hard: bool = typer.Option(
        False, "--hard", help="Permanently delete (cannot be undone)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a workflow."""
    try:
        # Try to parse as ID first
        try:
            workflow_id = int(workflow_name)
            workflow = workflow_registry.get_workflow(workflow_id)
        except ValueError:
            workflow = workflow_registry.get_workflow(workflow_name)

        if not workflow:
            console.print(f"[red]Workflow not found: {workflow_name}[/red]")
            raise typer.Exit(1)

        # Confirm deletion
        if not yes:
            delete_type = "permanently delete" if hard else "deactivate"
            if not Confirm.ask(
                f"Are you sure you want to {delete_type} workflow '{workflow.display_name}'?"
            ):
                console.print("[yellow]Cancelled[/yellow]")
                return

        success = workflow_registry.delete_workflow(workflow.id, hard_delete=hard)

        if success:
            action = "Deleted" if hard else "Deactivated"
            console.print(f"[green]✓ {action} workflow: {workflow.display_name}[/green]")
        else:
            console.print(f"[red]Failed to delete workflow[/red]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error deleting workflow: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Preset Commands
# =============================================================================

@app.command("presets")
def list_presets(
    workflow_name: Optional[str] = typer.Argument(
        None, help="Workflow name or ID (optional, shows all if not specified)"
    ),
):
    """List presets for a workflow (or all presets)."""
    try:
        workflow_id = None
        if workflow_name:
            # Try to parse as ID first
            try:
                workflow_id = int(workflow_name)
                workflow = workflow_registry.get_workflow(workflow_id)
            except ValueError:
                workflow = workflow_registry.get_workflow(workflow_name)

            if not workflow:
                console.print(f"[red]Workflow not found: {workflow_name}[/red]")
                raise typer.Exit(1)

            workflow_id = workflow.id
            console.print(f"[cyan]Presets for workflow:[/cyan] {workflow.display_name}\n")

        presets = wf_db.list_presets(workflow_id=workflow_id)

        if not presets:
            if workflow_name:
                console.print("[dim]No presets found for this workflow[/dim]")
                console.print("[dim]Create one with: emdx workflow preset create <workflow> <name> --var key=value[/dim]")
            else:
                console.print("[dim]No presets found[/dim]")
            return

        # Group by workflow if showing all
        if not workflow_name:
            # Get workflow names for grouping
            workflows_by_id = {}
            for preset in presets:
                wf_id = preset['workflow_id']
                if wf_id not in workflows_by_id:
                    wf = workflow_registry.get_workflow(wf_id)
                    workflows_by_id[wf_id] = wf.display_name if wf else f"Workflow #{wf_id}"

            current_wf = None
            for preset in presets:
                wf_id = preset['workflow_id']
                if wf_id != current_wf:
                    current_wf = wf_id
                    console.print(f"\n[cyan]{workflows_by_id[wf_id]}[/cyan]")

                _print_preset_row(preset)
        else:
            for preset in presets:
                _print_preset_row(preset)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error listing presets: {e}[/red]")
        raise typer.Exit(1)


def _print_preset_row(preset: dict):
    """Print a single preset row."""
    variables = json.loads(preset['variables_json']) if preset.get('variables_json') else {}
    default_marker = " [green]★ default[/green]" if preset.get('is_default') else ""
    usage = f"(used {preset['usage_count']}x)" if preset.get('usage_count', 0) > 0 else ""

    console.print(f"  [bold]{preset['name']}[/bold]{default_marker} {usage}")
    if preset.get('description'):
        console.print(f"    [dim]{preset['description']}[/dim]")
    if variables:
        var_str = ", ".join(f"{k}={v}" for k, v in list(variables.items())[:3])
        if len(variables) > 3:
            var_str += f", ... (+{len(variables) - 3} more)"
        console.print(f"    [dim]Variables: {var_str}[/dim]")


@app.command("preset")
def preset_command(
    action: str = typer.Argument(..., help="Action: create, show, update, delete, from-run"),
    workflow_name: Optional[str] = typer.Argument(None, help="Workflow name or ID"),
    preset_name: Optional[str] = typer.Argument(None, help="Preset name"),
    vars: Optional[List[str]] = typer.Option(
        None, "--var", "-v", help="Variables as key=value pairs"
    ),
    description: Optional[str] = typer.Option(
        None, "--desc", help="Preset description"
    ),
    default: bool = typer.Option(
        False, "--default", help="Set as default preset for this workflow"
    ),
    run_id: Optional[int] = typer.Option(
        None, "--run", "-r", help="Run ID (for from-run action)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Manage workflow presets.

    Actions:
      create    Create a new preset
      show      Show preset details
      update    Update a preset's variables
      delete    Delete a preset
      from-run  Create a preset from a workflow run's variables

    Examples:
      emdx workflow preset create parallel_analysis security_audit --var topic=Security
      emdx workflow preset show parallel_analysis security_audit
      emdx workflow preset from-run parallel_analysis perf_check --run 223
      emdx workflow preset delete parallel_analysis security_audit
    """
    try:
        if action == "create":
            if not workflow_name or not preset_name:
                console.print("[red]Usage: emdx workflow preset create <workflow> <preset_name> --var key=value[/red]")
                raise typer.Exit(1)

            # Get workflow
            workflow = _get_workflow_or_exit(workflow_name)

            # Parse variables
            variables = _parse_variables(vars)

            # Create preset
            display_name = preset_name.replace("_", " ").replace("-", " ").title()
            preset_id = wf_db.create_preset(
                workflow_id=workflow.id,
                name=preset_name,
                display_name=display_name,
                variables=variables,
                description=description,
                is_default=default,
                created_by="cli",
            )

            console.print(f"[green]✓ Created preset '{preset_name}' for {workflow.display_name}[/green]")
            console.print(f"  ID: {preset_id}")
            if variables:
                console.print(f"  Variables: {variables}")

        elif action == "show":
            if not workflow_name or not preset_name:
                console.print("[red]Usage: emdx workflow preset show <workflow> <preset_name>[/red]")
                raise typer.Exit(1)

            workflow = _get_workflow_or_exit(workflow_name)
            preset = wf_db.get_preset_by_name(workflow.id, preset_name)

            if not preset:
                console.print(f"[red]Preset '{preset_name}' not found for workflow '{workflow.name}'[/red]")
                raise typer.Exit(1)

            variables = json.loads(preset['variables_json']) if preset.get('variables_json') else {}

            console.print(f"[bold]{preset['display_name']}[/bold]")
            console.print(f"  Name: {preset['name']}")
            console.print(f"  Workflow: {workflow.display_name}")
            if preset.get('description'):
                console.print(f"  Description: {preset['description']}")
            console.print(f"  Default: {'Yes' if preset.get('is_default') else 'No'}")
            console.print(f"  Usage count: {preset.get('usage_count', 0)}")
            if preset.get('last_used_at'):
                console.print(f"  Last used: {preset['last_used_at']}")
            console.print(f"\n  Variables:")
            for k, v in variables.items():
                console.print(f"    {k}: {v}")

        elif action == "update":
            if not workflow_name or not preset_name:
                console.print("[red]Usage: emdx workflow preset update <workflow> <preset_name> --var key=value[/red]")
                raise typer.Exit(1)

            workflow = _get_workflow_or_exit(workflow_name)
            preset = wf_db.get_preset_by_name(workflow.id, preset_name)

            if not preset:
                console.print(f"[red]Preset '{preset_name}' not found[/red]")
                raise typer.Exit(1)

            # Parse new variables and merge with existing
            new_vars = _parse_variables(vars)
            existing_vars = json.loads(preset['variables_json']) if preset.get('variables_json') else {}
            merged_vars = {**existing_vars, **new_vars} if new_vars else None

            success = wf_db.update_preset(
                preset_id=preset['id'],
                description=description,
                variables=merged_vars,
                is_default=default if default else None,
            )

            if success:
                console.print(f"[green]✓ Updated preset '{preset_name}'[/green]")
            else:
                console.print(f"[red]Failed to update preset[/red]")
                raise typer.Exit(1)

        elif action == "delete":
            if not workflow_name or not preset_name:
                console.print("[red]Usage: emdx workflow preset delete <workflow> <preset_name>[/red]")
                raise typer.Exit(1)

            workflow = _get_workflow_or_exit(workflow_name)
            preset = wf_db.get_preset_by_name(workflow.id, preset_name)

            if not preset:
                console.print(f"[red]Preset '{preset_name}' not found[/red]")
                raise typer.Exit(1)

            if not yes:
                if not Confirm.ask(f"Delete preset '{preset_name}'?"):
                    console.print("[yellow]Cancelled[/yellow]")
                    return

            success = wf_db.delete_preset(preset['id'])
            if success:
                console.print(f"[green]✓ Deleted preset '{preset_name}'[/green]")
            else:
                console.print(f"[red]Failed to delete preset[/red]")
                raise typer.Exit(1)

        elif action == "from-run":
            if not workflow_name or not preset_name:
                console.print("[red]Usage: emdx workflow preset from-run <workflow> <preset_name> --run <run_id>[/red]")
                raise typer.Exit(1)

            if not run_id:
                console.print("[red]--run <run_id> is required for from-run action[/red]")
                raise typer.Exit(1)

            workflow = _get_workflow_or_exit(workflow_name)

            # Verify run belongs to this workflow
            run = wf_db.get_workflow_run(run_id)
            if not run:
                console.print(f"[red]Run #{run_id} not found[/red]")
                raise typer.Exit(1)

            if run['workflow_id'] != workflow.id:
                console.print(f"[red]Run #{run_id} is not from workflow '{workflow.name}'[/red]")
                raise typer.Exit(1)

            preset_id = wf_db.create_preset_from_run(
                run_id=run_id,
                name=preset_name,
                display_name=preset_name.replace("_", " ").replace("-", " ").title(),
                description=description or f"Created from run #{run_id}",
                created_by="cli",
            )

            console.print(f"[green]✓ Created preset '{preset_name}' from run #{run_id}[/green]")
            console.print(f"  ID: {preset_id}")

        else:
            console.print(f"[red]Unknown action: {action}[/red]")
            console.print("[dim]Valid actions: create, show, update, delete, from-run[/dim]")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _get_workflow_or_exit(workflow_name: str):
    """Get workflow by name or ID, exit if not found."""
    try:
        workflow_id = int(workflow_name)
        workflow = workflow_registry.get_workflow(workflow_id)
    except ValueError:
        workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        console.print(f"[red]Workflow not found: {workflow_name}[/red]")
        raise typer.Exit(1)

    return workflow


def _parse_variables(vars: Optional[List[str]]) -> dict:
    """Parse key=value variable list into dict."""
    variables = {}
    if vars:
        for var in vars:
            if "=" in var:
                key, value = var.split("=", 1)
                variables[key.strip()] = value.strip()
    return variables
