"""Quick task execution command for EMDX."""

import asyncio
import subprocess
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ..workflows.executor import workflow_executor
from .patterns import PATTERN_ALIASES, get_pattern
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
    pattern: str = typer.Option(
        "parallel", "--pattern", "-P",
        help="Workflow pattern: parallel (default), fix (auto-worktree), analyze (auto-synthesize)"
    ),
    list_patterns: bool = typer.Option(
        False, "--list-patterns",
        help="Show available workflow patterns and exit"
    ),
    jobs: int = typer.Option(
        None, "-j", "--jobs", "--parallel",
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

    Pattern examples:
        emdx run "task1" "task2" --pattern parallel    # Uses task_parallel (default)
        emdx run "fix auth" "fix api" --pattern fix    # Uses parallel_fix (auto-worktree)
        emdx run "analyze X" "analyze Y" -P analyze    # Uses parallel_analysis (auto-synthesize)
        emdx run --list-patterns                       # Show available patterns
        emdx run "task" --pattern some_workflow        # Use workflow directly by name
    """
    # Handle --list-patterns flag
    if list_patterns:
        _show_patterns()
        raise typer.Exit(0)

    # Resolve pattern to workflow configuration
    pattern_config = get_pattern(pattern)
    if pattern_config:
        workflow_name = pattern_config.workflow_name
        # Apply auto-settings from pattern
        if pattern_config.auto_worktree and not worktree:
            worktree = True
            console.print(f"[dim]Pattern '{pattern}' auto-enabled worktree[/dim]")
        if pattern_config.auto_synthesize and not synthesize:
            synthesize = True
            console.print(f"[dim]Pattern '{pattern}' auto-enabled synthesize[/dim]")
    else:
        # Pattern name not found in aliases, use it as a direct workflow name
        workflow_name = pattern
        console.print(f"[dim]Using workflow directly: {workflow_name}[/dim]")

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
            workflow_name=workflow_name,
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


def _show_patterns():
    """Display available workflow patterns."""
    table = Table(title="Available Patterns", show_header=True, header_style="bold cyan")
    table.add_column("Pattern", style="green", no_wrap=True)
    table.add_column("Workflow", style="yellow")
    table.add_column("Auto-Settings", style="blue")
    table.add_column("Description", style="white")

    for name, config in PATTERN_ALIASES.items():
        auto_settings = []
        if config.auto_worktree:
            auto_settings.append("worktree")
        if config.auto_synthesize:
            auto_settings.append("synthesize")
        auto_str = ", ".join(auto_settings) if auto_settings else "-"

        table.add_row(name, config.workflow_name, auto_str, config.description)

    console.print(table)
    console.print("\n[dim]Use --pattern <name> or -P <name> to select a pattern.[/dim]")
    console.print("[dim]Unknown patterns are treated as workflow names.[/dim]")


async def _execute_run(
    tasks: List[str],
    title: Optional[str],
    jobs: Optional[int],
    synthesize: bool,
    working_dir: Optional[str] = None,
    workflow_name: str = "task_parallel",
):
    """Execute the run using workflow executor."""
    # Prepare variables
    variables = {"tasks": tasks}
    if title:
        variables["task_title"] = title

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
