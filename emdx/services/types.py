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


# ── Execution Monitor types ───────────────────────────────────────────


class ProcessHealthStatus(TypedDict):
    """Health status of a single execution's process."""

    execution_id: int
    is_zombie: bool
    is_running: bool
    process_exists: bool
    is_stale: bool
    reason: str | None


class ExecutionMetrics(TypedDict):
    """Aggregate execution metrics."""

    total_executions: int
    status_breakdown: dict[str, int]
    recent_24h: dict[str, int]
    currently_running: int
    unhealthy_running: int
    average_duration_minutes: float
    failure_rate_percent: float
    metrics_timestamp: str


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


# ── Auto-tagger types ────────────────────────────────────────────────


# ── Unified Executor types ────────────────────────────────────────────


class ExecutionResultDict(TypedDict):
    """Dict returned by ExecutionResult.to_dict()."""

    success: bool
    execution_id: int
    log_file: str
    output_doc_id: int | None
    output_content: str | None
    tokens_used: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    execution_time_ms: int
    error_message: str | None
    exit_code: int | None
    cli_tool: str


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
