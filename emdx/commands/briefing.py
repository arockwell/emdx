"""
Briefing command - Show what happened in recent emdx activity.

Provides a summary of:
- Documents created in the timeframe
- Tasks that changed status (new, completed, blocked)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.cli_config import DEFAULT_LLM_MODEL
from ..database import db

console = Console()

app = typer.Typer(help="Show recent emdx activity briefing")


def _parse_since(since: str) -> datetime:
    """Parse --since argument into a datetime.

    Supports:
    - ISO format: 2026-02-14, 2026-02-14T10:00:00
    - Relative: '2 days ago', '1 week ago', '3 hours ago'
    - Natural: 'yesterday', 'last week'
    """
    since = since.strip().lower()

    # Handle 'yesterday'
    if since == "yesterday":
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

    # Handle 'last week'
    if since == "last week":
        return datetime.now() - timedelta(weeks=1)

    # Handle relative time: "N <unit> ago"
    relative_pattern = r"^(\d+)\s*(second|minute|hour|day|week|month)s?\s*ago$"
    match = re.match(relative_pattern, since)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)

        if unit == "second":
            return datetime.now() - timedelta(seconds=amount)
        elif unit == "minute":
            return datetime.now() - timedelta(minutes=amount)
        elif unit == "hour":
            return datetime.now() - timedelta(hours=amount)
        elif unit == "day":
            return datetime.now() - timedelta(days=amount)
        elif unit == "week":
            return datetime.now() - timedelta(weeks=amount)
        elif unit == "month":
            return datetime.now() - timedelta(days=amount * 30)

    # Try ISO format parsing
    try:
        # Handle date-only format
        if "T" not in since and " " not in since:
            return datetime.fromisoformat(since).replace(hour=0, minute=0, second=0, microsecond=0)
        return datetime.fromisoformat(since)
    except ValueError:
        pass

    # Fallback: default to 24 hours ago
    console.print(
        f"[yellow]Warning: Could not parse '{since}', defaulting to 24 hours ago[/yellow]"
    )
    return datetime.now() - timedelta(days=1)


def _get_documents_created(since: datetime) -> list[dict[str, Any]]:
    """Get documents created since the given datetime."""
    since_str = since.isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, project, created_at,
                   (SELECT GROUP_CONCAT(t.name, ', ')
                    FROM document_tags dt
                    JOIN tags t ON dt.tag_id = t.id
                    WHERE dt.document_id = d.id) as tags
            FROM documents d
            WHERE created_at >= ? AND is_deleted = 0
            ORDER BY created_at DESC
            """,
            (since_str,),
        )
        return [dict(row) for row in cursor.fetchall()]


# Tasks have no tags column of their own (see CLAUDE.md: tasks are organized
# by category/epic, not tags). These are the FK columns that link a task to a
# document, used as the proxy for "does this task belong to this tag" below.
_TASK_DOC_LINK_COLUMNS = ("gameplan_id", "source_doc_id", "output_doc_id")


def _task_linked_doc_ids(task: dict[str, Any]) -> list[int]:
    """Doc IDs linked to a task row, via its gameplan/source/output FKs."""
    return [
        doc_id for col in _TASK_DOC_LINK_COLUMNS if (doc_id := task.get(col)) is not None
    ]


def _strip_doc_link_columns(tasks: list[dict[str, Any]]) -> None:
    """Drop the internal FK columns added for tag-scoping before display/JSON."""
    for task in tasks:
        for col in _TASK_DOC_LINK_COLUMNS:
            task.pop(col, None)


def _tag_matching_doc_ids(doc_ids: set[int], tag_names: list[str], match_all: bool) -> set[int]:
    """Return the subset of doc_ids that carry the given tags.

    match_all=True requires every tag (AND semantics); False requires any
    one of them (OR semantics) — mirrors `emdx find --tags`/`--any-tags`.
    """
    if not doc_ids or not tag_names:
        return set()
    with db.get_connection() as conn:
        id_placeholders = ",".join("?" * len(doc_ids))
        tag_placeholders = ",".join("?" * len(tag_names))
        cursor = conn.execute(
            f"""
            SELECT dt.document_id, COUNT(DISTINCT t.name) as match_count
            FROM document_tags dt
            JOIN tags t ON dt.tag_id = t.id
            WHERE dt.document_id IN ({id_placeholders})
              AND t.name IN ({tag_placeholders})
            GROUP BY dt.document_id
            """,
            (*doc_ids, *tag_names),
        )
        required = len(tag_names) if match_all else 1
        return {row[0] for row in cursor.fetchall() if row[1] >= required}


