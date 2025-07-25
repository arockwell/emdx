"""CLI commands for cleanup operations."""

import os
import signal
import subprocess
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from ..models.executions import (
    get_running_executions,
    update_execution_status,
)
from ..database.connection import db_connection

app = typer.Typer()
console = Console()


@app.command(name="branches")
def cleanup_branches(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting"),
    force: bool = typer.Option(False, "--force", "-f", help="Force delete without confirmation"),
    pattern: str = typer.Option("exec-*", "--pattern", help="Branch name pattern to match"),
):
    """Clean up execution branches.
    
    Finds and deletes git branches created by EMDX executions.
    By default, only deletes merged branches. Use --force to delete all matching branches.
    """
    try:
        # Get all branches
        result = subprocess.run(
            ["git", "branch", "-a"],
            capture_output=True,
            text=True,
            check=True
        )
        
        all_branches = result.stdout.strip().split('\n')
        exec_branches = []
        
        # Filter execution branches
        for branch in all_branches:
            branch = branch.strip()
            if branch.startswith('*'):
                branch = branch[2:]  # Remove current branch marker
            
            # Check if branch matches pattern
            import fnmatch
            if fnmatch.fnmatch(branch, pattern):
                exec_branches.append(branch)
        
        if not exec_branches:
            console.print(f"[green]No branches matching pattern '{pattern}' found.[/green]")
            return
        
        # Check which branches are merged
        merged_result = subprocess.run(
            ["git", "branch", "--merged"],
            capture_output=True,
            text=True,
            check=True
        )
        merged_branches = {b.strip().lstrip('* ') for b in merged_result.stdout.strip().split('\n')}
        
        # Create table
        table = Table(title=f"Execution Branches (pattern: {pattern})")
        table.add_column("Branch", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Action", style="yellow")
        
        branches_to_delete = []
        
        for branch in exec_branches:
            is_merged = branch in merged_branches
            status = "[green]Merged[/green]" if is_merged else "[yellow]Not merged[/yellow]"
            
            if is_merged or force:
                action = "[red]Delete[/red]" if not dry_run else "[dim]Would delete[/dim]"
                branches_to_delete.append(branch)
            else:
                action = "[dim]Keep (not merged)[/dim]"
            
            table.add_row(branch, status, action)
        
        console.print(table)
        
        if not branches_to_delete:
            console.print("\n[yellow]No branches to delete.[/yellow]")
            return
        
        if dry_run:
            console.print(f"\n[yellow]Dry run: Would delete {len(branches_to_delete)} branch(es)[/yellow]")
            return
        
        # Confirm deletion
        if not force:
            confirm = typer.confirm(f"Delete {len(branches_to_delete)} branch(es)?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                return
        
        # Delete branches
        deleted = 0
        failed = 0
        
        for branch in branches_to_delete:
            try:
                # Use -D for force delete if --force flag is set
                delete_flag = "-D" if force else "-d"
                subprocess.run(
                    ["git", "branch", delete_flag, branch],
                    capture_output=True,
                    text=True,
                    check=True
                )
                deleted += 1
            except subprocess.CalledProcessError as e:
                console.print(f"[red]Failed to delete {branch}: {e.stderr.strip()}[/red]")
                failed += 1
        
        console.print(f"\n[green]✅ Deleted {deleted} branch(es)[/green]")
        if failed:
            console.print(f"[red]❌ Failed to delete {failed} branch(es)[/red]")
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Git error: {e.stderr.strip() if e.stderr else str(e)}[/red]")
        raise typer.Exit(1)


@app.command(name="processes")
def cleanup_processes(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be killed without killing"),
    force: bool = typer.Option(False, "--force", "-f", help="Force kill without confirmation"),
):
    """Clean up EMDX-related processes.
    
    Finds and kills zombie/stuck processes from failed executions.
    """
    # Get all running executions from database
    running_executions = get_running_executions()
    
    if not running_executions:
        console.print("[green]No running executions in database.[/green]")
        return
    
    # Check which processes are actually alive
    table = Table(title="EMDX Processes")
    table.add_column("Exec ID", style="cyan", width=10)
    table.add_column("PID", style="white")
    table.add_column("Document", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Action", style="yellow")
    
    zombies = []
    alive = []
    
    for exec in running_executions:
        if exec.pid:
            # Check if process exists
            try:
                # Send signal 0 to check if process exists
                os.kill(exec.pid, 0)
                status = "[green]Alive[/green]"
                alive.append(exec)
                action = "[dim]Keep[/dim]" if not force else "[red]Kill[/red]"
            except ProcessLookupError:
                status = "[red]Zombie (dead)[/red]"
                zombies.append(exec)
                action = "[red]Clean up[/red]" if not dry_run else "[dim]Would clean[/dim]"
            except PermissionError:
                status = "[yellow]No permission[/yellow]"
                action = "[dim]Skip[/dim]"
        else:
            status = "[yellow]No PID[/yellow]"
            zombies.append(exec)  # Treat as zombie if no PID
            action = "[red]Clean up[/red]" if not dry_run else "[dim]Would clean[/dim]"
        
        table.add_row(
            str(exec.id)[:8] + "...",
            str(exec.pid) if exec.pid else "N/A",
            exec.doc_title[:30] + "..." if len(exec.doc_title) > 30 else exec.doc_title,
            status,
            action
        )
    
    console.print(table)
    
    # Determine what to clean
    to_clean = zombies
    if force:
        to_clean = zombies + alive
    
    if not to_clean:
        console.print("\n[yellow]No processes to clean up.[/yellow]")
        return
    
    if dry_run:
        console.print(f"\n[yellow]Dry run: Would clean {len(to_clean)} process(es)[/yellow]")
        return
    
    # Confirm cleanup
    if not force and to_clean:
        confirm = typer.confirm(f"Clean up {len(to_clean)} process(es)?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return
    
    # Clean up processes
    cleaned = 0
    failed = 0
    
    for exec in to_clean:
        try:
            # Try to kill process if it has a PID and is alive
            if exec.pid and exec in alive:
                try:
                    os.kill(exec.pid, signal.SIGTERM)
                    console.print(f"[yellow]Sent SIGTERM to PID {exec.pid}[/yellow]")
                except (ProcessLookupError, PermissionError):
                    pass  # Process already dead or no permission
            
            # Update database status
            update_execution_status(exec.id, "failed", 137)  # 137 = killed
            cleaned += 1
            
        except Exception as e:
            console.print(f"[red]Failed to clean {exec.id}: {e}[/red]")
            failed += 1
    
    console.print(f"\n[green]✅ Cleaned {cleaned} process(es)[/green]")
    if failed:
        console.print(f"[red]❌ Failed to clean {failed} process(es)[/red]")


@app.command(name="executions")
def cleanup_executions(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be cleaned without cleaning"),
    timeout_minutes: int = typer.Option(30, "--timeout", help="Consider execution stuck after N minutes"),
    force: bool = typer.Option(False, "--force", "-f", help="Force cleanup without confirmation"),
):
    """Clean up stuck executions in database.
    
    Finds executions marked as 'running' that are likely stuck or abandoned,
    and marks them as 'failed' with a timeout reason.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        
        # Find stuck executions
        cursor.execute("""
            SELECT id, doc_id, doc_title, started_at, pid
            FROM executions
            WHERE status = 'running'
            AND datetime(started_at) < datetime('now', '-{} minutes')
            ORDER BY started_at DESC
        """.format(timeout_minutes))
        
        stuck_executions = cursor.fetchall()
        
        if not stuck_executions:
            console.print(f"[green]No executions older than {timeout_minutes} minutes found.[/green]")
            return
        
        # Create table
        table = Table(title=f"Stuck Executions (running > {timeout_minutes} minutes)")
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Document", style="white")
        table.add_column("Started", style="yellow")
        table.add_column("PID", style="white")
        table.add_column("Process", style="bold")
        table.add_column("Action", style="red")
        
        for exec_id, doc_id, doc_title, started_at, pid in stuck_executions:
            # Check if process is alive
            process_status = "Unknown"
            if pid:
                try:
                    os.kill(pid, 0)
                    process_status = "[green]Alive[/green]"
                except ProcessLookupError:
                    process_status = "[red]Dead[/red]"
                except PermissionError:
                    process_status = "[yellow]No access[/yellow]"
            else:
                process_status = "[dim]No PID[/dim]"
            
            action = "[red]Mark failed[/red]" if not dry_run else "[dim]Would mark failed[/dim]"
            
            table.add_row(
                str(exec_id),
                doc_title[:30] + "..." if len(doc_title) > 30 else doc_title,
                started_at,
                str(pid) if pid else "N/A",
                process_status,
                action
            )
        
        console.print(table)
        
        if dry_run:
            console.print(f"\n[yellow]Dry run: Would mark {len(stuck_executions)} execution(s) as failed[/yellow]")
            return
        
        # Confirm cleanup
        if not force:
            confirm = typer.confirm(f"Mark {len(stuck_executions)} execution(s) as failed?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                return
        
        # Update executions
        cleaned = 0
        for exec_id, _, _, _, _ in stuck_executions:
            try:
                update_execution_status(exec_id, "failed", 124)  # 124 = timeout
                cleaned += 1
            except Exception as e:
                console.print(f"[red]Failed to update execution {exec_id}: {e}[/red]")
        
        console.print(f"\n[green]✅ Marked {cleaned} execution(s) as failed (timeout)[/green]")


@app.command()
def all(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be cleaned without cleaning"),
    force: bool = typer.Option(False, "--force", "-f", help="Force cleanup without confirmation"),
):
    """Run all cleanup operations.
    
    Runs cleanup for branches, processes, and executions in sequence.
    """
    console.print("[bold cyan]🧹 Running comprehensive EMDX cleanup...[/bold cyan]\n")
    
    # Clean executions first (updates database)
    console.print("[bold]1. Cleaning stuck executions...[/bold]")
    cleanup_executions(dry_run=dry_run, force=force)
    console.print()
    
    # Clean processes (kills zombies)
    console.print("[bold]2. Cleaning zombie processes...[/bold]")
    cleanup_processes(dry_run=dry_run, force=force)
    console.print()
    
    # Clean branches last (removes git branches)
    console.print("[bold]3. Cleaning execution branches...[/bold]")
    cleanup_branches(dry_run=dry_run, force=force)
    
    console.print("\n[bold green]✅ Cleanup complete![/bold green]")


if __name__ == "__main__":
    app()