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
)

app = typer.Typer()
console = Console()


@app.command(name="list")
def list_executions(limit: int = typer.Option(20, help="Number of executions to show")):
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
    table.add_column("Duration", style="blue")
    
    for exec in executions:
        status_style = {
            'running': 'yellow',
            'completed': 'green',
            'failed': 'red'
        }.get(exec.status, 'white')
        
        duration = f"{exec.duration:.1f}s" if exec.duration else "-"
        
        table.add_row(
            exec.id[:8] + "...",  # Show first 8 chars of UUID
            exec.doc_title[:40] + "..." if len(exec.doc_title) > 40 else exec.doc_title,
            f"[{status_style}]{exec.status}[/{status_style}]",
            exec.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            duration
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
        table.add_row(
            exec.id[:8] + "...",
            exec.doc_title[:40] + "..." if len(exec.doc_title) > 40 else exec.doc_title,
            exec.started_at.strftime("%Y-%m-%d %H:%M:%S")
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
    
    console.print(f"Started: {execution.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if execution.completed_at:
        console.print(f"Completed: {execution.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        console.print(f"Duration: {execution.duration:.1f} seconds")
    
    if execution.exit_code is not None:
        console.print(f"Exit Code: {execution.exit_code}")
    
    if execution.log_file:
        console.print(f"Log File: {execution.log_file}")
    
    if execution.working_dir:
        console.print(f"Working Dir: {execution.working_dir}")


if __name__ == "__main__":
    app()