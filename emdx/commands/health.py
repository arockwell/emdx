"""
Health monitoring commands for EMDX knowledge base.
Provides health metrics, recommendations, and maintenance tracking.
"""

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich import box
from typing import Optional
from pathlib import Path
import json
from datetime import datetime

from ..config.settings import get_db_path
from ..services.health_monitor import HealthMonitor

app = typer.Typer()
console = Console()


def _get_status_color(status: str) -> str:
    """Get color for status display."""
    return {
        'good': 'green',
        'warning': 'yellow',
        'critical': 'red'
    }.get(status, 'white')


def _get_status_emoji(status: str) -> str:
    """Get emoji for status display."""
    return {
        'good': '🟢',
        'warning': '🟡',
        'critical': '🔴'
    }.get(status, '⚪')


def _format_score(score: float) -> str:
    """Format a score as percentage with color."""
    if score >= 0.8:
        return f"[green]{score:.0%}[/green]"
    elif score >= 0.6:
        return f"[yellow]{score:.0%}[/yellow]"
    else:
        return f"[red]{score:.0%}[/red]"


@app.command()
def health(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed metrics"),
    export: Optional[Path] = typer.Option(None, "--export", "-e", help="Export report to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Check knowledge base health and get recommendations."""
    
    monitor = HealthMonitor()
    
    with console.status("[bold green]Analyzing knowledge base health..."):
        health_data = monitor.calculate_overall_health()
    
    if json_output:
        # JSON output for automation
        if export:
            with open(export, 'w') as f:
                json.dump(health_data, f, indent=2, default=str)
            console.print(f"[green]Health data exported to {export}[/green]")
        else:
            console.print(json.dumps(health_data, indent=2, default=str))
        return
    
    # Display overall health
    overall_score = health_data['overall_score']
    overall_status = health_data['overall_status']
    status_emoji = _get_status_emoji(overall_status)
    
    console.print(
        Panel(
            f"[bold {_get_status_color(overall_status)}]{status_emoji} Overall Health: {overall_score:.0%}[/bold {_get_status_color(overall_status)}]\n"
            f"Status: {overall_status.upper()}",
            title="[bold cyan]EMDX Knowledge Base Health[/bold cyan]",
            box=box.DOUBLE
        )
    )
    
    # Display statistics
    stats = health_data['statistics']
    console.print("\n[bold]📊 Statistics:[/bold]")
    stats_table = Table(show_header=False, box=box.SIMPLE)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right")
    
    stats_table.add_row("Documents", f"{stats['total_documents']:,}")
    stats_table.add_row("Projects", str(stats['total_projects']))
    stats_table.add_row("Tags", str(stats['total_tags']))
    stats_table.add_row("Database Size", f"{stats['database_size_mb']} MB")
    
    console.print(stats_table)
    
    # Display metric summary
    console.print("\n[bold]🏥 Health Metrics:[/bold]")
    
    metrics_table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Score", justify="center")
    metrics_table.add_column("Status", justify="center")
    metrics_table.add_column("Details", no_wrap=False)
    
    for metric_name, metric in health_data['metrics'].items():
        metrics_table.add_row(
            metric_name.replace('_', ' ').title(),
            _format_score(metric.value),
            f"[{_get_status_color(metric.status)}]{metric.status}[/{_get_status_color(metric.status)}]",
            metric.details
        )
    
    console.print(metrics_table)
    
    # Show detailed metrics if requested
    if detailed:
        console.print("\n[bold]📋 Detailed Analysis:[/bold]\n")
        
        for metric_name, metric in health_data['metrics'].items():
            if metric.status != 'good' and metric.recommendations:
                color = _get_status_color(metric.status)
                console.print(f"[bold {color}]{metric_name.replace('_', ' ').title()}:[/bold {color}]")
                
                for rec in metric.recommendations:
                    console.print(f"  • {rec}")
                console.print()
    
    # Show recommendations
    recommendations = monitor.get_maintenance_recommendations()
    if recommendations:
        console.print("\n[bold]💡 Recommended Actions:[/bold]\n")
        
        for i, (priority, task, command) in enumerate(recommendations[:5], 1):
            priority_color = 'red' if priority == 'HIGH' else 'yellow'
            console.print(f"{i}. [{priority_color}][{priority}][/{priority_color}] {task}")
            if command:
                console.print(f"   [dim]→ {command}[/dim]")
            console.print()
        
        if len(recommendations) > 5:
            console.print(f"[dim]... and {len(recommendations) - 5} more recommendations[/dim]")
    else:
        console.print("\n✨ [green]Your knowledge base is in excellent health![/green]")
    
    # Export if requested
    if export:
        report = monitor.generate_health_report()
        export.write_text(report)
        console.print(f"\n[green]✅ Full report exported to {export}[/green]")


@app.command()
def projects(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of projects to show"),
    sort: str = typer.Option("score", "--sort", "-s", help="Sort by: score, docs, coverage, activity"),
    threshold: float = typer.Option(0.0, "--threshold", "-t", help="Only show projects below this health score"),
):
    """Show health metrics for individual projects."""
    
    monitor = HealthMonitor()
    
    with console.status("[bold green]Analyzing project health..."):
        projects = monitor.get_project_health()
    
    if not projects:
        console.print("[yellow]No projects found[/yellow]")
        return
    
    # Filter by threshold
    if threshold > 0:
        projects = [p for p in projects if p.overall_score < threshold]
        if not projects:
            console.print(f"[green]No projects below {threshold:.0%} health threshold[/green]")
            return
    
    # Sort projects
    if sort == "docs":
        projects.sort(key=lambda p: p.document_count, reverse=True)
    elif sort == "coverage":
        projects.sort(key=lambda p: p.tag_coverage, reverse=True)
    elif sort == "activity":
        projects.sort(key=lambda p: p.activity_score, reverse=True)
    # Default is already sorted by score
    
    # Display table
    console.print(f"\n[bold cyan]Project Health Report[/bold cyan] (sorted by {sort})\n")
    
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Project", style="cyan")
    table.add_column("Docs", justify="right")
    table.add_column("Tag Coverage", justify="center")
    table.add_column("Activity", justify="center")
    table.add_column("Org Score", justify="center")
    table.add_column("Overall", justify="center")
    table.add_column("Status", justify="center")
    
    for project in projects[:limit]:
        # Determine status
        if project.overall_score >= 0.8:
            status = "🟢 Good"
        elif project.overall_score >= 0.6:
            status = "🟡 Fair"
        else:
            status = "🔴 Poor"
        
        table.add_row(
            project.project[:30] + "..." if len(project.project) > 30 else project.project,
            str(project.document_count),
            _format_score(project.tag_coverage),
            _format_score(project.activity_score),
            _format_score(project.organization_score),
            _format_score(project.overall_score),
            status
        )
    
    console.print(table)
    
    if len(projects) > limit:
        console.print(f"\n[dim]Showing {limit} of {len(projects)} projects[/dim]")
    
    # Show summary
    avg_score = sum(p.overall_score for p in projects) / len(projects)
    poor_projects = sum(1 for p in projects if p.overall_score < 0.6)
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  • Average project health: {_format_score(avg_score)}")
    if poor_projects > 0:
        console.print(f"  • [red]{poor_projects} projects need attention[/red]")


@app.command()
def report(
    output: Path = typer.Argument(..., help="Output file path (markdown or HTML)"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown, html"),
    open_after: bool = typer.Option(False, "--open", "-o", help="Open report after generation"),
):
    """Generate a comprehensive health report."""
    
    monitor = HealthMonitor()
    
    with console.status("[bold green]Generating health report..."):
        report_content = monitor.generate_health_report()
    
    if format == "html":
        # Convert markdown to HTML
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>EMDX Health Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{
            color: #2c3e50;
        }}
        h1 {{
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            margin-top: 30px;
            color: #34495e;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
        pre {{
            background: #f4f4f4;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        ul {{
            line-height: 1.8;
        }}
        .status-good {{ color: #27ae60; }}
        .status-warning {{ color: #f39c12; }}
        .status-critical {{ color: #e74c3c; }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""
        # Convert markdown to HTML (simple conversion)
        import re
        html_content = report_content
        
        # Convert headers
        html_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        
        # Convert bold
        html_content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html_content)
        
        # Convert italic
        html_content = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', html_content)
        
        # Convert code blocks
        html_content = re.sub(r'```bash\n([^`]+)\n```', r'<pre><code>\1</code></pre>', html_content)
        html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
        
        # Convert line breaks
        html_content = re.sub(r'\n\n', r'</p><p>', html_content)
        html_content = f'<p>{html_content}</p>'
        
        # Convert lists
        html_content = re.sub(r'^- (.+)$', r'<li>\1</li>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'(<li>.*</li>\n?)+', r'<ul>\g<0></ul>', html_content)
        
        # Write HTML
        output.write_text(html_template.format(content=html_content))
    else:
        # Write markdown
        output.write_text(report_content)
    
    console.print(f"[green]✅ Health report saved to {output}[/green]")
    
    if open_after:
        import subprocess
        import sys
        
        if sys.platform == "darwin":
            subprocess.run(["open", str(output)])
        elif sys.platform == "linux":
            subprocess.run(["xdg-open", str(output)])
        elif sys.platform == "win32":
            subprocess.run(["start", str(output)], shell=True)


@app.command()
def monitor(
    interval: int = typer.Option(300, "--interval", "-i", help="Check interval in seconds (default: 5 min)"),
    threshold: float = typer.Option(0.7, "--threshold", "-t", help="Alert threshold (0-1)"),
):
    """Monitor health in real-time with alerts."""
    
    monitor = HealthMonitor()
    
    console.print("[bold cyan]🔍 Starting health monitoring...[/bold cyan]")
    console.print(f"[dim]Checking every {interval} seconds, alerting below {threshold:.0%}[/dim]\n")
    
    try:
        import time
        
        while True:
            # Clear previous output
            console.clear()
            
            # Get current health
            health_data = monitor.calculate_overall_health()
            overall_score = health_data['overall_score']
            overall_status = health_data['overall_status']
            
            # Display timestamp
            console.print(f"[dim]Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")
            
            # Display current status
            status_emoji = _get_status_emoji(overall_status)
            console.print(
                Panel(
                    f"[bold {_get_status_color(overall_status)}]{status_emoji} Health: {overall_score:.0%}[/bold]",
                    title="Current Status",
                    box=box.ROUNDED
                )
            )
            
            # Check for alerts
            alerts = []
            for metric_name, metric in health_data['metrics'].items():
                if metric.value < threshold and metric.status in ['warning', 'critical']:
                    alerts.append((metric_name, metric))
            
            if alerts:
                console.print("\n[bold red]⚠️  ALERTS:[/bold red]")
                for metric_name, metric in alerts:
                    console.print(f"  • {metric_name.replace('_', ' ').title()}: {metric.value:.0%} - {metric.details}")
                    if metric.recommendations:
                        console.print(f"    → {metric.recommendations[0]}")
            else:
                console.print("\n[green]✅ All metrics above threshold[/green]")
            
            # Show next check time
            console.print(f"\n[dim]Next check in {interval} seconds... (Ctrl+C to stop)[/dim]")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitoring stopped[/yellow]")


if __name__ == "__main__":
    app()