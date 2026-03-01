"""
Status command - Show delegate activity index and project status.

Provides a quick overview of:
- Active delegate tasks (running now)
- Recent completed tasks
- Failed tasks (with retry hints)
- Knowledge base health (--health)
- Knowledge base vitals (--vitals)
- Reflective KB mirror (--mirror)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from ..models.tasks import (
    get_active_delegate_tasks,
    get_children,
    get_failed_tasks,
    get_recent_completed_tasks,
)
from ..utils.output import print_json
from .types import (
    AccessBucket,
    HealthData,
    HealthMetricData,
    MirrorData,
    ProjectBalance,
    ProjectCount,
    StalenessBreakdown,
    TagShare,
    TaskStats,
    VitalsData,
    WeeklyActivity,
    WeeklyGrowth,
)

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


def _get_status_emoji(score: float) -> str:
    """Get status emoji based on score."""
    if score >= 80:
        return "✅"
    elif score >= 60:
        return "⚠️"
    else:
        return "❌"


def _show_health() -> None:
    """Show knowledge base health metrics and recommendations."""
    from ..services.health_monitor import HealthMonitor

    monitor = HealthMonitor()

    try:
        with console.status("[bold green]Analyzing knowledge base health..."):
            metrics = monitor.calculate_overall_health()
    except ImportError as e:
        console.print(f"  [red]{e}[/red]")
        return

    # Overall health score
    overall_score = metrics["overall_score"] * 100
    health_color = "green" if overall_score >= 80 else "yellow" if overall_score >= 60 else "red"

    console.print(
        f"[bold]Overall Health Score: [{health_color}]{overall_score:.0f}%[/{health_color}][/bold]"
    )

    # Detailed metrics table
    console.print("\n[bold]Health Metrics:[/bold]")

    metrics_table = Table(show_header=False, box=box.SIMPLE)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Score", justify="right")
    metrics_table.add_column("Status")
    metrics_table.add_column("Details")

    for key in ("tag_coverage", "duplicate_ratio", "organization", "activity"):
        metric = metrics["metrics"].get(key)
        if metric is None:
            continue
        score = metric.value * 100
        color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
        metrics_table.add_row(
            metric.name,
            f"[{color}]{score:.0f}%[/{color}]",
            _get_status_emoji(score),
            metric.details,
        )

    console.print(metrics_table)

    # Tag coverage details
    _show_tag_summary()

    # Recommendations
    all_recommendations: list[str] = []
    for metric in metrics["metrics"].values():
        all_recommendations.extend(metric.recommendations)

    if all_recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in all_recommendations:
            console.print(f"  • {rec}")

    console.print("\n[dim]For duplicates/similar docs: emdx maintain compact --dry-run[/dim]")


def _show_tag_summary() -> None:
    """Show tag coverage summary as part of health output."""
    from ..database.connection import db_connection

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(DISTINCT d.id) as total_docs,
                COUNT(DISTINCT CASE WHEN dt.document_id IS NOT NULL
                    THEN d.id END) as tagged_docs
            FROM documents d
            LEFT JOIN (
                SELECT document_id FROM document_tags GROUP BY document_id
            ) dt ON d.id = dt.document_id
            WHERE d.is_deleted = 0
        """)

        stats = cursor.fetchone()
        total = stats["total_docs"]
        tagged = stats["tagged_docs"]
        untagged = total - tagged

        if untagged > 0:
            console.print(
                f"\n  [yellow]{untagged} untagged documents[/yellow] out of {total} total"
            )


def _collect_health_json() -> HealthData:
    """Collect health metrics as structured data for JSON output."""
    from ..services.health_monitor import HealthMonitor

    monitor = HealthMonitor()
    try:
        metrics = monitor.calculate_overall_health()
    except ImportError as e:
        return HealthData(error=str(e))

    metrics_dict: dict[str, HealthMetricData] = {}
    for key, metric in metrics["metrics"].items():
        metrics_dict[key] = HealthMetricData(
            name=metric.name,
            value=metric.value,
            score=metric.value * 100,
            weight=metric.weight,
            status=metric.status,
            details=metric.details,
            recommendations=metric.recommendations,
        )

    return HealthData(
        overall_score=metrics["overall_score"],
        overall_status=metrics["overall_status"],
        metrics=metrics_dict,
        statistics=metrics["statistics"],
        timestamp=metrics["timestamp"],
    )


