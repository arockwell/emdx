"""Task CLI commands — simplified agent work queue.

Agent-facing commands for creating and consuming work items.
Delegate activity tracking is separate (shown via `emdx status`).
"""

import typer
from rich.table import Table
from rich.text import Text

from emdx.commands.categories import app as categories_app
from emdx.commands.epics import app as epics_app
from emdx.models import tasks
from emdx.models.types import TaskDict
from emdx.utils.output import console, is_non_interactive, print_json

app = typer.Typer(help="Agent work queue")
app.add_typer(epics_app, name="epic", help="Manage task epics")
app.add_typer(categories_app, name="cat", help="Manage task categories")

TASK_ID_HELP = "Task ID (e.g. 42 or TOOL-12)"

ICONS = {
    "open": "○",
    "active": "●",
    "done": "✓",
    "failed": "✗",
    "blocked": "⊘",
    "closed": "✓",
    "wontdo": "⊘",
}
STATUS_STYLE = {
    "open": "default",
    "active": "blue",
    "blocked": "yellow",
    "done": "green",
    "failed": "red",
    "closed": "green",
    "wontdo": "dim",
}


def _blocker_summary(task_id: int) -> str:
    """Get one-line blocker info for a task."""
    deps = tasks.get_dependencies(task_id)
    if not deps:
        return ""
    open_deps = [d for d in deps if d["status"] not in ("done", "closed", "wontdo")]
    if not open_deps:
        return ""
    names = ", ".join(f"#{d['id']}" for d in open_deps[:3])
    extra = f" +{len(open_deps) - 3}" if len(open_deps) > 3 else ""
    return f"{names}{extra}"


def _resolve_id(
    identifier: str,
    json_output: bool = False,
) -> int:
    """Resolve a task identifier string to a database ID.

    Prints an error and raises typer.Exit(1) if resolution fails.
    """
    task_id = tasks.resolve_task_id(identifier)
    if task_id is None:
        msg = f"Invalid task ID: {identifier}"
        if json_output:
            print_json({"error": msg})
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)
    return task_id