def _get_tasks_completed(since: datetime) -> list[dict[str, Any]]:
    """Get tasks completed since the given datetime."""
    since_str = since.isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, completed_at, project, gameplan_id, source_doc_id, output_doc_id
            FROM tasks
            WHERE status = 'done' AND completed_at >= ?
            ORDER BY completed_at DESC
            """,
            (since_str,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _get_tasks_added(since: datetime) -> list[dict[str, Any]]:
    """Get tasks created since the given datetime."""
    since_str = since.isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, status, priority, created_at, project,
                   gameplan_id, source_doc_id, output_doc_id
            FROM tasks
            WHERE created_at >= ?
            ORDER BY created_at DESC
            """,
            (since_str,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _get_tasks_blocked(since: datetime) -> list[dict[str, Any]]:
    """Get tasks that became blocked since the given datetime."""
    since_str = since.isoformat()
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, updated_at, project, gameplan_id, source_doc_id, output_doc_id
            FROM tasks
            WHERE status = 'blocked' AND updated_at >= ?
            ORDER BY updated_at DESC
            """,
            (since_str,),
        )
        return [dict(row) for row in cursor.fetchall()]


def _format_relative_time(dt_str: str | None) -> str:
    """Format a datetime string as relative time."""
    if not dt_str:
        return ""
    try:
        if isinstance(dt_str, str):
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            dt = dt_str
        age = datetime.now() - dt
        if age.total_seconds() < 0:
            return "just now"
        if age < timedelta(minutes=1):
            return f"{int(age.total_seconds())}s ago"
        if age < timedelta(hours=1):
            return f"{int(age.total_seconds() / 60)}m ago"
        if age < timedelta(days=1):
            return f"{int(age.total_seconds() / 3600)}h ago"
        return f"{age.days}d ago"
    except Exception:
        return ""


def _display_human_briefing(
    since: datetime,
    documents: list[dict[str, Any]],
    tasks_completed: list[dict[str, Any]],
    tasks_added: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    tags: list[str] | None = None,
) -> None:
    """Display briefing in human-readable format using Rich."""
    # Header with time range
    time_range = f"Since {since.strftime('%Y-%m-%d %H:%M')}"
    if tags:
        time_range += f" · tags: {', '.join(tags)}"
    console.print(Panel(f"[bold]📊 EMDX Briefing[/bold]\n{time_range}", expand=False))
    console.print()

    # Quick stats summary
    stats_parts = []
    if documents:
        stats_parts.append(f"[cyan]{len(documents)}[/cyan] docs created")
    if tasks_completed:
        stats_parts.append(f"[green]{len(tasks_completed)}[/green] tasks completed")
    if tasks_added:
        stats_parts.append(f"[blue]{len(tasks_added)}[/blue] tasks added")
    if blockers:
        stats_parts.append(f"[red]{len(blockers)}[/red] blockers")

    if stats_parts:
        console.print(" • ".join(stats_parts))
        console.print()

    # Documents Created section
    if documents:
        console.print("[bold cyan]📄 Documents Created[/bold cyan]")
        table = Table(show_header=True, header_style="dim")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="dim")
        table.add_column("Tags", style="magenta")
        table.add_column("When", style="green")

        for doc in documents[:10]:  # Limit to 10 for readability
            doc_tags_str = doc.get("tags") or ""
            project = doc.get("project") or ""
            when = _format_relative_time(doc.get("created_at"))
            table.add_row(
                str(doc["id"]),
                (doc["title"][:40] + "...") if len(doc["title"]) > 40 else doc["title"],
                project[:15] if project else "",
                doc_tags_str[:20] if doc_tags_str else "",
                when,
            )

        console.print(table)
        if len(documents) > 10:
            console.print(f"[dim]  ... and {len(documents) - 10} more[/dim]")
        console.print()

    # Tasks Completed section
    if tasks_completed:
        console.print("[bold green]✅ Tasks Completed[/bold green]")
        table = Table(show_header=True, header_style="dim")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("When", style="green")

        for task in tasks_completed[:10]:
            when = _format_relative_time(task.get("completed_at"))
            table.add_row(
                str(task["id"]),
                (task["title"][:50] + "...") if len(task["title"]) > 50 else task["title"],
                when,
            )

        console.print(table)
        if len(tasks_completed) > 10:
            console.print(f"[dim]  ... and {len(tasks_completed) - 10} more[/dim]")
        console.print()

    # Tasks Added section
    if tasks_added:
        console.print("[bold blue]➕ Tasks Added[/bold blue]")
        table = Table(show_header=True, header_style="dim")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("When", style="green")

        for task in tasks_added[:10]:
            when = _format_relative_time(task.get("created_at"))
            status = task.get("status", "open")
            status_style = {
                "open": "dim",
                "active": "yellow",
                "done": "green",
                "blocked": "red",
                "failed": "red",
            }.get(status, "white")
            table.add_row(
                str(task["id"]),
                (task["title"][:50] + "...") if len(task["title"]) > 50 else task["title"],
                f"[{status_style}]{status}[/{status_style}]",
                when,
            )

        console.print(table)
        if len(tasks_added) > 10:
            console.print(f"[dim]  ... and {len(tasks_added) - 10} more[/dim]")
        console.print()

    # Blockers section
    if blockers:
        console.print("[bold red]🚧 Blockers[/bold red]")
        table = Table(show_header=True, header_style="dim")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Since", style="red")

        for task in blockers[:5]:
            when = _format_relative_time(task.get("updated_at"))
            table.add_row(
                str(task["id"]),
                (task["title"][:50] + "...") if len(task["title"]) > 50 else task["title"],
                when,
            )

        console.print(table)
        if len(blockers) > 5:
            console.print(f"[dim]  ... and {len(blockers) - 5} more[/dim]")
        console.print()

    # No activity message
    if not documents and not tasks_completed and not tasks_added and not blockers:
        console.print("[dim]No activity in this timeframe.[/dim]")


def _build_json_output(
    since: datetime,
    documents: list[dict[str, Any]],
    tasks_completed: list[dict[str, Any]],
    tasks_added: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Build JSON output for --json flag."""
    # Convert comma-joined tag strings to arrays for JSON output
    for doc in documents:
        doc_tags = doc.get("tags")
        doc["tags"] = [t.strip() for t in doc_tags.split(",") if t.strip()] if doc_tags else []

    return {
        "since": since.isoformat(),
        "generated_at": datetime.now().isoformat(),
        "tags_filter": tags,
        "summary": {
            "documents_created": len(documents),
            "tasks_completed": len(tasks_completed),
            "tasks_added": len(tasks_added),
            "blockers": len(blockers),
        },
        "documents_created": documents,
        "tasks_completed": tasks_completed,
        "tasks_added": tasks_added,
        "blockers": blockers,
    }


@app.callback(invoke_without_command=True)
def briefing(
    ctx: typer.Context,
    since: str | None = typer.Option(
        None,
        "--since",
        "-s",
        help="Show activity since this time (e.g., '2 days ago', '2026-02-14', 'yesterday')",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON for agent consumption",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="Generate AI summary and save to knowledge base",
    ),
    hours: int = typer.Option(
        4,
        "--hours",
        "-h",
        help="Window for --save synthesis (default: 4 hours)",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model for --save synthesis",
    ),
    tags: str | None = typer.Option(
        None,
        "--tags",
        "-t",
        help="Scope the briefing to this tag (comma-separated for multiple)",
    ),
    any_tags: bool = typer.Option(
        False,
        "--any-tags",
        help="With --tags, match ANY of the tags instead of ALL of them",
    ),
) -> None:
    """
    Show what happened in recent emdx activity.

    By default shows activity from the last 24 hours across the whole KB.
    Use --tags to scope to a specific area instead of the whole KB — tasks
    don't carry tags directly, so a task is included when its linked
    gameplan/source/output document carries the tag.
    Use --save to generate an AI-synthesized session summary and persist it.

    Examples:
        emdx briefing
        emdx briefing --since '2 days ago'
        emdx briefing --since 2026-02-14
        emdx briefing --json
        emdx briefing --tags sentry-investigation --since '30 days ago'
        emdx briefing --tags investigation,security  # docs with BOTH tags
        emdx briefing --tags investigation,security --any-tags  # EITHER tag
        emdx briefing --save                   # AI summary of last 4 hours
        emdx briefing --save --hours 8          # AI summary of last 8 hours
        emdx briefing --save --tags sentry-investigation  # scoped AI summary
    """
    # If a subcommand was invoked, don't run the default behavior
    if ctx.invoked_subcommand is not None:
        return

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()] if tags else []

    # Handle --save: AI-synthesized session summary (replaces old `wrapup` command)
    if save:
        _briefing_save(hours=hours, model=model, tags=tag_list, any_tags=any_tags)
        return

    # Parse since argument (default to 24 hours ago)
    if since:
        since_dt = _parse_since(since)
    else:
        since_dt = datetime.now() - timedelta(days=1)

    # Gather data
    documents = _get_documents_created(since_dt)
    tasks_completed = _get_tasks_completed(since_dt)
    tasks_added = _get_tasks_added(since_dt)
    blockers = _get_tasks_blocked(since_dt)

    if tag_list:
        candidate_doc_ids = {doc["id"] for doc in documents}
        for task in (*tasks_completed, *tasks_added, *blockers):
            candidate_doc_ids.update(_task_linked_doc_ids(task))

        matched_doc_ids = _tag_matching_doc_ids(
            candidate_doc_ids, tag_list, match_all=not any_tags
        )

        documents = [doc for doc in documents if doc["id"] in matched_doc_ids]
        tasks_completed = [
            t for t in tasks_completed if matched_doc_ids.intersection(_task_linked_doc_ids(t))
        ]
        tasks_added = [
            t for t in tasks_added if matched_doc_ids.intersection(_task_linked_doc_ids(t))
        ]
        blockers = [
            t for t in blockers if matched_doc_ids.intersection(_task_linked_doc_ids(t))
        ]

    _strip_doc_link_columns(tasks_completed)
    _strip_doc_link_columns(tasks_added)
    _strip_doc_link_columns(blockers)

    # Output
    if json_output:
        output = _build_json_output(
            since_dt, documents, tasks_completed, tasks_added, blockers, tags=tag_list or None
        )
        print(json.dumps(output, indent=2, default=str))
    else:
        _display_human_briefing(
            since_dt, documents, tasks_completed, tasks_added, blockers, tags=tag_list or None
        )


