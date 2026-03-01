"""TypedDict definitions for the commands layer."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ..services.types import HealthStats

# ── Prime command types ────────────────────────────────────────────────


class EpicInfo(TypedDict):
    """Epic info returned by _get_active_epics() in prime.py."""

    id: int
    title: str
    status: str
    epic_key: str | None
    child_count: int
    children_done: int


class ReadyTask(TypedDict):
    """Ready task returned by _get_ready_tasks() in prime.py."""

    id: int
    title: str
    description: str | None
    priority: int
    status: str
    source_doc_id: int | None
    epic_key: str | None
    epic_seq: int | None


class InProgressTask(TypedDict):
    """In-progress task returned by _get_in_progress_tasks() in prime.py."""

    id: int
    title: str
    description: str | None
    priority: int
    epic_key: str | None
    epic_seq: int | None


class RecentDoc(TypedDict):
    """Recent document returned by _get_recent_docs() in prime.py."""

    id: int
    title: str
    project: str | None


class SmartRecentDoc(TypedDict):
    """Recent doc with timestamps/counts for --smart mode."""

    id: int
    title: str
    accessed_at: str
    access_count: int
    relative_time: str


class KeyDoc(TypedDict):
    """Key document returned by _get_key_docs() in prime.py."""

    id: int
    title: str
    access_count: int


class TagCount(TypedDict):
    """Tag with document count for knowledge map."""

    name: str
    count: int


class GitContextPR(TypedDict):
    """PR info in git context."""

    number: int
    title: str
    headRefName: str


class GitContext(TypedDict):
    """Git context returned by _get_git_context() in prime.py."""

    branch: str | None
    commits: list[str]
    prs: list[GitContextPR]
    error: str | None


class ExecutionMethod(TypedDict):
    """Execution method info for JSON output in prime.py."""

    command: str
    usage: str
    when: str
    key_flags: list[str]


class StaleDoc(TypedDict):
    """Stale document in prime output."""

    id: int
    title: str
    level: str
    days_stale: int


class WikiPrimeStatus(TypedDict):
    """Wiki status summary for prime output."""

    total_topics: int
    articles_generated: int
    stale_articles: int


class PrimeOutput(TypedDict, total=False):
    """Full prime output structure for JSON mode."""

    project: str | None
    timestamp: str
    active_epics: list[EpicInfo]
    ready_tasks: list[ReadyTask]
    in_progress_tasks: list[InProgressTask]
    git_context: GitContext
    wiki_status: WikiPrimeStatus | None
    # verbose fields (optional)
    execution_methods: list[ExecutionMethod]
    recent_docs: list[RecentDoc]
    key_docs: list[KeyDoc]
    stale_docs: list[StaleDoc]
    # smart fields (optional)
    smart_recent: list[SmartRecentDoc]
    tag_map: list[TagCount]


# ── Status command types (health) ─────────────────────────────────────


class HealthMetricData(TypedDict):
    """Health metric data for JSON output in status --health."""

    name: str
    value: float
    score: float
    weight: float
    status: str
    details: str
    recommendations: list[str]


class HealthData(TypedDict, total=False):
    """Health analysis data from status --health --json."""

    overall_score: float
    overall_status: str
    metrics: dict[str, HealthMetricData]
    statistics: HealthStats
    timestamp: str
    error: str  # only on error


# ── Status command types (vitals) ─────────────────────────────────────


class ProjectCount(TypedDict):
    """Document count per project."""

    project: str
    count: int


class WeeklyGrowth(TypedDict):
    """Weekly document growth rate."""

    week: str
    count: int


class AccessBucket(TypedDict):
    """Access frequency distribution bucket."""

    range: str
    count: int


class TaskStats(TypedDict):
    """Task status summary."""

    open: int
    done: int
    total: int


class VitalsData(TypedDict):
    """Data returned by --vitals flag."""

    total_docs: int
    by_project: list[ProjectCount]
    growth_per_week: list[WeeklyGrowth]
    embedding_coverage_pct: float
    access_distribution: list[AccessBucket]
    tag_coverage_pct: float
    tasks: TaskStats


# ── Status command types (mirror) ─────────────────────────────────────


class TagShare(TypedDict):
    """Tag with its share of documents."""

    tag: str
    count: int
    pct: float


class WeeklyActivity(TypedDict):
    """Weekly document creation activity."""

    week: str
    count: int


class ProjectBalance(TypedDict):
    """Document count per project for mirror."""

    project: str
    count: int


class StalenessBreakdown(TypedDict):
    """Percentage of docs not accessed in N days."""

    over_30_days_pct: float
    over_60_days_pct: float
    over_90_days_pct: float


class MirrorData(TypedDict):
    """Data returned by --mirror flag."""

    total_docs: int
    top_tags: list[TagShare]
    weekly_activity: list[WeeklyActivity]
    temporal_pattern: str
    project_balance: list[ProjectBalance]
    staleness: StalenessBreakdown


# ── Delegate command types ─────────────────────────────────────────────
