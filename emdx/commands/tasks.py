"""Task CLI commands — simplified agent work queue.

Agent-facing commands for creating and consuming work items.
Delegate activity tracking is separate (shown via `emdx status`).
"""


import typer
from rich.table import Table

from emdx.models import tasks
from emdx.utils.output import console

app = typer.Typer(help="Agent work queue")

ICONS = {"open": "○", "active": "●", "done": "✓", "failed": "✗"}


@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    doc: int | None = typer.Option(None, "-d", "--doc", help="Link to document ID"),
    description: str | None = typer.Option(None, "-D", "--description", help="Task description"),
):
    """Add a task to the work queue.

    Examples:
        emdx task add "Fix the auth bug"
        emdx task add "Implement this" --doc 42
        emdx task add "Refactor tests" -D "Split into unit and integration"
    """
    task_id = tasks.create_task(
        title,
        description=description or "",
        source_doc_id=doc,
    )
    msg = f"[green]✅ Task #{task_id}:[/green] {title}"
    if doc:
        msg += f" [dim](doc #{doc})[/dim]"
    console.print(msg)


@app.command()
def ready():
    """Show tasks ready to work on.

    Lists open tasks that aren't blocked by dependencies.
    Excludes delegate activity — only shows manually created tasks.

    Examples:
        emdx task ready
    """
    ready_tasks = tasks.get_ready_tasks()

    if not ready_tasks:
        console.print("[yellow]No ready tasks[/yellow]")
        return

    console.print(f"\n[bold]Ready ({len(ready_tasks)}):[/bold]")
    for t in ready_tasks:
        doc = f" [dim](doc #{t['source_doc_id']})[/dim]" if t.get("source_doc_id") else ""
        console.print(f"  ○ #{t['id']} {t['title']}{doc}")


@app.command()
def done(
    task_id: int = typer.Argument(..., help="Task ID"),
    note: str | None = typer.Option(None, "-n", "--note", help="Completion note"),
):
    """Mark a task as done.

    Examples:
        emdx task done 42
        emdx task done 42 --note "Fixed in PR #123"
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    kwargs = {"status": "done"}
    tasks.update_task(task_id, **kwargs)
    if note:
        tasks.log_progress(task_id, note)

    console.print(f"[green]✓ Done:[/green] #{task_id} {task['title']}")


@app.command("list")
def list_cmd(
    status: str | None = typer.Option(None, "-s", "--status", help="Filter by status (comma-sep)"),
    all: bool = typer.Option(False, "--all", "-a", help="Include delegate tasks"),
    limit: int = typer.Option(20, "-n", "--limit"),
):
    """List tasks.

    By default only shows manually created tasks (not delegate activity).
    Use --all to include everything.

    Examples:
        emdx task list
        emdx task list --all
        emdx task list -s open,active
    """
    status_list = [s.strip() for s in status.split(",")] if status else None
    exclude_delegate = not all
    task_list = tasks.list_tasks(status=status_list, limit=limit, exclude_delegate=exclude_delegate)

    if not task_list:
        console.print("[yellow]No tasks[/yellow]")
        return

    table = Table()
    table.add_column("", width=2)
    table.add_column("ID", width=5)
    table.add_column("Title")
    table.add_column("Doc", width=5)

    for t in task_list:
        doc = str(t["source_doc_id"]) if t.get("source_doc_id") else ""
        table.add_row(
            ICONS.get(t["status"], "?"),
            str(t["id"]),
            t["title"][:50],
            doc,
        )

    console.print(table)
    console.print(f"\n[dim]{len(task_list)} task(s)[/dim]")


@app.command()
def delete(
    task_id: int = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a task.

    Examples:
        emdx task delete 42
        emdx task delete 42 --force
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if not force:
        console.print(f"Delete task #{task_id}: {task['title']}?")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    tasks.delete_task(task_id)
    console.print(f"[green]✅ Deleted #{task_id}[/green]")
