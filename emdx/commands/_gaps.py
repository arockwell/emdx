"""Knowledge gap detection for emdx.

Analyzes the knowledge base to identify areas with sparse coverage:
- Tags/categories with very few documents compared to average
- Documents with many incoming links but no outgoing links (knowledge sinks)
- Documents with zero links (isolated/orphan knowledge)
- Categories/tags where all documents are old with no recent activity
- Projects with disproportionately few documents relative to their task count
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict, cast

from emdx.database import db

logger = logging.getLogger(__name__)


class TagGap(TypedDict):
    """A tag with significantly fewer documents than average."""

    tag_name: str
    doc_count: int
    avg_count: float
    severity: str
    suggestion: str


class LinkSink(TypedDict):
    """A document with incoming links but no outgoing links."""

    doc_id: int
    doc_title: str
    incoming_count: int
    outgoing_count: int
    severity: str
    suggestion: str


class OrphanDoc(TypedDict):
    """A document with zero links (isolated knowledge)."""

    doc_id: int
    doc_title: str
    project: str | None
    created_at: str | None
    severity: str
    suggestion: str


class StaleTopic(TypedDict):
    """A tag where all documents are old with no recent activity."""

    tag_name: str
    doc_count: int
    newest_doc_days: int
    severity: str
    suggestion: str


class ProjectImbalance(TypedDict):
    """A project with disproportionately few docs relative to task count."""

    project: str
    doc_count: int
    task_count: int
    ratio: float
    severity: str
    suggestion: str


class GapReport(TypedDict):
    """Complete knowledge gap analysis report."""

    tag_gaps: list[TagGap]
    link_sinks: list[LinkSink]
    orphan_docs: list[OrphanDoc]
    stale_topics: list[StaleTopic]
    project_imbalances: list[ProjectImbalance]


def _find_tag_gaps(top: int) -> list[TagGap]:
    """Find tags with significantly fewer documents than average.

    Computes the average document count per tag and returns tags
    that have fewer than half the average.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                t.name AS tag_name,
                COUNT(dt.document_id) AS doc_count
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = FALSE
            GROUP BY t.id, t.name
            ORDER BY doc_count ASC
            """
        )
        rows = [cast(dict[str, int | str], dict(row)) for row in cursor.fetchall()]

    if not rows:
        return []

    counts = [int(row["doc_count"]) for row in rows]
    avg_count = sum(counts) / len(counts) if counts else 0

    # Only flag tags below half the average (and average must be > 1)
    if avg_count <= 1:
        return []

    threshold = avg_count / 2
    gaps: list[TagGap] = []
    for row in rows:
        doc_count = int(row["doc_count"])
        if doc_count < threshold:
            severity = "high" if doc_count <= 1 else "medium"
            tag_name = str(row["tag_name"])
            gaps.append(
                TagGap(
                    tag_name=tag_name,
                    doc_count=doc_count,
                    avg_count=round(avg_count, 1),
                    severity=severity,
                    suggestion=(
                        f"Tag '{tag_name}' has only "
                        f"{doc_count} doc(s) vs avg "
                        f"{avg_count:.1f}. Consider adding "
                        f"more content or merging with a "
                        f"related tag."
                    ),
                )
            )

    return gaps[:top]


def _find_link_sinks(top: int) -> list[LinkSink]:
    """Find documents with many incoming links but no outgoing links.

    These are knowledge sinks -- documents that other docs reference
    but which don't link back to anything, potentially indicating
    missing connections.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                d.id AS doc_id,
                d.title AS doc_title,
                COALESCE(incoming.cnt, 0) AS incoming_count,
                COALESCE(outgoing.cnt, 0) AS outgoing_count
            FROM documents d
            LEFT JOIN (
                SELECT target_doc_id AS doc_id, COUNT(*) AS cnt
                FROM document_links
                GROUP BY target_doc_id
            ) incoming ON d.id = incoming.doc_id
            LEFT JOIN (
                SELECT source_doc_id AS doc_id, COUNT(*) AS cnt
                FROM document_links
                GROUP BY source_doc_id
            ) outgoing ON d.id = outgoing.doc_id
            WHERE d.is_deleted = FALSE
              AND COALESCE(incoming.cnt, 0) >= 2
              AND COALESCE(outgoing.cnt, 0) = 0
            ORDER BY incoming_count DESC
            LIMIT ?
            """,
            (top,),
        )
        results: list[LinkSink] = []
        for row in cursor.fetchall():
            r = dict(row)
            incoming: int = r["incoming_count"]
            doc_title: str = r["doc_title"]
            doc_id: int = r["doc_id"]
            severity = "high" if incoming >= 5 else "medium"
            results.append(
                LinkSink(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    incoming_count=incoming,
                    outgoing_count=r["outgoing_count"],
                    severity=severity,
                    suggestion=(
                        f"Doc #{doc_id} "
                        f'"{doc_title}" has '
                        f"{incoming} incoming link(s) but "
                        f"no outgoing links. Consider adding "
                        f"references to related documents."
                    ),
                )
            )
        return results


def _find_orphan_docs(top: int) -> list[OrphanDoc]:
    """Find documents with zero links in either direction.

    These are isolated knowledge islands that aren't connected
    to any other document in the knowledge graph.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                d.id AS doc_id,
                d.title AS doc_title,
                d.project,
                d.created_at
            FROM documents d
            WHERE d.is_deleted = FALSE
              AND d.id NOT IN (
                  SELECT source_doc_id FROM document_links
                  UNION
                  SELECT target_doc_id FROM document_links
              )
            ORDER BY d.created_at ASC
            LIMIT ?
            """,
            (top,),
        )
        results: list[OrphanDoc] = []
        for row in cursor.fetchall():
            r = dict(row)
            doc_id: int = r["doc_id"]
            doc_title: str = r["doc_title"]
            results.append(
                OrphanDoc(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    project=r["project"],
                    created_at=(str(r["created_at"]) if r["created_at"] else None),
                    severity="low",
                    suggestion=(
                        f"Doc #{doc_id} "
                        f'"{doc_title}" has no links. '
                        f"Run 'emdx maintain link --all' to "
                        f"auto-detect connections."
                    ),
                )
            )
        return results


def _find_stale_topics(stale_days: int, top: int) -> list[StaleTopic]:
    """Find tags where all documents are old with no recent activity.

    A tag is considered stale when its newest document is older
    than stale_days.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                t.name AS tag_name,
                COUNT(dt.document_id) AS doc_count,
                CAST(
                    julianday('now')
                    - julianday(
                        MAX(
                            COALESCE(d.updated_at, d.created_at)
                        )
                    )
                    AS INTEGER
                ) AS newest_doc_days
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = FALSE
            GROUP BY t.id, t.name
            HAVING newest_doc_days > ?
            ORDER BY newest_doc_days DESC
            LIMIT ?
            """,
            (stale_days, top),
        )
        results: list[StaleTopic] = []
        for row in cursor.fetchall():
            r = dict(row)
            days: int = r["newest_doc_days"]
            tag_name: str = r["tag_name"]
            doc_count: int = r["doc_count"]
            severity = "high" if days > 120 else "medium"
            results.append(
                StaleTopic(
                    tag_name=tag_name,
                    doc_count=doc_count,
                    newest_doc_days=days,
                    severity=severity,
                    suggestion=(
                        f"Tag '{tag_name}' has "
                        f"{doc_count} doc(s), newest "
                        f"is {days} days old. Consider "
                        f"updating or archiving."
                    ),
                )
            )
        return results


def _find_project_imbalances(top: int) -> list[ProjectImbalance]:
    """Find projects with few docs relative to their task count.

    A project is imbalanced when it has many tasks but very few
    documents, suggesting knowledge is being generated but not
    captured.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                p.project,
                p.doc_count,
                COALESCE(t.task_count, 0) AS task_count
            FROM (
                SELECT project, COUNT(*) AS doc_count
                FROM documents
                WHERE is_deleted = FALSE
                  AND project IS NOT NULL
                  AND project != ''
                GROUP BY project
            ) p
            LEFT JOIN (
                SELECT project, COUNT(*) AS task_count
                FROM tasks
                WHERE project IS NOT NULL
                  AND project != ''
                GROUP BY project
            ) t ON p.project = t.project
            WHERE COALESCE(t.task_count, 0) > 0
            ORDER BY
                CAST(p.doc_count AS REAL)
                / COALESCE(t.task_count, 1) ASC
            LIMIT ?
            """,
            (top,),
        )
        results: list[ProjectImbalance] = []
        for row in cursor.fetchall():
            r = dict(row)
            doc_count: int = r["doc_count"]
            task_count: int = r["task_count"]
            project: str = r["project"]
            ratio = round(doc_count / task_count if task_count > 0 else 0, 2)
            # Only flag if ratio is low (< 0.5 docs per task)
            if ratio >= 0.5:
                continue
            severity = "high" if ratio < 0.2 else "medium"
            results.append(
                ProjectImbalance(
                    project=project,
                    doc_count=doc_count,
                    task_count=task_count,
                    ratio=ratio,
                    severity=severity,
                    suggestion=(
                        f"Project '{project}' has "
                        f"{doc_count} doc(s) but "
                        f"{task_count} task(s) "
                        f"(ratio: {ratio}). Consider "
                        f"documenting findings from "
                        f"completed tasks."
                    ),
                )
            )
        return results


def analyze_gaps(top: int = 10, stale_days: int = 60) -> GapReport:
    """Run full gap analysis and return structured report."""
    return GapReport(
        tag_gaps=_find_tag_gaps(top),
        link_sinks=_find_link_sinks(top),
        orphan_docs=_find_orphan_docs(top),
        stale_topics=_find_stale_topics(stale_days, top),
        project_imbalances=_find_project_imbalances(top),
    )


def _format_plain(report: GapReport, top: int) -> str:
    """Format gap report as plain text."""
    has_gaps = (
        report["tag_gaps"]
        or report["link_sinks"]
        or report["orphan_docs"]
        or report["stale_topics"]
        or report["project_imbalances"]
    )

    if not has_gaps:
        return "No knowledge gaps detected -- coverage looks good!"

    lines: list[str] = []
    lines.append(f"Knowledge Gap Report (top {top})")
    lines.append("=" * 50)

    # Tag coverage gaps
    if report["tag_gaps"]:
        lines.append("")
        lines.append(f"Tag Coverage Gaps ({len(report['tag_gaps'])})")
        lines.append("-" * 30)
        for gap in report["tag_gaps"]:
            lines.append(
                f"  [{gap['severity'].upper()}] "
                f"'{gap['tag_name']}': "
                f"{gap['doc_count']} doc(s) "
                f"(avg: {gap['avg_count']})"
            )

    # Link sinks
    if report["link_sinks"]:
        lines.append("")
        lines.append(f"Link Dead-Ends ({len(report['link_sinks'])})")
        lines.append("-" * 30)
        for sink in report["link_sinks"]:
            lines.append(
                f"  [{sink['severity'].upper()}] "
                f"#{sink['doc_id']} "
                f'"{sink["doc_title"]}": '
                f"{sink['incoming_count']} incoming, "
                f"{sink['outgoing_count']} outgoing"
            )

    # Orphan documents
    if report["orphan_docs"]:
        lines.append("")
        lines.append(f"Orphan Documents ({len(report['orphan_docs'])})")
        lines.append("-" * 30)
        for orphan in report["orphan_docs"]:
            project = f" [{orphan['project']}]" if orphan["project"] else ""
            lines.append(
                f"  [{orphan['severity'].upper()}] "
                f"#{orphan['doc_id']} "
                f'"{orphan["doc_title"]}"{project}'
            )

    # Stale topics
    if report["stale_topics"]:
        lines.append("")
        lines.append(f"Stale Topics ({len(report['stale_topics'])})")
        lines.append("-" * 30)
        for topic in report["stale_topics"]:
            lines.append(
                f"  [{topic['severity'].upper()}] "
                f"'{topic['tag_name']}': "
                f"{topic['doc_count']} doc(s), "
                f"newest {topic['newest_doc_days']} days old"
            )

    # Project imbalances
    if report["project_imbalances"]:
        lines.append("")
        lines.append(f"Project Imbalances ({len(report['project_imbalances'])})")
        lines.append("-" * 30)
        for imb in report["project_imbalances"]:
            lines.append(
                f"  [{imb['severity'].upper()}] "
                f"'{imb['project']}': "
                f"{imb['doc_count']} doc(s) / "
                f"{imb['task_count']} task(s) "
                f"(ratio: {imb['ratio']})"
            )

    return "\n".join(lines)


def _format_json(report: GapReport) -> str:
    """Format gap report as JSON."""
    return json.dumps(report, indent=2, default=str)


def run_gaps(
    top: int = 10,
    stale_days: int = 60,
    json_output: bool = False,
) -> None:
    """Run gap analysis and print results."""
    report = analyze_gaps(top=top, stale_days=stale_days)

    if json_output:
        print(_format_json(report))
    else:
        print(_format_plain(report, top))
