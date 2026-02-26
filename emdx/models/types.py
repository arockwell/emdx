"""TypedDict definitions for the models layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias, TypedDict

TaskStatus = Literal["open", "active", "blocked", "done", "failed", "wontdo"]

# User-facing task identifier: "42", "#42", or "FEAT-77".
# Resolved to int by resolve_task_id().
TaskRef: TypeAlias = str


class TaskDict(TypedDict):
    id: int
    title: str
    description: str | None
    status: str
    priority: int
    gameplan_id: int | None
    project: str | None
    current_step: str | None
    created_at: str | None
    updated_at: str | None
    completed_at: str | None
    prompt: str | None
    type: str
    execution_id: int | None
    output_doc_id: int | None
    source_doc_id: int | None
    parent_task_id: int | None
    seq: int | None
    retry_of: int | None
    error: str | None
    tags: str | None
    epic_key: str | None
    epic_seq: int | None


class ActiveDelegateTaskDict(TaskDict):
    child_count: int
    children_done: int
    children_active: int


class EpicTaskDict(TaskDict):
    child_count: int
    children_open: int
    children_done: int


class EpicViewDict(TaskDict):
    children: list[TaskDict]


class TaskLogEntryDict(TypedDict):
    id: int
    task_id: int
    message: str
    created_at: str | None


class CategoryDict(TypedDict):
    key: str
    name: str
    description: str
    created_at: str | None


class CategoryWithStatsDict(CategoryDict):
    open_count: int
    done_count: int
    epic_count: int
    total_count: int


class CategoryRenameResultDict(TypedDict):
    tasks_moved: int
    epics_moved: int
    old_category_deleted: bool


class TagStatsDict(TypedDict):
    id: int
    name: str
    count: int
    created_at: datetime | None
    last_used: datetime | None


class TagSearchResultDict(TypedDict):
    id: int
    title: str
    project: str | None
    created_at: str | None
    access_count: int
    tags: str


class ExecutionStatsDict(TypedDict):
    total: int
    recent_24h: int
    running: int
    completed: int
    failed: int
