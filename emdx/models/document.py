"""Document domain model for emdx.

Single source of truth for the Document type. Replaces the scattered
TypedDict projections (DocumentRow, DocumentListItem, RecentDocumentItem,
etc.) with a proper dataclass that supports:

- Factory construction from sqlite3.Row with datetime parsing
- Attribute access (doc.title, doc.id)
- Serialization to dict for JSON output
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

from ..utils.datetime_utils import parse_datetime

# Fields that store datetime values and should be parsed from SQLite strings.
_DATETIME_FIELDS: frozenset[str] = frozenset(
    {"created_at", "updated_at", "accessed_at", "deleted_at", "archived_at"}
)


@dataclass(slots=True)
class Document:
    """Core document domain object.

    Constructed via ``Document.from_row()`` at the database boundary.
    Access fields via attributes: ``doc.title``, ``doc.id``.
    """

    id: int
    title: str
    content: str = ""
    project: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    accessed_at: datetime | None = None
    access_count: int = 0
    deleted_at: datetime | None = None
    is_deleted: bool = False
    parent_id: int | None = None
    relationship: str | None = None
    archived_at: datetime | None = None
    stage: str | None = None
    doc_type: str = "user"

    # ── Factory methods ───────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> Document:
        """Construct a Document from a full database row.

        Parses datetime string fields into ``datetime`` objects using
        the centralized ``parse_datetime`` utility. Unknown columns in
        the row are silently ignored (safe for SELECT * with extra cols).

        The ``is_deleted`` field is normalized to ``bool`` (SQLite stores
        it as 0/1 integer).
        """
        if isinstance(row, sqlite3.Row):
            raw = dict(row)
        else:
            raw = dict(row)  # defensive copy

        return cls._from_dict(raw)

    @classmethod
    def from_partial_row(cls, row: sqlite3.Row | dict[str, Any]) -> Document:
        """Construct a Document from a partial SELECT.

        Missing fields get their dataclass defaults (empty string for
        content, None for optional fields, 0 for counts, etc.).
        Functionally identical to ``from_row`` — both tolerate missing
        columns — but the separate name signals intent to callers.
        """
        return cls.from_row(row)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> Document:
        """Internal: build a Document from a raw dict, parsing datetimes."""
        known = frozenset(f.name for f in fields(cls))
        kwargs: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key in _DATETIME_FIELDS and isinstance(value, str):
                kwargs[key] = parse_datetime(value)
            elif key == "is_deleted":
                # SQLite stores boolean as 0/1 int
                kwargs[key] = bool(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization.

        Datetime fields are formatted as ISO 8601 strings.
        """
        result = asdict(self)
        for key in _DATETIME_FIELDS:
            val = result.get(key)
            if isinstance(val, datetime):
                result[key] = val.isoformat()
        return result