@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    doc: int | None = typer.Option(None, "-d", "--doc", help="Link to document ID"),
    description: str | None = typer.Option(None, "-D", "--description", help="Task description"),
    epic: int | None = typer.Option(None, "-e", "--epic", help="Add to epic (task ID)"),
    cat: str | None = typer.Option(None, "-c", "--cat", help="Category key (e.g. SEC)"),
    after: list[int] | None = typer.Option(
        None, "--after", help="Task IDs this depends on (repeatable)"
    ),
) -> None:
    """Add a task to the work queue.

    Examples:
        emdx task add "Fix the auth bug"
        emdx task add "Implement this" --doc 42
        emdx task add "Refactor tests" -D "Split into unit and integration"
        emdx task add "Test task" --epic 510
        emdx task add "Another task" --cat SEC
        emdx task add "Deploy" --after 10 --after 11
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

    depends_on = after if after else None

    task_id = tasks.create_task(
        title,
        description=description or "",
        source_doc_id=doc,
        parent_task_id=parent_task_id,
        epic_key=epic_key,
        depends_on=depends_on,
    )
    msg = f"[green]✅ Task #{task_id}:[/green] {title}"
    if doc:
        msg += f" [dim](doc #{doc})[/dim]"
    if epic_key:
        msg += f" [dim]({epic_key})[/dim]"
    if depends_on:
        dep_ids = " ".join(f"#{d}" for d in depends_on)
        msg += f" [dim](after {dep_ids})[/dim]"
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
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    note: str | None = typer.Option(None, "-n", "--note", help="Completion note"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark a task as done.

    Examples:
        emdx task done 42
        emdx task done TOOL-12
        emdx task done 42 --note "Fixed in PR #123"
    """
    task_id = _resolve_id(task_id_str, json_output=json_output)
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
def wontdo(
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    note: str | None = typer.Option(None, "-n", "--note", help="Reason for closing"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark a task as won't do (closed without completing).

    The task is treated as terminal (unblocks dependents) but
    semantically distinct from done.

    Examples:
        emdx task wontdo 42
        emdx task wontdo TOOL-12
        emdx task wontdo 42 --note "Superseded by #55"
    """
    task_id = _resolve_id(task_id_str, json_output=json_output)
    task = tasks.get_task(task_id)
    if not task:
        if json_output:
            print_json({"error": f"Task #{task_id} not found"})
        else:
            console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.update_task(task_id, status="wontdo")
    if note:
        tasks.log_progress(task_id, f"Won't do: {note}")

    if json_output:
        print_json({"id": task_id, "title": task["title"], "status": "wontdo"})
    else:
        console.print(f"[dim]⊘ Won't do:[/dim] #{task_id} {task['title']}")


@app.command()
def view(
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
) -> None:
    """View full task details.

    Shows title, description, status, epic/category, source doc,
    dependencies, and recent work log entries.

    Examples:
        emdx task view 42
        emdx task view TOOL-12
    """
    task_id = _resolve_id(task_id_str)
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
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    note: str | None = typer.Option(None, "-n", "--note", help="Progress note"),
) -> None:
    """Mark a task as in-progress.

    Use this at session start after picking a task from 'emdx task ready'.

    Examples:
        emdx task active 42
        emdx task active TOOL-12
        emdx task active 42 --note "Starting work on auth refactor"
    """
    task_id = _resolve_id(task_id_str)
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
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    message: str | None = typer.Argument(None, help="Log message (omit to view log)"),
) -> None:
    """View or add to a task's work log.

    Without a message, shows the log history.
    With a message, appends an entry.

    Examples:
        emdx task log 42
        emdx task log TOOL-12
        emdx task log 42 "Investigated root cause — issue is in auth middleware"
    """
    task_id = _resolve_id(task_id_str)
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
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    message: str = typer.Argument(..., help="Progress note"),
) -> None:
    """Log a progress note on a task without changing its status.

    Shorthand for 'emdx task log <id> "message"'.

    Examples:
        emdx task note 42 "Root cause is in auth middleware"
        emdx task note TOOL-12 "Tried approach X, didn't work — switching to Y"
    """
    task_id = _resolve_id(task_id_str)
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.log_progress(task_id, message)
    console.print(f"[green]Logged:[/green] #{task_id} — {message}")


@app.command()
def blocked(
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    reason: str = typer.Option("", "-r", "--reason", help="Why the task is blocked"),
) -> None:
    """Mark a task as blocked.

    Optionally provide a reason, which is logged to the work log.

    Examples:
        emdx task blocked 42
        emdx task blocked TOOL-12
        emdx task blocked 42 --reason "Waiting on API key from infra team"
    """
    task_id = _resolve_id(task_id_str)
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
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a task.

    Examples:
        emdx task delete 42
        emdx task delete TOOL-12
        emdx task delete 42 --force
    """
    task_id = _resolve_id(task_id_str)
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if not force and not is_non_interactive():
        console.print(f"Delete task #{task_id}: {task['title']}?")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    tasks.delete_task(task_id)
    console.print(f"[green]✅ Deleted #{task_id}[/green]")


# --- Task dependency subcommands ---

dep_app = typer.Typer(help="Manage task dependencies")
app.add_typer(dep_app, name="dep")


@dep_app.command("add")
def dep_add(
    task_id: str = typer.Argument(..., help=TASK_ID_HELP),
    depends_on: str = typer.Argument(
        ..., help="Task that must be completed first (e.g. 42 or TOOL-12)"
    ),
) -> None:
    """Add a dependency between tasks.

    TASK_ID will be blocked until DEPENDS_ON is done.

    Examples:
        emdx task dep add 5 3        # task 5 depends on task 3
        emdx task dep add FEAT-5 3   # FEAT-5 depends on task 3
    """
    resolved_id = _resolve_id(task_id)
    resolved_dep = _resolve_id(depends_on)

    for tid in (resolved_id, resolved_dep):
        if not tasks.get_task(tid):
            console.print(f"[red]Task #{tid} not found[/red]")
            raise typer.Exit(1)

    ok = tasks.add_dependency(resolved_id, resolved_dep)
    if ok:
        console.print(f"[green]✅ #{resolved_id} now depends on #{resolved_dep}[/green]")
    else:
        console.print("[red]Cannot add: dependency already exists or would create a cycle[/red]")
        raise typer.Exit(1)


@dep_app.command("rm")
def dep_rm(
    task_id: str = typer.Argument(..., help=TASK_ID_HELP),
    depends_on: str = typer.Argument(..., help="Dependency to remove (e.g. 42 or TOOL-12)"),
) -> None:
    """Remove a dependency between tasks.

    Examples:
        emdx task dep rm 5 3        # task 5 no longer depends on task 3
        emdx task dep rm FEAT-5 3   # FEAT-5 no longer depends on task 3
    """
    resolved_id = _resolve_id(task_id)
    resolved_dep = _resolve_id(depends_on)
    ok = tasks.remove_dependency(resolved_id, resolved_dep)
    if ok:
        console.print(
            f"[green]✅ Removed: #{resolved_id} no longer depends on #{resolved_dep}[/green]"
        )
    else:
        console.print("[yellow]No such dependency[/yellow]")


@dep_app.command("list")
def dep_list(
    task_id: str = typer.Argument(..., help=TASK_ID_HELP),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show dependencies for a task.

    Lists what this task depends on (blockers) and what depends on it (blocked by this).

    Examples:
        emdx task dep list 5
        emdx task dep list FEAT-5
    """
    task_id_int = _resolve_id(task_id, json_output)
    task = tasks.get_task(task_id_int)
    if not task:
        console.print(f"[red]Task #{task_id_int} not found[/red]")
        raise typer.Exit(1)

    deps = tasks.get_dependencies(task_id_int)
    dependents = tasks.get_dependents(task_id_int)

    if json_output:

        def _dep_summary(d: TaskDict) -> dict[str, str | int]:
            return {"id": d["id"], "title": d["title"], "status": d["status"]}

        print_json(
            {
                "task_id": task_id_int,
                "depends_on": [_dep_summary(d) for d in deps],
                "blocks": [_dep_summary(d) for d in dependents],
            }
        )
        return

    if not deps and not dependents:
        console.print(f"[yellow]#{task_id_int} has no dependencies[/yellow]")
        return

    if deps:
        console.print(f"[bold]#{task_id_int} depends on:[/bold]")
        for d in deps:
            icon = ICONS.get(d["status"], "?")
            console.print(f"  {icon} #{d['id']} {d['title']}")

    if dependents:
        console.print(f"[bold]#{task_id_int} blocks:[/bold]")
        for d in dependents:
            icon = ICONS.get(d["status"], "?")
            console.print(f"  {icon} #{d['id']} {d['title']}")


@app.command()
def chain(
    task_id: str = typer.Argument(..., help=TASK_ID_HELP),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show the full dependency chain for a task.

    Traces upward through blockers and downward through dependents
    to show the complete dependency graph rooted at this task.

    Examples:
        emdx task chain 5
        emdx task chain FEAT-5
    """
    task_id_int = _resolve_id(task_id, json_output)
    task = tasks.get_task(task_id_int)
    if not task:
        console.print(f"[red]Task #{task_id_int} not found[/red]")
        raise typer.Exit(1)

    # Walk upward: everything this task is waiting on (transitively)
    upstream = _walk_deps(task_id_int, direction="up")
    # Walk downward: everything waiting on this task (transitively)
    downstream = _walk_deps(task_id_int, direction="down")

    if json_output:

        def _task_summary(t: TaskDict) -> dict[str, str | int]:
            return {"id": t["id"], "title": t["title"], "status": t["status"]}

        print_json(
            {
                "task": _task_summary(task),
                "upstream": [_task_summary(t) for t in upstream],
                "downstream": [_task_summary(t) for t in downstream],
            }
        )
        return

    icon = ICONS.get(task["status"], "?")
    console.print(f"\n[bold]Chain for #{task_id_int}: {task['title']}[/bold]")

    if upstream:
        console.print("\n[bold]Upstream (must finish first):[/bold]")
        for t in upstream:
            t_icon = ICONS.get(t["status"], "?")
            console.print(f"  {t_icon} #{t['id']} {t['title']}")

    console.print(
        f"\n  [bold cyan]{icon} #{task_id_int} {task['title']}[/bold cyan]  ← you are here"
    )

    if downstream:
        console.print("\n[bold]Downstream (waiting on this):[/bold]")
        for t in downstream:
            t_icon = ICONS.get(t["status"], "?")
            console.print(f"  {t_icon} #{t['id']} {t['title']}")

    if not upstream and not downstream:
        console.print("\n[yellow]No dependencies in either direction[/yellow]")


def _walk_deps(task_id: int, direction: str) -> list[TaskDict]:
    """BFS walk of dependency graph. Returns tasks in traversal order."""
    visited: set[int] = set()
    queue = [task_id]
    result: list[TaskDict] = []

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        if direction == "up":
            neighbors = tasks.get_dependencies(current)
        else:
            neighbors = tasks.get_dependents(current)

        for n in neighbors:
            if n["id"] not in visited:
                result.append(n)
                queue.append(n["id"])

    return result
