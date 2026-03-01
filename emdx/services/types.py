"""TypedDict definitions for the services layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ..services.health_monitor import HealthMetric

# ── Health Monitor types ──────────────────────────────────────────────


class HealthStats(TypedDict):
    """Basic statistics about the knowledge base."""

    total_documents: int
    total_projects: int
    total_tags: int
    database_size: int
    database_size_mb: float


class OverallHealthResult(TypedDict):
    """Result from calculate_overall_health()."""

    overall_score: float
    overall_status: str  # 'good' | 'warning' | 'critical'
    metrics: dict[str, HealthMetric]
    statistics: HealthStats
    timestamp: str


# ── Duplicate Detector types ──────────────────────────────────────────


class DuplicateDocument(TypedDict, total=False):
    """A document record used in duplicate detection results."""

    id: int
    title: str
    content: str
    project: str | None
    access_count: int
    created_at: str | None
    updated_at: str | None  # only in find_duplicates
    content_length: int  # only in near-dup / similar-title methods
    tags: str | None  # only in find_duplicates (GROUP_CONCAT)


class MostDuplicated(TypedDict):
    """Info about the most-duplicated content."""

    title: str
    copies: int
    total_views: int


class DuplicateStats(TypedDict):
    """Statistics about duplicates in the knowledge base."""

    duplicate_groups: int
    total_duplicates: int
    space_wasted: int
    most_duplicated: MostDuplicated | None


# ── Document Merger types ─────────────────────────────────────────────


class DocumentMetadata(TypedDict):
    """Metadata for a document used in merge candidate evaluation."""

    title: str
    content: str
    project: str | None
    access_count: int


# ── Backup types ────────────────────────────────────────────────────


class BackupInfo(TypedDict):
    """Info about a single backup file for --json output."""

    filename: str
    path: str
    size_bytes: int
    created_at: str


# ── Wiki Quality types ─────────────────────────────────────────────


class WikiQualityBreakdown(TypedDict):
    """Per-dimension scores from wiki quality analysis."""

    coverage: float
    freshness: float
    coherence: float
    source_density: float


class WikiQualityResult(TypedDict, total=False):
    """Result from score_article() or score_all_articles()."""

    topic_id: int
    topic_label: str
    article_id: int
    document_id: int
    coverage: float
    freshness: float
    coherence: float
    source_density: float
    composite: float
    article_title: str
    error: str  # only present on failure
