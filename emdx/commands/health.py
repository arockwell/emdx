"""
Health check command for EMDX knowledge base.
Quick health status with CI/CD-friendly exit codes.
"""

import json
from typing import Any, Dict

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from ..services.health_monitor import HealthMonitor
from ..utils.output import console


def health(
    detailed: bool = typer.Option(
        False, "--detailed", "-d",
        help="Show detailed metric breakdown"
    ),
    projects: bool = typer.Option(
        False, "--projects", "-p",
        help="Show per-project health analysis"
    ),
    recommendations: bool = typer.Option(
        True, "--recommendations/--no-recommendations",
        help="Show maintenance recommendations"
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON for scripting"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Exit code only, no output"
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="Exit non-zero if health is not good (>=70%)"
    ),
):
    """
    Check knowledge base health with CI/CD-friendly exit codes.

    Exit codes:
      0 - Good health (>=70%) or non-strict mode
      1 - Warning health (40-69%) in strict mode
      2 - Critical health (<40%) in strict mode

    Examples:
        emdx health                    # Quick health overview
        emdx health --detailed         # Full metric breakdown
        emdx health --json             # JSON output for scripting
        emdx health --quiet --strict   # CI/CD check (exit code only)
    """
    monitor = HealthMonitor()
    health_data = monitor.calculate_overall_health()

    overall_status = health_data["overall_status"]

    # Determine exit code
    if overall_status == "critical":
        exit_code = 2
    elif overall_status == "warning":
        exit_code = 1
    else:
        exit_code = 0

    # Quiet mode - just exit with code
    if quiet:
        if strict and exit_code > 0:
            raise typer.Exit(exit_code)
        raise typer.Exit(0)

    # JSON output
    if json_output:
        output = _build_json_output(health_data, detailed, projects, monitor)
        print(json.dumps(output, indent=2, default=str))
        if strict and exit_code > 0:
            raise typer.Exit(exit_code)
        return

    # Human-readable output
    _display_health_output(health_data, detailed, projects, recommendations, monitor)

    # Exit with appropriate code in strict mode
    if strict and exit_code > 0:
        raise typer.Exit(exit_code)


def _build_json_output(
    health_data: Dict[str, Any],
    detailed: bool,
    projects: bool,
    monitor: HealthMonitor
) -> Dict[str, Any]:
    """Build JSON output structure."""
    output = {
        "overall_health": {
            "score": round(health_data["overall_score"] * 100, 1),
            "score_raw": health_data["overall_score"],
            "status": health_data["overall_status"],
            "timestamp": health_data["timestamp"]
        },
        "statistics": health_data["statistics"]
    }

    if detailed:
        output["metrics"] = {}
        for name, metric in health_data["metrics"].items():
            output["metrics"][name] = {
                "score": round(metric.value * 100, 1),
                "score_raw": metric.value,
                "weight": metric.weight,
                "status": metric.status,
                "details": metric.details,
                "recommendations": metric.recommendations
            }

    if projects:
        project_health = monitor.get_project_health(limit=10)
        output["projects"] = [
            {
                "project": p.project,
                "document_count": p.document_count,
                "tag_coverage": round(p.tag_coverage * 100, 1),
                "activity_score": round(p.activity_score * 100, 1),
                "overall_score": round(p.overall_score * 100, 1)
            }
            for p in project_health
        ]

    return output


def _display_health_output(
    health_data: Dict[str, Any],
    detailed: bool,
    projects: bool,
    recommendations: bool,
    monitor: HealthMonitor
):
    """Display human-readable health output."""
    overall_score = health_data["overall_score"] * 100
    overall_status = health_data["overall_status"]
    stats = health_data["statistics"]

    # Status indicators
    status_emoji = "🟢" if overall_status == "good" else "🟡" if overall_status == "warning" else "🔴"
    status_color = "green" if overall_status == "good" else "yellow" if overall_status == "warning" else "red"

    # Header panel
    console.print()
    console.print(Panel(
        f"[bold]Knowledge Base Health Check[/bold]\n\n"
        f"{status_emoji} Overall Health: [{status_color}]{overall_score:.0f}%[/{status_color}]\n"
        f"Status: [{status_color}]{overall_status.upper()}[/{status_color}]",
        title="[bold cyan]emdx health[/bold cyan]",
        box=box.ROUNDED
    ))

    # Statistics
    console.print("\n[bold]Database Statistics:[/bold]")
    console.print(f"  Documents: {stats['total_documents']:,}")
    console.print(f"  Projects:  {stats['total_projects']}")
    console.print(f"  Tags:      {stats['total_tags']}")
    console.print(f"  Size:      {stats['database_size_mb']} MB")

    # Detailed metrics breakdown
    if detailed:
        console.print("\n[bold]Health Metrics Breakdown:[/bold]")

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Details")

        for name, metric in health_data["metrics"].items():
            score = metric.value * 100
            color = "green" if metric.status == "good" else "yellow" if metric.status == "warning" else "red"
            emoji = "✅" if metric.status == "good" else "⚠️" if metric.status == "warning" else "❌"

            table.add_row(
                name.replace("_", " ").title(),
                f"[{color}]{score:.0f}%[/{color}]",
                emoji,
                metric.details
            )

        console.print(table)

    # Per-project health
    if projects:
        project_health = monitor.get_project_health(limit=10)
        if project_health:
            console.print("\n[bold]Project Health:[/bold]")

            table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
            table.add_column("Project", style="cyan")
            table.add_column("Docs", justify="right")
            table.add_column("Tags", justify="right")
            table.add_column("Activity", justify="right")
            table.add_column("Score", justify="right")

            for p in project_health:
                score_color = "green" if p.overall_score >= 0.7 else "yellow" if p.overall_score >= 0.4 else "red"
                table.add_row(
                    p.project[:30],
                    str(p.document_count),
                    f"{p.tag_coverage:.0%}",
                    f"{p.activity_score:.0%}",
                    f"[{score_color}]{p.overall_score:.0%}[/{score_color}]"
                )

            console.print(table)

    # Recommendations
    if recommendations:
        recs = monitor.get_maintenance_recommendations()
        if recs:
            console.print("\n[bold]Recommended Actions:[/bold]")
            for priority, task, command in recs[:5]:
                priority_color = "red" if priority == "HIGH" else "yellow"
                console.print(f"  [{priority_color}]{priority}[/{priority_color}]: {task}")
                if command:
                    console.print(f"    → [cyan]{command}[/cyan]")

            if len(recs) > 5:
                console.print(f"  [dim]... and {len(recs) - 5} more[/dim]")

            console.print("\n[dim]Run 'emdx maintain' to apply fixes[/dim]")

    console.print()
