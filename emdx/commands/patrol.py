"""Patrol commands - autonomous work item processing."""

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..services.patrol import PatrolRunner, PatrolConfig, run_patrol
from ..work import WorkService

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="patrol",
    help="Autonomous work item processing through cascade stages",
)


@app.command("run")
def patrol_run(
    cascade: Optional[str] = typer.Option(None, "--cascade", "-c", help="Filter to specific cascade"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter to specific stage"),
    poll_interval: int = typer.Option(10, "--interval", "-i", help="Seconds between polls"),
    max_iterations: Optional[int] = typer.Option(None, "--max", "-m", help="Stop after N iterations"),
    once: bool = typer.Option(False, "--once", help="Process one batch and exit"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Don't execute Claude, just show what would happen"),
    name: str = typer.Option("patrol:worker", "--name", help="Patrol identity for claiming"),
):
    """
    Run a patrol that processes work items through stages.

    The patrol will:
    1. Find ready (unblocked, unclaimed) work items
    2. Claim them for exclusive processing
    3. Execute Claude with the stage processor prompt
    4. Advance to the next stage
    5. Release the claim

    Examples:
        emdx patrol run                     # Run forever, all cascades
        emdx patrol run --once              # Process one batch and exit
        emdx patrol run -c default -s idea  # Only process 'idea' stage
        emdx patrol run --dry-run           # Show what would happen
        emdx patrol run -i 30               # Poll every 30 seconds
    """
    if once:
        max_iterations = 1

    console.print(f"[bold cyan]Starting patrol {name}[/bold cyan]")
    console.print(f"  Cascade: {cascade or '[dim]all[/dim]'}")
    console.print(f"  Stage: {stage or '[dim]all non-terminal[/dim]'}")
    console.print(f"  Poll interval: {poll_interval}s")
    if dry_run:
        console.print("  [yellow]DRY RUN - no Claude execution[/yellow]")
    console.print()
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    console.print()

    try:
        stats = run_patrol(
            cascade=cascade,
            stage=stage,
            poll_interval=poll_interval,
            max_iterations=max_iterations,
            dry_run=dry_run,
            name=name,
        )

        console.print()
        console.print("[bold]Patrol Summary[/bold]")
        console.print(f"  Processed: {stats.items_processed}")
        console.print(f"  Succeeded: [green]{stats.items_succeeded}[/green]")
        console.print(f"  Failed: [red]{stats.items_failed}[/red]")
        console.print(f"  Total time: {stats.total_time:.1f}s")

        if stats.errors:
            console.print()
            console.print("[bold red]Errors:[/bold red]")
            for error in stats.errors[:5]:
                console.print(f"  • {error}")
            if len(stats.errors) > 5:
                console.print(f"  ... and {len(stats.errors) - 5} more")

    except KeyboardInterrupt:
        console.print("\n[yellow]Patrol stopped by user[/yellow]")


@app.command("status")
def patrol_status(
    cascade: Optional[str] = typer.Option(None, "--cascade", "-c", help="Filter to specific cascade"),
):
    """
    Show work items ready for patrol processing.

    Examples:
        emdx patrol status
        emdx patrol status -c default
    """
    service = WorkService()

    # Get ready items
    ready = service.ready(cascade=cascade, limit=50)

    if not ready:
        console.print("[dim]No work items ready for processing[/dim]")
        return

    # Group by cascade/stage
    by_cascade: dict = {}
    for item in ready:
        key = item.cascade
        if key not in by_cascade:
            by_cascade[key] = {}
        if item.stage not in by_cascade[key]:
            by_cascade[key][item.stage] = []
        by_cascade[key][item.stage].append(item)

    console.print(f"[bold]Ready for Processing ({len(ready)} items)[/bold]")
    console.print()

    for cascade_name, stages in by_cascade.items():
        cascade_def = service.get_cascade(cascade_name)
        console.print(f"[bold cyan]{cascade_name}[/bold cyan]")

        for stage, items in stages.items():
            processor = cascade_def.get_processor(stage) if cascade_def else None
            has_processor = "✓" if processor else "○"
            console.print(f"  {has_processor} {stage}: {len(items)} item(s)")
            for item in items[:3]:
                console.print(f"      [dim]{item.id}[/dim] {item.title[:40]}")
            if len(items) > 3:
                console.print(f"      [dim]... and {len(items) - 3} more[/dim]")
        console.print()


@app.command("process")
def patrol_process(
    work_id: str = typer.Argument(..., help="Work item ID to process"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show prompt without executing"),
):
    """
    Process a single work item through its current stage.

    This is useful for testing or manually advancing specific items.

    Examples:
        emdx patrol process emdx-a3f2dd
        emdx patrol process emdx-a3f2dd --dry-run
    """
    service = WorkService()

    item = service.get(work_id)
    if not item:
        console.print(f"[red]Work item not found:[/red] {work_id}")
        raise typer.Exit(1)

    cascade = service.get_cascade(item.cascade)
    if not cascade:
        console.print(f"[red]Cascade not found:[/red] {item.cascade}")
        raise typer.Exit(1)

    processor = cascade.get_processor(item.stage)

    console.print(f"[bold]Processing {item.id}[/bold]")
    console.print(f"  Title: {item.title}")
    console.print(f"  Stage: {item.stage} → {cascade.get_next_stage(item.stage) or '[terminal]'}")
    console.print()

    if processor:
        console.print("[bold]Processor prompt:[/bold]")
        console.print(f"[dim]{processor[:200]}{'...' if len(processor) > 200 else ''}[/dim]")
        console.print()
    else:
        console.print("[yellow]No processor for this stage - will advance directly[/yellow]")
        console.print()

    if dry_run:
        console.print("[yellow]DRY RUN - not executing[/yellow]")
        return

    # Process using PatrolRunner
    config = PatrolConfig(name="patrol:manual", dry_run=False)
    runner = PatrolRunner(config)

    # Claim the item
    try:
        service.claim(item.id, config.name)
    except ValueError as e:
        console.print(f"[red]Could not claim item:[/red] {e}")
        raise typer.Exit(1)

    try:
        success = runner.process_one(item)
        if success:
            console.print("[green]✓ Processing completed[/green]")
            # Reload to show new state
            item = service.get(work_id)
            console.print(f"  New stage: {item.stage}")
        else:
            console.print("[red]✗ Processing failed[/red]")
            if runner.stats.errors:
                for error in runner.stats.errors:
                    console.print(f"  [red]{error}[/red]")
            raise typer.Exit(1)
    finally:
        try:
            service.release(item.id)
        except Exception:
            pass


@app.command("test")
def patrol_test():
    """
    Test patrol connectivity and configuration.

    Verifies:
    - Database connection
    - Cascade definitions
    - Claude availability
    """
    console.print("[bold]Patrol System Test[/bold]")
    console.print()

    # Test database
    try:
        service = WorkService()
        cascades = service.list_cascades()
        console.print(f"[green]✓[/green] Database connection OK")
        console.print(f"[green]✓[/green] Found {len(cascades)} cascade(s)")
    except Exception as e:
        console.print(f"[red]✗[/red] Database error: {e}")
        raise typer.Exit(1)

    # Test cascades have processors
    for cascade in cascades:
        has_processors = len(cascade.processors) > 0
        if has_processors:
            console.print(f"[green]✓[/green] {cascade.name}: {len(cascade.processors)} processor(s)")
        else:
            console.print(f"[yellow]○[/yellow] {cascade.name}: no processors (items will just advance)")

    # Test Claude availability
    try:
        from ..utils.environment import validate_execution_environment
        is_valid, env_info = validate_execution_environment(verbose=False)
        if is_valid:
            console.print(f"[green]✓[/green] Claude environment OK")
        else:
            errors = env_info.get('errors', ['Unknown error'])
            console.print(f"[red]✗[/red] Claude environment: {'; '.join(errors)}")
    except Exception as e:
        console.print(f"[yellow]○[/yellow] Could not check Claude environment: {e}")

    # Show ready items
    ready = service.ready(limit=5)
    console.print()
    console.print(f"[bold]Ready items:[/bold] {len(ready)}")
    for item in ready[:5]:
        console.print(f"  {item.id} [{item.cascade}/{item.stage}] {item.title[:40]}")

    console.print()
    console.print("[dim]Run 'emdx patrol run --dry-run' to test processing[/dim]")
