"""Document freshness scoring for emdx.

Scores every document on a 0-1 freshness scale by combining multiple signals:
- Age decay: exponential decay with ~30-day half-life
- View recency: when the doc was last accessed
- Link health: whether linked documents are still active (not deleted)
- Content length: very short docs (<100 chars) are likely stubs
- Tag signals: "active" tag boosts freshness, "done" penalizes it
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import TypedDict, cast

from emdx.database import db

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

AGE_HALF_LIFE_DAYS = 30.0
"""Half-life for exponential age decay (days)."""

VIEW_RECENCY_HALF_LIFE_DAYS = 14.0
"""Half-life for view-recency decay (days)."""

STUB_THRESHOLD_CHARS = 100
"""Content shorter than this is considered a stub."""

TAG_BOOST: dict[str, float] = {
    "active": 0.2,
    "security": 0.1,
    "gameplan": 0.1,
    "reference": 0.1,
}
"""Tags that boost freshness (added to the tag signal)."""

TAG_PENALTY: dict[str, float] = {
    "done": -0.3,
    "failed": -0.2,
    "archived": -0.4,
}
"""Tags that penalize freshness (subtracted from the tag signal)."""

# ── Signal weights (must sum to 1.0) ─────────────────────────────────────

WEIGHT_AGE = 0.30
WEIGHT_VIEW_RECENCY = 0.25
WEIGHT_LINK_HEALTH = 0.15
WEIGHT_CONTENT_LENGTH = 0.10
WEIGHT_TAGS = 0.20


# ── TypedDicts ────────────────────────────────────────────────────────────


class SignalScores(TypedDict):
    """Individual signal scores (each 0-1)."""

    age_decay: float
    view_recency: float
    link_health: float
    content_length: float
    tag_signal: float


class DocFreshnessScore(TypedDict):
    """Freshness score for a single document."""

    id: int
    title: str
    freshness: float
    signals: SignalScores


class FreshnessReport(TypedDict):
    """Complete freshness analysis report."""

    total_documents: int
    scored_documents: int
    stale_count: int
    threshold: float
    scores: list[DocFreshnessScore]


# ── Internal row type for the SQL query ───────────────────────────────────


class _DocRow(TypedDict):
    """Row returned from the documents query."""

    id: int
    title: str
    content: str
    created_at: str | datetime
    accessed_at: str | datetime | None
    is_deleted: int


# ── Scoring helpers ──────────────────────────────────────────────────────


def _exponential_decay(days: float, half_life: float) -> float:
    """Return a 0-1 score that decays exponentially over time."""
    if days <= 0:
        return 1.0
    return math.exp(-math.log(2) * days / half_life)


def _days_since(timestamp: str | datetime | None, now: datetime) -> float:
    """Parse a timestamp and return days elapsed since *now*.

    SQLite may return either a string or a datetime object depending
    on detect_types settings, so we handle both.
    """
    if timestamp is None:
        return 365.0  # Treat missing timestamps as very old
    try:
        if isinstance(timestamp, datetime):
            dt = timestamp
        else:
            dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        return max(delta.total_seconds() / 86400.0, 0.0)
    except (ValueError, TypeError):
        return 365.0


def _score_age(created_at: str | datetime | None, now: datetime) -> float:
    """Age decay signal: newer docs score higher."""
    days = _days_since(created_at, now)
    return _exponential_decay(days, AGE_HALF_LIFE_DAYS)


def _score_view_recency(accessed_at: str | datetime | None, now: datetime) -> float:
    """View recency signal: recently-viewed docs score higher."""
    days = _days_since(accessed_at, now)
    return _exponential_decay(days, VIEW_RECENCY_HALF_LIFE_DAYS)


def _score_link_health(doc_id: int) -> float:
    """Link health signal: fraction of linked docs that are active.

    Returns 1.0 if the document has no links (absence of evidence).
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN d.is_deleted = 0 THEN 1 ELSE 0 END) AS alive
            FROM document_links dl
            JOIN documents d
              ON d.id = CASE
                   WHEN dl.source_doc_id = ? THEN dl.target_doc_id
                   ELSE dl.source_doc_id
                 END
            WHERE dl.source_doc_id = ? OR dl.target_doc_id = ?
            """,
            (doc_id, doc_id, doc_id),
        )
        row = cursor.fetchone()
        if row is None or row["total"] == 0:
            return 1.0  # No links => neutral
        alive: int = row["alive"] or 0
        total: int = row["total"]
        return alive / total


def _score_content_length(content: str) -> float:
    """Content length signal: penalize very short stubs."""
    length = len(content.strip())
    if length >= STUB_THRESHOLD_CHARS:
        return 1.0
    if length == 0:
        return 0.0
    return length / STUB_THRESHOLD_CHARS


def _score_tags(doc_id: int) -> float:
    """Tag signal: boost/penalize based on specific tags.

    Base score is 0.5 (neutral). Boosts and penalties shift the
    score within [0, 1].
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT t.name
            FROM document_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.document_id = ?
            """,
            (doc_id,),
        )
        tag_names = [row["name"] for row in cursor.fetchall()]

    score = 0.5
    for tag in tag_names:
        score += TAG_BOOST.get(tag, 0.0)
        score += TAG_PENALTY.get(tag, 0.0)

    return max(0.0, min(1.0, score))


def _compute_freshness(signals: SignalScores) -> float:
    """Weighted combination of all signals into a single 0-1 score."""
    return (
        WEIGHT_AGE * signals["age_decay"]
        + WEIGHT_VIEW_RECENCY * signals["view_recency"]
        + WEIGHT_LINK_HEALTH * signals["link_health"]
        + WEIGHT_CONTENT_LENGTH * signals["content_length"]
        + WEIGHT_TAGS * signals["tag_signal"]
    )


# ── Public API ────────────────────────────────────────────────────────────


def analyze_freshness(threshold: float = 0.3, stale_only: bool = False) -> FreshnessReport:
    """Score all non-deleted documents and return a FreshnessReport."""
    now = datetime.now(tz=timezone.utc)

    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, title, content, created_at, accessed_at, is_deleted
            FROM documents
            WHERE is_deleted = 0
            ORDER BY id
            """
        )
        rows = [cast(_DocRow, dict(row)) for row in cursor.fetchall()]

    scores: list[DocFreshnessScore] = []
    for row in rows:
        signals = SignalScores(
            age_decay=_score_age(row["created_at"], now),
            view_recency=_score_view_recency(row["accessed_at"], now),
            link_health=_score_link_health(row["id"]),
            content_length=_score_content_length(row["content"]),
            tag_signal=_score_tags(row["id"]),
        )
        freshness = round(_compute_freshness(signals), 4)

        if stale_only and freshness >= threshold:
            continue

        scores.append(
            DocFreshnessScore(
                id=row["id"],
                title=row["title"],
                freshness=freshness,
                signals=signals,
            )
        )

    # Sort by freshness ascending (stalest first)
    scores.sort(key=lambda s: s["freshness"])

    stale_count = sum(1 for s in scores if s["freshness"] < threshold)

    return FreshnessReport(
        total_documents=len(rows),
        scored_documents=len(scores),
        stale_count=stale_count,
        threshold=threshold,
        scores=scores,
    )


