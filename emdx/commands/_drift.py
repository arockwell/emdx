"""Drift detection for abandoned/forgotten work in emdx.

Analyzes task and epic timestamps to surface:
- Stale epics with no recent activity
- Orphaned active tasks not touched recently
- Documents linked to stale tasks
- Epics with burst-then-stop activity patterns
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict, cast

from emdx.database import db

logger = logging.getLogger(__name__)


class StaleEpicDict(TypedDict):
    """An epic that has gone silent."""

    id: int
    title: str
    epic_key: str | None
    status: str
    open_tasks: int
    last_activity: str | None
    days_silent: int


class OrphanedTaskDict(TypedDict):
    """A task marked active but not touched recently."""

    id: int
    title: str
    status: str
    epic_key: str | None
    parent_task_id: int | None
    updated_at: str | None
    days_idle: int


class StaleLinkedDocDict(TypedDict):
    """A document linked to a stale task."""

    doc_id: int
    doc_title: str
    task_id: int
    task_title: str
    link_type: str
    days_idle: int


class BurstEpicDict(TypedDict):
    """An epic with burst-then-stop activity pattern."""

    id: int
    title: str
    epic_key: str | None
    total_tasks: int
    burst_days: int
    silent_days: int


class DriftReport(TypedDict):
    """Complete drift analysis report."""

    stale_epics: list[StaleEpicDict]
    orphaned_tasks: list[OrphanedTaskDict]
    stale_linked_docs: list[StaleLinkedDocDict]
    burst_epics: list[BurstEpicDict]


def _find_stale_epics(days: int) -> list[StaleEpicDict]:
    """Find epics with open tasks where activity stopped >days ago."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                e.id,
                e.title,
                e.epic_key,
                e.status,
                COUNT(c.id) AS open_tasks,
                MAX(
                    COALESCE(c.updated_at, c.created_at)
                ) AS last_activity,
                CAST(
                    julianday('now')
                    - julianday(
                        MAX(COALESCE(c.updated_at, c.created_at))
                    )
                    AS INTEGER
                ) AS days_silent
            FROM tasks e
            JOIN tasks c ON c.parent_task_id = e.id
            WHERE e.type = 'epic'
              AND e.status NOT IN ('done', 'wontdo', 'failed')
              AND c.status IN ('open', 'active', 'blocked')
            GROUP BY e.id
            HAVING days_silent > ?
            ORDER BY days_silent DESC
            """,
            (days,),
        )
        return [cast(StaleEpicDict, dict(row)) for row in cursor.fetchall()]


def _find_orphaned_active_tasks(days: int) -> list[OrphanedTaskDict]:
    """Find tasks marked active but not touched in >days/2 days."""
    active_threshold = max(days // 2, 7)
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                t.id,
                t.title,
                t.status,
                t.epic_key,
                t.parent_task_id,
                t.updated_at,
                CAST(
                    julianday('now')
                    - julianday(COALESCE(t.updated_at, t.created_at))
                    AS INTEGER
                ) AS days_idle
            FROM tasks t
            WHERE t.status = 'active'
              AND CAST(
                  julianday('now')
                  - julianday(COALESCE(t.updated_at, t.created_at))
                  AS INTEGER
              ) > ?
            ORDER BY days_idle DESC
            """,
            (active_threshold,),
        )
        return [cast(OrphanedTaskDict, dict(row)) for row in cursor.fetchall()]


def _find_stale_linked_docs(days: int) -> list[StaleLinkedDocDict]:
    """Find documents linked to tasks that have gone stale."""
    with db.get_connection() as conn:
        results: list[StaleLinkedDocDict] = []

        # Check source_doc_id links
        cursor = conn.execute(
            """
            SELECT
                d.id AS doc_id,
                d.title AS doc_title,
                t.id AS task_id,
                t.title AS task_title,
                'source' AS link_type,
                CAST(
                    julianday('now')
                    - julianday(
                        COALESCE(t.updated_at, t.created_at)
                    )
                    AS INTEGER
                ) AS days_idle
            FROM tasks t
            JOIN documents d ON t.source_doc_id = d.id
            WHERE t.status IN ('open', 'active', 'blocked')
              AND d.is_deleted = FALSE
              AND CAST(
                  julianday('now')
                  - julianday(
                      COALESCE(t.updated_at, t.created_at)
                  )
                  AS INTEGER
              ) > ?
            ORDER BY days_idle DESC
            """,
            (days,),
        )
        results.extend(cast(StaleLinkedDocDict, dict(row)) for row in cursor.fetchall())

        # Deduplicate by (doc_id, task_id)
        seen: set[tuple[int, int]] = set()
        unique: list[StaleLinkedDocDict] = []
        for item in results:
            key = (item["doc_id"], item["task_id"])
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique


