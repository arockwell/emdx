"""Session wrapup command for generating activity summaries.

Queries recent tasks, documents, and delegate executions to generate a
coherent session summary via AI synthesis.
"""

import json
import sys
from datetime import datetime
from typing import Any

import typer

from ..database.documents import get_docs_in_window, save_document
from ..models.executions import get_execution_stats_in_window
from ..models.tasks import get_delegate_tasks_in_window, get_tasks_in_window
from ..services.synthesis_service import _execute_prompt

app = typer.Typer(name="wrapup", help="Generate session summary from recent activity")


def _collect_activity(hours: int) -> dict[str, Any]:
    """Collect activity data from the last N hours."""
    return {
        "window_hours": hours,
        "tasks": get_tasks_in_window(hours),
        "docs": get_docs_in_window(hours),
        "delegate_tasks": get_delegate_tasks_in_window(hours),
        "execution_stats": get_execution_stats_in_window(hours),
    }


def _build_synthesis_prompt(activity: dict[str, Any]) -> str:
    """Build the synthesis prompt from activity data."""
    sections = []

    # Header
    sections.append(
        f"Generate a concise session summary for the last {activity['window_hours']} hours.\n"
        "Focus on: what was accomplished, what's in progress, and what needs attention next."
    )

    # Tasks section
    tasks = activity["tasks"]
    if tasks:
        done = [t for t in tasks if t["status"] == "done"]
        active = [t for t in tasks if t["status"] == "active"]
        blocked = [t for t in tasks if t["status"] == "blocked"]

        task_lines = []
        if done:
            task_lines.append("## Completed Tasks")
            for t in done[:10]:
                task_lines.append(f"- {t['title']}")
        if active:
            task_lines.append("## In-Progress Tasks")
            for t in active[:5]:
                task_lines.append(f"- {t['title']}")
        if blocked:
            task_lines.append("## Blocked Tasks")
            for t in blocked[:5]:
                task_lines.append(f"- {t['title']}")

        if task_lines:
            sections.append("\n".join(task_lines))

    # Documents section
    docs = activity["docs"]
    if docs:
        doc_lines = ["## Documents Created"]
        for d in docs[:15]:
            doc_lines.append(f"- #{d['id']}: {d['title']}")
        sections.append("\n".join(doc_lines))

    # Delegate activity section
    delegate_tasks = activity["delegate_tasks"]
    exec_stats = activity["execution_stats"]
    if delegate_tasks or exec_stats["total"] > 0:
        delegate_lines = ["## Delegate Activity"]
        delegate_lines.append(
            f"- Total executions: {exec_stats['total']} "
            f"(completed: {exec_stats['completed']}, failed: {exec_stats['failed']})"
        )
        if exec_stats["total_cost_usd"] > 0:
            delegate_lines.append(f"- Total cost: ${exec_stats['total_cost_usd']:.4f}")
        if delegate_tasks:
            delegate_lines.append("\n### Recent Delegate Tasks:")
            for dt in delegate_tasks[:10]:
                status = "done" if dt["status"] == "done" else dt["status"]
                doc_ref = f" -> #{dt['output_doc_id']}" if dt.get("output_doc_id") else ""
                delegate_lines.append(f"- [{status}] {dt['title']}{doc_ref}")
        sections.append("\n".join(delegate_lines))

    # Final instruction
    sections.append(
        "---\n\n"
        "Based on the above activity, write a session summary that:\n"
        "1. Highlights key accomplishments (what was completed)\n"
        "2. Notes work in progress (what's being worked on)\n"
        "3. Flags blockers or failures that need attention\n"
        "4. Suggests next steps (what should happen next)\n\n"
        "Format as markdown. Keep it concise but actionable."
    )

    return "\n\n".join(sections)


