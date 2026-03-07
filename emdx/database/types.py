"""TypedDict definitions for the database layer.

Document-related types have been replaced by the Document dataclass
in emdx.models.document. Remaining types here are for non-document
database structures (stats, links, wiki, standing queries).
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

# ── Stats types ───────────────────────────────────────────────────────


class MostViewedDoc(TypedDict):
    """Most viewed document summary."""

    id: int
    title: str
    access_count: int


class DatabaseStats(TypedDict, total=False):
    """Statistics returned by get_stats."""

    total_documents: int
    total_projects: int
    total_views: int
    avg_views: float
    newest_doc: str | None
    last_accessed: str | None
    table_size: str
    most_viewed: MostViewedDoc


# ── Document link types ───────────────────────────────────────────────


class DocumentLinkDetail(TypedDict):
    """A document link with joined document titles for display."""

    id: int
    source_doc_id: int
    source_title: str
    target_doc_id: int
    target_title: str
    similarity_score: float
    created_at: str | None
    link_type: str


# ── Wiki types ────────────────────────────────────────────────────────


class WikiArticleTimingDict(TypedDict):
    """Step-level timing (milliseconds) for wiki article generation.

    Values are floats rounded to 2 decimal places so that sub-millisecond
    phases (route, outline, validate) are not truncated to 0.
    """

    prepare_ms: float
    route_ms: float
    outline_ms: float
    write_ms: float
    validate_ms: float
    save_ms: float


# ── Standing query types ──────────────────────────────────────────────


class StandingQueryRow(TypedDict):
    """Row from the standing_queries table."""

    id: int
    query: str
    tags: str | None
    project: str | None
    created_at: datetime | None
    last_checked_at: datetime | None
    notify_count: int


class StandingQueryMatch(TypedDict):
    """A new document matching a standing query."""

    query_id: int
    query: str
    doc_id: int
    doc_title: str
    doc_created_at: str | None
