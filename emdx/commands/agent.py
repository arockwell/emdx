"""Run a Claude Code sub-agent with EMDX tracking.

This command bridges the gap between human-initiated and AI-initiated work
by ensuring all sub-agent outputs are properly tagged and tracked.

Works the same whether called by a human or an AI agent.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from ..models.executions import create_execution, update_execution_status
from ..workflows.output_parser import extract_output_doc_id, extract_token_usage_detailed
from ..utils.environment import ensure_claude_in_path
from ..services.document_executor import DEFAULT_ALLOWED_TOOLS
from .claude_execute import format_claude_output

console = Console()


def _build_output_instruction(
    title: Optional[str],
    tags: Optional[List[str]],
    group_id: Optional[int],
    group_role: str,
    create_pr: bool = False,
) -> str:
    """Build the output instruction with user's metadata injected."""
    title_str = title or "Agent Output"

    # Build the emdx save command with all options
    cmd_parts = [f'emdx save --title "{title_str}"']

    if tags:
        tag_str = ",".join(tags)
        cmd_parts.append(f'--tags "{tag_str}"')

    if group_id is not None:
        cmd_parts.append(f'--group {group_id}')
        if group_role != "member":
            cmd_parts.append(f'--group-role {group_role}')

    save_cmd = " ".join(cmd_parts)

    instruction = f'''

IMPORTANT: When you complete this task, save your final output/analysis using:
echo "YOUR OUTPUT HERE" | {save_cmd}

Report the document ID that was created.'''

    if create_pr:
        instruction += '''

After saving your output, if you made any code changes, create a pull request:
1. Create a new branch with a descriptive name
2. Commit your changes with a clear message
3. Push and create a PR using: gh pr create --title "..." --body "..."
4. Report the PR URL that was created.'''

    return instruction


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
    ensure_claude_in_path()

    # Flatten tags (handle both comma-separated and multiple -t flags)
    flat_tags = []
    if tags:
        for t in tags:
            flat_tags.extend(t.split(','))

    # Set up logging
    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    log_file = log_dir / f"agent-{timestamp}.log"

    # Create execution record
    exec_id = create_execution(
        doc_id=None,
        doc_title=title or f"Agent: {prompt[:50]}...",
        log_file=str(log_file),
        working_dir=str(Path.cwd()),
    )

    # Build full prompt with output instruction (metadata injected)
    output_instruction = _build_output_instruction(title, flat_tags, group, group_role, create_pr)
    full_prompt = prompt + output_instruction

    # Build command
    cmd = [
        "claude",
        "--print", full_prompt,
        "--allowedTools", ",".join(DEFAULT_ALLOWED_TOOLS),
        "--output-format", "stream-json",
        "--verbose"
    ]

    console.print(f"[cyan]Running agent task...[/cyan]")
    if verbose:
        console.print(f"[dim]Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}[/dim]")

    start_time = time.time()

    try:
        # Run Claude
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(Path.cwd()),
        )

        # Stream output to log (and optionally console)
        with open(log_file, 'w') as log:
            for line in process.stdout:
                formatted = format_claude_output(line, time.time())
                if formatted:
                    log.write(formatted + "\n")
                    log.flush()
                    if verbose:
                        console.print(formatted)

        exit_code = process.wait()
        duration = time.time() - start_time

        # Update execution status
        status = 'completed' if exit_code == 0 else 'failed'
        update_execution_status(exec_id, status, exit_code)

        if exit_code != 0:
            console.print(f"[red]Agent failed (exit code {exit_code})[/red]")
            console.print(f"[dim]Log: {log_file}[/dim]")
            raise typer.Exit(1)

        # Extract output document ID from log
        output_doc_id = extract_output_doc_id(log_file)

        # Get token usage
        usage = extract_token_usage_detailed(log_file)

        if output_doc_id:
            console.print(f"[green]✓ Agent completed[/green]")
            console.print(f"  Output: #{output_doc_id}")
            if flat_tags:
                console.print(f"  Tags: {', '.join(flat_tags)}")
            if group:
                console.print(f"  Group: #{group} (as {group_role})")
            console.print(f"  Duration: {duration:.1f}s")
            console.print(f"  Tokens: {usage.get('total', 0):,}")

            # Print doc ID on its own line for easy parsing by other agents
            print(f"doc_id:{output_doc_id}")
        else:
            console.print(f"[yellow]Agent completed but no output document found[/yellow]")
            console.print(f"[dim]Log: {log_file}[/dim]")

    except FileNotFoundError:
        console.print("[red]Error: claude command not found[/red]")
        console.print("[dim]Make sure Claude Code is installed and in PATH[/dim]")
        raise typer.Exit(1)
