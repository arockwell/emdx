"""
Status command - Show consolidated project status.

Provides a quick overview of:
- Ready tasks
- In-progress work
- Recent activity
- Cascade queue
"""

import typer
from datetime import datetime, timedelta
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..database import db
from ..utils.git import get_git_project

console = Console()


def status(
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show additional details"
    ),
):
    """
    Show consolidated project status.

    Displays ready tasks, in-progress work, recent activity,
    and cascade queue status in a single view.

    Examples:
        emdx status
        emdx status --verbose
    """
    project = get_git_project()

    console.print()
    console.print(Panel(
        f"[bold cyan]📊 EMDX Status[/bold cyan]" +
        (f" - [dim]{project}[/dim]" if project else ""),
        expand=False
    ))
    console.print()

    # Ready tasks
    _show_ready_tasks(verbose)

    # In-progress tasks
    _show_in_progress_tasks()

    # Recent activity
    _show_recent_activity(verbose)

    # Cascade status
    _show_cascade_status()

    # Quick tips
    console.print()
    console.print("[dim]Quick commands:[/dim]")
    console.print("  [cyan]emdx task ready[/cyan]      - Full ready task list")
    console.print("  [cyan]emdx task run <id>[/cyan]   - Start working on a task")
    console.print("  [cyan]emdx prime[/cyan]           - Output context for Claude")
    console.print()


def _show_ready_tasks(verbose: bool):
    """Show ready tasks."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.title, t.priority
            FROM tasks t
            WHERE t.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM task_deps td
                JOIN tasks blocker ON td.depends_on = blocker.id
                WHERE td.task_id = t.id AND blocker.status != 'completed'
            )
            ORDER BY t.priority ASC, t.created_at ASC
            LIMIT 7
        """)
        tasks = cursor.fetchall()

        # Count total
        cursor.execute("""
            SELECT COUNT(*)
            FROM tasks t
            WHERE t.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM task_deps td
                JOIN tasks blocker ON td.depends_on = blocker.id
                WHERE td.task_id = t.id AND blocker.status != 'completed'
            )
        """)
        total = cursor.fetchone()[0]

    if tasks:
        console.print(f"[bold green]Ready Tasks[/bold green] ({total} total):")
        for task_id, title, priority in tasks:
            priority_colors = ["red", "yellow", "blue", "dim", "dim"]
            priority_labels = ["P0", "P1", "P2", "P3", "P4"]
            p_idx = min(priority, 4)
            console.print(f"  [cyan]#{task_id}[/cyan] [{priority_colors[p_idx]}]{priority_labels[p_idx]}[/{priority_colors[p_idx]}] {title[:60]}")
        if total > 7:
            console.print(f"  [dim]... and {total - 7} more[/dim]")
        console.print()
    else:
        console.print("[yellow]No ready tasks.[/yellow] Create with [cyan]emdx task create[/cyan]")
        console.print()


def _show_in_progress_tasks():
    """Show in-progress tasks."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, updated_at
            FROM tasks
            WHERE status = 'in_progress'
            ORDER BY updated_at DESC
            LIMIT 5
        """)
        tasks = cursor.fetchall()

    if tasks:
        console.print("[bold yellow]In Progress:[/bold yellow]")
        for task_id, title, updated_at in tasks:
            console.print(f"  [cyan]#{task_id}[/cyan] {title[:60]}")
        console.print()


def _show_recent_activity(verbose: bool):
    """Show recent document activity."""
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Recent documents
        cursor.execute("""
            SELECT id, title, created_at
            FROM documents
            WHERE is_deleted = 0
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent = cursor.fetchall()

    if recent and verbose:
        console.print("[bold blue]Recent Activity:[/bold blue]")
        for doc_id, title, created_at in recent:
            # Format time relative
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    age = datetime.now() - dt.replace(tzinfo=None)
                    if age < timedelta(hours=1):
                        time_str = f"{int(age.seconds / 60)}m ago"
                    elif age < timedelta(days=1):
                        time_str = f"{int(age.seconds / 3600)}h ago"
                    else:
                        time_str = f"{age.days}d ago"
                except:
                    time_str = ""
            else:
                time_str = ""

            title_short = title[:50] + "..." if len(title) > 50 else title
            console.print(f"  [cyan]#{doc_id}[/cyan] {title_short} [dim]{time_str}[/dim]")
        console.print()


def _show_cascade_status():
    """Show cascade queue status."""
    stages = ["idea", "prompt", "analyzed", "planned"]

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cascade_stage, COUNT(*)
                FROM documents
                WHERE cascade_stage IS NOT NULL AND cascade_stage != '' AND cascade_stage != 'done'
                AND is_deleted = 0
                GROUP BY cascade_stage
            """)
            counts = dict(cursor.fetchall())

        total = sum(counts.values())
        if total > 0:
            console.print("[bold magenta]Cascade Queue:[/bold magenta]")
            parts = []
            for stage in stages:
                if counts.get(stage, 0) > 0:
                    parts.append(f"{stage}: {counts[stage]}")
            console.print("  " + " → ".join(parts))
            console.print("  [dim]Run [cyan]emdx cascade process <stage>[/cyan] to advance[/dim]")
            console.print()
    except Exception:
        # cascade_stage column may not exist in older databases
        pass


# Create typer app for the command
app = typer.Typer()
app.command()(status)
