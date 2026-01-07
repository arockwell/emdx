"""
Lifecycle management commands for EMDX.
Track and manage document lifecycles, especially for gameplans.
"""

from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table
from rich.tree import Tree

from ..models.documents import get_document
from ..services.lifecycle_tracker import LifecycleTracker

app = typer.Typer()
console = Console()


def _get_stage_emoji(stage: str) -> str:
    """Get emoji for lifecycle stage."""
    return {
        'planning': '🎯',
        'active': '🚀',
        'blocked': '🚧',
        'completed': '✅',
        'success': '🎉',
        'failed': '❌',
        'archived': '📦'
    }.get(stage, '❓')


def _get_stage_color(stage: str) -> str:
    """Get color for lifecycle stage."""
    return {
        'planning': 'cyan',
        'active': 'green',
        'blocked': 'yellow',
        'completed': 'blue',
        'success': 'bright_green',
        'failed': 'red',
        'archived': 'dim'
    }.get(stage, 'white')


@app.command()
def status(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter by stage"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all documents, not just gameplans"),
):
    """Show lifecycle status of documents."""
    
    tracker = LifecycleTracker()
    
    # Get gameplans
    with console.status("[bold green]Analyzing document lifecycles..."):
        gameplans = tracker.get_gameplans(stage=stage)
        
        if project:
            gameplans = [gp for gp in gameplans if gp['project'] == project]
    
    if not gameplans:
        console.print("[yellow]No gameplans found[/yellow]")
        return
    
    # Display gameplans by stage
    console.print(Panel(
        "[bold cyan]📊 Gameplan Lifecycle Status[/bold cyan]",
        box=box.DOUBLE
    ))
    
    # Group by stage
    by_stage = {}
    for gp in gameplans:
        stage_name = gp['stage'] or 'untracked'
        if stage_name not in by_stage:
            by_stage[stage_name] = []
        by_stage[stage_name].append(gp)
    
    # Display each stage
    stage_order = ['planning', 'active', 'blocked', 'completed', 'success', 'failed', 'archived', 'untracked']
    
    for stage_name in stage_order:
        if stage_name not in by_stage:
            continue
        
        docs = by_stage[stage_name]
        emoji = _get_stage_emoji(stage_name)
        color = _get_stage_color(stage_name)
        
        console.print(f"\n[bold {color}]{emoji} {stage_name.upper()} ({len(docs)})[/bold {color}]")
        
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("ID", style="dim", width=6)
        table.add_column("Title", style="cyan")
        table.add_column("Project", style="yellow")
        table.add_column("Age", justify="right")
        table.add_column("Views", justify="right")
        
        for doc in docs[:10]:  # Show max 10 per stage
            age = f"{doc['age_days']}d"
            table.add_row(
                str(doc['id']),
                doc['title'][:40] + "..." if len(doc['title']) > 40 else doc['title'],
                doc['project'] or '-',
                age,
                str(doc['access_count'])
            )
        
        console.print(table)
        
        if len(docs) > 10:
            console.print(f"[dim]... and {len(docs) - 10} more[/dim]")
    
    # Show summary
    analysis = tracker.analyze_lifecycle_patterns()
    
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  • Total gameplans: {analysis['total_gameplans']}")
    if analysis['total_gameplans'] > 0:
        console.print(f"  • Success rate: {analysis['success_rate']:.0f}%")
        console.print(f"  • Average duration: {analysis['average_duration']:.0f} days")
        
        if analysis['insights']:
            console.print("\n[bold]Insights:[/bold]")
            for insight in analysis['insights']:
                console.print(f"  • {insight}")


