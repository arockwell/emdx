"""
CLI commands for the Unified Work System.

Provides commands for managing work items that flow through cascade stages.
"""

import json
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from ..work import WorkService, WorkItem

app = typer.Typer(help="Unified work system - manage work items through cascade stages")
console = Console()

# Singleton service instance
_service: Optional[WorkService] = None


def get_service() -> WorkService:
    """Get or create the work service singleton."""
    global _service
    if _service is None:
        _service = WorkService()
    return _service


# =============================================================================
# WORK ITEM COMMANDS
# =============================================================================


@app.command("add")
def add_work(
    title: str = typer.Argument(..., help="Title/description of the work item"),
    cascade: str = typer.Option("default", "--cascade", "-c", help="Cascade pipeline to use"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Initial stage (defaults to first stage)"),
    priority: int = typer.Option(3, "--priority", "-p", help="Priority: 0=critical, 1=high, 2=medium, 3=low, 4=backlog"),
    type_: str = typer.Option("task", "--type", "-t", help="Type: task, bug, feature, epic, research, review"),
    depends_on: Optional[List[str]] = typer.Option(None, "--depends-on", "-d", help="Work item IDs this depends on"),
    parent: Optional[str] = typer.Option(None, "--parent", help="Parent work item ID (for epics)"),
    content: Optional[str] = typer.Option(None, "--content", help="Initial content/description"),
):
    """
    Add a new work item.

    Examples:
        emdx work add "Make the app faster"
        emdx work add "Fix null pointer" --stage planned --priority 1
        emdx work add "Review PR #42" --cascade review --stage draft
        emdx work add "Add caching" --depends-on emdx-a3f2dd
    """
    service = get_service()

    try:
        item = service.add(
            title=title,
            cascade=cascade,
            stage=stage,
            priority=priority,
            type_=type_,
            depends_on=depends_on,
            parent_id=parent,
            content=content,
        )
        console.print(f"[green]✓[/green] Created [cyan]{item.id}[/cyan]: {item.title}")
        console.print(f"  Cascade: {item.cascade} | Stage: {item.stage} | Priority: {item.priority_label}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("ready")
def ready_work(
    cascade: Optional[str] = typer.Option(None, "--cascade", "-c", help="Filter by cascade"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter by stage"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum items to show"),
):
    """
    Show work items that are ready (unblocked, unclaimed).

    Examples:
        emdx work ready
        emdx work ready --cascade review
        emdx work ready --stage planned
        emdx work ready --json
    """
    service = get_service()
    items = service.ready(cascade=cascade, stage=stage, limit=limit)

    if json_output:
        output = [
            {
                "id": item.id,
                "title": item.title,
                "cascade": item.cascade,
                "stage": item.stage,
                "priority": item.priority,
                "type": item.type,
            }
            for item in items
        ]
        print(json.dumps(output, indent=2))
        return

    if not items:
        console.print("[yellow]No ready work items.[/yellow]")
        console.print("Add work with: [cyan]emdx work add \"description\"[/cyan]")
        return

    console.print(f"\n[bold green]Ready Work[/bold green] ({len(items)} items)\n")

    for item in items:
        priority_colors = ["red", "yellow", "blue", "dim", "dim"]
        priority_labels = ["P0", "P1", "P2", "P3", "P4"]
        p_idx = min(item.priority, 4)

        cascade_stage = f"{item.cascade}/{item.stage}"
        console.print(
            f"  [cyan]{item.id}[/cyan]  "
            f"[{priority_colors[p_idx]}]{priority_labels[p_idx]}[/{priority_colors[p_idx]}]  "
            f"{item.title[:50]}  "
            f"[dim]{cascade_stage}[/dim]"
        )

    console.print()
    console.print("[dim]Commands: [cyan]emdx work show <id>[/cyan] | [cyan]emdx work advance <id>[/cyan] | [cyan]emdx work start <id>[/cyan][/dim]")


@app.command("show")
def show_work(
    work_id: str = typer.Argument(..., help="Work item ID"),
    transitions: bool = typer.Option(False, "--transitions", "-t", help="Show transition history"),
):
    """
    Show details of a work item.

    Examples:
        emdx work show emdx-a3f2dd
        emdx work show emdx-a3f2dd --transitions
    """
    service = get_service()
    item = service.get(work_id)

    if not item:
        console.print(f"[red]Work item not found:[/red] {work_id}")
        raise typer.Exit(1)

    # Header
    console.print()
    console.print(Panel(
        f"[bold cyan]{item.id}[/bold cyan] - {item.title}",
        expand=False
    ))

    # Status info
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="dim")
    table.add_column("Value")

    table.add_row("Cascade", item.cascade)
    table.add_row("Stage", item.stage)
    table.add_row("Priority", item.priority_label)
    table.add_row("Type", item.type)

    if item.project:
        table.add_row("Project", item.project)
    if item.parent_id:
        table.add_row("Parent", item.parent_id)
    if item.pr_number:
        table.add_row("PR", f"#{item.pr_number}")
    if item.claimed_by:
        table.add_row("Claimed by", item.claimed_by)
    if item.is_blocked:
        table.add_row("Blocked by", ", ".join(item.blocked_by))

    console.print(table)

    # Content
    if item.content:
        console.print()
        console.print("[bold]Content:[/bold]")
        console.print(Panel(Markdown(item.content), expand=False))

    # Dependencies
    deps = service.get_dependencies(work_id)
    if deps:
        console.print()
        console.print("[bold]Dependencies:[/bold]")
        for dep, dep_item in deps:
            status = "✓" if dep_item.is_done else "○"
            console.print(f"  {status} [{dep.dep_type}] [cyan]{dep_item.id}[/cyan] {dep_item.title[:40]} ({dep_item.stage})")

    # Transitions history
    if transitions:
        trans = service.get_transitions(work_id)
        if trans:
            console.print()
            console.print("[bold]Transitions:[/bold]")
            for t in trans:
                from_str = t.from_stage or "(created)"
                console.print(f"  {t.created_at} {from_str} → {t.to_stage} [{t.transitioned_by}]")

    console.print()


@app.command("advance")
def advance_work(
    work_id: str = typer.Argument(..., help="Work item ID to advance"),
    by: str = typer.Option("manual", "--by", help="Who/what is advancing (for audit)"),
):
    """
    Advance a work item to the next stage.

    Examples:
        emdx work advance emdx-a3f2dd
        emdx work advance emdx-a3f2dd --by "patrol:worker"
    """
    service = get_service()

    try:
        item = service.advance(work_id, transitioned_by=by)
        console.print(f"[green]✓[/green] Advanced [cyan]{item.id}[/cyan] to stage: [bold]{item.stage}[/bold]")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("start")
def start_work(
    work_id: str = typer.Argument(..., help="Work item ID to start"),
    claim_as: Optional[str] = typer.Option(None, "--claim-as", help="Claim as this agent/patrol"),
):
    """
    Start working on a work item (move to implementing stage).

    Examples:
        emdx work start emdx-a3f2dd
        emdx work start emdx-a3f2dd --claim-as "patrol:worker"
    """
    service = get_service()

    try:
        item = service.get(work_id)
        if not item:
            console.print(f"[red]Work item not found:[/red] {work_id}")
            raise typer.Exit(1)

        # Claim if requested
        if claim_as:
            item = service.claim(work_id, claim_as)

        # Move to implementing (or equivalent stage)
        cascade = service.get_cascade(item.cascade)
        implementing_stages = ["implementing", "draft", "fixing", "working"]
        target_stage = None
        for stage in implementing_stages:
            if stage in cascade.stages:
                target_stage = stage
                break

        if target_stage and item.stage != target_stage:
            # Skip to implementing stage
            item = service.set_stage(work_id, target_stage, "start")

        console.print(f"[green]✓[/green] Started [cyan]{item.id}[/cyan]")
        console.print(f"  Stage: {item.stage}")
        if item.claimed_by:
            console.print(f"  Claimed by: {item.claimed_by}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("done")
def done_work(
    work_id: str = typer.Argument(..., help="Work item ID to mark done"),
    pr: Optional[int] = typer.Option(None, "--pr", help="Associated PR number"),
    doc: Optional[int] = typer.Option(None, "--doc", help="Associated output document ID"),
):
    """
    Mark a work item as done.

    Examples:
        emdx work done emdx-a3f2dd
        emdx work done emdx-a3f2dd --pr 123
    """
    service = get_service()

    try:
        item = service.done(work_id, pr_number=pr, output_doc_id=doc)
        console.print(f"[green]✓[/green] Completed [cyan]{item.id}[/cyan]")
        console.print(f"  Final stage: {item.stage}")
        if item.pr_number:
            console.print(f"  PR: #{item.pr_number}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("list")
def list_work(
    cascade: Optional[str] = typer.Option(None, "--cascade", "-c", help="Filter by cascade"),
    stage: Optional[str] = typer.Option(None, "--stage", "-s", help="Filter by stage"),
    include_done: bool = typer.Option(False, "--all", "-a", help="Include completed items"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum items"),
):
    """
    List work items with optional filters.

    Examples:
        emdx work list
        emdx work list --cascade review
        emdx work list --stage planned
        emdx work list --all
    """
    service = get_service()
    items = service.list(cascade=cascade, stage=stage, include_done=include_done, limit=limit)

    if not items:
        console.print("[yellow]No work items found.[/yellow]")
        return

    table = Table(title=f"Work Items ({len(items)})")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Cascade/Stage")
    table.add_column("Priority")
    table.add_column("Status")

    for item in items:
        status = ""
        if item.is_done:
            status = "[green]✓ done[/green]"
        elif item.claimed_by:
            status = f"[yellow]⚡ {item.claimed_by}[/yellow]"
        elif item.is_blocked:
            status = "[red]⛔ blocked[/red]"
        else:
            status = "[dim]ready[/dim]"

        table.add_row(
            item.id,
            item.title[:40] + ("..." if len(item.title) > 40 else ""),
            f"{item.cascade}/{item.stage}",
            item.priority_label,
            status,
        )

    console.print(table)


@app.command("claim")
def claim_work(
    work_id: str = typer.Argument(..., help="Work item ID to claim"),
    as_: str = typer.Option(..., "--as", help="Claim as this agent/patrol"),
):
    """
    Claim a work item for exclusive processing.

    Examples:
        emdx work claim emdx-a3f2dd --as "patrol:worker"
    """
    service = get_service()

    try:
        item = service.claim(work_id, as_)
        console.print(f"[green]✓[/green] Claimed [cyan]{item.id}[/cyan] as {as_}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("release")
def release_work(
    work_id: str = typer.Argument(..., help="Work item ID to release"),
):
    """
    Release a claimed work item.

    Examples:
        emdx work release emdx-a3f2dd
    """
    service = get_service()
    item = service.release(work_id)
    console.print(f"[green]✓[/green] Released [cyan]{item.id}[/cyan]")


@app.command("dep")
def manage_deps(
    work_id: str = typer.Argument(..., help="Work item ID"),
    add: Optional[str] = typer.Option(None, "--add", "-a", help="Add dependency on this work item"),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="Remove dependency on this work item"),
    dep_type: str = typer.Option("blocks", "--type", "-t", help="Dependency type: blocks, related, discovered-from"),
):
    """
    Manage dependencies for a work item.

    Examples:
        emdx work dep emdx-a3f2dd --add emdx-b4c5ee
        emdx work dep emdx-a3f2dd --add emdx-c6d7ff --type related
        emdx work dep emdx-a3f2dd --remove emdx-b4c5ee
    """
    service = get_service()

    if add:
        try:
            dep = service.add_dependency(work_id, add, dep_type)
            console.print(f"[green]✓[/green] Added {dep_type} dependency: {work_id} → {add}")
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    elif remove:
        if service.remove_dependency(work_id, remove):
            console.print(f"[green]✓[/green] Removed dependency: {work_id} → {remove}")
        else:
            console.print(f"[yellow]Dependency not found[/yellow]")
    else:
        # Show dependencies
        deps = service.get_dependencies(work_id)
        if deps:
            console.print(f"\n[bold]Dependencies of {work_id}:[/bold]")
            for dep, item in deps:
                status = "✓" if item.is_done else "○"
                console.print(f"  {status} [{dep.dep_type}] [cyan]{item.id}[/cyan] {item.title[:40]} ({item.stage})")
        else:
            console.print(f"[dim]No dependencies for {work_id}[/dim]")

        dependents = service.get_dependents(work_id)
        if dependents:
            console.print(f"\n[bold]Dependents on {work_id}:[/bold]")
            for dep, item in dependents:
                console.print(f"  [{dep.dep_type}] [cyan]{item.id}[/cyan] {item.title[:40]} ({item.stage})")


# =============================================================================
# CASCADE COMMANDS
# =============================================================================


@app.command("cascades")
def list_cascades():
    """
    List all cascade definitions.

    Examples:
        emdx work cascades
    """
    service = get_service()
    cascades = service.list_cascades()

    console.print("\n[bold]Available Cascades[/bold]\n")

    for c in cascades:
        stages_str = " → ".join(c.stages)
        console.print(f"[cyan]{c.name}[/cyan]: {stages_str}")
        if c.description:
            console.print(f"  [dim]{c.description}[/dim]")
        console.print()


@app.command("status")
def work_status(
    cascade: Optional[str] = typer.Option(None, "--cascade", "-c", help="Filter by cascade"),
):
    """
    Show work status overview by cascade and stage.

    Examples:
        emdx work status
        emdx work status --cascade default
    """
    service = get_service()
    counts = service.get_stage_counts(cascade)

    if not counts:
        console.print("[yellow]No work items found.[/yellow]")
        return

    console.print("\n[bold]Work Status[/bold]\n")

    for cascade_name, stage_counts in counts.items():
        cascade_def = service.get_cascade(cascade_name)
        if not cascade_def:
            continue

        total = sum(stage_counts.values())
        console.print(f"[cyan]{cascade_name}[/cyan] ({total} items)")

        # Show stages in order with counts
        stages_display = []
        for stage in cascade_def.stages:
            count = stage_counts.get(stage, 0)
            if count > 0:
                stages_display.append(f"{stage}({count})")
            else:
                stages_display.append(f"[dim]{stage}[/dim]")

        console.print("  " + " → ".join(stages_display))
        console.print()

    # Show ready count
    ready = service.ready(cascade=cascade)
    console.print(f"[green]Ready to work:[/green] {len(ready)} items")
    console.print()
