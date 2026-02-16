"""
Prime command - Output context for Claude session injection.

This is the key command for making Claude use emdx natively.
It outputs priming context that should be injected at session start.
"""

import subprocess
from datetime import datetime
from typing import Any

import typer
from rich.console import Console

from ..database import db
from ..utils.git import get_git_project

console = Console()


def prime(
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text (for injection), markdown, or json"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Include execution guidance, recent docs, cascade status"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output - just ready tasks"),
) -> None:
    """
    Output priming context for Claude Code session injection.

    This command outputs context that helps Claude understand the current
    state of work and use emdx natively. Use it in session hooks or
    pipe it to Claude's context.

    Examples:
        # Basic priming
        emdx prime

        # With full context (execution guidance, recent docs)
        emdx prime --verbose

        # Minimal (just ready tasks)
        emdx prime --quiet

        # For session hooks
        emdx prime >> /tmp/claude-context.md
    """
    db.ensure_schema()
    project = get_git_project()

    if format == "json":
        _output_json(project, verbose, quiet)
    else:
        _output_text(project, verbose, quiet)


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------


def _output_text(
    project: str | None,
    verbose: bool,
    quiet: bool,
    markdown: bool = False,
    execution: bool = False,
) -> None:
    """Output priming context as text."""
    lines = []

    # Header + usage instructions
    if not quiet:
        lines.append("=" * 60)
        lines.append("EMDX WORK CONTEXT")
        lines.append("=" * 60)
        if project:
            lines.append(f"Project: {project}")
        lines.append("")
        lines.extend(_get_usage_instructions())

    # Active epics with progress bars
    if not quiet:
        epics = _get_active_epics()
        if epics:
            lines.append("ACTIVE EPICS:")
            lines.append("")
            for e in epics:
                lines.append(_format_epic_line(e))
            lines.append("")

    # Ready tasks
    ready_tasks = _get_ready_tasks()
    if ready_tasks:
        lines.append(f"READY TASKS ({len(ready_tasks)}):")
        lines.append("")
        for task in ready_tasks[:15]:
            label = _task_label(task)
            doc_ref = f" (doc #{task['source_doc_id']})" if task.get("source_doc_id") else ""
            lines.append(f"  {label}  {task['title']}{doc_ref}")
            if task.get("description") and verbose:
                desc = task["description"][:100]
                if len(task["description"]) > 100:
                    desc += "..."
                lines.append(f"         {desc}")
        lines.append("")
    else:
        lines.append("No ready tasks. Create new tasks with 'emdx task add'.")
        lines.append("")

    # In-progress tasks
    in_progress = _get_in_progress_tasks()
    if in_progress:
        lines.append(f"IN-PROGRESS ({len(in_progress)}):")
        lines.append("")
        for task in in_progress[:5]:
            label = _task_label(task)
            lines.append(f"  {label}  {task['title']}")
        lines.append("")

    # Recent failures
    recent_failures = _get_recent_failures()
    if recent_failures:
        lines.append(f"RECENT FAILURES ({len(recent_failures)}):")
        lines.append("")
        for task in recent_failures:
            label = _task_label(task)
            title = task.get("title", "")[:40]
            error = task.get("error", "")
            prompt = task.get("prompt", "")

            lines.append(f"  {label}  {title}")
            if error:
                # Truncate error to one line, max 60 chars
                error_snippet = error.split("\n")[0][:60]
                if len(error) > 60 or "\n" in error:
                    error_snippet += "..."
                lines.append(f"         error: {error_snippet}")
            if prompt:
                escaped = prompt[:50].replace('"', '\\"')
                lines.append(f'         retry: emdx delegate "{escaped}"')
        lines.append("")

    # Git context (always shown, not quiet-only)
    if not quiet:
        git_ctx = _get_git_context()
        if git_ctx["branch"] or git_ctx["commits"] or git_ctx["prs"]:
            lines.append("GIT CONTEXT:")
            lines.append("")
            if git_ctx["branch"]:
                lines.append(f"  Branch: {git_ctx['branch']}")
            if git_ctx["commits"]:
                lines.append("  Recent commits:")
                for commit in git_ctx["commits"]:
                    lines.append(f"    {commit}")
            if git_ctx["prs"]:
                lines.append("  Open PRs:")
                for pr in git_ctx["prs"]:
                    lines.append(f"    #{pr['number']} {pr['title']} ({pr['headRefName']})")
            lines.append("")

    # Verbose additions
    if verbose and not quiet:
        # Stale documents needing review
        stale_docs = _get_stale_docs()
        if stale_docs:
            lines.append("STALE DOCS (needs review):")
            lines.append("")
            for doc in stale_docs[:5]:
                level = doc["level"].upper()
                lines.append(f"  [{level}] #{doc['id']}  {doc['title']} ({doc['days_stale']}d)")
            lines.append("")

        recent = _get_recent_docs()
        if recent:
            lines.append("RECENT DOCS:")
            lines.append("")
            for rdoc in recent[:5]:
                lines.append(f"  #{rdoc['id']}  {rdoc['title']}")
            lines.append("")

        key_docs = _get_key_docs()
        if key_docs:
            lines.append("KEY DOCS (most accessed):")
            lines.append("")
            for kdoc in key_docs:
                lines.append(f'  #{kdoc["id"]} "{kdoc["title"]}" — {kdoc["access_count"]} views')
            lines.append("")

        cascade_status = _get_cascade_status()
        if any(cascade_status.values()):
            lines.append("CASCADE QUEUE:")
            lines.append("")
            for stage, count in cascade_status.items():
                if count > 0:
                    lines.append(f"  {stage}: {count} item(s)")
            lines.append("")

    # Footer
    if not quiet:
        lines.append("=" * 60)

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _task_label(task: dict) -> str:
    """Format a task label: use epic key (e.g. DEBT-10) if available, else #id."""
    epic_key = task.get("epic_key")
    epic_seq = task.get("epic_seq")
    if epic_key and epic_seq:
        label = f"{epic_key}-{epic_seq}"
    else:
        label = f"#{task['id']}"
    # Pad to 8 chars for alignment
    return f"{label:<8}"


