"""Quick task execution command for EMDX."""

import asyncio
import subprocess
from typing import List, Optional

import typer

from ..utils.output import console
from ..workflows.executor import workflow_executor
from .workflows import create_worktree_for_workflow, cleanup_worktree


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
    discover: str = typer.Option(
        None, "-d", "--discover",
        help="Shell command to discover tasks"
    ),
    template: str = typer.Option(
        None, "-t", "--template",
        help="Template for discovered tasks (use {{item}})"
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree", "-w",
        help="Create isolated git worktree for execution (recommended for parallel fixes)",
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
    cli_tool: str = typer.Option(
        "claude",
        "--cli", "-C",
        help="CLI tool to use: claude or cursor",
    ),
    model: str = typer.Option(
        None,
        "--model", "-m",
        help="Model to use (overrides CLI default)",
    ),
):
    """Run tasks in parallel.

    Examples:
        emdx run "analyze auth module"
        emdx run "task1" "task2" "task3"
        emdx run 5350 5351 5352
        emdx run --synthesize "analyze" "review" "plan"
        emdx run -d "gh pr list --json number -q '.[].number'" -t "Fix PR #{{item}}"
        emdx run --worktree "fix X" "fix Y"   # Isolated git worktree
        emdx run --cli cursor "analyze code"  # Use Cursor instead of Claude

    For reusable commands with saved discovery+templates, use `emdx each` instead.
    """
    task_list = list(tasks) if tasks else []

    # Handle discovery if specified
    if discover and not task_list:
        task_list = _run_discovery(discover)

    # Validate we have tasks
    if not task_list:
        console.print("[red]Error: No tasks provided[/red]")
        console.print('Usage: emdx run "task description"')
        console.print('       emdx run -d "discovery command" -t "template {{item}}"')
        raise typer.Exit(1)

    # Apply template if specified
    if template:
        # Support both {{item}} (preferred) and {{task}} (deprecated)
        task_list = [
            template.replace("{{item}}", t).replace("{{task}}", t)
            for t in task_list
        ]

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
            cli_tool=cli_tool,
            model=model,
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
    cli_tool: str = "claude",
    model: Optional[str] = None,
):
    """Execute the run using workflow executor."""
    # Prepare variables
    variables = {"tasks": tasks}
    if title:
        variables["task_title"] = title

    # Override max_concurrent if specified
    if jobs:
        variables["_max_concurrent_override"] = jobs

    # Pass CLI tool and model to workflow
    if cli_tool != "claude":
        variables["_cli_tool"] = cli_tool
    if model:
        variables["_model"] = model

    # Execute
    cli_name = "Cursor" if cli_tool == "cursor" else "Claude"
    console.print(f"[cyan]Running {len(tasks)} task(s) with {cli_name}...[/cyan]")
    if working_dir:
        console.print(f"  Working dir: {working_dir}")

    try:
        result = await workflow_executor.execute_workflow(
            workflow_name_or_id="task_parallel",
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