def _collect_vitals_data() -> VitalsData:
    """Collect KB vitals via pure SQL queries."""
    from ..database.connection import db_connection

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Total doc count
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs: int = cursor.fetchone()[0]

        # Count by project
        cursor.execute(
            "SELECT COALESCE(project, '(none)') as project, "
            "COUNT(*) as cnt "
            "FROM documents WHERE is_deleted = 0 "
            "GROUP BY project ORDER BY cnt DESC"
        )
        by_project: list[ProjectCount] = [
            ProjectCount(project=row[0], count=row[1]) for row in cursor.fetchall()
        ]

        # Growth rate: docs per week for last 4 weeks
        growth: list[WeeklyGrowth] = []
        for i in range(3, -1, -1):
            start = f"-{(i + 1) * 7} days"
            end = f"-{i * 7} days"
            cursor.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE is_deleted = 0 "
                "AND created_at > datetime('now', ?) "
                "AND created_at <= datetime('now', ?)",
                (start, end),
            )
            count: int = cursor.fetchone()[0]
            week_label = f"{i * 7 + 1}-{(i + 1) * 7}d ago"
            if i == 0:
                week_label = "last 7d"
            growth.append(WeeklyGrowth(week=week_label, count=count))

        # Embedding coverage
        cursor.execute(
            "SELECT COUNT(DISTINCT de.document_id) "
            "FROM document_embeddings de "
            "JOIN documents d ON de.document_id = d.id "
            "WHERE d.is_deleted = 0"
        )
        embedded_count: int = cursor.fetchone()[0]
        embed_pct = round(embedded_count / total_docs * 100, 1) if total_docs > 0 else 0.0

        # Access frequency distribution
        buckets = [
            ("0 views", "access_count = 0"),
            ("1-5 views", "access_count BETWEEN 1 AND 5"),
            ("6-20 views", "access_count BETWEEN 6 AND 20"),
            ("21+ views", "access_count > 20"),
        ]
        access_dist: list[AccessBucket] = []
        for label, condition in buckets:
            cursor.execute(f"SELECT COUNT(*) FROM documents WHERE is_deleted = 0 AND {condition}")
            access_dist.append(AccessBucket(range=label, count=cursor.fetchone()[0]))

        # Tag coverage
        cursor.execute(
            "SELECT COUNT(DISTINCT dt.document_id) "
            "FROM document_tags dt "
            "JOIN documents d ON dt.document_id = d.id "
            "WHERE d.is_deleted = 0"
        )
        tagged_count: int = cursor.fetchone()[0]
        tag_pct = round(tagged_count / total_docs * 100, 1) if total_docs > 0 else 0.0

        # Task stats
        cursor.execute(
            "SELECT "
            "SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), "
            "COUNT(*) "
            "FROM tasks"
        )
        task_row = cursor.fetchone()
        tasks = TaskStats(
            open=task_row[0] or 0,
            done=task_row[1] or 0,
            total=task_row[2] or 0,
        )

    return VitalsData(
        total_docs=total_docs,
        by_project=by_project,
        growth_per_week=growth,
        embedding_coverage_pct=embed_pct,
        access_distribution=access_dist,
        tag_coverage_pct=tag_pct,
        tasks=tasks,
    )


def _show_vitals(rich_output: bool = False) -> None:
    """Display KB vitals dashboard."""
    from ..database.connection import db_connection

    # Quick empty-KB check
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        if cursor.fetchone()[0] == 0:
            msg = "No documents yet -- try `emdx save`"
            if rich_output:
                console.print(f"[dim]{msg}[/dim]")
            else:
                print(msg)
            return

    data = _collect_vitals_data()

    if rich_output:
        _show_vitals_rich(data)
    else:
        _show_vitals_plain(data)


def _show_vitals_plain(data: VitalsData) -> None:
    """Plain text vitals output."""
    print(f"Documents: {data['total_docs']}")
    for p in data["by_project"]:
        print(f"  {p['project']}: {p['count']}")

    print()
    print("Growth (docs/week):")
    for w in data["growth_per_week"]:
        print(f"  {w['week']}: {w['count']}")

    print()
    print(f"Embedding coverage: {data['embedding_coverage_pct']}%")
    print(f"Tag coverage: {data['tag_coverage_pct']}%")

    print()
    print("Access distribution:")
    for b in data["access_distribution"]:
        print(f"  {b['range']}: {b['count']}")

    print()
    t = data["tasks"]
    print(f"Tasks: {t['open']} open, {t['done']} done, {t['total']} total")