def _format_epic_line(epic: dict) -> str:
    """Format an epic line with progress bar."""
    done = epic["children_done"]
    total = epic["child_count"]
    cat = epic.get("epic_key") or ""

    # Progress bar: 5 chars wide
    if total > 0:
        filled = round(done / total * 5)
        bar = "\u25a0" * filled + "\u25a1" * (5 - filled)
        progress = f"{bar}  {done}/{total} done"
        if done == total:
            progress += " \u2713"
    else:
        progress = "     no tasks"

    name = epic["title"][:30]
    return f"  {cat:<5}{name:<32}{progress}"


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------


def _get_active_epics() -> list[dict[str, Any]]:
    """Get active/open epics with child task counts."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.title, t.status, t.epic_key,
                COUNT(c.id) as child_count,
                COUNT(CASE WHEN c.status = 'done' THEN 1 END) as children_done
            FROM tasks t
            LEFT JOIN tasks c ON c.parent_task_id = t.id AND c.type != 'epic'
            WHERE t.type = 'epic' AND t.status IN ('open', 'active')
            GROUP BY t.id
            ORDER BY t.updated_at DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "status": r[2],
                "epic_key": r[3],
                "child_count": r[4],
                "children_done": r[5],
            }
            for r in rows
        ]


def _get_ready_tasks() -> list[dict[str, Any]]:
    """Get tasks that are ready to work on (open + no blockers, excludes delegate)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.title, t.description, t.priority, t.status,
                   t.source_doc_id, t.epic_key, t.epic_seq
            FROM tasks t
            WHERE t.status = 'open'
            AND t.prompt IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM task_deps td
                JOIN tasks blocker ON td.depends_on = blocker.id
                WHERE td.task_id = t.id AND blocker.status != 'done'
            )
            ORDER BY t.priority ASC, t.created_at ASC
            LIMIT 20
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "description": r[2],
                "priority": r[3],
                "status": r[4],
                "source_doc_id": r[5],
                "epic_key": r[6],
                "epic_seq": r[7],
            }
            for r in rows
        ]


def _get_in_progress_tasks() -> list[dict[str, Any]]:
    """Get manually created tasks currently in progress (excludes delegate)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, priority, epic_key, epic_seq
            FROM tasks
            WHERE status = 'active'
            AND prompt IS NULL
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "description": r[2],
                "priority": r[3],
                "epic_key": r[4],
                "epic_seq": r[5],
            }
            for r in rows
        ]


def _get_recent_failures() -> list[dict[str, Any]]:
    """Get recent failures for prime output."""
    from typing import cast

    from ..models.tasks import get_recent_failures

    return cast(list[dict[str, Any]], get_recent_failures(hours=24, limit=5))


def _get_recent_docs() -> list[dict[str, Any]]:
    """Get recently accessed documents."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, project
            FROM documents
            WHERE is_deleted = 0
            ORDER BY last_accessed_at DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return [{"id": r[0], "title": r[1], "project": r[2]} for r in rows]


