"""Run a Claude Code sub-agent with EMDX tracking.

This command bridges the gap between human-initiated and AI-initiated work
by ensuring all sub-agent outputs are properly tagged and tracked.

Works the same whether called by a human or an AI agent.

Uses the UnifiedExecutor service for consistent execution behavior
across all EMDX execution paths (agent, workflow, cascade).
"""

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ..services.unified_executor import execute_with_output_tracking

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
):
    """Run a Claude Code sub-agent with automatic EMDX tracking.

    This ensures outputs are properly tagged and grouped, whether
    called by a human or another AI agent. The agent is instructed
    to save its output with the specified metadata.

    Examples:
        emdx agent "Analyze the auth module" --tags analysis,security
        emdx agent "Review error handling" -t refactor -g 123
        emdx agent "Deep dive on caching" -T "Cache Analysis" -t analysis
        emdx agent "Fix the bug in auth" -t bugfix --pr
    """
    # Flatten tags (handle both comma-separated and multiple -t flags)
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(','))

    # Determine title
    doc_title = title or f"Agent: {prompt[:50]}..."

    console.print(f"[cyan]Running agent task...[/cyan]")
    if verbose:
        console.print(f"[dim]Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}[/dim]")

    # Use the unified executor
    result = execute_with_output_tracking(
        prompt=prompt,
        title=doc_title,
        tags=flat_tags if flat_tags else None,
        group_id=group,
        group_role=group_role,
        create_pr=create_pr,
        working_dir=str(Path.cwd()),
        timeout=timeout,
        verbose=verbose,
    )

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

        # Print doc ID on its own line for easy parsing by other agents
        print(f"doc_id:{result.output_doc_id}")
    else:
        console.print(f"[yellow]Agent completed but no output document found[/yellow]")
        console.print(f"[dim]Log: {result.log_file}[/dim]")
