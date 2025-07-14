"""CLI commands for managing executions."""

import typer
from rich.console import Console
from rich.table import Table
from typing import Optional

from ..models.executions import (
    get_recent_executions,
    get_execution,
    get_execution_stats,
    get_running_executions,
    update_execution_status,
)

app = typer.Typer()
console = Console()


@app.command(name="list")
def list_executions(limit: int = typer.Option(50, help="Number of executions to show")):
    """List recent executions."""
    executions = get_recent_executions(limit)
    
    if not executions:
        console.print("[yellow]No executions found.[/yellow]")
        return
    
    table = Table(title="Recent Executions")
    table.add_column("ID", style="cyan", width=36)
    table.add_column("Document", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Started", style="green")
    
    for exec in executions:
        status_style = {
            'running': 'yellow',
            'completed': 'green',
            'failed': 'red'
        }.get(exec.status, 'white')
        
        # Format timestamp in local timezone
        local_time = exec.started_at.astimezone()
        formatted_time = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        table.add_row(
            exec.id[:8] + "...",  # Show first 8 chars of UUID
            exec.doc_title[:40] + "..." if len(exec.doc_title) > 40 else exec.doc_title,
            f"[{status_style}]{exec.status}[/{status_style}]",
            formatted_time
        )
    
    console.print(table)


@app.command()
def running():
    """Show currently running executions."""
    executions = get_running_executions()
    
    if not executions:
        console.print("[green]No running executions.[/green]")
        return
    
    table = Table(title="Running Executions")
    table.add_column("ID", style="cyan", width=36)
    table.add_column("Document", style="white")
    table.add_column("Started", style="green")
    
    for exec in executions:
        # Format timestamp in local timezone
        local_time = exec.started_at.astimezone()
        formatted_time = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        table.add_row(
            exec.id[:8] + "...",
            exec.doc_title[:40] + "..." if len(exec.doc_title) > 40 else exec.doc_title,
            formatted_time
        )
    
    console.print(table)
    console.print(f"\n[yellow]Total: {len(executions)} running execution(s)[/yellow]")


@app.command()
def stats():
    """Show execution statistics."""
    stats = get_execution_stats()
    
    console.print("\n[bold]Execution Statistics[/bold]")
    console.print(f"Total executions: {stats['total']}")
    console.print(f"Recent (24h): {stats['recent_24h']}")
    console.print(f"Running: [yellow]{stats['running']}[/yellow]")
    console.print(f"Completed: [green]{stats['completed']}[/green]")
    console.print(f"Failed: [red]{stats['failed']}[/red]")


@app.command()
def show(exec_id: str):
    """Show details of a specific execution."""
    execution = get_execution(exec_id)
    
    if not execution:
        console.print(f"[red]Execution {exec_id} not found.[/red]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold]Execution Details[/bold]")
    console.print(f"ID: [cyan]{execution.id}[/cyan]")
    console.print(f"Document: {execution.doc_title} (ID: {execution.doc_id})")
    
    status_style = {
        'running': 'yellow',
        'completed': 'green',
        'failed': 'red'
    }.get(execution.status, 'white')
    console.print(f"Status: [{status_style}]{execution.status}[/{status_style}]")
    
    # Format timestamps in local timezone
    local_started = execution.started_at.astimezone()
    console.print(f"Started: {local_started.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    if execution.completed_at:
        local_completed = execution.completed_at.astimezone()
        console.print(f"Completed: {local_completed.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    if execution.exit_code is not None:
        console.print(f"Exit Code: {execution.exit_code}")
    
    if execution.log_file:
        console.print(f"Log File: {execution.log_file}")
    
    if execution.working_dir:
        console.print(f"Working Dir: {execution.working_dir}")


@app.command(name="kill")
def kill_execution(exec_id: Optional[str] = typer.Argument(None)):
    """Kill a running execution and mark it as completed.
    
    If no exec_id provided, shows running executions to choose from.
    Use partial exec_id (first 8+ chars) for convenience.
    """
    if not exec_id:
        # Show running executions for user to choose
        executions = get_running_executions()
        
        if not executions:
            console.print("[green]No running executions to kill.[/green]")
            return
        
        console.print("\n[bold]Running Executions:[/bold]")
        for i, exec in enumerate(executions, 1):
            console.print(f"{i}. [cyan]{exec.id[:8]}...[/cyan] - {exec.doc_title}")
        
        console.print(f"\n[dim]Usage: emdx exec kill <exec_id>[/dim]")
        console.print(f"[dim]Example: emdx exec kill {executions[0].id[:8]}[/dim]")
        return
    
    # Find execution by partial or full ID
    all_running = get_running_executions()
    matching_executions = [e for e in all_running if e.id.startswith(exec_id)]
    
    if not matching_executions:
        console.print(f"[red]No running execution found with ID starting with '{exec_id}'[/red]")
        return
    
    if len(matching_executions) > 1:
        console.print(f"[yellow]Multiple executions match '{exec_id}':[/yellow]")
        for exec in matching_executions:
            console.print(f"  [cyan]{exec.id[:8]}...[/cyan] - {exec.doc_title}")
        console.print("[dim]Use more characters to uniquely identify the execution.[/dim]")
        return
    
    execution = matching_executions[0]
    
    # Mark as completed with exit code 130 (interrupted)
    update_execution_status(execution.id, "completed", 130)
    
    console.print(f"[green]✅ Killed execution {execution.id[:8]}...[/green]")
    console.print(f"[dim]Document: {execution.doc_title}[/dim]")
    console.print(f"[dim]Marked as completed with exit code 130 (interrupted)[/dim]")


@app.command(name="killall")
def kill_all_executions():
    """Kill ALL running executions at once."""
    executions = get_running_executions()
    
    if not executions:
        console.print("[green]No running executions to kill.[/green]")
        return
    
    console.print(f"[yellow]About to kill {len(executions)} running execution(s):[/yellow]")
    for exec in executions:
        console.print(f"  [cyan]{exec.id[:8]}...[/cyan] - {exec.doc_title}")
    
    # Ask for confirmation
    confirm = typer.confirm("Are you sure you want to kill all running executions?")
    if not confirm:
        console.print("[yellow]Cancelled.[/yellow]")
        return
    
    # Kill all running executions
    for execution in executions:
        update_execution_status(execution.id, "completed", 130)
    
    console.print(f"[green]✅ Killed {len(executions)} execution(s)[/green]")
    console.print("[dim]All marked as completed with exit code 130 (interrupted)[/dim]")


if __name__ == "__main__":
    app()