def _get_cascade_status() -> dict:
    """Get cascade queue status by stage."""
    stages = ["idea", "prompt", "analyzed", "planned", "done"]
    status = dict.fromkeys(stages, 0)

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cascade_stage, COUNT(*)
                FROM documents
                WHERE cascade_stage IS NOT NULL AND cascade_stage != ''
                AND is_deleted = 0
                GROUP BY cascade_stage
            """)
            for stage, count in cursor.fetchall():
                if stage in status:
                    status[stage] = count
    except Exception:
        # cascade_stage column may not exist in older databases
        pass

    return status


def _get_stale_docs() -> list:
    """Get stale documents for priming context."""
    try:
        from emdx.commands.stale import get_top_stale_for_priming

        return get_top_stale_for_priming(limit=5)
    except Exception:
        # stale module may not be available or have issues
        return []


def _get_git_context() -> dict[str, Any]:
    """
    Get git context: current branch, recent commits, and open PRs.

    Returns a dict with:
        - branch: str | None — current branch name
        - commits: list[str] — last 3 commit summaries (oneline)
        - prs: list[dict] — open PRs with number, title, headRefName
        - error: str | None — error message if git/gh not available
    """
    result: dict[str, Any] = {
        "branch": None,
        "commits": [],
        "prs": [],
        "error": None,
    }

    # Current branch
    try:
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            result["branch"] = proc.stdout.strip() or None
    except FileNotFoundError:
        result["error"] = "git not installed"
        return result
    except subprocess.TimeoutExpired:
        result["error"] = "git command timed out"
        return result
    except Exception as e:
        result["error"] = f"git error: {e}"
        return result

    # Last 3 commits
    try:
        proc = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result["commits"] = proc.stdout.strip().split("\n")
    except Exception:
        # Not critical, continue without commits
        pass

    # Open PRs via gh CLI
    try:
        import json as json_module

        proc = subprocess.run(
            ["gh", "pr", "list", "--state=open", "--limit=5", "--json", "number,title,headRefName"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            result["prs"] = json_module.loads(proc.stdout)
    except FileNotFoundError:
        # gh not installed, that's okay
        pass
    except Exception:
        # gh error, continue without PRs
        pass

    return result


def _get_key_docs(limit: int = 5) -> list[dict[str, Any]]:
    """
    Get the most frequently accessed documents.

    Args:
        limit: Maximum number of documents to return

    Returns:
        List of dicts with id, title, access_count
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, access_count
            FROM documents
            WHERE deleted_at IS NULL AND access_count > 0
            ORDER BY access_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [{"id": r[0], "title": r[1], "access_count": r[2]} for r in rows]


# ---------------------------------------------------------------------------
# Execution guidance (verbose only)
# ---------------------------------------------------------------------------


def _get_usage_instructions() -> list[str]:
    """Return concise emdx usage instructions for Claude sessions."""
    return [
        "RULES: Save significant outputs. Check ready tasks. Mark tasks done.",
        "",
        "EMDX COMMANDS:",
        '  Save:     echo "output" | emdx save --title "Title" --tags "tag1,tag2"',
        '  Search:   emdx find "query"',
        "  View:     emdx view <id>",
        "  Tasks:    emdx task ready | emdx task view <id> | emdx task active <id>",
        '            emdx task add "title" | emdx task done <id> | emdx task log <id>',
        "  Epics:    emdx epic list | emdx epic view <id>",
        '  Delegate: emdx delegate "task"             Single AI execution',
        '            emdx delegate "t1" "t2" "t3"     Parallel execution',
        '            emdx delegate --pr "task"         Execute + create PR',
        '            emdx delegate --chain "a" "b"     Sequential pipeline',
        '            emdx delegate --doc 42 "task"     With doc context',
        "",
    ]


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def _get_execution_methods_json() -> list[dict[str, Any]]:
    """Return execution methods as structured data for JSON output."""
    return [
        {
            "command": "emdx delegate",
            "usage": 'emdx delegate "task" --tags analysis',
            "when": "All one-shot AI execution (single, parallel, PR, worktree)",
            "key_flags": [
                "--doc",
                "--each/--do",
                "--chain",
                "--pr",
                "--worktree",
                "--synthesize",
                "--tags",
            ],
        },
    ]


def _get_recent_failures_json() -> list[dict[str, Any]]:
    """Get recent failures formatted for JSON output."""
    from ..models.tasks import get_recent_failures

    failures = get_recent_failures(hours=24, limit=5)
    return [
        {
            "id": f["id"],
            "title": f["title"],
            "error": f.get("error", ""),
            "prompt": f.get("prompt", ""),
            "retry_command": f'emdx delegate "{f.get("prompt", "")}"' if f.get("prompt") else None,
            "updated_at": f.get("updated_at"),
        }
        for f in failures
    ]


def _output_json(project: str | None, verbose: bool, quiet: bool) -> None:
    """Output priming context as JSON."""
    import json

    data: dict[str, Any] = {
        "project": project,
        "timestamp": datetime.now().isoformat(),
        "active_epics": _get_active_epics(),
        "ready_tasks": _get_ready_tasks(),
        "in_progress_tasks": _get_in_progress_tasks(),
        "recent_failures": _get_recent_failures_json(),
        "git_context": _get_git_context(),
    }

    if verbose:
        data["execution_methods"] = _get_execution_methods_json()
        data["recent_docs"] = _get_recent_docs()
        data["key_docs"] = _get_key_docs()
        data["cascade_status"] = _get_cascade_status()
        # Include stale documents needing review
        stale_docs = _get_stale_docs()
        if stale_docs:
            data["stale_docs"] = [
                {
                    "id": d["id"],
                    "title": d["title"],
                    "level": d["level"].value if hasattr(d["level"], "value") else d["level"],
                    "days_stale": d["days_stale"],
                }
                for d in stale_docs
            ]

    print(json.dumps(data, indent=2, default=str))


# Create typer app for the command
app = typer.Typer(help="Output priming context for Claude session injection")
app.command()(prime)
