"""
Prime command - Output context for Claude session injection.

This is the key command for making Claude use emdx natively.
It outputs priming context that should be injected at session start.
"""

import typer
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..database import db
from ..utils.git import get_git_project

console = Console()


def prime(
    format: str = typer.Option(
        "text",
        "--format", "-f",
        help="Output format: text (for injection), markdown, or json"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Include additional context (recent docs, cascade status)"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Minimal output - just ready tasks"
    ),
    execution: bool = typer.Option(
        True,
        "--execution/--no-execution",
        help="Include execution method guidance"
    ),
):
    """
    Output priming context for Claude Code session injection.

    This command outputs context that helps Claude understand the current
    state of work and use emdx natively. Use it in session hooks or
    pipe it to Claude's context.

    Examples:
        # Basic priming
        emdx prime

        # With full context
        emdx prime --verbose

        # Minimal (just ready tasks)
        emdx prime --quiet

        # For session hooks
        emdx prime >> /tmp/claude-context.md
    """
    project = get_git_project()

    if format == "json":
        _output_json(project, verbose, quiet, execution)
    else:
        _output_text(project, verbose, quiet, format == "markdown", execution)


def _get_execution_guidance() -> list[str]:
    """Return execution method guidance with decision tree."""
    return [
        "EXECUTION METHODS - Decision Tree:",
        "",
        "  ┌─ One-shot AI execution? (emdx delegate) ───────────────────┐",
        "  │                                                             │",
        "  │   Single task:                                              │",
        "  │     → emdx delegate \"task\" --tags analysis                  │",
        "  │     → emdx delegate --doc 42 \"implement this\"               │",
        "  │                                                             │",
        "  │   Multiple tasks in parallel:                               │",
        "  │     → emdx delegate \"task1\" \"task2\" \"task3\"                 │",
        "  │     → emdx delegate --synthesize \"t1\" \"t2\" \"t3\"            │",
        "  │                                                             │",
        "  │   Sequential pipeline (output chains forward):              │",
        "  │     → emdx delegate --chain \"analyze\" \"plan\" \"implement\"    │",
        "  │                                                             │",
        "  │   Dynamic discovery (for each X, do Y):                      │",
        "  │     → emdx delegate --each \"fd -e py\" --do \"Review {{item}}\" │",
        "  │                                                             │",
        "  │   With PR creation / worktree isolation:                    │",
        "  │     → emdx delegate --pr \"fix the auth bug\"                 │",
        "  │     → emdx delegate --worktree --pr \"fix X\"                 │",
        "  │                                                             │",
        "  ├─ Reusable recipe? ─────────────────────────────────────────┤",
        "  │     → emdx recipe run 42                                    │",
        "  │                                                             │",
        "  ├─ Autonomous idea → code pipeline? ──────────────────────────┤",
        "  │     → emdx cascade add \"feature idea\" --auto                │",
        "  │                                                             │",
        "  └─────────────────────────────────────────────────────────────┘",
        "",
        "  Key flags for delegate:",
        "    --doc/-d      Use document as input context",
        "    --each/--do   Dynamic discovery: for each item from cmd, do action",
        "    --chain       Sequential pipeline (each step sees previous output)",
        "    --pr          Create PR after completion",
        "    --worktree    Isolate in git worktree",
        "    --tags/-t     Tag output for searchability",
        "    --synthesize  Combine outputs from parallel tasks",
        "",
    ]


def _get_execution_methods_json() -> list[dict]:
    """Return execution methods as structured data for JSON output."""
    return [
        {
            "command": "emdx delegate",
            "usage": 'emdx delegate "task" --tags analysis',
            "when": "All one-shot AI execution (single, parallel, chain, PR, worktree)",
            "key_flags": ["--doc", "--each/--do", "--chain", "--pr", "--worktree", "--synthesize", "--tags"],
        },
        {
            "command": "emdx recipe",
            "usage": "emdx recipe run 42",
            "when": "Run a saved recipe (document tagged 📋) via delegate",
            "key_flags": ["--pr", "--worktree", "--model"],
        },
        {
            "command": "emdx cascade",
            "usage": 'emdx cascade add "idea" --auto',
            "when": "Transform idea into working code with PR autonomously",
            "key_flags": ["--auto", "--stop", "--sync"],
        },
    ]