def _show_vitals_rich(data: VitalsData) -> None:
    """Rich formatted vitals output with table."""
    table = Table(
        title="KB Vitals",
        box=box.ROUNDED,
        show_header=True,
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total docs", str(data["total_docs"]))

    for p in data["by_project"]:
        table.add_row(f"  {p['project']}", str(p["count"]))

    # Growth sparkline
    growth_parts = [f"{w['count']}" for w in data["growth_per_week"]]
    table.add_row("Growth (docs/wk)", " -> ".join(growth_parts))

    embed_pct = data["embedding_coverage_pct"]
    color = "green" if embed_pct >= 80 else ("yellow" if embed_pct >= 50 else "red")
    table.add_row(
        "Embedding coverage",
        f"[{color}]{embed_pct}%[/{color}]",
    )

    tag_pct = data["tag_coverage_pct"]
    color = "green" if tag_pct >= 80 else ("yellow" if tag_pct >= 50 else "red")
    table.add_row("Tag coverage", f"[{color}]{tag_pct}%[/{color}]")

    for b in data["access_distribution"]:
        table.add_row(f"  {b['range']}", str(b["count"]))

    t = data["tasks"]
    table.add_row(
        "Tasks",
        f"{t['open']} open / {t['done']} done / {t['total']} total",
    )

    console.print(table)


def _collect_mirror_data() -> MirrorData:
    """Collect reflective KB mirror data via pure SQL (no LLM)."""
    from ..database.connection import db_connection

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        # Total docs
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs: int = cursor.fetchone()[0]

        # Top 10 tags by document count
        cursor.execute(
            "SELECT t.name, COUNT(dt.document_id) as cnt "
            "FROM tags t "
            "JOIN document_tags dt ON t.id = dt.tag_id "
            "JOIN documents d ON dt.document_id = d.id "
            "WHERE d.is_deleted = 0 "
            "GROUP BY t.name ORDER BY cnt DESC LIMIT 10"
        )
        top_tags: list[TagShare] = []
        for row in cursor.fetchall():
            pct = round(row[1] / total_docs * 100, 1) if total_docs > 0 else 0.0
            top_tags.append(TagShare(tag=row[0], count=row[1], pct=pct))

        # Weekly activity: docs created per week for last 8 weeks
        weekly: list[WeeklyActivity] = []
        for i in range(7, -1, -1):
            start = f"-{(i + 1) * 7} days"
            end = f"-{i * 7} days"
            cursor.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE is_deleted = 0 "
                "AND created_at > datetime('now', ?) "
                "AND created_at <= datetime('now', ?)",
                (start, end),
            )
            count: int = cursor.fetchone()[0]
            label = f"w-{i}" if i > 0 else "this week"
            weekly.append(WeeklyActivity(week=label, count=count))

        # Temporal pattern detection
        counts = [w["count"] for w in weekly]
        nonzero = [c for c in counts if c > 0]
        if not nonzero:
            pattern = "inactive"
        elif len(nonzero) <= 2:
            pattern = "sporadic"
        else:
            avg = sum(counts) / len(counts)
            max_c = max(counts)
            if max_c > avg * 3 and avg > 0:
                pattern = "burst"
            else:
                pattern = "steady"

        # Project balance
        cursor.execute(
            "SELECT COALESCE(project, '(none)') as project, "
            "COUNT(*) as cnt "
            "FROM documents WHERE is_deleted = 0 "
            "GROUP BY project ORDER BY cnt DESC"
        )
        project_balance: list[ProjectBalance] = [
            ProjectBalance(project=row[0], count=row[1]) for row in cursor.fetchall()
        ]

        # Staleness: % of docs not accessed in 30/60/90 days
        stale: dict[str, float] = {}
        for days in (30, 60, 90):
            cursor.execute(
                "SELECT COUNT(*) FROM documents "
                "WHERE is_deleted = 0 "
                "AND accessed_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            stale_count: int = cursor.fetchone()[0]
            pct = round(stale_count / total_docs * 100, 1) if total_docs > 0 else 0.0
            stale[f"over_{days}_days_pct"] = pct

        staleness = StalenessBreakdown(
            over_30_days_pct=stale["over_30_days_pct"],
            over_60_days_pct=stale["over_60_days_pct"],
            over_90_days_pct=stale["over_90_days_pct"],
        )

    return MirrorData(
        total_docs=total_docs,
        top_tags=top_tags,
        weekly_activity=weekly,
        temporal_pattern=pattern,
        project_balance=project_balance,
        staleness=staleness,
    )


def _show_mirror(rich_output: bool = False) -> None:
    """Display reflective KB summary as narrative text."""
    from ..database.connection import db_connection

    # Quick check for empty/small KB
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total = cursor.fetchone()[0]

    if total == 0:
        msg = "No documents yet -- try `emdx save`"
        if rich_output:
            console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)
        return

    if total < 5:
        msg = "Too few documents for meaningful reflection. Keep saving!"
        if rich_output:
            console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)
        return

    data = _collect_mirror_data()

    lines: list[str] = []

    # Topic distribution narrative
    if data["top_tags"]:
        top = data["top_tags"][:3]
        tag_parts = [f"{t['pct']}% '{t['tag']}'" for t in top]
        lines.append(f"Your KB is {', '.join(tag_parts)} (by tag coverage).")
        if len(data["top_tags"]) > 3:
            rest_tags = data["top_tags"][3:]
            bottom_part = ", ".join(f"'{t['tag']}' ({t['pct']}%)" for t in rest_tags[:3])
            lines.append(f"Less covered: {bottom_part}.")
    else:
        lines.append("No tags found -- consider tagging your docs.")

    # Temporal pattern
    pattern = data["temporal_pattern"]
    if pattern == "burst":
        lines.append("Activity pattern: burst -- you have spikes of intense saving.")
    elif pattern == "steady":
        lines.append("Activity pattern: steady -- consistent saving over time.")
    elif pattern == "sporadic":
        lines.append("Activity pattern: sporadic -- only a few active weeks recently.")
    else:
        lines.append("Activity pattern: inactive -- no recent documents.")

    # Staleness
    s = data["staleness"]
    if s["over_30_days_pct"] > 0:
        lines.append(
            f"{s['over_30_days_pct']}% of docs not accessed in 30+ "
            f"days, {s['over_60_days_pct']}% in 60+, "
            f"{s['over_90_days_pct']}% in 90+."
        )

    # Project balance
    if len(data["project_balance"]) > 1:
        proj_parts = [f"{p['project']} ({p['count']})" for p in data["project_balance"][:5]]
        lines.append(f"Project balance: {', '.join(proj_parts)}.")

    if rich_output:
        console.print()
        for line in lines:
            console.print(f"  {line}")
        console.print()
    else:
        for line in lines:
            print(line)


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
            f'[blue]Most Viewed:[/blue] "{most_viewed["title"]}" '
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
    stats: bool = typer.Option(False, "--stats", help="Show knowledge base statistics"),
    health: bool = typer.Option(
        False,
        "--health",
        "-H",
        help="Show knowledge base health metrics",
    ),
    vitals: bool = typer.Option(
        False,
        "--vitals",
        help="Show KB vitals dashboard",
    ),
    mirror: bool = typer.Option(
        False,
        "--mirror",
        help="Reflective KB summary (narrative)",
    ),
    rich_output: bool = typer.Option(
        False,
        "--rich",
        help="Enable colored Rich output",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed statistics (with --stats)",
    ),
    stat_project: str | None = typer.Option(
        None, "--project", "-p", help="Filter stats by project"
    ),
) -> None:
    """
    Show delegate activity index and project status.

    Displays active delegate tasks, recent completions, and failures.
    Use --stats for knowledge base statistics.
    Use --health for health scores, tag coverage, and recommendations.
    Use --vitals for a quick KB health dashboard.
    Use --mirror for a reflective narrative summary of your KB.

    Examples:
        emdx status
        emdx status --verbose
        emdx status --stats
        emdx status --stats --detailed
        emdx status --health
        emdx status --health --json
        emdx status --vitals
        emdx status --vitals --rich
        emdx status --mirror
    """
    if health:
        if json_output:
            print(json.dumps(_collect_health_json(), indent=2))
        else:
            console.print()
            _show_health()
            console.print()
        return

    if vitals:
        if json_output:
            print_json(_collect_vitals_data())
        else:
            _show_vitals(rich_output=rich_output)
        return

    if mirror:
        if json_output:
            print_json(_collect_mirror_data())
        else:
            _show_mirror(rich_output=rich_output)
        return

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
