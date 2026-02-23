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


class KeyDoc(TypedDict):
    """Key document returned by _get_key_docs() in prime.py."""

    id: int
    title: str
    access_count: int


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


class PrimeOutput(TypedDict, total=False):
    """Full prime output structure for JSON mode."""

    project: str | None
    timestamp: str
    active_epics: list[EpicInfo]
    ready_tasks: list[ReadyTask]
    in_progress_tasks: list[InProgressTask]
    git_context: GitContext
    # verbose fields (optional)
    execution_methods: list[ExecutionMethod]
    recent_docs: list[RecentDoc]
    key_docs: list[KeyDoc]
    stale_docs: list[StaleDoc]


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


# ── Delegate command types ─────────────────────────────────────────────


class CreateTaskParams(TypedDict, total=False):
    """Parameters for create_task() in delegate.py.

    All fields are optional since different callers use different subsets.
    """

    title: str
    description: str
    priority: int
    gameplan_id: int | None
    project: str | None
    depends_on: list[int] | None
    prompt: str | None
    task_type: str
    execution_id: int | None
    output_doc_id: int | None
    source_doc_id: int | None
    parent_task_id: int | None
    seq: int | None
    retry_of: int | None
    tags: str | None
    status: str
    epic_key: str | None


class UpdateTaskParams(TypedDict, total=False):
    """Parameters for update_task() in delegate.py.

    These match the ALLOWED_UPDATE_COLUMNS in models/tasks.py.
    """

    title: str
    description: str
    priority: int
    status: str
    error: str | None
    gameplan_id: int | None
    project: str | None
    prompt: str | None
    type: str
    execution_id: int | None
    output_doc_id: int | None
    source_doc_id: int | None
    parent_task_id: int | None
    seq: int | None
    retry_of: int | None
    tags: str | None
    epic_key: str | None
    epic_seq: int | None


class UpdateExecutionParams(TypedDict, total=False):
    """Parameters for update_execution() in delegate.py.

    These match the ALLOWED_EXECUTION_COLUMNS in models/executions.py.
    """

    doc_id: int | None
    doc_title: str
    status: str
    completed_at: str
    log_file: str
    exit_code: int | None
    working_dir: str | None
    pid: int | None
    task_id: int | None
    cost_usd: float | None
    tokens_used: int | None
    input_tokens: int | None
    output_tokens: int | None
    output_text: str | None
