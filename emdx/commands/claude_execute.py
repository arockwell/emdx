"""Execute EMDX documents with Claude Code.

CLI commands for document execution. The core execution logic has been
extracted to services/claude_executor.py to break bidirectional dependencies.
"""

import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..models.documents import get_document
from ..models.executions import (
    Execution,
    update_execution_status,
)
from ..utils.environment import validate_execution_environment

# Re-export from services for backward compatibility
from ..services.claude_executor import (
    ExecutionType,
    DEFAULT_ALLOWED_TOOLS,
    STAGE_TOOLS,
    TOOL_EMOJIS,
    EXECUTION_TYPE_EMOJIS,
    generate_unique_execution_id,
    get_execution_context,
    parse_task_content,
    format_timestamp,
    parse_log_timestamp,
    format_claude_output,
    validate_environment,
    execute_with_claude_detached,
    execute_with_claude,
    create_execution_worktree,
    execute_document_smart_background,
    execute_document_smart,
    monitor_execution_detached,
    monitor_execution,
)

app = typer.Typer(name="claude", help="Execute documents with Claude")
console = Console()


@app.command(name="check-env")
def check_environment(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed environment info")
):
    """Check if the execution environment is properly configured."""
    console.print("[bold]Checking EMDX execution environment...[/bold]\n")

    # Use the comprehensive validation
    is_valid, env_info = validate_execution_environment(verbose=True)

    # Additional quick checks
    console.print("\n[bold]Quick Status:[/bold]")
    checks = [
        ("Python", lambda: sys.version.split()[0]),
        ("Claude Code", lambda: "✓" if shutil.which("claude") else "✗"),
        ("Git", lambda: "✓" if shutil.which("git") else "✗"),
        ("EMDX", lambda: "✓" if shutil.which("emdx") else "✗"),
    ]

    for name, check_func in checks:
        try:
            result = check_func()
            if result and result != "✗":
                console.print(f"  {name}: [green]{result}[/green]")
            else:
                console.print(f"  {name}: [red]Not found[/red]")
        except Exception:
            console.print(f"  {name}: [red]Error[/red]")

    # Show PATH info if verbose
    if verbose:
        console.print(f"\n[dim]PATH entries: {len(os.environ.get('PATH', '').split(os.pathsep))}[/dim]")
        console.print(f"[dim]Installation: {env_info.get('info', {}).get('installation', 'unknown')}[/dim]")

    # Overall result
    if is_valid:
        console.print("\n[bold green]✅ Environment is properly configured![/bold green]")
        console.print("[dim]You can run executions without issues.[/dim]")
    else:
        console.print("\n[bold red]❌ Environment issues detected[/bold red]")
        console.print("[dim]Please fix the issues above before running executions.[/dim]")

        # Suggest fixes
        if env_info and env_info.get('errors'):
            console.print("\n[yellow]Suggested fixes:[/yellow]")
            for error in env_info['errors']:
                if "claude" in error.lower():
                    console.print("  • Install Claude Code: https://github.com/anthropics/claude-code")
                elif "git" in error.lower():
                    console.print("  • Install Git: https://git-scm.com/")
                elif "python" in error.lower():
                    console.print("  • Upgrade Python to 3.8 or later")


@app.command()
def execute(
    doc_id: str = typer.Argument(..., help="Document ID to execute"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t",
                                        help="Comma-separated list of allowed tools"),
    smart: bool = typer.Option(True, "--smart/--no-smart",
                              help="Use smart context-aware execution"),
    exec_id: Optional[int] = typer.Option(None, "--exec-id",
                                          help="Use existing execution ID from database")
):
    """Execute a document with Claude Code."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Parse allowed tools
    allowed_tools = tools.split(",") if tools else None

    # Handle execution ID and log file
    if exec_id:
        # Use provided execution ID from database
        from ..models.executions import get_execution
        existing_exec = get_execution(exec_id)
        if not existing_exec:
            console.print(f"[red]Execution #{exec_id} not found[/red]")
            raise typer.Exit(1)

        # Use the existing log file path
        log_file = Path(existing_exec.log_file)
        execution_id = f"claude-{doc['id']}-{exec_id}"  # Keep simple for backward compat
        console.print(f"[yellow]Using existing execution #{exec_id}[/yellow]")
    else:
        # Generate new execution ID with guaranteed uniqueness
        execution_id = generate_unique_execution_id(doc['id'])

        # Set up log file
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_file = log_dir / f"{execution_id}.log"



    if smart:
        # Get document tags
        from ..models.tags import get_document_tags
        doc_tags = get_document_tags(doc_id)

        # Use smart execution
        if background:
            console.print("[green]Starting smart execution in background...[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")

            # Get execution context to show what will happen
            context = get_execution_context(doc_tags)
            exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
            exec_type = context['type'].value.upper()
            console.print(f"[bold cyan]{exec_emoji} {exec_type} EXECUTION[/bold cyan]")
            console.print(f"[cyan]📋 {context['description']}[/cyan]")

            # Execute in background without blocking
            execute_document_smart_background(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                use_stage_tools=True,
                db_exec_id=exec_id
            )

            console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
        else:
            # Run smart execution in foreground
            execute_document_smart(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                verbose=True,
                background=False
            )
    else:
        # Legacy execution mode - use default tools if none specified
        if allowed_tools is None:
            allowed_tools = DEFAULT_ALLOWED_TOOLS

        if background:
            # Run in background thread
            console.print("[green]Starting execution in background...[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")

            # Execute in background without blocking
            monitor_execution_detached(
                execution_id=execution_id,
                task=doc['content'],
                doc_id=str(doc['id']),
                doc_title=doc['title'],
                log_file=log_file,
                allowed_tools=allowed_tools
            )

            console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
        else:
            # Run in foreground
            console.print(f"[green]Executing document #{doc_id}: {doc['title']}[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")
            console.print()

            # Create worktree for execution
            worktree_path = create_execution_worktree(execution_id, doc['title'])
            working_dir = str(worktree_path) if worktree_path else os.getcwd()

            # Create execution record
            execution = Execution(
                id=execution_id,
                doc_id=int(doc_id),
                doc_title=doc['title'],
                status="running",
                started_at=datetime.now(timezone.utc),
                log_file=str(log_file),
                working_dir=working_dir
            )

            # Execute in worktree
            exit_code = execute_with_claude(
                task=doc['content'],
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                verbose=True,
                working_dir=working_dir,
                doc_id=doc_id,
                context=None  # Direct execution - no context analysis
            )

            # Update status
            status = "completed" if exit_code == 0 else "failed"
            update_execution_status(execution_id, status, exit_code)

            if exit_code != 0:
                raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
