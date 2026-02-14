"""
Status command - Show delegate activity index and project status.

Provides a quick overview of:
- Active delegate tasks (running now)
- Recent completed tasks
- Failed tasks (with retry hints)
- Cascade queue
"""

import typer
from datetime import datetime, timedelta
from typing import Optional

import sqlite3

from rich.console import Console
from rich.text import Text

from ..database import db
from ..models.tasks import (
    get_active_delegate_tasks,
    get_children,
    get_failed_tasks,
    get_recent_completed_tasks,
)

console = Console()


def _parse_timestamp(value) -> Optional[datetime]:
    """Parse a timestamp that may be a datetime, string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        # Invalid datetime string format
        return None


def _relative_time(timestamp) -> str:
    """Format a timestamp as relative time (e.g. '4m ago', '2h ago')."""
    dt = _parse_timestamp(timestamp)
    if dt is None:
        return ""
    age = datetime.utcnow() - dt
    if age.total_seconds() < 0:
        return "just now"
    if age < timedelta(minutes=1):
        return f"{int(age.total_seconds())}s ago"
    if age < timedelta(hours=1):
        return f"{int(age.total_seconds() / 60)}m ago"
    if age < timedelta(days=1):
        return f"{int(age.total_seconds() / 3600)}h ago"
    return f"{age.days}d ago"


def _running_duration(timestamp) -> str:
    """Format how long something has been running."""
    dt = _parse_timestamp(timestamp)
    if dt is None:
        return ""
    age = datetime.utcnow() - dt
    if age.total_seconds() < 0:
        return "0s"
    total_secs = int(age.total_seconds())
    if total_secs < 60:
        return f"{total_secs}s"
    mins = total_secs // 60
    secs = total_secs % 60
    if mins < 60:
        return f"{mins}m{secs:02d}s"
    hours = mins // 60
    mins = mins % 60
    return f"{hours}h{mins:02d}m"


def _show_active_tasks():
    """Show active delegate tasks with children."""
    active = get_active_delegate_tasks()
    if not active:
        return

    console.print(f"[bold yellow]⚡ Active ({len(active)})[/bold yellow]")
    for task in active:
        task_type = task.get("type", "single")
        title = task.get("title", "")[:50]
        task_id = task["id"]
        duration = _running_duration(task.get("created_at"))

        if task_type in ("group", "chain"):
            child_count = task.get("child_count", 0)
            children_done = task.get("children_done", 0)
            children_active = task.get("children_active", 0)
            progress = f"step {children_done + 1}/{child_count}" if child_count else ""
            console.print(
                f"  [cyan]#{task_id}[/cyan]  {task_type:<7} "
                f'"{title}"  {progress}  {duration}'
            )

            # Show children
            children = get_children(task_id)
            for i, child in enumerate(children):
                is_last = i == len(children) - 1
                prefix = "└─" if is_last else "├─"
                child_status = child.get("status", "open")
                child_title = child.get("title", "")[:40]
                child_id = child["id"]
                out_doc = child.get("output_doc_id")

                if child_status == "done":
                    doc_ref = f"→ doc #{out_doc}" if out_doc else ""
                    time_ref = _relative_time(child.get("completed_at"))
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f"[green]done[/green]    \"{child_title}\"  "
                        f"[dim]{doc_ref}  {time_ref}[/dim]"
                    )
                elif child_status == "active":
                    dur = _running_duration(child.get("updated_at") or child.get("created_at"))
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f"[yellow]active[/yellow]  \"{child_title}\"  "
                        f"running {dur}"
                    )
                elif child_status == "failed":
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f"[red]failed[/red]  \"{child_title}\""
                    )
                else:
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f"[dim]open[/dim]    \"{child_title}\"  waiting"
                    )
        else:
            console.print(
                f"  [cyan]#{task_id}[/cyan]  single  "
                f'"{title}"  running {duration}'
            )

    console.print()


def _show_recent_tasks():
    """Show recent completed top-level tasks."""
    recent = get_recent_completed_tasks(limit=5)
    if not recent:
        return

    console.print(f"[bold blue]📋 Recent ({len(recent)})[/bold blue]")
    for task in recent:
        task_id = task["id"]
        title = task.get("title", "")[:50]
        out_doc = task.get("output_doc_id")
        doc_ref = f"→ doc #{out_doc}" if out_doc else ""
        time_ref = _relative_time(task.get("completed_at"))
        console.print(
            f"  [cyan]#{task_id}[/cyan]  [green]done[/green]    "
            f'"{title}"  [dim]{doc_ref}  {time_ref}[/dim]'
        )
    console.print()


def _show_failed_tasks():
    """Show failed top-level tasks with retry hints."""
    failed = get_failed_tasks(limit=3)
    if not failed:
        return

    console.print(f"[bold red]❌ Failed ({len(failed)})[/bold red]")
    for task in failed:
        task_id = task["id"]
        title = task.get("title", "")[:50]
        time_ref = _relative_time(task.get("updated_at"))
        error = task.get("error", "")
        console.print(
            f'  [cyan]#{task_id}[/cyan]  "{title}"  [dim]{time_ref}[/dim]'
        )
        if error:
            console.print(f"       error: {error[:80]}")
        # Show retry hint using delegate
        prompt = task.get("prompt", "")
        if prompt:
            escaped = prompt[:60].replace('"', '\\"')
            console.print(f'       → [cyan]emdx delegate "{escaped}"[/cyan]')
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
            console.print("[bold magenta]🌊 Cascade Queue:[/bold magenta]")
            parts = []
            for stage in stages:
                if counts.get(stage, 0) > 0:
                    parts.append(f"{stage}: {counts[stage]}")
            console.print("  " + " → ".join(parts))
            console.print("  [dim]Run [cyan]emdx cascade process <stage>[/cyan] to advance[/dim]")
            console.print()
    except sqlite3.OperationalError:
        # cascade_stage column may not exist in older databases
        pass


def status(
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show additional details"
    ),
):
    """
    Show delegate activity index and project status.

    Displays active delegate tasks, recent completions, failures,
    and cascade queue status.

    Examples:
        emdx status
        emdx status --verbose
    """
    console.print()

    # Active delegate tasks
    _show_active_tasks()

    # Recent completed tasks
    _show_recent_tasks()

    # Failed tasks with retry hints
    _show_failed_tasks()

    # Cascade status
    _show_cascade_status()

    # Quick tips
    console.print("[dim]Quick commands:[/dim]")
    console.print("  [cyan]emdx delegate \"task\"[/cyan]    - Run a task")
    console.print("  [cyan]emdx task ready[/cyan]         - Show work queue")
    console.print("  [cyan]emdx task list --all[/cyan]    - Full task list")
    console.print()


# Create typer app for the command
app = typer.Typer()
app.command()(status)
