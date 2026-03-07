"""TypedDict definitions for the models layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias, TypedDict

TaskStatus = Literal["open", "active", "blocked", "done", "failed", "wontdo", "duplicate"]

# User-facing task identifier: "42", "#42", or "FEAT-77".
# Resolved to int by resolve_task_id().
TaskRef: TypeAlias = str


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
