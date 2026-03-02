"""Task CLI commands — simplified agent work queue.

Agent-facing commands for creating and consuming work items.
"""

import re
from datetime import date, datetime

import typer
from rich.table import Table
from rich.text import Text

from emdx.commands.categories import app as categories_app
from emdx.commands.epics import app as epics_app
from emdx.models import tasks
from emdx.models.types import TaskDict, TaskRef
from emdx.utils.lazy_group import make_alias_group
from emdx.utils.output import console, is_non_interactive, print_json

app = typer.Typer(help="Agent work queue", cls=make_alias_group({"create": "add"}))
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


def _display_id(task: TaskDict) -> str:
    """Return KEY-N display ID if available, otherwise #id."""
    if task.get("epic_key") and task.get("epic_seq"):
        return f"{task['epic_key']}-{task['epic_seq']}"
    return f"#{task['id']}"


def _resolve_id(
    identifier: TaskRef,
    json_output: bool = False,
) -> int:
    """Resolve a task identifier string to a database ID.

    Prints an error and raises typer.Exit(1) if resolution fails.
    """
    task_id = tasks.resolve_task_id(identifier)
    if task_id is None:
        msg = f"Task not found: {identifier}"
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
    epic: TaskRef | None = typer.Option(None, "-e", "--epic", help="Epic ID (e.g. 510 or SEC-1)"),
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
        emdx task add "Test task" --epic SEC-1
        emdx task add "Another task" --cat SEC
        emdx task add "Deploy" --after 10 --after 11
    """
    parent_task_id = None
    epic_key = cat.upper() if cat else None

    if epic:
        epic_id = _resolve_id(epic)
        parent_task = tasks.get_task(epic_id)
        if not parent_task:
            console.print(f"[red]Epic #{epic_id} not found[/red]")
            raise typer.Exit(1)
        parent_task_id = epic_id
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

    task_data = tasks.get_task(task_id)
    display_id = _display_id(task_data) if task_data else f"#{task_id}"

    msg = f"[green]✅ Task {display_id}:[/green] {title}"
    if doc:
        msg += f" [dim](doc #{doc})[/dim]"
    if depends_on:
        dep_ids = " ".join(f"#{d}" for d in depends_on)
        msg += f" [dim](after {dep_ids})[/dim]"
    console.print(msg)


@app.command()
def plan(
    parent: str = typer.Argument(..., help="Parent task epic_key (e.g. FEAT-25)"),
    titles: list[str] = typer.Argument(..., help="Subtask titles (at least one)"),
    cat: str | None = typer.Option(None, "-c", "--cat", help="Category for all subtasks"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Create multiple subtasks under a parent in one call.

    Subtasks are chained sequentially: each depends on the previous one.

    Examples:
        emdx task plan FEAT-25 "Read code" "Implement" "Test"
        emdx task plan FEAT-25 --cat FEAT "Read code" "Implement"
    """
    if not titles:
        msg = "At least one subtask title is required"
        if json_output:
            print_json({"error": msg})
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    parent_id = _resolve_id(parent, json_output=json_output)
    parent_task = tasks.get_task(parent_id)
    if not parent_task:
        msg = f"Parent task {parent} not found"
        if json_output:
            print_json({"error": msg})
        else:
            console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    epic_key = cat.upper() if cat else None
    if not epic_key and parent_task.get("epic_key"):
        epic_key = parent_task["epic_key"]

    created: list[dict[str, str | int]] = []
    prev_id: int | None = None

    for title in titles:
        depends_on = [prev_id] if prev_id is not None else None
        task_id = tasks.create_task(
            title,
            description="",
            parent_task_id=parent_id,
            epic_key=epic_key,
            depends_on=depends_on,
        )
        task_data = tasks.get_task(task_id)
        display = _display_id(task_data) if task_data else f"#{task_id}"
        created.append({"id": task_id, "epic_key": display, "title": title})
        prev_id = task_id

    parent_display = _display_id(parent_task)

    if json_output:
        print_json({"parent": parent_display, "subtasks": created})
    else:
        print(f"Created {len(created)} subtasks under {parent_display}:")
        for sub in created:
            print(f"  {sub['epic_key']}  {sub['title']}")


