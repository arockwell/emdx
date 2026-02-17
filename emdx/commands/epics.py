"""Epic CLI commands — manage task epics (grouped work within categories)."""

import typer
from rich.table import Table

from emdx.models import tasks
from emdx.utils.output import console

app = typer.Typer(help="Manage task epics")

ICONS = {"open": "○", "active": "●", "done": "✓", "failed": "✗", "blocked": "⊘"}


@app.command()
def create(
    name: str = typer.Argument(..., help="Epic name"),
    cat: str = typer.Option(..., "--cat", "-c", help="Category key (e.g. SEC)"),
    description: str | None = typer.Option(None, "-D", "--description", help="Epic description"),
) -> None:
    """Create a new epic.

    Examples:
        emdx epic create "Security Hardening" --cat SEC
        emdx epic create "Security Hardening" --cat SEC -D "January 2026 security sweep"
    """
    try:
        epic_id = tasks.create_epic(name, cat, description or "")
        console.print(f"[green]Created epic #{epic_id}: {name} ({cat.upper()})[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@app.command("list")
def list_cmd(
    cat: str | None = typer.Option(None, "--cat", "-c", help="Filter by category"),
    status: str | None = typer.Option(None, "-s", "--status", help="Filter by status (comma-sep)"),
) -> None:
    """List epics with child task counts.

    Examples:
        emdx epic list
        emdx epic list --cat SEC
        emdx epic list --status open,active
    """
    status_list = [s.strip() for s in status.split(",")] if status else None
    epics = tasks.list_epics(category_key=cat, status=status_list)

    if not epics:
        console.print("[yellow]No epics[/yellow]")
        return

    table = Table()
    table.add_column("#", width=5)
    table.add_column("Epic")
    table.add_column("Cat", width=5)
    table.add_column("Status", width=8)
    table.add_column("Open", justify="right", width=5)
    table.add_column("Done", justify="right", width=5)
    table.add_column("Total", justify="right", width=6)

    for e in epics:
        table.add_row(
            str(e["id"]),
            e["title"][:40],
            e.get("epic_key") or "",
            e["status"],
            str(e["children_open"]),
            str(e["children_done"]),
            str(e["child_count"]),
        )

    console.print(table)


@app.command()
def view(
    epic_id: int = typer.Argument(..., help="Epic task ID"),
) -> None:
    """View an epic and its tasks.

    Examples:
        emdx epic view 510
    """
    epic = tasks.get_epic_view(epic_id)
    if not epic:
        console.print(f"[red]Epic #{epic_id} not found[/red]")
        raise typer.Exit(1)

    cat_label = f" ({epic['epic_key']})" if epic.get("epic_key") else ""
    console.print(
        f"\n[bold]Epic #{epic['id']}: {epic['title']}{cat_label}[/bold] — {epic['status']}"
    )
    if epic.get("description"):
        console.print(f"[dim]{epic['description']}[/dim]")
    console.print(f"[dim]Created: {epic.get('created_at', 'unknown')}[/dim]\n")

    children = epic.get("children", [])
    if children:
        console.print("[bold]Tasks:[/bold]")
        done_count = 0
        for c in children:
            icon = ICONS.get(c["status"], "?")
            seq_label = f"{c['epic_key']}-{c['epic_seq']}" if c.get("epic_seq") else f"#{c['id']}"
            console.print(f"  {icon}  {seq_label}  {c['title']}")
            if c["status"] == "done":
                done_count += 1
        console.print(f"\n[dim]Progress: {done_count}/{len(children)} done[/dim]")
    else:
        console.print("[dim]No tasks yet[/dim]")


@app.command()
def done(
    epic_id: int = typer.Argument(..., help="Epic task ID"),
) -> None:
    """Mark an epic as done.

    Examples:
        emdx epic done 510
    """
    epic = tasks.get_task(epic_id)
    if not epic:
        console.print(f"[red]Epic #{epic_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(epic_id, status="done")
    console.print(f"[green]✓ Done:[/green] Epic #{epic_id} {epic['title']}")


@app.command()
def active(
    epic_id: int = typer.Argument(..., help="Epic task ID"),
) -> None:
    """Mark an epic as active.

    Examples:
        emdx epic active 510
    """
    epic = tasks.get_task(epic_id)
    if not epic:
        console.print(f"[red]Epic #{epic_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(epic_id, status="active")
    console.print(f"[green]● Active:[/green] Epic #{epic_id} {epic['title']}")