def _find_burst_epics(days: int) -> list[BurstEpicDict]:
    """Find epics that had burst activity then sudden stop.

    Pattern: multiple tasks created within a short window,
    then nothing for >days.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                e.id,
                e.title,
                e.epic_key,
                COUNT(c.id) AS total_tasks,
                CAST(
                    julianday(MAX(c.created_at))
                    - julianday(MIN(c.created_at))
                    AS INTEGER
                ) AS burst_days,
                CAST(
                    julianday('now')
                    - julianday(
                        MAX(COALESCE(c.updated_at, c.created_at))
                    )
                    AS INTEGER
                ) AS silent_days
            FROM tasks e
            JOIN tasks c ON c.parent_task_id = e.id
            WHERE e.type = 'epic'
              AND e.status NOT IN ('done', 'wontdo', 'failed')
            GROUP BY e.id
            HAVING total_tasks >= 3
              AND burst_days <= 7
              AND silent_days > ?
            ORDER BY silent_days DESC
            """,
            (days,),
        )
        return [cast(BurstEpicDict, dict(row)) for row in cursor.fetchall()]


def analyze_drift(days: int = 30) -> DriftReport:
    """Run full drift analysis and return structured report."""
    return DriftReport(
        stale_epics=_find_stale_epics(days),
        orphaned_tasks=_find_orphaned_active_tasks(days),
        stale_linked_docs=_find_stale_linked_docs(days),
        burst_epics=_find_burst_epics(days),
    )


def _format_plain(report: DriftReport, days: int) -> str:
    """Format drift report as plain text."""
    lines: list[str] = []

    has_drift = (
        report["stale_epics"]
        or report["orphaned_tasks"]
        or report["stale_linked_docs"]
        or report["burst_epics"]
    )

    if not has_drift:
        return "No drift detected \u2014 everything looks active! \U0001f3af"

    lines.append(f"Drift Report (threshold: {days} days)")
    lines.append("=" * 50)

    # Stale epics
    if report["stale_epics"]:
        lines.append("")
        lines.append(f"Stale Epics ({len(report['stale_epics'])})")
        lines.append("-" * 30)
        for epic in report["stale_epics"]:
            key = epic.get("epic_key") or "?"
            lines.append(
                f"  #{epic['id']} {epic['title']} "
                f"[{key}] -- went silent "
                f"{epic['days_silent']} days ago "
                f"({epic['open_tasks']} open tasks)"
            )

    # Orphaned active tasks
    if report["orphaned_tasks"]:
        lines.append("")
        lines.append(f"Orphaned Active Tasks ({len(report['orphaned_tasks'])})")
        lines.append("-" * 30)
        for task in report["orphaned_tasks"]:
            key = task.get("epic_key") or ""
            prefix = f"[{key}] " if key else ""
            lines.append(
                f"  #{task['id']} {prefix}{task['title']} -- idle {task['days_idle']} days"
            )

    # Stale linked docs
    if report["stale_linked_docs"]:
        lines.append("")
        lines.append(f"Docs Linked to Stale Tasks ({len(report['stale_linked_docs'])})")
        lines.append("-" * 30)
        for doc in report["stale_linked_docs"]:
            lines.append(
                f"  Doc #{doc['doc_id']} "
                f'"{doc["doc_title"]}" '
                f"linked ({doc['link_type']}) to "
                f"task #{doc['task_id']} "
                f'"{doc["task_title"]}" '
                f"-- idle {doc['days_idle']} days"
            )

    # Burst epics
    if report["burst_epics"]:
        lines.append("")
        lines.append(f"Burst-Then-Stop Epics ({len(report['burst_epics'])})")
        lines.append("-" * 30)
        for burst in report["burst_epics"]:
            key = burst.get("epic_key") or "?"
            lines.append(
                f"  #{burst['id']} {burst['title']} "
                f"[{key}] -- "
                f"{burst['total_tasks']} tasks created "
                f"in {burst['burst_days']} day(s), "
                f"then silent for "
                f"{burst['silent_days']} days"
            )

    return "\n".join(lines)


def _format_json(report: DriftReport) -> str:
    """Format drift report as JSON."""
    return json.dumps(report, indent=2, default=str)


def run_drift(days: int = 30, json_output: bool = False) -> None:
    """Run drift analysis and print results."""
    report = analyze_drift(days=days)

    if json_output:
        print(_format_json(report))
    else:
        print(_format_plain(report, days))