@app.command()
def ready(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show tasks ready to work on.

    Lists open tasks that aren't blocked by dependencies.

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
    output_doc: int | None = typer.Option(
        None, "--output-doc", help="Link an output document to this task"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Mark a task as done.

    Examples:
        emdx task done 42
        emdx task done TOOL-12
        emdx task done 42 --note "Fixed in PR #123"
        emdx task done 42 --output-doc 99
    """
    task_id = _resolve_id(task_id_str, json_output=json_output)
    task = tasks.get_task(task_id)
    if not task:
        if json_output:
            print_json({"error": f"Task #{task_id} not found"})
        else:
            console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if output_doc is not None:
        tasks.set_task_output_doc(task_id, output_doc)
    kwargs = {"status": "done"}
    tasks.update_task(task_id, **kwargs)
    if note:
        tasks.log_progress(task_id, note)

    if json_output:
        result: dict[str, str | int | None] = {
            "id": task_id,
            "title": task["title"],
            "status": "done",
        }
        if output_doc is not None:
            result["output_doc_id"] = output_doc
        print_json(result)
    else:
        msg = f"[green]✓ Done:[/green] {_display_id(task)} {task['title']}"
        if output_doc is not None:
            msg += f" [dim](output #{output_doc})[/dim]"
        console.print(msg)


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
    # Header: show KEY-N with raw ID in parens for cross-reference
    display = _display_id(task)
    label = f"{display} (#{task_id})" if display != f"#{task_id}" else display
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
            console.print(f"  [dim]Source:[/dim] #{source_id} [cyan]{source_doc['title']}[/cyan]")
        else:
            console.print(f"  [dim]Source:[/dim] #{source_id} [dim](deleted)[/dim]")
    if output_id:
        output_doc = get_document(output_id)
        if output_doc:
            console.print(f"  [dim]Output:[/dim] #{output_id} [cyan]{output_doc['title']}[/cyan]")
        else:
            console.print(f"  [dim]Output:[/dim] #{output_id} [dim](deleted)[/dim]")

    # Description
    desc = task.get("description") or ""
    if desc:
        console.print()
        from emdx.ui.markdown_config import MarkdownConfig

        md = MarkdownConfig.create_markdown(desc)
        console.print(md)

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

    console.print(f"[blue]● Active:[/blue] {_display_id(task)} {task['title']}")


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
        console.print(f"[green]Logged:[/green] {_display_id(task)} — {message}")
        return

    entries = tasks.get_task_log(task_id, limit=20)
    if not entries:
        console.print(f"[yellow]No log entries for {_display_id(task)}[/yellow]")
        return

    console.print(f"\n[bold]Log for {_display_id(task)}: {task['title']}[/bold]")
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
    console.print(f"[green]Logged:[/green] {_display_id(task)} — {message}")


@app.command()
def brief(
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    log_limit: int = typer.Option(10, "--log-limit", help="Max log entries to show"),
) -> None:
    """Get a comprehensive brief for a task.

    Assembles task details, dependencies, subtasks, work log,
    and related documents in one call. Designed for agents
    starting work on a task.

    Examples:
        emdx task brief FEAT-25
        emdx task brief 42 --json
        emdx task brief FEAT-25 --log-limit 20
    """
    task_id = _resolve_id(task_id_str, json_output=json_output)
    task = tasks.get_task(task_id)
    if not task:
        if json_output:
            print_json({"error": f"Task not found: {task_id_str}"})
        else:
            print(f"Error: Task not found: {task_id_str}")
        raise typer.Exit(1)

    brief_data = _assemble_brief(task, task_id, log_limit)

    if json_output:
        print_json(brief_data)
    else:
        _print_brief_plain(brief_data)


def _assemble_brief(
    task: TaskDict,
    task_id: int,
    log_limit: int,
) -> dict[str, object]:
    """Gather all context for a task brief."""
    from emdx.models.documents import get_document

    display = _display_id(task)

    data: dict[str, object] = {
        "id": task_id,
        "display_id": display,
        "title": _display_title(task),
        "status": task["status"],
        "priority": task.get("priority", 3),
        "category": task.get("epic_key"),
        "description": task.get("description") or "",
    }

    # Epic info
    parent_id = task.get("parent_task_id")
    if parent_id:
        parent = tasks.get_task(parent_id)
        data["epic"] = {
            "id": parent_id,
            "title": parent["title"] if parent else "(deleted)",
            "display_id": _display_id(parent) if parent else f"#{parent_id}",
        }

    # Dependencies
    deps = tasks.get_dependencies(task_id)
    data["dependencies"] = [
        {
            "id": d["id"],
            "display_id": _display_id(d),
            "title": _display_title(d),
            "status": d["status"],
        }
        for d in deps
    ]

    # Dependents
    dependents = tasks.get_dependents(task_id)
    data["dependents"] = [
        {
            "id": d["id"],
            "display_id": _display_id(d),
            "title": _display_title(d),
            "status": d["status"],
        }
        for d in dependents
    ]

    # Subtasks
    children = tasks.get_children(task_id)
    data["subtasks"] = [
        {
            "id": c["id"],
            "display_id": _display_id(c),
            "title": _display_title(c),
            "status": c["status"],
        }
        for c in children
    ]

    # Task log
    log_entries = tasks.get_task_log(task_id, limit=log_limit)
    data["log"] = [
        {"created_at": e.get("created_at", ""), "message": e["message"]} for e in log_entries
    ]

    # Related documents
    related_docs: list[dict[str, object]] = []

    source_id = task.get("source_doc_id")
    if source_id:
        source_doc = get_document(source_id)
        related_docs.append(
            {
                "id": source_id,
                "title": source_doc["title"] if source_doc else "(deleted)",
                "relation": "source",
            }
        )

    output_id: int | None = None
    try:
        output_id = dict(task).get("output_doc_id")  # type: ignore[assignment]
    except Exception:
        pass
    if output_id:
        output_doc = get_document(output_id)
        related_docs.append(
            {
                "id": output_id,
                "title": output_doc["title"] if output_doc else "(deleted)",
                "relation": "output",
            }
        )

    data["related_documents"] = related_docs

    # Key files extracted from description and log
    all_text = task.get("description") or ""
    for entry in log_entries:
        all_text += "\n" + entry["message"]
    data["key_files"] = _extract_file_paths(all_text)

    return data


# Pattern for file paths: word/word.ext or word/word/word etc.
_FILE_PATH_RE = re.compile(
    r"(?:^|[\s`\"'(])"  # preceded by whitespace, backtick, quote, or paren
    r"((?:[\w.-]+/)+[\w.-]+\.[\w]+)"  # path/to/file.ext
)


def _extract_file_paths(text: str) -> list[str]:
    """Extract likely file paths from text."""
    matches = _FILE_PATH_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _print_brief_plain(data: dict[str, object]) -> None:
    """Print task brief in plain text format."""
    display_id = data["display_id"]
    title = data["title"]
    print(f"TASK BRIEF: {display_id} — {title}")
    print("=" * 50)
    print()

    print(f"Status: {data['status']}")
    if data.get("category"):
        print(f"Category: {data['category']}")
    epic = data.get("epic")
    if epic and isinstance(epic, dict):
        print(f"Epic: {epic.get('display_id')} — {epic.get('title')}")
    print(f"Priority: {data['priority']}")
    print()

    desc = data.get("description", "")
    if desc:
        print("DESCRIPTION:")
        for line in str(desc).splitlines():
            print(f"  {line}")
        print()

    deps = data.get("dependencies")
    if isinstance(deps, list) and deps:
        print("DEPENDENCIES (must complete first):")
        for d in deps:
            assert isinstance(d, dict)
            print(f"  {d['display_id']} ({d['status']}) — {d['title']}")
        print()

    dependents = data.get("dependents")
    if isinstance(dependents, list) and dependents:
        print("BLOCKED TASKS (waiting on this):")
        for d in dependents:
            assert isinstance(d, dict)
            print(f"  {d['display_id']} — {d['title']}")
        print()

    subtasks = data.get("subtasks")
    if isinstance(subtasks, list) and subtasks:
        print("SUBTASKS:")
        for s in subtasks:
            assert isinstance(s, dict)
            print(f"  {s['display_id']} ({s['status']}) — {s['title']}")
        print()

    log_entries = data.get("log")
    if isinstance(log_entries, list) and log_entries:
        print("TASK LOG (recent):")
        for entry in log_entries:
            assert isinstance(entry, dict)
            ts = entry.get("created_at", "")
            print(f"  {ts} — {entry['message']}")
        print()

    related = data.get("related_documents")
    if isinstance(related, list) and related:
        print("RELATED DOCUMENTS:")
        for doc in related:
            assert isinstance(doc, dict)
            print(f'  #{doc["id"]} "{doc["title"]}" ({doc["relation"]})')
        print()

    key_files = data.get("key_files")
    if isinstance(key_files, list) and key_files:
        print("KEY FILES (from task description/log):")
        for f in key_files:
            print(f"  {f}")
        print()


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

    msg = f"[yellow]⊘ Blocked:[/yellow] {_display_id(task)} {task['title']}"
    if reason:
        msg += f"\n  [dim]{reason}[/dim]"
    console.print(msg)


@app.command("list")
def list_cmd(
    status: str | None = typer.Option(None, "-s", "--status", help="Filter by status (comma-sep)"),
    all: bool = typer.Option(False, "--all", "-a", help="Include all tasks"),
    done: bool = typer.Option(False, "--done", help="Show done tasks"),
    limit: int = typer.Option(20, "-n", "--limit"),
    epic: TaskRef | None = typer.Option(None, "-e", "--epic", help="Epic ID (e.g. 510 or SEC-1)"),
    cat: str | None = typer.Option(None, "-c", "--cat", help="Filter by category"),
    since: str | None = typer.Option(
        None, "--since", help="Show tasks completed on or after DATE (YYYY-MM-DD)"
    ),
    today: bool = typer.Option(False, "--today", help="Show tasks completed today"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List tasks.

    By default shows open, active, and blocked tasks (hides done).

    Examples:
        emdx task list
        emdx task list --done
        emdx task list --done --today
        emdx task list --done --since 2026-01-15
        emdx task list --all
        emdx task list -s open,active
        emdx task list --cat SEC
        emdx task list --epic 510
        emdx task list --epic SEC-1
    """
    since_date: str | None = None
    if today:
        since_date = date.today().isoformat()
    elif since:
        try:
            datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(code=1) from None
        since_date = since

    # --since/--today imply --done when no explicit status is given
    if status:
        status_list = [s.strip() for s in status.split(",")]
    elif done or since_date:
        status_list = ["done"]
    else:
        status_list = ["open", "active", "blocked"]

    resolved_epic = _resolve_id(epic) if epic else None
    task_list = tasks.list_tasks(
        status=status_list,
        limit=limit,
        epic_key=cat,
        parent_task_id=resolved_epic,
        since=since_date,
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
def priority(
    task_id_str: str = typer.Argument(..., metavar="TASK_ID", help=TASK_ID_HELP),
    value: int | None = typer.Argument(None, help="Priority value (1=highest, 5=lowest)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get or set task priority.

    Without a value, shows the current priority.
    With a value (1-5), sets the priority.

    Examples:
        emdx task priority 42           # Show current priority
        emdx task priority 42 1         # Set to highest priority
        emdx task priority FEAT-5 2     # Set priority on epic task
    """
    task_id = _resolve_id(task_id_str, json_output=json_output)
    task = tasks.get_task(task_id)
    if not task:
        if json_output:
            print_json({"error": f"Task #{task_id} not found"})
        else:
            console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if value is None:
        current = task.get("priority", 3)
        if json_output:
            print_json({"id": task_id, "title": task["title"], "priority": current})
        else:
            console.print(f"{_display_id(task)} {task['title']}: priority {current}")
        return

    if value < 1 or value > 5:
        if json_output:
            print_json({"error": "Priority must be between 1 and 5"})
        else:
            console.print("[red]Priority must be between 1 and 5[/red]")
        raise typer.Exit(1)

    tasks.update_task(task_id, priority=value)
    if json_output:
        print_json({"id": task_id, "title": task["title"], "priority": value})
    else:
        console.print(f"[green]✅ {_display_id(task)}[/green] priority set to {value}")


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
        console.print(f"Delete task {_display_id(task)}: {task['title']}?")
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    tasks.delete_task(task_id)
    console.print(f"[green]✅ Deleted {_display_id(task)}[/green]")


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
