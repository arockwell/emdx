"""Task CLI commands — simplified agent work queue.

Agent-facing commands for creating and consuming work items.
Delegate activity tracking is separate (shown via `emdx status`).
"""

import typer
from rich.table import Table
from rich.text import Text

from emdx.models import tasks
from emdx.models.types import TaskDict
from emdx.utils.output import console, print_json

app = typer.Typer(help="Agent work queue")

ICONS = {"open": "○", "active": "●", "done": "✓", "failed": "✗", "blocked": "⊘", "closed": "✓"}
STATUS_STYLE = {
    "open": "default",
    "active": "blue",
    "blocked": "yellow",
    "done": "green",
    "failed": "red",
    "closed": "green",
}


def _blocker_summary(task_id: int) -> str:
    """Get one-line blocker info for a task."""
    deps = tasks.get_dependencies(task_id)
    if not deps:
        return ""
    open_deps = [d for d in deps if d["status"] not in ("done", "closed")]
    if not open_deps:
        return ""
    names = ", ".join(f"#{d['id']}" for d in open_deps[:3])
    extra = f" +{len(open_deps) - 3}" if len(open_deps) > 3 else ""
    return f"{names}{extra}"


@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    doc: int | None = typer.Option(None, "-d", "--doc", help="Link to document ID"),
    description: str | None = typer.Option(None, "-D", "--description", help="Task description"),
    epic: int | None = typer.Option(None, "-e", "--epic", help="Add to epic (task ID)"),
    cat: str | None = typer.Option(None, "-c", "--cat", help="Category key (e.g. SEC)"),
) -> None:
    """Add a task to the work queue.

    Examples:
        emdx task add "Fix the auth bug"
        emdx task add "Implement this" --doc 42
        emdx task add "Refactor tests" -D "Split into unit and integration"
        emdx task add "Test task" --epic 510
        emdx task add "Another task" --cat SEC
    """
    parent_task_id = None
    epic_key = cat.upper() if cat else None

    if epic:
        parent_task = tasks.get_task(epic)
        if not parent_task:
            console.print(f"[red]Epic #{epic} not found[/red]")
            raise typer.Exit(1)
        parent_task_id = epic
        # Inherit epic_key from the parent epic if not explicitly set
        if not epic_key and parent_task.get("epic_key"):
            epic_key = parent_task["epic_key"]

    task_id = tasks.create_task(
        title,
        description=description or "",
        source_doc_id=doc,
        parent_task_id=parent_task_id,
        epic_key=epic_key,
    )
    msg = f"[green]✅ Task #{task_id}:[/green] {title}"
    if doc:
        msg += f" [dim](doc #{doc})[/dim]"
    if epic_key:
        msg += f" [dim]({epic_key})[/dim]"
    console.print(msg)


