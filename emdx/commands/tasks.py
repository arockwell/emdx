"""Task CLI commands."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from emdx.models import tasks

app = typer.Typer(help="Task management")
console = Console()

ICONS = {'open': '○', 'active': '●', 'blocked': '⚠', 'done': '✓', 'failed': '✗'}


@app.command()
def create(
    title: str = typer.Argument(..., help="Task title"),
    gameplan: Optional[int] = typer.Option(None, "-g", "--gameplan", help="Gameplan doc ID"),
    priority: int = typer.Option(3, "-p", "--priority", help="Priority 1-5"),
    depends: Optional[str] = typer.Option(None, "-d", "--depends", help="Depends on (comma-sep IDs)"),
    description: Optional[str] = typer.Option(None, "-D", "--description", help="Task description"),
    project: Optional[str] = typer.Option(None, "--project", help="Project name"),
):
    """Create a task."""
    deps = [int(x) for x in depends.split(',') if x.strip()] if depends else None
    task_id = tasks.create_task(
        title,
        description=description or "",
        priority=priority,
        gameplan_id=gameplan,
        project=project,
        depends_on=deps,
    )
    console.print(f"[green]✅ Created task #{task_id}[/green]")


@app.command("list")
def list_cmd(
    status: Optional[str] = typer.Option(None, "-s", "--status", help="Filter by status (comma-sep)"),
    gameplan: Optional[int] = typer.Option(None, "-g", "--gameplan", help="Filter by gameplan"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project"),
    limit: int = typer.Option(50, "-n", "--limit"),
):
    """List tasks."""
    status_list = [s.strip() for s in status.split(',')] if status else None
    task_list = tasks.list_tasks(status=status_list, gameplan_id=gameplan, project=project, limit=limit)

    if not task_list:
        console.print("[yellow]No tasks[/yellow]")
        return

    table = Table()
    table.add_column("", width=2)
    table.add_column("ID", width=5)
    table.add_column("Title")
    table.add_column("P", width=2)
    table.add_column("GP", width=5)

    for t in task_list:
        gp = str(t['gameplan_id']) if t['gameplan_id'] else ""
        table.add_row(
            ICONS.get(t['status'], '?'),
            str(t['id']),
            t['title'][:40],
            str(t['priority']),
            gp,
        )

    console.print(table)
    console.print(f"\n[dim]{len(task_list)} task(s)[/dim]")


@app.command()
def show(task_id: int = typer.Argument(..., help="Task ID")):
    """Show task details."""
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]#{task['id']}[/bold] {ICONS.get(task['status'], '?')} {task['title']}")
    console.print(f"Status: {task['status']}  Priority: {task['priority']}")

    if task['gameplan_id']:
        console.print(f"Gameplan: #{task['gameplan_id']}")
    if task['project']:
        console.print(f"Project: {task['project']}")
    if task['current_step']:
        console.print(f"Current step: {task['current_step']}")

    if task['description']:
        console.print(f"\n[bold]Description:[/bold]\n{task['description']}")

    deps = tasks.get_dependencies(task_id)
    if deps:
        console.print("\n[bold]Depends on:[/bold]")
        for d in deps:
            console.print(f"  {ICONS.get(d['status'], '?')} #{d['id']} {d['title']}")

    log = tasks.get_task_log(task_id, limit=10)
    if log:
        console.print("\n[bold]Recent log:[/bold]")
        for entry in reversed(log):
            console.print(f"  {entry['message']}")


@app.command()
def update(
    task_id: int = typer.Argument(..., help="Task ID"),
    status: Optional[str] = typer.Option(None, "-s", "--status", help="New status"),
    priority: Optional[int] = typer.Option(None, "-p", "--priority", help="New priority"),
    step: Optional[str] = typer.Option(None, "--step", help="Current step (for resume)"),
    note: Optional[str] = typer.Option(None, "-n", "--note", help="Add to log"),
):
    """Update task."""
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    kwargs = {}
    if status:
        kwargs['status'] = status
    if priority:
        kwargs['priority'] = priority
    if step:
        kwargs['current_step'] = step

    if kwargs:
        tasks.update_task(task_id, **kwargs)
    if note:
        tasks.log_progress(task_id, note)

    console.print(f"[green]✅ Updated #{task_id}[/green]")


@app.command()
def log(
    task_id: int = typer.Argument(..., help="Task ID"),
    message: str = typer.Argument(..., help="Log message"),
):
    """Add log entry."""
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    tasks.log_progress(task_id, message)
    console.print(f"[green]✅ Logged to #{task_id}[/green]")


@app.command()
def ready(
    gameplan: Optional[int] = typer.Option(None, "-g", "--gameplan", help="Filter by gameplan"),
    project: Optional[str] = typer.Option(None, "--project", help="Filter by project"),
):
    """Show tasks ready to work (open + deps satisfied)."""
    ready_tasks = tasks.get_ready_tasks(gameplan_id=gameplan)

    # Filter by project if specified
    if project:
        ready_tasks = [t for t in ready_tasks if t.get('project') == project]

    if not ready_tasks:
        console.print("[yellow]No ready tasks[/yellow]")
        return

    console.print(f"\n[bold]Ready ({len(ready_tasks)}):[/bold]")
    for t in ready_tasks:
        gp = f" [dim]GP#{t['gameplan_id']}[/dim]" if t['gameplan_id'] else ""
        console.print(f"  ○ #{t['id']} {t['title']} [dim]P{t['priority']}[/dim]{gp}")


@app.command()
def depends(
    task_id: int = typer.Argument(..., help="Task ID"),
    on: Optional[int] = typer.Option(None, "--on", help="Add dependency on this task ID"),
    remove: Optional[int] = typer.Option(None, "--remove", help="Remove dependency on this task ID"),
):
    """Manage dependencies."""
    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    if on:
        if tasks.add_dependency(task_id, on):
            console.print(f"[green]✅ #{task_id} now depends on #{on}[/green]")
        else:
            console.print(f"[red]Cannot add dependency (cycle or invalid)[/red]")
            raise typer.Exit(1)
    elif remove:
        # Remove dependency
        from emdx.database import db
        with db.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM task_deps WHERE task_id = ? AND depends_on = ?",
                (task_id, remove)
            )
            conn.commit()
            if cursor.rowcount > 0:
                console.print(f"[green]✅ Removed dependency #{task_id} → #{remove}[/green]")
            else:
                console.print(f"[yellow]Dependency not found[/yellow]")
    else:
        # Show current dependencies
        deps = tasks.get_dependencies(task_id)
        if deps:
            console.print(f"\n[bold]#{task_id} depends on:[/bold]")
            for d in deps:
                console.print(f"  {ICONS.get(d['status'], '?')} #{d['id']} {d['title']}")
        else:
            console.print(f"[dim]#{task_id} has no dependencies[/dim]")


@app.command()
def delete(
    task_id: int = typer.Argument(..., help="Task ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a task."""
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


