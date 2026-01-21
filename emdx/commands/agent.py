"""Run a CLI agent sub-process with EMDX tracking."""

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ..services.unified_executor import ExecutionConfig, UnifiedExecutor

console = Console()


def agent(
    prompt: str = typer.Argument(..., help="Task for the agent"),
    tags: Optional[List[str]] = typer.Option(
        None, "--tags", "-t",
        help="Tags to apply to output (can be comma-separated or multiple -t flags)"
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-T",
        help="Title for the output document"
    ),
    group: Optional[int] = typer.Option(
        None, "--group", "-g",
        help="Group ID to add output to"
    ),
    group_role: str = typer.Option(
        "exploration", "--group-role",
        help="Role in group (primary, exploration, synthesis, variant, member)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show agent output in real-time"
    ),
    create_pr: bool = typer.Option(
        False, "--pr",
        help="Instruct agent to create a PR if it makes code changes"
    ),
    timeout: int = typer.Option(
        300, "--timeout",
        help="Timeout in seconds (default 5 minutes)"
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
    """Run a CLI agent sub-process with automatic EMDX tracking.

    Supports both Claude Code and Cursor Agent CLIs.

    Examples:
        emdx agent "analyze the auth module" --tags analysis
        emdx agent --cli cursor "analyze the auth module"
        emdx agent --cli cursor --model auto "quick task"
    """
    # Flatten tags (handle both comma-separated and multiple -t flags)
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(','))

    doc_title = title or f"Agent: {prompt[:50]}..."

    console.print(f"[cyan]Running agent task...[/cyan]")
    if verbose:
        console.print(f"[dim]Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}[/dim]")

    # Build the save command
    cmd_parts = [f'emdx save --title "{doc_title}"']
    if flat_tags:
        cmd_parts.append(f'--tags "{",".join(flat_tags)}"')
    if group is not None:
        cmd_parts.append(f'--group {group}')
        if group_role != "member":
            cmd_parts.append(f'--group-role {group_role}')

    save_cmd = " ".join(cmd_parts)

    output_instruction = f'''

IMPORTANT: When you complete this task, save your final output/analysis using:
echo "YOUR OUTPUT HERE" | {save_cmd}

Report the document ID that was created.'''

    if create_pr:
        output_instruction += '''

After saving your output, if you made any code changes, create a pull request:
1. Create a new branch with a descriptive name
2. Commit your changes with a clear message
3. Push and create a PR using: gh pr create --title "..." --body "..."
4. Report the PR URL that was created.'''

    config = ExecutionConfig(
        prompt=prompt,
        title=doc_title,
        output_instruction=output_instruction,
        working_dir=str(Path.cwd()),
        timeout_seconds=timeout,
        cli_tool=cli_tool,
        model=model,
        verbose=verbose,
    )

    cli_name = "Cursor" if cli_tool == "cursor" else "Claude"
    console.print(f"[dim]Using {cli_name}[/dim]")

    result = UnifiedExecutor().execute(config)

    if not result.success:
        console.print(f"[red]Agent failed: {result.error_message}[/red]")
        console.print(f"[dim]Log: {result.log_file}[/dim]")
        raise typer.Exit(1)

    if result.output_doc_id:
        console.print(f"[green]✓ Agent completed[/green]")
        console.print(f"  Output: #{result.output_doc_id}")
        if flat_tags:
            console.print(f"  Tags: {', '.join(flat_tags)}")
        if group:
            console.print(f"  Group: #{group} (as {group_role})")
        console.print(f"  Duration: {result.execution_time_ms / 1000:.1f}s")
        console.print(f"  Tokens: {result.tokens_used:,}")
        print(f"doc_id:{result.output_doc_id}")
    else:
        console.print(f"[yellow]Agent completed but no output document found[/yellow]")
        console.print(f"[dim]Log: {result.log_file}[/dim]")
