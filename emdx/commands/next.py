"""
Next command - Return the single best next action for an AI agent.

Outputs exactly one actionable command to stdout. Reasoning goes to stderr.
Designed for machine consumption: pipe stdout directly into shell or use --json.

Priority order:
1. In-progress tasks (finish what you started)
2. Ready tasks (unblocked, highest priority first)
3. Stale gameplans (tagged active + gameplan, older than 7 days)
4. Fallback: emdx prime
"""

import sys
from datetime import datetime, timedelta

import typer

from ..database import db
from ..models.tags import search_by_tags
from ..models.tasks import get_ready_tasks
from ..models.types import TagSearchResultDict, TaskDict
from ..utils.output import print_json

STALE_DAYS = 7


def next_action(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed reasoning"),
) -> None:
    """
    Return the single next action for an AI agent.

    Prints exactly one emdx command to stdout. Reasoning goes to stderr.
    Use this at session start to pick up where you left off.

    Priority:
    1. In-progress tasks → emdx task view <id>
    2. Ready tasks → emdx task active <id>
    3. Stale gameplans → emdx view <id>
    4. Fallback → emdx prime

    Examples:
        emdx next
        emdx next --json
        eval $(emdx next)
    """
    db.ensure_schema()

    action, reasoning, priority = _decide_next()

    if json_output:
        print_json(
            {
                "action": action,
                "reasoning": reasoning,
                "priority": priority,
            }
        )
    else:
        # Action to stdout (machine-readable)
        print(action)
        # Reasoning to stderr (human-readable)
        if verbose:
            print(f"reason: {reasoning}", file=sys.stderr)
            print(f"priority: {priority}", file=sys.stderr)
        else:
            print(reasoning, file=sys.stderr)


def _decide_next() -> tuple[str, str, str]:
    """Decide the next action. Returns (action, reasoning, priority)."""

    # 1. In-progress tasks — finish what you started
    in_progress = _get_in_progress_tasks()
    if in_progress:
        task = in_progress[0]
        task_id = task["id"]
        title = task.get("title", "Untitled")
        return (
            f"emdx task view {task_id}",
            f"Continue in-progress task #{task_id}: {title}",
            "in_progress",
        )

    # 2. Ready tasks — pick up unblocked work
    ready = get_ready_tasks()
    if ready:
        ready_task: TaskDict = ready[0]
        return (
            f"emdx task active {ready_task['id']}",
            f"Start ready task #{ready_task['id']}: {ready_task['title']}",
            "ready",
        )

    # 3. Stale gameplans — gameplans tagged active older than 7 days
    stale = _get_stale_gameplans()
    if stale:
        doc = stale[0]
        doc_id = doc["id"]
        title = doc.get("title", "Untitled")
        return (
            f"emdx view {doc_id}",
            f"Review stale gameplan #{doc_id}: {title}",
            "stale_gameplan",
        )

    # 4. Fallback
    return (
        "emdx prime",
        "No tasks or stale gameplans found. Run prime for full context.",
        "fallback",
    )


def _get_in_progress_tasks() -> list[dict[str, object]]:
    """Get non-delegate tasks with status='active' (in-progress)."""
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT * FROM tasks
            WHERE status = 'active'
            AND parent_task_id IS NULL
            AND prompt IS NULL
            ORDER BY priority ASC, updated_at DESC
            LIMIT 5
        """)
        return [dict(row) for row in cursor.fetchall()]


def _get_stale_gameplans() -> list[TagSearchResultDict]:
    """Get gameplan documents tagged active that are older than STALE_DAYS."""
    cutoff = datetime.now() - timedelta(days=STALE_DAYS)
    cutoff_str = cutoff.isoformat()

    # Find docs tagged both "gameplan" and "active"
    results = search_by_tags(
        ["gameplan", "active"],
        mode="all",
        prefix_match=False,
        limit=10,
    )

    # Filter to docs older than cutoff
    stale: list[TagSearchResultDict] = []
    for doc in results:
        created = doc.get("created_at", "")
        if created and str(created) < cutoff_str:
            stale.append(doc)

    return stale


# Typer app for test invocation
app = typer.Typer(help="Return the single next action for an AI agent")
app.command()(next_action)
