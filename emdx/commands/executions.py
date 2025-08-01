"""CLI commands for managing executions."""

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..models.executions import (
    get_execution,
    get_execution_stats,
    get_recent_executions,
    get_running_executions,
    update_execution_status,
)

app = typer.Typer()
console = Console()


def tail_log_subprocess(log_path: Path, follow: bool = False, lines: int = 50) -> None:
    """Tail a log file using system tail command."""
    cmd = ['tail', f'-n{lines}']
    if follow:
        cmd.append('-f')
    cmd.append(str(log_path))
    
    try:
        if follow:
            # Stream output for follow mode
            console.print("\n[dim]Following log file... Press Ctrl+C to stop[/dim]\n")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE, text=True)
            try:
                for line in process.stdout:
                    console.print(line.rstrip())
            except KeyboardInterrupt:
                process.terminate()
                console.print("\n[yellow]Stopped following log[/yellow]")
        else:
            # Get static output
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                console.print(result.stdout)
            else:
                raise FileNotFoundError("tail command failed")
    except (FileNotFoundError, OSError):
        # Fallback to Python implementation
        tail_log_python(log_path, follow, lines)


def tail_log_python(log_path: Path, follow: bool = False, lines: int = 50) -> None:
    """Pure Python log tailing implementation."""
    if not log_path.exists():
        console.print(f"[red]Log file not found: {log_path}[/red]")
        return
    
    # Read last N lines efficiently
    with open(log_path, 'rb') as f:
        # Seek to end and work backwards
        f.seek(0, 2)  # Go to end
        file_size = f.tell()
        
        # Read chunks from end until we have enough lines
        chunk_size = 8192
        chunks = []
        lines_found = 0
        
        while lines_found < lines and f.tell() > 0:
            # Read chunk
            read_size = min(chunk_size, f.tell())
            f.seek(-read_size, 1)
            chunk = f.read(read_size)
            f.seek(-read_size, 1)
            
            # Count lines
            lines_found += chunk.count(b'\n')
            chunks.append(chunk)
        
        # Combine chunks and get last N lines
        content = b''.join(reversed(chunks))
        all_lines = content.decode('utf-8', errors='replace').splitlines()
        display_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        for line in display_lines:
            console.print(line)
    
    # Follow mode
    if follow:
        console.print("\n[dim]Following log file... Press Ctrl+C to stop[/dim]\n")
        with open(log_path, 'r') as f:
            # Seek to end
            f.seek(0, 2)
            
            try:
                while True:
                    line = f.readline()
                    if line:
                        console.print(line.rstrip())
                    else:
                        time.sleep(0.1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopped following log[/yellow]")


def display_execution_metadata(execution) -> None:
    """Display execution metadata in a formatted way."""
    console.print(f"\n[bold]Execution Details[/bold]")
    console.print(f"ID: [cyan]{execution.id}[/cyan]")
    console.print(f"Document: {execution.doc_title} (ID: {execution.doc_id})")
    
    status_style = {
        'running': 'yellow',
        'completed': 'green',
        'failed': 'red'
    }.get(execution.status, 'white')
    
    # Check for zombie process
    if execution.is_zombie:
        console.print(f"Status: [{status_style}]{execution.status}[/{status_style}] [red](process dead - zombie!)[/red]")
    else:
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


@app.command(name="list")
def list_executions(limit: int = typer.Option(50, help="Number of executions to show")):
    """List recent executions."""
    executions = get_recent_executions(limit)
    
    if not executions:
        console.print("[yellow]No executions found.[/yellow]")
        return
    
    table = Table(title="Recent Executions")
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Document", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Started", style="green")
    table.add_column("Worktree", style="dim")
    
    for exec in executions:
        status_style = {
            'running': 'yellow',
            'completed': 'green',
            'failed': 'red'
        }.get(exec.status, 'white')
        
        # Format timestamp in local timezone
        local_time = exec.started_at.astimezone()
        formatted_time = local_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Check for zombie
        status_display = f"[{status_style}]{exec.status}[/{status_style}]"
        if exec.is_zombie:
            status_display += " [red]💀[/red]"
        
        # Extract worktree name from path if available
        worktree = ""
        if exec.working_dir:
            # Get just the last part of the path for display
            worktree_parts = exec.working_dir.split('/')
            if worktree_parts:
                worktree = worktree_parts[-1]
                # Truncate if too long
                if len(worktree) > 30:
                    worktree = worktree[:27] + "..."
        
        table.add_row(
            str(exec.id),  # Show numeric ID
            exec.doc_title[:40] + "..." if len(exec.doc_title) > 40 else exec.doc_title,
            status_display,
            formatted_time,
            worktree
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
def show(
    exec_id: str,
    follow: bool = typer.Option(None, "--follow", "-f", 
                               help="Follow log output (auto for running)"),
    lines: int = typer.Option(50, "--lines", "-n", 
                             help="Number of log lines to show"),
    no_header: bool = typer.Option(False, "--no-header", 
                                  help="Skip metadata, show only logs"),
    full: bool = typer.Option(False, "--full", 
                             help="Show entire log file")
):
    """Show execution details with integrated log viewer."""
    execution = get_execution(exec_id)
    
    if not execution:
        console.print(f"[red]Execution {exec_id} not found.[/red]")
        raise typer.Exit(1)
    
    # Show metadata unless suppressed
    if not no_header:
        display_execution_metadata(execution)
    
    # Handle log display
    if execution.log_file:
        log_path = Path(execution.log_file)
        
        if not log_path.exists():
            console.print("\n[yellow]Log file not yet created[/yellow]")
            if execution.is_running:
                console.print("[dim]Execution just started, waiting for log...[/dim]")
            return
        
        # Determine display mode
        if full:
            # Show entire log file
            console.print(f"\n[bold]📋 Full Execution Log:[/bold]\n")
            with open(log_path, 'r') as f:
                console.print(f.read())
        else:
            # Auto-follow for running executions unless explicitly disabled
            should_follow = follow if follow is not None else execution.is_running
            
            if should_follow and execution.is_running:
                console.print(f"\n[bold]📋 Following Execution Log:[/bold]")
                tail_log_subprocess(log_path, follow=True, lines=lines)
            else:
                console.print(f"\n[bold]📋 Execution Log (last {lines} lines):[/bold]\n")
                tail_log_subprocess(log_path, follow=False, lines=lines)


@app.command()
def logs(
    exec_id: str,
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show")
):
    """Show only the logs for an execution (no metadata)."""
    show(exec_id, follow=follow, lines=lines, no_header=True, full=False)


@app.command()
def tail(exec_id: str):
    """Follow the log of a running execution (alias for show -f)."""
    show(exec_id, follow=True)


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


@app.command(name="health")
def execution_health():
    """Show detailed health status of running executions."""
    import psutil

    from ..services.execution_monitor import ExecutionMonitor
    
    monitor = ExecutionMonitor()
    running = get_running_executions()
    
    if not running:
        console.print("[green]No running executions.[/green]")
        return
    
    # Get metrics first
    metrics = monitor.get_execution_metrics()
    
    # Show summary
    console.print(Panel(
        f"[bold]Execution Health Status[/bold]\n"
        f"Running: [cyan]{metrics['currently_running']}[/cyan] | "
        f"Unhealthy: [red]{metrics['unhealthy_running']}[/red] | "
        f"Failure Rate: [yellow]{metrics['failure_rate_percent']:.1f}%[/yellow]",
        box=box.ROUNDED
    ))
    
    # Create health table
    table = Table(title="Running Executions Health Check")
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Document", style="white")
    table.add_column("PID", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Runtime", style="green")
    table.add_column("Health", style="bold")
    
    for exec in running:
        health = monitor.check_process_health(exec)
        
        # Format runtime
        runtime = (datetime.now(timezone.utc) - exec.started_at).total_seconds()
        if runtime > 3600:
            runtime_str = f"{runtime/3600:.1f}h"
        else:
            runtime_str = f"{runtime/60:.0f}m"
        
        # Determine health status
        if health['is_zombie']:
            health_status = "[red]ZOMBIE[/red]"
        elif not health['process_exists'] and exec.pid:
            health_status = "[red]DEAD[/red]"
        elif health['is_stale']:
            health_status = "[yellow]STALE[/yellow]"
        elif health['is_running']:
            health_status = "[green]HEALTHY[/green]"
        else:
            health_status = "[yellow]UNKNOWN[/yellow]"
        
        # Process status
        if exec.pid:
            try:
                proc = psutil.Process(exec.pid)
                cpu = proc.cpu_percent(interval=0.1)
                mem = proc.memory_info().rss / 1024 / 1024  # MB
                proc_status = f"CPU: {cpu:.0f}% MEM: {mem:.0f}MB"
            except:
                proc_status = "N/A"
        else:
            proc_status = "No PID"
        
        table.add_row(
            str(exec.id),
            exec.doc_title[:30] + "..." if len(exec.doc_title) > 30 else exec.doc_title,
            str(exec.pid) if exec.pid else "-",
            proc_status,
            runtime_str,
            health_status
        )
    
    console.print(table)
    
    # Show recommendations if there are unhealthy executions
    if metrics['unhealthy_running'] > 0:
        console.print("\n[yellow]⚠ Found unhealthy executions![/yellow]")
        console.print("Run [cyan]emdx maintain cleanup --executions --execute[/cyan] to clean up")


@app.command(name="monitor")
def monitor_executions(
    interval: int = typer.Option(5, "--interval", "-i", help="Refresh interval in seconds"),
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f/-F", help="Continuously monitor")
):
    """Monitor execution status in real-time."""
    import psutil

    from ..services.execution_monitor import ExecutionMonitor
    
    monitor = ExecutionMonitor()
    
    try:
        while True:
            # Clear screen for better display
            if follow:
                console.clear()
            
            # Get current executions
            running = get_running_executions()
            
            # Header
            console.print(f"[bold]📊 Execution Monitor[/bold] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            console.print("-" * 80)
            
            if not running:
                console.print("[dim]No running executions[/dim]")
            else:
                # Create monitoring table
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("ID", width=6)
                table.add_column("Document", width=30)
                table.add_column("Runtime", width=10)
                table.add_column("CPU %", width=8)
                table.add_column("Memory", width=10)
                table.add_column("Status", width=15)
                
                for exec in running:
                    # Get process info
                    cpu_str = "-"
                    mem_str = "-"
                    status_str = "[yellow]Unknown[/yellow]"
                    
                    if exec.pid:
                        try:
                            proc = psutil.Process(exec.pid)
                            cpu = proc.cpu_percent(interval=0.1)
                            mem_mb = proc.memory_info().rss / 1024 / 1024
                            cpu_str = f"{cpu:.1f}"
                            mem_str = f"{mem_mb:.0f} MB"
                            
                            # Check health
                            health = monitor.check_process_health(exec)
                            if health['is_zombie']:
                                status_str = "[red]Zombie[/red]"
                            elif health['is_running']:
                                status_str = "[green]Running[/green]"
                            else:
                                status_str = "[yellow]Unknown[/yellow]"
                                
                        except psutil.NoSuchProcess:
                            status_str = "[red]Dead[/red]"
                        except psutil.AccessDenied:
                            status_str = "[dim]No Access[/dim]"
                    
                    # Calculate runtime
                    runtime = (datetime.now(timezone.utc) - exec.started_at).total_seconds()
                    runtime_str = f"{int(runtime/60)}:{int(runtime%60):02d}"
                    
                    # Add row
                    table.add_row(
                        str(exec.id),
                        exec.doc_title[:30] + "..." if len(exec.doc_title) > 30 else exec.doc_title,
                        runtime_str,
                        cpu_str,
                        mem_str,
                        status_str
                    )
                
                console.print(table)
            
            if not follow:
                break
            
            # Wait for next update
            console.print(f"\n[dim]Refreshing every {interval} seconds. Press Ctrl+C to stop.[/dim]")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped[/yellow]")


if __name__ == "__main__":
    app()