# ── Formatting ────────────────────────────────────────────────────────────


def _freshness_label(score: float) -> str:
    """Human-readable label for a freshness score."""
    if score >= 0.7:
        return "fresh"
    if score >= 0.3:
        return "aging"
    return "stale"


def _format_plain(report: FreshnessReport) -> str:
    """Format freshness report as plain text table."""
    lines: list[str] = []

    if not report["scores"]:
        if report["total_documents"] == 0:
            return "No documents found in the knowledge base."
        return "No stale documents found — everything looks fresh!"

    lines.append(
        f"Freshness Report  "
        f"(threshold: {report['threshold']:.1f}, "
        f"stale: {report['stale_count']}/{report['total_documents']})"
    )
    lines.append("=" * 72)

    # Header
    lines.append(
        f"{'ID':>5}  {'Score':>6}  {'Status':>6}  "
        f"{'Age':>5} {'View':>5} {'Link':>5} {'Len':>5} {'Tag':>5}  "
        f"Title"
    )
    lines.append("-" * 72)

    for entry in report["scores"]:
        sig = entry["signals"]
        title = entry["title"]
        if len(title) > 30:
            title = title[:27] + "..."
        label = _freshness_label(entry["freshness"])
        lines.append(
            f"{entry['id']:>5}  "
            f"{entry['freshness']:>6.3f}  "
            f"{label:>6}  "
            f"{sig['age_decay']:>5.2f} "
            f"{sig['view_recency']:>5.2f} "
            f"{sig['link_health']:>5.2f} "
            f"{sig['content_length']:>5.2f} "
            f"{sig['tag_signal']:>5.2f}  "
            f"{title}"
        )

    return "\n".join(lines)


def _format_json(report: FreshnessReport) -> str:
    """Format freshness report as JSON."""
    return json.dumps(report, indent=2, default=str)


def run_freshness(
    threshold: float = 0.3,
    stale_only: bool = False,
    json_output: bool = False,
) -> None:
    """Run freshness analysis and print results."""
    report = analyze_freshness(threshold=threshold, stale_only=stale_only)

    if json_output:
        print(_format_json(report))
    else:
        print(_format_plain(report))