def _briefing_save(
    hours: int,
    model: str | None,
    tags: list[str] | None = None,
    any_tags: bool = False,
) -> None:
    """Generate AI summary of recent activity and save to KB."""
    import sys

    from ..database.documents import get_docs_in_window, save_document
    from ..models.tasks import get_tasks_in_window
    from ..services.synthesis_service import _execute_prompt

    tasks = get_tasks_in_window(hours)
    docs = get_docs_in_window(hours)

    if tags:
        candidate_doc_ids = {d.id for d in docs}
        for task in tasks:
            candidate_doc_ids.update(
                doc_id
                for doc_id in (task.gameplan_id, task.source_doc_id, task.output_doc_id)
                if doc_id is not None
            )
        matched_doc_ids = _tag_matching_doc_ids(candidate_doc_ids, tags, match_all=not any_tags)
        docs = [d for d in docs if d.id in matched_doc_ids]
        tasks = [
            t
            for t in tasks
            if matched_doc_ids.intersection(
                doc_id
                for doc_id in (t.gameplan_id, t.source_doc_id, t.output_doc_id)
                if doc_id is not None
            )
        ]

    total_items = len(tasks) + len(docs)
    if total_items == 0:
        scope = f" matching tags '{', '.join(tags)}'" if tags else ""
        print(f"No activity{scope} in the last {hours} hours.")
        return

    # Build synthesis prompt
    scope_note = f" scoped to tag(s): {', '.join(tags)}" if tags else ""
    sections = []
    sections.append(
        f"Generate a concise session summary for the last {hours} hours{scope_note}.\n"
        "Focus on: what was accomplished, what's in progress, and what needs attention."
    )

    if tasks:
        done = [t for t in tasks if t.status == "done"]
        active_tasks = [t for t in tasks if t.status == "active"]
        blocked = [t for t in tasks if t.status == "blocked"]
        task_lines = []
        if done:
            task_lines.append("## Completed Tasks")
            task_lines.extend(f"- {t.title}" for t in done[:10])
        if active_tasks:
            task_lines.append("## In-Progress Tasks")
            task_lines.extend(f"- {t.title}" for t in active_tasks[:5])
        if blocked:
            task_lines.append("## Blocked Tasks")
            task_lines.extend(f"- {t.title}" for t in blocked[:5])
        if task_lines:
            sections.append("\n".join(task_lines))

    if docs:
        doc_lines = ["## Documents Created"]
        doc_lines.extend(f"- #{d.id}: {d.title}" for d in docs[:15])
        sections.append("\n".join(doc_lines))

    sections.append(
        "---\n\nBased on the above, write a concise session summary:\n"
        "1. Key accomplishments\n2. Work in progress\n"
        "3. Blockers needing attention\n4. Suggested next steps\n\n"
        "Format as markdown."
    )

    prompt = "\n\n".join(sections)
    title_suffix = f" [{', '.join(tags)}]" if tags else ""
    title = f"Session Summary{title_suffix} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

    sys.stderr.write(f"briefing: synthesizing {total_items} items...\n")

    system_prompt = (
        "You are a session summarizer. Generate concise, actionable summaries "
        "of work activity. Focus on accomplishments, blockers, and next steps."
    )
    try:
        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=prompt,
            title=title,
            model=model or DEFAULT_LLM_MODEL,
        )
        if result.success and result.output_content:
            print(result.output_content)
            saved_doc_tags = ["session-summary", "active", *(tags or [])]
            doc_id = save_document(
                title=title, content=result.output_content, tags=saved_doc_tags
            )
            sys.stderr.write(f"briefing: saved as doc #{doc_id}\n")
        else:
            sys.stderr.write("briefing: synthesis failed\n")
            raise typer.Exit(1)
    except RuntimeError as e:
        sys.stderr.write(f"briefing: synthesis failed: {e}\n")
        raise typer.Exit(1) from None