@app.command()
def transition(
    doc_id: int = typer.Argument(..., help="Document ID to transition"),
    new_stage: str = typer.Argument(None, help="New stage (planning/active/blocked/completed/success/failed/archived)"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Transition notes"),
    force: bool = typer.Option(False, "--force", "-f", help="Force transition even if invalid"),
):
    """Transition a document to a new lifecycle stage."""
    
    tracker = LifecycleTracker()
    
    # Get current stage
    current_stage = tracker.get_document_stage(doc_id)
    doc = get_document(str(doc_id))
    
    if not doc:
        console.print(f"[red]Error: Document #{doc_id} not found[/red]")
        raise typer.Exit(1)
    
    # If no new stage specified, show suggestions
    if not new_stage:
        console.print(f"\n[bold]Document #{doc_id}: {doc['title']}[/bold]")
        console.print(f"Current stage: [{_get_stage_color(current_stage or 'none')}]{current_stage or 'untracked'}[/{_get_stage_color(current_stage or 'none')}]")
        
        suggestions = tracker.suggest_transitions(doc_id)
        if suggestions:
            console.print("\n[bold]Valid transitions:[/bold]")
            for stage, recommendation in suggestions:
                emoji = _get_stage_emoji(stage)
                color = _get_stage_color(stage)
                console.print(f"  • [{color}]{emoji} {stage}[/{color}] - {recommendation}")
            console.print(f"\n[dim]Use: emdx lifecycle transition {doc_id} STAGE[/dim]")
        else:
            console.print("[yellow]No valid transitions from current stage[/yellow]")
        return
    
    # Validate stage
    valid_stages = ['planning', 'active', 'blocked', 'completed', 'success', 'failed', 'archived']
    if new_stage not in valid_stages:
        console.print(f"[red]Error: Invalid stage '{new_stage}'[/red]")
        console.print(f"[dim]Valid stages: {', '.join(valid_stages)}[/dim]")
        raise typer.Exit(1)
    
    # Attempt transition
    if force or tracker.transition_document(doc_id, new_stage, notes):
        if force and current_stage:
            # Force transition by removing old tags first
            from ..models.tags import remove_tags_from_document
            for stage_name, tags in tracker.STAGES.items():
                if stage_name == current_stage:
                    for tag in tags:
                        try:
                            remove_tags_from_document(doc_id, [tag])
                        except (ValueError, LookupError, RuntimeError):
                            pass
            tracker.transition_document(doc_id, new_stage, notes)
        
        console.print(f"[green]✅ Transitioned #{doc_id} from {current_stage or 'untracked'} → {new_stage}[/green]")
        
        if notes:
            console.print(f"[dim]Note: {notes}[/dim]")
    else:
        console.print(f"[red]Invalid transition from {current_stage} to {new_stage}[/red]")
        console.print("[dim]Use --force to override[/dim]")


@app.command()
def analyze(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed analysis"),
):
    """Analyze lifecycle patterns and success rates."""
    
    tracker = LifecycleTracker()
    
    with console.status("[bold green]Analyzing lifecycle patterns..."):
        analysis = tracker.analyze_lifecycle_patterns()
    
    # Display analysis
    console.print(Panel(
        "[bold cyan]📈 Lifecycle Analysis[/bold cyan]",
        box=box.DOUBLE
    ))
    
    if analysis['total_gameplans'] == 0:
        console.print("[yellow]No gameplans found to analyze[/yellow]")
        return
    
    # Key metrics
    console.print("[bold]Key Metrics:[/bold]")
    console.print(f"  • Total gameplans: {analysis['total_gameplans']}")
    # Color-code success rate based on performance
    success_rate = analysis['success_rate']
    color = 'green' if success_rate >= 70 else 'yellow' if success_rate >= 50 else 'red'
    console.print(f"  • Success rate: [{color}]{success_rate:.0f}%[/]")
    console.print(f"  • Average duration: {analysis['average_duration']:.0f} days")
    
    # Stage distribution
    if analysis['stage_distribution']:
        console.print("\n[bold]Stage Distribution:[/bold]")
        
        total = sum(analysis['stage_distribution'].values())
        for stage, count in analysis['stage_distribution'].items():
            emoji = _get_stage_emoji(stage)
            color = _get_stage_color(stage)
            percentage = (count / total * 100) if total > 0 else 0
            bar_length = int(percentage / 2)
            bar = "█" * bar_length
            
            console.print(f"  [{color}]{emoji} {stage:10}[/{color}] {bar} {count} ({percentage:.0f}%)")
    
    # Insights
    if analysis['insights']:
        console.print("\n[bold]Insights:[/bold]")
        for insight in analysis['insights']:
            console.print(f"  • {insight}")
    
    # Recommendations
    console.print("\n[bold]Recommendations:[/bold]")
    
    if analysis.get('stale_active', 0) > 0:
        console.print(f"  • Review {analysis['stale_active']} stale active gameplans")
        console.print("    [dim]Run: emdx lifecycle auto-detect[/dim]")
    
    if analysis.get('blocked_count', 0) > 0:
        console.print(f"  • Address {analysis['blocked_count']} blocked gameplans")
        console.print("    [dim]Run: emdx lifecycle status --stage blocked[/dim]")
    
    if analysis['success_rate'] < 50:
        console.print("  • Low success rate - review failed gameplans for patterns")
        console.print("    [dim]Run: emdx lifecycle status --stage failed[/dim]")


@app.command(name="auto-detect")
def auto_detect(
    apply: bool = typer.Option(False, "--apply", "-a", help="Apply suggested transitions"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
):
    """Auto-detect and suggest lifecycle transitions."""
    
    tracker = LifecycleTracker()
    
    with console.status("[bold green]Detecting transition opportunities..."):
        suggestions = tracker.auto_detect_transitions()
    
    if not suggestions:
        console.print("[green]✨ No transition suggestions found![/green]")
        console.print("[dim]All documents appear to be in appropriate stages[/dim]")
        return
    
    # Filter by project if specified
    if project:
        suggestions = [s for s in suggestions if get_document(str(s['doc_id']))['project'] == project]
    
    # Display suggestions
    console.print(f"\n[bold cyan]🔄 Found {len(suggestions)} transition suggestions[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Title", style="cyan")
    table.add_column("Current", justify="center")
    table.add_column("→", justify="center", width=3)
    table.add_column("Suggested", justify="center")
    table.add_column("Reason", style="dim")
    
    for s in suggestions:
        current_emoji = _get_stage_emoji(s['current_stage'])
        suggested_emoji = _get_stage_emoji(s['suggested_stage'])
        
        table.add_row(
            str(s['doc_id']),
            s['title'][:30] + "..." if len(s['title']) > 30 else s['title'],
            f"{current_emoji} {s['current_stage']}",
            "→",
            f"{suggested_emoji} {s['suggested_stage']}",
            s['reason']
        )
    
    console.print(table)
    
    if not apply:
        console.print("\n[yellow]🔍 DRY RUN MODE - No changes made[/yellow]")
        console.print("[dim]Run with --apply to apply transitions[/dim]")
        return
    
    # Apply transitions
    if not typer.confirm(f"\n🔄 Apply {len(suggestions)} transitions?"):
        console.print("[red]Transitions cancelled[/red]")
        return
    
    success_count = 0
    for s in track(suggestions, description="Applying transitions..."):
        if tracker.transition_document(
            s['doc_id'], 
            s['suggested_stage'], 
            f"Auto-detected: {s['reason']}"
        ):
            success_count += 1
    
    console.print(f"\n[green]✅ Successfully applied {success_count} transitions![/green]")


@app.command()
def flow():
    """Visualize the lifecycle flow diagram."""
    
    console.print(Panel(
        "[bold cyan]📊 Document Lifecycle Flow[/bold cyan]",
        box=box.DOUBLE
    ))
    
    # Create a tree representation of the lifecycle
    tree = Tree("[bold]Document Lifecycle[/bold]")
    
    # Planning branch
    planning = tree.add("[cyan]🎯 Planning[/cyan]")
    planning.add("[green]→ 🚀 Active[/green] (start work)")
    planning.add("[yellow]→ 🚧 Blocked[/yellow] (hit obstacles)")
    planning.add("[dim]→ 📦 Archived[/dim] (abandon)")
    
    # Active branch
    active = tree.add("[green]🚀 Active[/green]")
    active.add("[yellow]→ 🚧 Blocked[/yellow] (hit obstacles)")
    active.add("[blue]→ ✅ Completed[/blue] (finish work)")
    active.add("[dim]→ 📦 Archived[/dim] (abandon)")
    
    # Blocked branch
    blocked = tree.add("[yellow]🚧 Blocked[/yellow]")
    blocked.add("[green]→ 🚀 Active[/green] (unblocked)")
    blocked.add("[red]→ ❌ Failed[/red] (give up)")
    blocked.add("[dim]→ 📦 Archived[/dim] (abandon)")
    
    # Completed branch
    completed = tree.add("[blue]✅ Completed[/blue]")
    completed.add("[bright_green]→ 🎉 Success[/bright_green] (goals achieved)")
    completed.add("[red]→ ❌ Failed[/red] (goals not met)")
    completed.add("[dim]→ 📦 Archived[/dim] (finalize)")
    
    # Terminal states
    tree.add("[bright_green]🎉 Success[/bright_green] [dim]→ 📦 Archived[/dim]")
    tree.add("[red]❌ Failed[/red] [dim]→ 📦 Archived[/dim]")
    tree.add("[dim]📦 Archived[/dim] (terminal state)")
    
    console.print(tree)
    
    console.print("\n[bold]Usage:[/bold]")
    console.print("  • Documents start in [cyan]Planning[/cyan] when tagged as gameplans")
    console.print("  • Move to [green]Active[/green] when work begins")
    console.print("  • Mark as [blue]Completed[/blue] when done")
    console.print("  • Specify [bright_green]Success[/bright_green] or [red]Failed[/red] outcome")
    console.print("  • [dim]Archive[/dim] when no longer relevant")


if __name__ == "__main__":
    app()