def _print_dry_run_summary(activity: dict[str, Any]) -> None:
    """Print a summary of what would be synthesized."""
    hours = activity["window_hours"]
    tasks = activity["tasks"]
    docs = activity["docs"]
    delegate_tasks = activity["delegate_tasks"]
    exec_stats = activity["execution_stats"]

    print(f"Would summarize activity from the last {hours} hours:\n")

    done_count = len([t for t in tasks if t["status"] == "done"])
    active_count = len([t for t in tasks if t["status"] == "active"])
    blocked_count = len([t for t in tasks if t["status"] == "blocked"])

    print(f"  Tasks: {len(tasks)} total")
    print(f"    - Done: {done_count}")
    print(f"    - Active: {active_count}")
    print(f"    - Blocked: {blocked_count}")

    print(f"\n  Documents: {len(docs)} created")

    print(f"\n  Delegate executions: {exec_stats['total']} total")
    print(f"    - Completed: {exec_stats['completed']}")
    print(f"    - Failed: {exec_stats['failed']}")
    print(f"    - Running: {exec_stats['running']}")
    if exec_stats["total_cost_usd"] > 0:
        print(f"    - Cost: ${exec_stats['total_cost_usd']:.4f}")

    print(f"\n  Delegate tasks: {len(delegate_tasks)} top-level")


def _run_synthesis(
    prompt: str,
    title: str,
    model: str | None,
) -> str | None:
    """Run synthesis via the synthesis service. Returns content or None."""
    system_prompt = (
        "You are a session summarizer. Generate concise, actionable summaries "
        "of work activity. Focus on accomplishments, blockers, and next steps."
    )

    try:
        result = _execute_prompt(
            system_prompt=system_prompt,
            user_message=prompt,
            title=title,
            model=model,
        )

        if result.success and result.output_content:
            return result.output_content
    except RuntimeError as e:
        sys.stderr.write(f"wrapup: synthesis failed: {e}\n")

    return None


@app.callback(invoke_without_command=True)
def wrapup(
    ctx: typer.Context,
    hours: int = typer.Option(
        4, "--hours", "-h", help="Window of activity to summarize (default: 4 hours)"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model to use (default: claude-sonnet-4-5)"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress metadata, just output summary"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output activity data as JSON (no synthesis)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be summarized without synthesizing"
    ),
    save: bool = typer.Option(False, "--save", "-s", help="Save summary to knowledge base"),
) -> None:
    """Generate a session summary from recent activity.

    Queries tasks, documents, and delegate executions from the last N hours,
    then synthesizes a coherent summary. Output goes to stdout.
    Use --save to persist to the knowledge base.

    Examples:
        emdx wrapup                    # Summarize last 4 hours
        emdx wrapup --hours 8          # Summarize last 8 hours
        emdx wrapup --save             # Summarize and save to KB
        emdx wrapup --dry-run          # Preview what would be summarized
        emdx wrapup --json             # Get raw activity data
    """
    # Collect activity data
    activity = _collect_activity(hours)

    # Handle JSON output mode
    if json_output:
        # Convert any datetime objects to strings for JSON serialization
        def serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        output = json.dumps(activity, default=serialize, indent=2)
        print(output)
        return

    # Handle dry-run mode
    if dry_run:
        _print_dry_run_summary(activity)
        return

    # Check if there's anything to summarize
    total_items = len(activity["tasks"]) + len(activity["docs"]) + len(activity["delegate_tasks"])
    if total_items == 0:
        print(f"No activity in the last {hours} hours.")
        return

    # Build synthesis prompt
    prompt = _build_synthesis_prompt(activity)

    # Run synthesis
    title = f"Session Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})"

    if not quiet:
        sys.stderr.write(f"wrapup: synthesizing {total_items} items...\n")

    content = _run_synthesis(
        prompt=prompt,
        title=title,
        model=model or "claude-sonnet-4-5-20250929",
    )

    if not content:
        sys.stderr.write("wrapup: synthesis failed, no output generated\n")
        raise typer.Exit(1)

    print(content)

    if save:
        tags = ["session-summary", "active"]
        doc_id = save_document(title=title, content=content, tags=tags)
        if not quiet:
            sys.stderr.write(f"wrapup: saved as doc #{doc_id}\n")
