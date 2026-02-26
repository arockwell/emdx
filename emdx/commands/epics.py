"""Epic CLI commands — manage task epics (grouped work within categories)."""

import typer
from rich.table import Table

from emdx.models import tasks
from emdx.models.types import TaskRef
from emdx.utils.output import console

app = typer.Typer(help="Manage task epics")

ICONS = {"open": "○", "active": "●", "done": "✓", "failed": "✗", "blocked": "⊘"}

EPIC_ID_HELP = "Epic ID (e.g. 510 or SEC-1)"


def _resolve_epic_id(identifier: TaskRef) -> int:
    """Resolve an epic identifier string to a database ID.

    Accepts integer IDs (510) or category keys (SEC-1).
    Prints an error and raises typer.Exit(1) if resolution fails.
    """
    task_id = tasks.resolve_task_id(identifier)
    if task_id is None:
        console.print(f"[red]Epic not found: {identifier}[/red]")
        raise typer.Exit(1)
    return task_id


@app.command()
def create(
    name: str = typer.Argument(..., help="Epic name"),
    cat: str = typer.Option(..., "--cat", "-c", help="Category key (e.g. SEC)"),
    description: str | None = typer.Option(None, "-D", "--description", help="Epic description"),
) -> None:
    """Create a new epic.

    Examples:
        emdx task epic create "Security Hardening" --cat SEC
        emdx task epic create "Security Hardening" --cat SEC -D "January 2026 security sweep"
    """
    try:
        epic_id = tasks.create_epic(name, cat, description or "")
        epic = tasks.get_task(epic_id)
        seq = epic["epic_seq"] if epic else None
        key_label = f"{cat.upper()}-{seq}" if seq else f"#{epic_id}"
        id_suffix = f" (#{epic_id})" if seq else ""
        console.print(f"[green]Created epic {key_label}{id_suffix}: {name}[/green]")
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
        emdx task epic list
        emdx task epic list --cat SEC
        emdx task epic list --status open,active
    """
    status_list = [s.strip() for s in status.split(",")] if status else None
    epics = tasks.list_epics(category_key=cat, status=status_list)

    if not epics:
        console.print("[yellow]No epics[/yellow]")
        return

    table = Table()
    table.add_column("Key", width=9)
    table.add_column("Epic")
    table.add_column("Status", width=8)
    table.add_column("Open", justify="right", width=5)
    table.add_column("Done", justify="right", width=5)
    table.add_column("Total", justify="right", width=6)

    for e in epics:
        epic_key = e.get("epic_key") or ""
        epic_seq = e.get("epic_seq")
        key_label = f"{epic_key}-{epic_seq}" if epic_key and epic_seq else str(e["id"])
        table.add_row(
            key_label,
            e["title"][:40],
            e["status"],
            str(e["children_open"]),
            str(e["children_done"]),
            str(e["child_count"]),
        )

    console.print(table)


@app.command()
def view(
    epic_id_str: str = typer.Argument(..., metavar="EPIC_ID", help=EPIC_ID_HELP),
) -> None:
    """View an epic and its tasks.

    Examples:
        emdx task epic view 510
        emdx task epic view SEC-1
    """
    epic_id = _resolve_epic_id(epic_id_str)
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
def delete(
    epic_id_str: str = typer.Argument(..., metavar="EPIC_ID", help=EPIC_ID_HELP),
    force: bool = typer.Option(
        False, "--force", "-f", help="Delete even if open/active child tasks exist"
    ),
) -> None:
    """Delete an epic and unlink its child tasks.

    Child tasks are NOT deleted — their parent_task_id is cleared.
    Refuses to delete if open/active children exist unless --force is used.

    Examples:
        emdx task epic delete 510
        emdx task epic delete SEC-1 --force
    """
    epic_id = _resolve_epic_id(epic_id_str)
    try:
        result = tasks.delete_epic(epic_id, force=force)
        console.print(f"[green]Deleted epic #{epic_id}[/green]")
        if result["children_unlinked"]:
            console.print(f"[yellow]Unlinked {result['children_unlinked']} child task(s)[/yellow]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def done(
    epic_id_str: str = typer.Argument(..., metavar="EPIC_ID", help=EPIC_ID_HELP),
) -> None:
    """Mark an epic as done.

    Examples:
        emdx task epic done 510
        emdx task epic done SEC-1
    """
    epic_id = _resolve_epic_id(epic_id_str)
    epic = tasks.get_task(epic_id)
    if not epic:
        console.print(f"[red]Epic #{epic_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(epic_id, status="done")
    console.print(f"[green]✓ Done:[/green] Epic #{epic_id} {epic['title']}")


@app.command()
def active(
    epic_id_str: str = typer.Argument(..., metavar="EPIC_ID", help=EPIC_ID_HELP),
) -> None:
    """Mark an epic as active.

    Examples:
        emdx task epic active 510
        emdx task epic active SEC-1
    """
    epic_id = _resolve_epic_id(epic_id_str)
    epic = tasks.get_task(epic_id)
    if not epic:
        console.print(f"[red]Epic #{epic_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(epic_id, status="active")
    console.print(f"[green]● Active:[/green] Epic #{epic_id} {epic['title']}")


TASK_ID_HELP = "Task ID (e.g. 42 or TOOL-12)"


@app.command()
def attach(
    task_ids: list[TaskRef] = typer.Argument(..., help=TASK_ID_HELP),
    epic: TaskRef = typer.Option(..., "-e", "--epic", help=EPIC_ID_HELP),
) -> None:
    """Attach existing tasks to an epic.

    Tasks inherit the epic's category key and get assigned a sequence number.

    Examples:
        emdx task epic attach TOOL-14 --epic TOOL-68
        emdx task epic attach TOOL-14 TOOL-15 TOOL-16 --epic SEC-1
        emdx task epic attach 42 43 --epic 510
    """
    epic_id = _resolve_epic_id(epic)

    resolved_ids: list[int] = []
    for tid_str in task_ids:
        resolved = tasks.resolve_task_id(tid_str)
        if resolved is None:
            console.print(f"[red]Invalid task ID: {tid_str}[/red]")
            raise typer.Exit(1)
        resolved_ids.append(resolved)

    try:
        count = tasks.attach_to_epic(resolved_ids, epic_id)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    epic_task = tasks.get_task(epic_id)
    epic_label = f"#{epic_id}"
    if epic_task and epic_task.get("epic_key") and epic_task.get("epic_seq"):
        epic_label = f"{epic_task['epic_key']}-{epic_task['epic_seq']}"

    console.print(f"[green]✅ Attached {count} task(s) to epic {epic_label}[/green]")
