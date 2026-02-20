"""
Status command - Show delegate activity index and project status.

Provides a quick overview of:
- Active delegate tasks (running now)
- Recent completed tasks
- Failed tasks (with retry hints)
"""

from datetime import datetime, timedelta
from typing import Any

import typer
from rich.console import Console

from ..models.tasks import (
    get_active_delegate_tasks,
    get_children,
    get_failed_tasks,
    get_recent_completed_tasks,
)
from ..utils.output import print_json

console = Console()


def _parse_timestamp(value: object) -> datetime | None:
    """Parse a timestamp that may be a datetime, string, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _relative_time(timestamp: object) -> str:
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


def _running_duration(timestamp: object) -> str:
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


def _show_active_tasks() -> None:
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

        if task_type == "group":
            child_count = task.get("child_count", 0)
            children_done = task.get("children_done", 0)
            task.get("children_active", 0)
            progress = f"step {children_done + 1}/{child_count}" if child_count else ""
            console.print(
                f'  [cyan]#{task_id}[/cyan]  {task_type:<7} "{title}"  {progress}  {duration}'
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
                        f'[green]done[/green]    "{child_title}"  '
                        f"[dim]{doc_ref}  {time_ref}[/dim]"
                    )
                elif child_status == "active":
                    dur = _running_duration(child.get("updated_at") or child.get("created_at"))
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f'[yellow]active[/yellow]  "{child_title}"  '
                        f"running {dur}"
                    )
                elif child_status == "failed":
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f'[red]failed[/red]  "{child_title}"'
                    )
                else:
                    console.print(
                        f"       {prefix} [cyan]#{child_id}[/cyan]  "
                        f'[dim]open[/dim]    "{child_title}"  waiting'
                    )
        else:
            console.print(f'  [cyan]#{task_id}[/cyan]  single  "{title}"  running {duration}')

    console.print()


def _show_recent_tasks() -> None:
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


def _show_failed_tasks() -> None:
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
        console.print(f'  [cyan]#{task_id}[/cyan]  "{title}"  [dim]{time_ref}[/dim]')
        if error:
            console.print(f"       error: {error[:80]}")
        # Show retry hint using delegate
        prompt = task.get("prompt", "")
        if prompt:
            escaped = prompt[:60].replace('"', '\\"')
            console.print(f'       → [cyan]emdx delegate "{escaped}"[/cyan]')
    console.print()


def _collect_status_data() -> dict[str, Any]:
    """Collect all status data for JSON output."""
    active = get_active_delegate_tasks()
    recent = get_recent_completed_tasks(limit=5)
    failed = get_failed_tasks(limit=3)

    # Enrich active tasks with children
    enriched: list[dict[str, Any]] = [dict(t) for t in active]
    for task in enriched:
        if task.get("type") == "group":
            task["children"] = get_children(task["id"])

    return {
        "active": enriched,
        "recent": recent,
        "failed": failed,
    }


def _show_kb_stats(project: str | None = None, detailed: bool = False) -> None:
    """Show knowledge base statistics (folded from old `stats` command)."""
    from emdx.database import db
    from emdx.models.documents import get_stats
    from emdx.utils.datetime_utils import format_datetime as _format_datetime

    stats_data = get_stats(project=project)

    if project:
        console.print(f"[bold]Knowledge Base Statistics - Project: {project}[/bold]")
    else:
        console.print("[bold]Knowledge Base Statistics[/bold]")
    console.print("=" * 40)

    console.print(f"[blue]Total Documents:[/blue] {stats_data.get('total_documents', 0)}")
    if not project:
        console.print(f"[blue]Total Projects:[/blue] {stats_data.get('total_projects', 0)}")
    console.print(f"[blue]Total Views:[/blue] {stats_data.get('total_views', 0)}")
    console.print(f"[blue]Average Views:[/blue] {stats_data.get('avg_views', 0):.1f}")
    console.print(f"[blue]Database Size:[/blue] {stats_data.get('table_size', '0 MB')}")

    if stats_data.get("most_viewed"):
        most_viewed = stats_data["most_viewed"]
        console.print(
            f"[blue]Most Viewed:[/blue] \"{most_viewed['title']}\" "
            f"({most_viewed['access_count']} views)"
        )

    newest_date = stats_data.get("newest_doc")
    console.print(f"[blue]Most Recent:[/blue] {_format_datetime(newest_date)}")

    if detailed:
        from rich.table import Table as RichTable

        console.print("\n[bold]Detailed Statistics[/bold]")
        console.print("-" * 40)

        if not project:
            with db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT project, COUNT(*) as doc_count, "
                    "SUM(access_count) as total_views, "
                    "MAX(created_at) as last_updated "
                    "FROM documents WHERE is_deleted = FALSE "
                    "GROUP BY project ORDER BY doc_count DESC"
                )
                project_table = RichTable(title="Documents by Project")
                project_table.add_column("Project", style="green")
                project_table.add_column("Documents", justify="right", style="cyan")
                project_table.add_column("Total Views", justify="right", style="blue")
                project_table.add_column("Last Updated", style="yellow")

                for row in cursor.fetchall():
                    project_table.add_row(
                        row[0] or "None",
                        str(row[1]),
                        str(row[2] or 0),
                        _format_datetime(row[3], "%Y-%m-%d"),
                    )
                console.print(project_table)

    console.print()


def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show additional details"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    stats: bool = typer.Option(
        False, "--stats", help="Show knowledge base statistics"
    ),
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Show detailed statistics (with --stats)"
    ),
    stat_project: str | None = typer.Option(
        None, "--project", "-p", help="Filter stats by project"
    ),
) -> None:
    """
    Show delegate activity index and project status.

    Displays active delegate tasks, recent completions, and failures.
    Use --stats for knowledge base statistics.

    Examples:
        emdx status
        emdx status --verbose
        emdx status --stats
        emdx status --stats --detailed
    """
    if json_output:
        print_json(_collect_status_data())
        return

    console.print()

    if stats:
        _show_kb_stats(project=stat_project, detailed=detailed)
        return

    # Active delegate tasks
    _show_active_tasks()

    # Recent completed tasks
    _show_recent_tasks()

    # Failed tasks with retry hints
    _show_failed_tasks()

    # Quick tips
    console.print("[dim]Quick commands:[/dim]")
    console.print('  [cyan]emdx delegate "task"[/cyan]    - Run a task')
    console.print("  [cyan]emdx task ready[/cyan]         - Show work queue")
    console.print("  [cyan]emdx task list --all[/cyan]    - Full task list")
    console.print()


# Create typer app for the command
app = typer.Typer(help="Show delegate activity and project status")
app.command()(status)
