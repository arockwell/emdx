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
from ..utils.git_ops import get_current_branch, get_git_status

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
        "  ┌─ Quick one-off tasks? ────────────────────────────────────┐",
        "  │                                                           │",
        "  │   Single task needing tracked output?                     │",
        "  │     → emdx agent \"task\" --tags analysis                   │",
        "  │     → emdx agent 123 --tags analysis  (use doc #123)      │",
        "  │                                                           │",
        "  │   Multiple independent tasks in parallel?                 │",
        "  │     → emdx run \"task1\" \"task2\" \"task3\"                    │",
        "  │     → emdx run 101 102 103  (use doc IDs as tasks)        │",
        "  │     → emdx run --worktree \"fix1\" \"fix2\"  (code changes)   │",
        "  │                                                           │",
        "  ├─ Reusable patterns? ──────────────────────────────────────┤",
        "  │                                                           │",
        "  │   \"For each X discovered, do Y\" (save for later)?         │",
        "  │     → emdx each create name --from \"discovery\" --do \"Y\"   │",
        "  │     → emdx each run name                                  │",
        "  │                                                           │",
        "  │   Complex multi-stage with synthesis?                     │",
        "  │     → emdx workflow run task_parallel -t \"t1\" -t \"t2\"     │",
        "  │     → emdx workflow run task_parallel -t 101 -t 102       │",
        "  │                                                           │",
        "  ├─ Autonomous pipeline? ────────────────────────────────────┤",
        "  │                                                           │",
        "  │   Transform idea → working code with PR?                  │",
        "  │     → emdx cascade add \"feature idea\" --auto              │",
        "  │                                                           │",
        "  └───────────────────────────────────────────────────────────┘",
        "",
        "  Tasks can be text prompts OR document IDs (e.g., 123, #123)",
        "",
        "  Key flags:",
        "    --worktree    Isolate in git worktree (parallel code changes)",
        "    --tags/-t     Tag output for searchability",
        "    --pr          Create PR after completion",
        "    --synthesize  Combine outputs from parallel tasks",
        "",
    ]


