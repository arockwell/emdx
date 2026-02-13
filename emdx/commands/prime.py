"""
Prime command - Output context for Claude session injection.

This is the key command for making Claude use emdx natively.
It outputs priming context that should be injected at session start.

The --smart flag provides context-aware priming with:
- Recent activity (last 7 days)
- Key docs (most viewed/referenced)
- Knowledge map (tags across project)
- Staleness detection (docs needing review)
"""

import subprocess
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console

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
    smart: bool = typer.Option(
        False,
        "--smart", "-s",
        help="Context-aware priming with recent activity, key docs, knowledge map, and staleness detection"
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

        # Smart context-aware priming (recommended)
        emdx prime --smart

        # With full context
        emdx prime --verbose

        # Minimal (just ready tasks)
        emdx prime --quiet

        # For session hooks
        emdx prime >> /tmp/claude-context.md
    """
    project = get_git_project()

    if smart:
        if format == "json":
            _output_smart_json(project)
        else:
            _output_smart_text(project)
    elif format == "json":
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


def _output_text(project: str | None, verbose: bool, quiet: bool, markdown: bool, execution: bool):
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


def _output_json(project: str | None, verbose: bool, quiet: bool, execution: bool):
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


# =============================================================================
# Smart Priming Functions
# =============================================================================


def _get_git_context() -> dict:
    """Get git context: branch, recent commits, open PRs."""
    context = {
        "branch": None,
        "recent_commits": [],
        "open_prs": [],
    }

    try:
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            context["branch"] = result.stdout.strip()

        # Get recent commits (last 3)
        result = subprocess.run(
            ["git", "log", "--oneline", "-3", "--no-decorate"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            commits = result.stdout.strip().split("\n")
            context["recent_commits"] = [c for c in commits if c]

        # Get open PRs (requires gh CLI)
        result = subprocess.run(
            ["gh", "pr", "list", "--state=open", "--limit=3", "--json=number,title"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            import json
            try:
                prs = json.loads(result.stdout)
                context["open_prs"] = [{"number": pr["number"], "title": pr["title"]} for pr in prs]
            except (json.JSONDecodeError, KeyError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return context


def _get_recent_activity(project: Optional[str], days: int = 7) -> list:
    """Get recent docs for project within last N days."""
    cutoff = datetime.now() - timedelta(days=days)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        if project:
            cursor.execute("""
                SELECT id, title, accessed_at, access_count
                FROM documents
                WHERE is_deleted = 0
                AND project = ?
                AND accessed_at >= ?
                ORDER BY accessed_at DESC
                LIMIT 10
            """, (project, cutoff.isoformat()))
        else:
            cursor.execute("""
                SELECT id, title, accessed_at, access_count
                FROM documents
                WHERE is_deleted = 0
                AND accessed_at >= ?
                ORDER BY accessed_at DESC
                LIMIT 10
            """, (cutoff.isoformat(),))

        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "accessed_at": r[2],
                "views": r[3]
            }
            for r in rows
        ]


def _get_key_docs(project: Optional[str], limit: int = 5) -> list:
    """Get key docs sorted by view count (importance score)."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if project:
            cursor.execute("""
                SELECT id, title, access_count
                FROM documents
                WHERE is_deleted = 0
                AND project = ?
                AND access_count > 0
                ORDER BY access_count DESC
                LIMIT ?
            """, (project, limit))
        else:
            cursor.execute("""
                SELECT id, title, access_count
                FROM documents
                WHERE is_deleted = 0
                AND access_count > 0
                ORDER BY access_count DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        return [
            {"id": r[0], "title": r[1], "views": r[2]}
            for r in rows
        ]


def _get_knowledge_map(project: Optional[str]) -> dict:
    """Get tag aggregation for project - shows what topics are covered."""
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get tags with counts for this project
        if project:
            cursor.execute("""
                SELECT t.name, COUNT(dt.document_id) as count
                FROM tags t
                JOIN document_tags dt ON t.id = dt.tag_id
                JOIN documents d ON dt.document_id = d.id
                WHERE d.is_deleted = 0
                AND d.project = ?
                GROUP BY t.name
                ORDER BY count DESC
                LIMIT 20
            """, (project,))
        else:
            cursor.execute("""
                SELECT t.name, COUNT(dt.document_id) as count
                FROM tags t
                JOIN document_tags dt ON t.id = dt.tag_id
                JOIN documents d ON dt.document_id = d.id
                WHERE d.is_deleted = 0
                GROUP BY t.name
                ORDER BY count DESC
                LIMIT 20
            """)

        rows = cursor.fetchall()
        tags = {r[0]: r[1] for r in rows}

        # Expected topics - used to detect gaps
        expected_topics = {
            "architecture", "testing", "deployment", "docs", "security",
            "api", "database", "performance", "ci/cd", "design"
        }

        # Find covered vs missing
        covered = [tag for tag in tags.keys() if any(
            exp in tag.lower() for exp in expected_topics
        )]
        missing = [topic for topic in expected_topics if not any(
            topic in tag.lower() for tag in tags.keys()
        )]

        return {
            "tags": tags,
            "covered_topics": covered,
            "potential_gaps": missing[:5],  # Limit to top 5 gaps
        }


def _get_stale_docs(project: Optional[str], stale_days: int = 14, importance_threshold: int = 3) -> list:
    """Get important docs that haven't been viewed recently."""
    cutoff = datetime.now() - timedelta(days=stale_days)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        if project:
            cursor.execute("""
                SELECT id, title, accessed_at, access_count
                FROM documents
                WHERE is_deleted = 0
                AND project = ?
                AND access_count >= ?
                AND accessed_at < ?
                ORDER BY access_count DESC
                LIMIT 5
            """, (project, importance_threshold, cutoff.isoformat()))
        else:
            cursor.execute("""
                SELECT id, title, accessed_at, access_count
                FROM documents
                WHERE is_deleted = 0
                AND access_count >= ?
                AND accessed_at < ?
                ORDER BY access_count DESC
                LIMIT 5
            """, (importance_threshold, cutoff.isoformat()))

        rows = cursor.fetchall()
        result = []
        for r in rows:
            accessed_at = r[2]
            if isinstance(accessed_at, str):
                try:
                    accessed_dt = datetime.fromisoformat(accessed_at.replace("Z", "+00:00"))
                    days_stale = (datetime.now() - accessed_dt.replace(tzinfo=None)).days
                except (ValueError, TypeError):
                    days_stale = stale_days
            else:
                days_stale = stale_days

            result.append({
                "id": r[0],
                "title": r[1],
                "views": r[3],
                "days_stale": days_stale,
            })
        return result


def _format_relative_time(dt_str: str) -> str:
    """Format datetime string as relative time (e.g., 'yesterday', '2 days ago')."""
    try:
        if isinstance(dt_str, str):
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            dt = dt.replace(tzinfo=None)
        else:
            dt = dt_str

        now = datetime.now()
        diff = now - dt
        days = diff.days

        # Handle future dates (can happen with timezone issues)
        if days < 0:
            days = 0

        if days == 0:
            return "today"
        elif days == 1:
            return "yesterday"
        elif days < 7:
            return f"{days} days ago"
        elif days < 30:
            weeks = days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        else:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
    except (ValueError, TypeError, AttributeError):
        return "unknown"


def _output_smart_text(project: Optional[str]):
    """Output smart priming context as compact text (<500 tokens target)."""
    lines = []

    # Header - compact
    lines.append(f"EMDX CONTEXT — Project: {project or 'unknown'}")
    lines.append("")

    # Git context
    git_ctx = _get_git_context()
    if git_ctx["branch"]:
        lines.append(f"Branch: {git_ctx['branch']}")
    if git_ctx["recent_commits"]:
        lines.append(f"Recent commits: {', '.join(git_ctx['recent_commits'][:2])}")
    if git_ctx["open_prs"]:
        pr_strs = [f"#{pr['number']}" for pr in git_ctx["open_prs"]]
        lines.append(f"Open PRs: {', '.join(pr_strs)}")
    if any([git_ctx["branch"], git_ctx["recent_commits"], git_ctx["open_prs"]]):
        lines.append("")

    # Recent activity (last 7 days)
    recent = _get_recent_activity(project)
    if recent:
        lines.append("📅 Recent activity (last 7 days):")
        for doc in recent[:5]:
            relative = _format_relative_time(doc["accessed_at"])
            views_str = f", {doc['views']} views" if doc["views"] > 1 else ""
            lines.append(f"  #{doc['id']} \"{doc['title']}\" ({relative}{views_str})")
        lines.append("")

    # Key docs (most viewed)
    key_docs = _get_key_docs(project)
    if key_docs:
        lines.append("🔑 Key docs (most viewed):")
        for doc in key_docs:
            lines.append(f"  #{doc['id']} \"{doc['title']}\" — {doc['views']} views")
        lines.append("")

    # Knowledge map
    knowledge = _get_knowledge_map(project)
    if knowledge["tags"]:
        # Format as compact tag list with counts
        tag_strs = [f"{tag}({count})" for tag, count in list(knowledge["tags"].items())[:8]]
        lines.append(f"🏷️ Active tags: {', '.join(tag_strs)}")
        if knowledge["potential_gaps"]:
            lines.append(f"   Potential gaps: {', '.join(knowledge['potential_gaps'])}")
        lines.append("")

    # Stale docs needing review
    stale = _get_stale_docs(project)
    if stale:
        lines.append("⏰ Needs review:")
        for doc in stale[:3]:
            importance = "HIGH" if doc["views"] >= 5 else "MEDIUM"
            lines.append(f"  #{doc['id']} \"{doc['title']}\" — {doc['days_stale']} days stale, {importance} importance")
        lines.append("")

    # Compact footer
    lines.append("Run 'emdx view <id>' to access any document.")

    print("\n".join(lines))


def _output_smart_json(project: Optional[str]):
    """Output smart priming context as JSON."""
    import json

    data = {
        "project": project,
        "timestamp": datetime.now().isoformat(),
        "git_context": _get_git_context(),
        "recent_activity": _get_recent_activity(project),
        "key_docs": _get_key_docs(project),
        "knowledge_map": _get_knowledge_map(project),
        "stale_docs": _get_stale_docs(project),
    }

    print(json.dumps(data, indent=2, default=str))


# Create typer app for the command
app = typer.Typer(help="Output priming context for Claude session injection")
app.command()(prime)