@app.command()
def ready(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show tasks ready to work on.

    Lists open tasks that aren't blocked by dependencies.
    Excludes delegate activity — only shows manually created tasks.

    Examples:
        emdx task ready
    """
    ready_tasks = tasks.get_ready_tasks()

    if json_output:
        print_json(ready_tasks)
        return

    if not ready_tasks:
        console.print("[yellow]No ready tasks[/yellow]")
        return

    table = Table(title=f"Ready ({len(ready_tasks)})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title")

    for t in ready_tasks:
        table.add_row(_task_label(t), _display_title(t))

    console.print(table)


@app.command()
def done(
    task_id: int = typer.Argument(..., help="Task ID"),
    note: str | None = typer.Option(None, "-n", "--note", help="Completion note"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark a task as done.

    Examples:
        emdx task done 42
        emdx task done 42 --note "Fixed in PR #123"
    """
    task = tasks.get_task(task_id)
    if not task:
        if json_output:
            print_json({"error": f"Task #{task_id} not found"})
        else:
            console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    kwargs = {"status": "done"}
    tasks.update_task(task_id, **kwargs)
    if note:
        tasks.log_progress(task_id, note)

    if json_output:
        print_json({"id": task_id, "title": task["title"], "status": "done"})
    else:
        console.print(f"[green]✓ Done:[/green] #{task_id} {task['title']}")


@app.command()
def view(
    task_id: int = typer.Argument(..., help="Task ID"),
) -> None:
    """View full task details.

    Shows title, description, status, epic/category, source doc,
    dependencies, and recent work log entries.

    Examples:
        emdx task view 42
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    icon = ICONS.get(task["status"], "?")
    # Header
    label = f"#{task_id}"
    if task.get("epic_key") and task.get("epic_seq"):
        label = f"{task['epic_key']}-{task['epic_seq']} (#{task_id})"
    console.print(f"\n[bold]{icon} {label}: {task['title']}[/bold]")

    # Metadata line
    meta = [f"Status: {task['status']}"]
    if task.get("epic_key"):
        meta.append(f"Category: {task['epic_key']}")
    if task.get("parent_task_id"):
        meta.append(f"Epic: #{task['parent_task_id']}")
    if task.get("priority") and task["priority"] != 3:
        meta.append(f"Priority: {task['priority']}")
    console.print(f"[dim]{' | '.join(meta)}[/dim]")

    if task.get("created_at"):
        console.print(f"[dim]Created: {task['created_at']}[/dim]")

    # Linked documents
    from emdx.models.documents import get_document

    source_id = task.get("source_doc_id")
    output_id = task.get("output_doc_id")
    if source_id or output_id:
        console.print()
        if source_id:
            source_doc = get_document(source_id)
            if source_doc:
                console.print(
                    f"  [dim]Input:[/dim]  #{source_id} [cyan]{source_doc['title']}[/cyan]"
                )
            else:
                console.print(f"  [dim]Input:[/dim]  #{source_id} [dim](deleted)[/dim]")
        if output_id:
            output_doc = get_document(output_id)
            if output_doc:
                console.print(
                    f"  [dim]Output:[/dim] #{output_id} [cyan]{output_doc['title']}[/cyan]"
                )
            else:
                console.print(f"  [dim]Output:[/dim] #{output_id} [dim](deleted)[/dim]")

    # Description
    if task.get("description"):
        console.print(f"\n{task['description']}")

    # Dependencies
    deps = tasks.get_dependencies(task_id)
    if deps:
        console.print("\n[bold]Blocked by:[/bold]")
        for d in deps:
            dep_icon = ICONS.get(d["status"], "?")
            console.print(f"  {dep_icon} #{d['id']} {d['title']}")

    dependents = tasks.get_dependents(task_id)
    if dependents:
        console.print("\n[bold]Blocks:[/bold]")
        for d in dependents:
            dep_icon = ICONS.get(d["status"], "?")
            console.print(f"  {dep_icon} #{d['id']} {d['title']}")

    # Work log
    log = tasks.get_task_log(task_id, limit=5)
    if log:
        console.print("\n[bold]Work log:[/bold]")
        for entry in log:
            ts = entry.get("created_at", "")
            console.print(f"  [dim]{ts}[/dim] {entry['message']}")


@app.command()
def active(
    task_id: int = typer.Argument(..., help="Task ID"),
    note: str | None = typer.Option(None, "-n", "--note", help="Progress note"),
) -> None:
    """Mark a task as in-progress.

    Use this at session start after picking a task from 'emdx task ready'.

    Examples:
        emdx task active 42
        emdx task active 42 --note "Starting work on auth refactor"
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(task_id, status="active")
    if note:
        tasks.log_progress(task_id, note)

    console.print(f"[blue]● Active:[/blue] #{task_id} {task['title']}")


@app.command()
def log(
    task_id: int = typer.Argument(..., help="Task ID"),
    message: str | None = typer.Argument(None, help="Log message (omit to view log)"),
) -> None:
    """View or add to a task's work log.

    Without a message, shows the log history.
    With a message, appends an entry.

    Examples:
        emdx task log 42
        emdx task log 42 "Investigated root cause — issue is in auth middleware"
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if message:
        tasks.log_progress(task_id, message)
        console.print(f"[green]Logged:[/green] #{task_id} — {message}")
        return

    entries = tasks.get_task_log(task_id, limit=20)
    if not entries:
        console.print(f"[yellow]No log entries for #{task_id}[/yellow]")
        return

    console.print(f"\n[bold]Log for #{task_id}: {task['title']}[/bold]")
    for entry in entries:
        ts = entry.get("created_at", "")
        console.print(f"  [dim]{ts}[/dim] {entry['message']}")


@app.command()
def note(
    task_id: int = typer.Argument(..., help="Task ID"),
    message: str = typer.Argument(..., help="Progress note"),
) -> None:
    """Log a progress note on a task without changing its status.

    Shorthand for 'emdx task log <id> "message"'.

    Examples:
        emdx task note 42 "Root cause is in auth middleware"
        emdx task note 42 "Tried approach X, didn't work — switching to Y"
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.log_progress(task_id, message)
    console.print(f"[green]Logged:[/green] #{task_id} — {message}")


@app.command()
def blocked(
    task_id: int = typer.Argument(..., help="Task ID"),
    reason: str = typer.Option("", "-r", "--reason", help="Why the task is blocked"),
) -> None:
    """Mark a task as blocked.

    Optionally provide a reason, which is logged to the work log.

    Examples:
        emdx task blocked 42
        emdx task blocked 42 --reason "Waiting on API key from infra team"
    """
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(task_id, status="blocked")
    if reason:
        tasks.log_progress(task_id, f"Blocked: {reason}")

    msg = f"[yellow]⊘ Blocked:[/yellow] #{task_id} {task['title']}"
    if reason:
        msg += f"\n  [dim]{reason}[/dim]"
    console.print(msg)


@app.command("list")
def list_cmd(
    status: str | None = typer.Option(None, "-s", "--status", help="Filter by status (comma-sep)"),
    all: bool = typer.Option(False, "--all", "-a", help="Include delegate tasks"),
    done: bool = typer.Option(False, "--done", help="Include done/failed tasks"),
    limit: int = typer.Option(20, "-n", "--limit"),
    epic: int | None = typer.Option(None, "-e", "--epic", help="Filter by epic ID"),
    cat: str | None = typer.Option(None, "-c", "--cat", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List tasks.

    By default shows open, active, and blocked tasks (hides done/failed).

    Examples:
        emdx task list
        emdx task list --done
        emdx task list --all
        emdx task list -s open,active
        emdx task list --cat SEC
        emdx task list --epic 510
    """
    if status:
        status_list = [s.strip() for s in status.split(",")]
    elif not done:
        status_list = ["open", "active", "blocked"]
    else:
        status_list = None

    exclude_delegate = not all
    task_list = tasks.list_tasks(
        status=status_list,
        limit=limit,
        exclude_delegate=exclude_delegate,
        epic_key=cat,
        parent_task_id=epic,
    )

    if json_output:
        print_json(task_list)
        return

    if not task_list:
        console.print("[yellow]No tasks[/yellow]")
        return

    table = Table(title=f"Tasks ({len(task_list)})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Title")

    for t in task_list:
        style = STATUS_STYLE.get(t["status"], "default")
        title = _display_title(t)
        if t["status"] == "blocked":
            blocker = _blocker_summary(t["id"])
            if blocker:
                title += f" (blocked by {blocker})"
        table.add_row(_task_label(t), Text(t["status"], style=style), title)

    console.print(table)


def _task_label(task: TaskDict) -> str:
    """Format task label: DEBT-13 if epic, else #id."""
    epic_key = task.get("epic_key")
    epic_seq = task.get("epic_seq")
    if epic_key and epic_seq:
        return f"{epic_key}-{epic_seq}"
    return f"#{task['id']}"


def _display_title(task: TaskDict) -> str:
    """Strip redundant KEY-N: prefix from title since the ID column has it."""
    title = task["title"]
    epic_key = task.get("epic_key")
    epic_seq = task.get("epic_seq")
    if epic_key and epic_seq:
        prefix = f"{epic_key}-{epic_seq}: "
        if title.startswith(prefix):
            return title[len(prefix) :]
    return title


@app.command()
def delete(
    task_id: int = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
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