def _output_text(project: Optional[str], verbose: bool, quiet: bool, markdown: bool, execution: bool):
    """Output priming context as text."""

    lines = []

    # Header with imperative instructions
    if not quiet:
        lines.append("=" * 60)
        lines.append("EMDX WORK CONTEXT - READ AND FOLLOW THESE INSTRUCTIONS")
        lines.append("=" * 60)
        lines.append("")
        lines.append("YOU MUST follow these rules when working in this codebase:")
        lines.append("")
        lines.append("1. ALWAYS save significant outputs to emdx:")
        lines.append("   echo \"output\" | emdx save --title \"Title\" --tags \"tag1,tag2\"")
        lines.append("")
        lines.append("2. ALWAYS check ready tasks before starting work:")
        lines.append("   emdx task ready")
        lines.append("")
        lines.append("3. Create tasks for discovered work:")
        lines.append("   emdx task add \"Title\" --doc 42")
        lines.append("")
        lines.append("4. Mark tasks done when finished:")
        lines.append("   emdx task done <id> --note \"summary\"")
        lines.append("")
        lines.append("-" * 60)
        lines.append("")

    # Execution guidance (after instructions, before tasks)
    if execution and not quiet:
        lines.extend(_get_execution_guidance())

    # Project context
    if project:
        lines.append(f"Project: {project}")
        lines.append("")

    # Ready tasks (the most important section)
    ready_tasks = _get_ready_tasks()
    if ready_tasks:
        lines.append("READY TASKS (work you can start immediately):")
        lines.append("")
        for task in ready_tasks[:10]:  # Limit to top 10
            doc = f" (doc #{task['source_doc_id']})" if task.get("source_doc_id") else ""
            lines.append(f"  #{task['id']} {task['title']}{doc}")
            if task.get('description') and verbose:
                desc = task['description'][:100] + "..." if len(task['description']) > 100 else task['description']
                lines.append(f"      {desc}")
        lines.append("")
    else:
        lines.append("No ready tasks. Create new tasks with 'emdx task add'.")
        lines.append("")

    # In-progress tasks (manual only, not delegate)
    in_progress = _get_in_progress_tasks()
    if in_progress:
        lines.append("IN-PROGRESS TASKS (work already started):")
        lines.append("")
        for task in in_progress[:5]:
            lines.append(f"  #{task['id']} {task['title']}")
        lines.append("")

    # Verbose additions
    if verbose and not quiet:
        # Recent documents
        recent = _get_recent_docs()
        if recent:
            lines.append("RECENT CONTEXT (documents to reference):")
            lines.append("")
            for doc in recent[:5]:
                lines.append(f"  #{doc['id']} {doc['title']}")
            lines.append("")

        # Cascade status
        cascade_status = _get_cascade_status()
        if any(cascade_status.values()):
            lines.append("CASCADE QUEUE:")
            lines.append("")
            for stage, count in cascade_status.items():
                if count > 0:
                    lines.append(f"  {stage}: {count} item(s)")
            lines.append("")

    # Footer reminder
    if not quiet:
        lines.append("-" * 60)
        lines.append("Remember: Track your work. Save outputs. Mark tasks done.")
        lines.append("=" * 60)

    # Output
    print("\n".join(lines))


def _output_json(project: Optional[str], verbose: bool, quiet: bool, execution: bool):
    """Output priming context as JSON."""
    import json

    data = {
        "project": project,
        "timestamp": datetime.now().isoformat(),
        "ready_tasks": _get_ready_tasks(),
        "in_progress_tasks": _get_in_progress_tasks(),
    }

    if execution:
        data["execution_methods"] = _get_execution_methods_json()

    if verbose:
        data["recent_docs"] = _get_recent_docs()
        data["cascade_status"] = _get_cascade_status()

    print(json.dumps(data, indent=2, default=str))


def _get_ready_tasks() -> list:
    """Get tasks that are ready to work on (open + no blockers, excludes delegate)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.title, t.description, t.priority, t.status, t.source_doc_id
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
            {"id": r[0], "title": r[1], "description": r[2], "priority": r[3], "status": r[4], "source_doc_id": r[5]}
            for r in rows
        ]


def _get_in_progress_tasks() -> list:
    """Get manually created tasks currently in progress (excludes delegate)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, priority
            FROM tasks
            WHERE status = 'active'
            AND prompt IS NULL
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return [
            {"id": r[0], "title": r[1], "description": r[2], "priority": r[3]}
            for r in rows
        ]


def _get_recent_docs() -> list:
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
        return [
            {"id": r[0], "title": r[1], "project": r[2]}
            for r in rows
        ]


def _get_cascade_status() -> dict:
    """Get cascade queue status by stage."""
    stages = ["idea", "prompt", "analyzed", "planned", "done"]
    status = {stage: 0 for stage in stages}

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


# Create typer app for the command
app = typer.Typer(help="Output priming context for Claude session injection")
app.command()(prime)
