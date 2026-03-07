"""Task domain model for emdx.

Single source of truth for the Task type. Replaces the scattered
TypedDict projections (TaskDict, EpicTaskDict, EpicViewDict,
TaskLogEntryDict) with proper dataclasses that support:

- Factory construction from sqlite3.Row with datetime parsing
- Backward-compatible bracket access (task["title"]) for incremental migration
- Serialization to dict for JSON output
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any

from ..utils.datetime_utils import parse_datetime

# Fields that store datetime values and should be parsed from SQLite strings.
_TASK_DATETIME_FIELDS: frozenset[str] = frozenset({"created_at", "updated_at", "completed_at"})


@dataclass(slots=True)
class Task:
    """Core task domain object.

    Constructed via ``Task.from_row()`` at the database boundary.
    Supports ``task["field"]`` and ``task.get("field")`` for backward
    compatibility with code that previously used TypedDict dicts.
    """

    id: int
    title: str
    description: str | None = None
    status: str = "open"
    priority: int = 5
    gameplan_id: int | None = None
    project: str | None = None
    current_step: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    type: str = "single"
    source_doc_id: int | None = None
    output_doc_id: int | None = None
    parent_task_id: int | None = None
    epic_key: str | None = None
    epic_seq: int | None = None

    # Epic-specific fields (populated by epic queries, default to 0)
    child_count: int = 0
    children_open: int = 0
    children_done: int = 0

    # Children list (populated by get_epic_view, default empty)
    children: list[Task] = field(default_factory=list)

    # ── Dict-compatibility layer ──────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        """Allow ``task["title"]`` access for backward compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key: str, default: Any = None) -> Any:
        """Allow ``task.get("title", "Untitled")`` for backward compatibility."""
        return getattr(self, key, default)

    def __contains__(self, key: object) -> bool:
        """Allow ``"title" in task`` checks."""
        if not isinstance(key, str):
            return False
        return key in self._field_names()

    def keys(self) -> list[str]:
        """Return field names, for code that iterates dict keys."""
        return list(self._field_names())

    def items(self) -> Iterator[tuple[str, Any]]:
        """Yield (field_name, value) pairs, for dict-like iteration."""
        for name in self._field_names():
            yield name, getattr(self, name)

    def values(self) -> Iterator[Any]:
        """Yield field values, for dict-like iteration."""
        for name in self._field_names():
            yield getattr(self, name)

    @classmethod
    def _field_names(cls) -> frozenset[str]:
        """Cached set of field names for this dataclass."""
        cache_attr = "_cached_field_names"
        cached: frozenset[str] | None = cls.__dict__.get(cache_attr)
        if cached is not None:
            return cached
        names = frozenset(f.name for f in fields(cls))
        type.__setattr__(cls, cache_attr, names)
        return names

    # ── Factory methods ───────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> Task:
        """Construct a Task from a full database row.

        Parses datetime string fields into ``datetime`` objects using
        the centralized ``parse_datetime`` utility. Unknown columns in
        the row are silently ignored (safe for SELECT * with extra cols).
        """
        if isinstance(row, sqlite3.Row):
            raw = dict(row)
        else:
            raw = dict(row)  # defensive copy

        return cls._from_dict(raw)

    @classmethod
    def from_partial_row(cls, row: sqlite3.Row | dict[str, Any]) -> Task:
        """Construct a Task from a partial SELECT.

        Missing fields get their dataclass defaults. Functionally
        identical to ``from_row`` — both tolerate missing columns —
        but the separate name signals intent to callers.
        """
        return cls.from_row(row)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> Task:
        """Internal: build a Task from a raw dict, parsing datetimes."""
        known = cls._field_names()
        kwargs: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key in _TASK_DATETIME_FIELDS and isinstance(value, str):
                kwargs[key] = parse_datetime(value)
            elif key == "children" and isinstance(value, list):
                # Recursively convert child dicts to Task objects
                kwargs[key] = [
                    cls.from_row(c) if isinstance(c, (dict, sqlite3.Row)) else c for c in value
                ]
            else:
                kwargs[key] = value
        return cls(**kwargs)

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization.

        Datetime fields are formatted as ISO 8601 strings.
        Children are recursively serialized.
        """
        result = asdict(self)
        for key in _TASK_DATETIME_FIELDS:
            val = result.get(key)
            if isinstance(val, datetime):
                result[key] = val.isoformat()
        # Recursively serialize children
        if result.get("children"):
            result["children"] = [c.to_dict() if isinstance(c, Task) else c for c in self.children]
        return result


# Fields that store datetime values for TaskLogEntry
_LOG_DATETIME_FIELDS: frozenset[str] = frozenset({"created_at"})


@dataclass(slots=True)
class TaskLogEntry:
    """A single entry in a task's work log."""

    id: int
    task_id: int
    message: str
    created_at: datetime | None = None

    # ── Dict-compatibility layer ──────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        """Allow ``entry["message"]`` access for backward compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def get(self, key: str, default: Any = None) -> Any:
        """Allow ``entry.get("created_at")`` for backward compatibility."""
        return getattr(self, key, default)

    def __contains__(self, key: object) -> bool:
        """Allow ``"message" in entry`` checks."""
        if not isinstance(key, str):
            return False
        return key in self._field_names()

    def keys(self) -> list[str]:
        """Return field names, for code that iterates dict keys."""
        return list(self._field_names())

    def items(self) -> Iterator[tuple[str, Any]]:
        """Yield (field_name, value) pairs, for dict-like iteration."""
        for name in self._field_names():
            yield name, getattr(self, name)

    def values(self) -> Iterator[Any]:
        """Yield field values, for dict-like iteration."""
        for name in self._field_names():
            yield getattr(self, name)

    @classmethod
    def _field_names(cls) -> frozenset[str]:
        """Cached set of field names for this dataclass."""
        cache_attr = "_cached_field_names"
        cached: frozenset[str] | None = cls.__dict__.get(cache_attr)
        if cached is not None:
            return cached
        names = frozenset(f.name for f in fields(cls))
        type.__setattr__(cls, cache_attr, names)
        return names

    # ── Factory methods ───────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> TaskLogEntry:
        """Construct a TaskLogEntry from a database row."""
        if isinstance(row, sqlite3.Row):
            raw = dict(row)
        else:
            raw = dict(row)  # defensive copy

        known = cls._field_names()
        kwargs: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key in _LOG_DATETIME_FIELDS and isinstance(value, str):
                kwargs[key] = parse_datetime(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)

    @classmethod
    def from_partial_row(cls, row: sqlite3.Row | dict[str, Any]) -> TaskLogEntry:
        """Alias for from_row — both tolerate missing columns."""
        return cls.from_row(row)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization."""
        result = asdict(self)
        for key in _LOG_DATETIME_FIELDS:
            val = result.get(key)
            if isinstance(val, datetime):
                result[key] = val.isoformat()
        return result
