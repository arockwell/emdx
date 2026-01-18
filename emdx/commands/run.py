"""Quick task execution command for EMDX."""

import asyncio
import subprocess
from typing import List, Optional

import typer
from rich.console import Console

from ..workflows.executor import workflow_executor
from .workflows import create_worktree_for_workflow, cleanup_worktree

console = Console()


def run(
    tasks: List[str] = typer.Argument(
        None,
        help="Tasks to run (strings or document IDs)"
    ),
    title: str = typer.Option(
        None, "--title", "-T",
        help="Title for this run (shows in Activity)"
    ),
    jobs: int = typer.Option(
        None, "-j", "--jobs", "-P", "--parallel",
        help="Max parallel tasks (default: auto)"
    ),
    synthesize: bool = typer.Option(
        False, "--synthesize", "-s",
        help="Combine outputs with synthesis stage"
    ),
    preset: str = typer.Option(
        None, "-p", "--preset",
        help="Use a saved preset (prefix with @)"
    ),
    discover: str = typer.Option(
        None, "-d", "--discover",
        help="Shell command to discover tasks"
    ),
    template: str = typer.Option(
        None, "-t", "--template",
        help="Template for discovered tasks (use {{task}})"
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree", "-w",
        help="Create isolated git worktree for execution (recommended for parallel runs)",
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
):
    """Run tasks in parallel with worktree isolation.

    Examples:
        emdx run "analyze auth module"
        emdx run "task1" "task2" "task3"
        emdx run 5350 5351 5352
        emdx run --synthesize "analyze" "review" "plan"
        emdx run -p fix-conflicts
        emdx run -d "gh pr list --json number -q '.[].number'" -t "Fix PR #{{task}}"
    """
    task_list = list(tasks) if tasks else []

    # Handle preset if specified
    if preset:
        from ..presets import get_preset, increment_usage

        preset_name = preset.lstrip('@')
        preset_config = get_preset(preset_name)

        if not preset_config:
            console.print(f"[red]Preset '{preset_name}' not found[/red]")
            raise typer.Exit(1)

        # Apply preset settings
        if preset_config.discover_command and not task_list:
            discover = preset_config.discover_command
        if preset_config.task_template and not template:
            template = preset_config.task_template
        if preset_config.synthesize:
            synthesize = True
        if preset_config.max_jobs and not jobs:
            jobs = preset_config.max_jobs

        # Track usage
        increment_usage(preset_name)

    # Handle discovery if specified
    if discover and not task_list:
        task_list = _run_discovery(discover)

    # Validate we have tasks
    if not task_list:
        console.print("[red]Error: No tasks provided[/red]")
        console.print('Usage: emdx run "task description"')
        console.print('       emdx run -d "discovery command" -t "template {{task}}"')
        raise typer.Exit(1)

    # Apply template if specified
    if template:
        task_list = [template.replace("{{task}}", t) for t in task_list]

    # Create worktree if requested
    worktree_path = None
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

    # Execute
    try:
        asyncio.run(_execute_run(
            tasks=task_list,
            title=title,
            jobs=jobs,
            synthesize=synthesize,
            working_dir=working_dir,
        ))
    finally:
        # Cleanup worktree unless told to keep it
        if worktree_path and not keep_worktree:
            console.print(f"[dim]Cleaning up worktree: {worktree_path}[/dim]")
            cleanup_worktree(worktree_path)


def _run_discovery(command: str) -> List[str]:
    """Run a discovery command and return tasks."""
    console.print(f"[dim]Running discovery: {command}[/dim]")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            console.print(f"[red]Discovery failed: {result.stderr}[/red]")
            raise typer.Exit(1)

        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        console.print(f"[dim]Discovered {len(lines)} tasks[/dim]")
        return lines

    except subprocess.TimeoutExpired:
        console.print("[red]Discovery command timed out after 30s[/red]")
        raise typer.Exit(1)


async def _execute_run(
    tasks: List[str],
    title: Optional[str],
    jobs: Optional[int],
    synthesize: bool,
    working_dir: Optional[str] = None,
):
    """Execute the run using workflow executor."""
    # Prepare variables
    variables = {"tasks": tasks}
    if title:
        variables["task_title"] = title

    # Use task_parallel workflow
    workflow_name = "task_parallel"

    # Override max_concurrent if specified
    if jobs:
        variables["_max_concurrent_override"] = jobs

    # Execute
    console.print(f"[cyan]Running {len(tasks)} task(s)...[/cyan]")
    if working_dir:
        console.print(f"  Working dir: {working_dir}")

    try:
        result = await workflow_executor.execute_workflow(
            workflow_name_or_id=workflow_name,
            input_variables=variables,
            working_dir=working_dir,
        )

        if result.status == "completed":
            console.print(f"[green]✓ Run #{result.id} completed[/green]")
            console.print(f"  Tokens: {result.total_tokens_used:,}")
            if result.output_doc_ids:
                console.print(f"  Outputs: {result.output_doc_ids}")
        else:
            console.print(f"[red]✗ Run #{result.id} failed[/red]")
            if result.error_message:
                console.print(f"  Error: {result.error_message}")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