@app.command()
def run(
    task_id: int = typer.Argument(..., help="Task ID"),
    workflow: Optional[str] = typer.Option(None, "-w", "--workflow", help="Run via workflow (e.g., deep_analysis)"),
    var: Optional[list[str]] = typer.Option(None, "--var", help="Workflow variables (key=value, can repeat)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show prompt only"),
):
    """Run task with Claude or workflow.

    Examples:
        emdx task run 1                    # Direct Claude execution
        emdx task run 1 -w deep_analysis   # Run via deep_analysis workflow
        emdx task run 1 -w code_fix --var fix_type=production_todos --var fix_description="Remove TODOs"
        emdx task run 1 --dry-run          # Preview prompt
    """
    from emdx.services.task_runner import run_task, build_task_prompt

    if dry_run:
        console.print(build_task_prompt(task_id))
        return

    # Parse variables from --var options
    variables = {}
    if var:
        for v in var:
            if '=' in v:
                key, value = v.split('=', 1)
                variables[key.strip()] = value.strip()
            else:
                console.print(f"[yellow]Warning: Ignoring invalid variable '{v}' (use key=value format)[/yellow]")

    try:
        task_exec_id = run_task(task_id, workflow_name=workflow, variables=variables if variables else None)
        mode = f"workflow '{workflow}'" if workflow else "direct"
        console.print(f"[green]✅ Started task #{task_id} ({mode}), task_exec #{task_exec_id}[/green]")
        if workflow:
            console.print(f"[dim]View: emdx workflow runs[/dim]")
        else:
            console.print(f"[dim]View: emdx exec list[/dim]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def manual(
    task_id: int = typer.Argument(..., help="Task ID"),
    note: Optional[str] = typer.Option(None, "-n", "--note", help="Completion note"),
):
    """Mark task as manually completed."""
    from emdx.services.task_runner import mark_task_manual

    try:
        task_exec_id = mark_task_manual(task_id, notes=note)
        console.print(f"[green]✅ Task #{task_id} marked as manually completed (exec #{task_exec_id})[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def executions(
    task_id: int = typer.Argument(..., help="Task ID"),
    limit: int = typer.Option(10, "-n", "--limit"),
):
    """Show execution history for a task."""
    from emdx.models.task_executions import list_task_executions, get_execution_stats

    task = tasks.get_task(task_id)
    if not task:
        console.print(f"[red]Task #{task_id} not found[/red]")
        raise typer.Exit(1)

    # Show stats
    stats = get_execution_stats(task_id)
    console.print(f"\n[bold]Task #{task_id}: {task['title']}[/bold]")
    console.print(f"Executions: {stats['total']} total ({stats['completed']} completed, {stats['failed']} failed, {stats['running']} running)")
    console.print(f"By type: {stats['workflow_runs']} workflow, {stats['direct_runs']} direct, {stats['manual_runs']} manual")

    # Show history
    execs = list_task_executions(task_id=task_id, limit=limit)
    if execs:
        console.print("\n[bold]Execution history:[/bold]")
        table = Table()
        table.add_column("ID", width=4)
        table.add_column("Type", width=10)
        table.add_column("Status", width=10)
        table.add_column("Started", width=20)
        table.add_column("Notes")

        for e in execs:
            table.add_row(
                str(e['id']),
                e['execution_type'],
                e['status'],
                str(e['started_at'])[:19] if e['started_at'] else "",
                (e['notes'] or "")[:30],
            )
        console.print(table)
