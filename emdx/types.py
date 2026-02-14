"""Type definitions for EMDX.

This module contains TypedDict definitions and type aliases used throughout
the codebase for better type safety and documentation.
"""

from datetime import datetime
from typing import TypedDict


class ProcessHealthInfo(TypedDict):
    """Health check result for an execution process."""

    execution_id: int
    is_zombie: bool
    is_running: bool
    process_exists: bool
    is_stale: bool
    reason: str | None


class CleanupAction(TypedDict, total=False):
    """Action taken or proposed during cleanup operations."""

    execution_id: int
    doc_title: str
    action: str
    reason: str
    details: str | None
    completed: bool
    pid: int
    error: str


class ExecutionMetrics(TypedDict):
    """Metrics about executions."""

    total_executions: int
    status_breakdown: dict[str, int]
    recent_24h: dict[str, int]
    currently_running: int
    unhealthy_running: int
    average_duration_minutes: float
    failure_rate_percent: float
    metrics_timestamp: str


class PipelineActivityItem(TypedDict):
    """Activity item from a cascade pipeline."""

    exec_id: int
    input_id: int | None
    input_title: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    log_file: str | None
    output_id: int | None
    output_title: str | None
    output_stage: str | None
    from_stage: str


class ChildDocInfo(TypedDict):
    """Information about a child document."""

    id: int
    title: str
    stage: str | None