def _get_execution_methods_json() -> list[dict]:
    """Return execution methods as structured data for JSON output."""
    return [
        {
            "command": "emdx agent",
            "usage": 'emdx agent "task" --tags analysis',
            "when": "Single task needing tracked output with metadata",
            "key_flags": ["--tags", "--title", "--group", "--pr", "--verbose"],
        },
        {
            "command": "emdx run",
            "usage": 'emdx run "task1" "task2"',
            "when": "Multiple independent tasks to run in parallel",
            "key_flags": ["--worktree", "--synthesize", "-j", "--discover"],
        },
        {
            "command": "emdx each",
            "usage": 'emdx each create name --from "cmd" --do "action"',
            "when": "Reusable 'for each X, do Y' patterns you'll run again",
            "key_flags": ["--from", "--do", "--pr", "--pr-single"],
        },
        {
            "command": "emdx workflow",
            "usage": "emdx workflow run task_parallel -t task1 -t task2",
            "when": "Complex multi-stage orchestration with synthesis",
            "key_flags": ["--worktree", "-t", "--preset", "-j"],
        },
        {
            "command": "emdx cascade",
            "usage": 'emdx cascade add "idea" --auto',
            "when": "Transform idea into working code with PR autonomously",
            "key_flags": ["--auto", "--stop", "--analyze", "--plan"],
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
        lines.append("2. ALWAYS create tasks for discovered work:")
        lines.append("   emdx task create \"Title\" --description \"Details\"")
        lines.append("")
        lines.append("3. ALWAYS check ready tasks before starting work:")
        lines.append("   emdx task ready")
        lines.append("")
        lines.append("4. NEVER end session without updating task status")
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

    # Git context
    lines.extend(_get_git_context_lines())
    lines.append("")

    # Ready tasks (the most important section)
    ready_tasks = _get_ready_tasks()
    if ready_tasks:
        lines.append("READY TASKS (work you can start immediately):")
        lines.append("")
        for task in ready_tasks[:10]:  # Limit to top 10
            priority_label = ["P0-CRITICAL", "P1-HIGH", "P2-MEDIUM", "P3-LOW", "P4-BACKLOG"][min(task['priority'], 4)]
            lines.append(f"  #{task['id']} [{priority_label}] {task['title']}")
            if task.get('description') and verbose:
                desc = task['description'][:100] + "..." if len(task['description']) > 100 else task['description']
                lines.append(f"      {desc}")
        lines.append("")
        lines.append(f"Run 'emdx task show <id>' for details, 'emdx task run <id>' to start work.")
        lines.append("")
    else:
        lines.append("No ready tasks. Create new tasks with 'emdx task create'.")
        lines.append("")

    # In-progress tasks
    in_progress = _get_in_progress_tasks()
    if in_progress:
        lines.append("IN-PROGRESS TASKS (work already started):")
        lines.append("")
        for task in in_progress[:5]:
            lines.append(f"  #{task['id']} {task['title']}")
        lines.append("")

    # Blocked tasks
    blocked_lines = _get_blocked_tasks_lines()
    if blocked_lines:
        lines.extend(blocked_lines)

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

        # Recent executions
        recent_exec_lines = _get_recent_executions_lines()
        if recent_exec_lines:
            lines.extend(recent_exec_lines)

    # Footer reminder
    if not quiet:
        lines.append("-" * 60)
        lines.append("Remember: Track your work. Save outputs. Update tasks.")
        lines.append("=" * 60)

    # Output
    print("\n".join(lines))


def _output_json(project: Optional[str], verbose: bool, quiet: bool, execution: bool):
    """Output priming context as JSON."""
    import json

    data = {
        "project": project,
        "timestamp": datetime.now().isoformat(),
        "git": _get_git_context(),
        "ready_tasks": _get_ready_tasks(),
        "in_progress_tasks": _get_in_progress_tasks(),
        "blocked_tasks": _get_blocked_tasks(),
    }

    if execution:
        data["execution_methods"] = _get_execution_methods_json()

    if verbose:
        data["recent_docs"] = _get_recent_docs()
        data["cascade_status"] = _get_cascade_status()
        data["recent_executions"] = _get_recent_executions()

    print(json.dumps(data, indent=2, default=str))


def _get_ready_tasks() -> list:
    """Get tasks that are ready to work on (open + no blockers)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.title, t.description, t.priority, t.status
            FROM tasks t
            WHERE t.status = 'open'
            AND NOT EXISTS (
                SELECT 1 FROM task_deps td
                JOIN tasks blocker ON td.depends_on = blocker.id
                WHERE td.task_id = t.id AND blocker.status != 'completed'
            )
            ORDER BY t.priority ASC, t.created_at ASC
            LIMIT 20
        """)
        rows = cursor.fetchall()
        return [
            {"id": r[0], "title": r[1], "description": r[2], "priority": r[3], "status": r[4]}
            for r in rows
        ]


def _get_in_progress_tasks() -> list:
    """Get tasks currently in progress."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, priority
            FROM tasks
            WHERE status = 'in_progress'
            ORDER BY updated_at DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return [
            {"id": r[0], "title": r[1], "description": r[2], "priority": r[3]}
            for r in rows
        ]


def _get_blocked_tasks() -> list[dict]:
    """Get tasks that are blocked (have incomplete dependencies)."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Single query to get all blocked tasks with their blockers (avoids N+1)
            cursor.execute("""
                SELECT t.id, t.title, td.depends_on
                FROM tasks t
                JOIN task_deps td ON td.task_id = t.id
                JOIN tasks blocker ON td.depends_on = blocker.id
                WHERE t.status = 'open' AND blocker.status != 'completed'
                ORDER BY t.priority ASC, t.created_at ASC
            """)
            rows = cursor.fetchall()

            # Group by task_id
            tasks_dict: dict[int, dict] = {}
            for task_id, title, blocked_by_id in rows:
                if task_id not in tasks_dict:
                    tasks_dict[task_id] = {
                        "id": task_id,
                        "title": title,
                        "blocked_by": [],
                    }
                tasks_dict[task_id]["blocked_by"].append(blocked_by_id)

            # Return as list, limited to 20
            return list(tasks_dict.values())[:20]
    except Exception:
        # tasks/task_deps tables may not exist in older databases
        return []


def _get_blocked_tasks_lines() -> list[str]:
    """Return formatted lines for blocked tasks section."""
    blocked_tasks = _get_blocked_tasks()
    if not blocked_tasks:
        return []

    lines = ["BLOCKED TASKS (waiting on dependencies):", ""]
    for task in blocked_tasks:
        blocked_by_str = ", ".join(f"#{bid}" for bid in task["blocked_by"])
        lines.append(f"  #{task['id']} {task['title']} (blocked by {blocked_by_str})")
    lines.append("")
    return lines


def _get_recent_docs() -> list:
    """Get recently accessed documents."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Try with last_accessed_at first, fall back to created_at
            try:
                cursor.execute("""
                    SELECT id, title, project
                    FROM documents
                    WHERE is_deleted = 0
                    ORDER BY last_accessed_at DESC
                    LIMIT 10
                """)
            except Exception:
                cursor.execute("""
                    SELECT id, title, project
                    FROM documents
                    WHERE is_deleted = 0
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
            rows = cursor.fetchall()
            return [
                {"id": r[0], "title": r[1], "project": r[2]}
                for r in rows
            ]
    except Exception:
        return []


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


def _get_git_context() -> dict:
    """Get git session context information."""
    branch = get_current_branch()
    changed_files = get_git_status()
    is_dirty = len(changed_files) > 0

    return {
        "branch": branch,
        "is_dirty": is_dirty,
        "changed_files_count": len(changed_files),
    }


def _get_git_context_lines() -> list[str]:
    """Return lines for git context text output."""
    context = _get_git_context()
    branch = context["branch"]
    changed_count = context["changed_files_count"]

    if context["is_dirty"]:
        status_text = f"{changed_count} uncommitted change{'s' if changed_count != 1 else ''}"
    else:
        status_text = "clean"

    return [f"Git: {branch} ({status_text})"]


def _get_recent_executions() -> list[dict]:
    """Get the last 5 workflow runs from the database.

    Returns a list of dicts with: id, status, started_at, error_message (if failed).
    """
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, status, started_at, error_message
                FROM workflow_runs
                ORDER BY started_at DESC
                LIMIT 5
            """)
            rows = cursor.fetchall()
            result = []
            for row in rows:
                execution = {
                    "id": row[0],
                    "status": row[1],
                    "started_at": row[2],
                }
                # Only include error_message if status is failed
                if row[1] == "failed" and row[3]:
                    execution["error_message"] = row[3]
                result.append(execution)
            return result
    except Exception:
        # workflow_runs table may not exist in older databases
        return []


def _get_recent_executions_lines() -> list[str]:
    """Get formatted lines showing recent execution status.

    Returns lines like:
      RECENT EXECUTIONS:
        ✓ Run #42 completed
        ✗ Run #41 failed: Error message here
        ○ Run #40 running
    """
    executions = _get_recent_executions()
    if not executions:
        return []

    lines = ["RECENT EXECUTIONS:"]
    for ex in executions:
        run_id = ex["id"]
        status = ex["status"]

        if status == "completed":
            lines.append(f"  ✓ Run #{run_id} completed")
        elif status == "failed":
            error_msg = ex.get("error_message", "Unknown error")
            # Truncate long error messages
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            lines.append(f"  ✗ Run #{run_id} failed: {error_msg}")
        else:
            # running, pending, paused, cancelled
            lines.append(f"  ○ Run #{run_id} {status}")

    lines.append("")
    return lines


# Create typer app for the command
app = typer.Typer()
app.command()(prime)
