"""Category domain model for emdx.

Single source of truth for the Category type. Replaces the scattered
TypedDict projections (CategoryDict, CategoryWithStatsDict) with a
proper dataclass that supports:

- Factory construction from sqlite3.Row with datetime parsing
- Serialization to dict for JSON output
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any

from ..utils.datetime_utils import parse_datetime

# Fields that store datetime values and should be parsed from SQLite strings.
_CATEGORY_DATETIME_FIELDS: frozenset[str] = frozenset({"created_at"})


@dataclass(slots=True)
class Category:
    """Core category domain object.

    Constructed via ``Category.from_row()`` at the database boundary.
    """

    key: str
    name: str
    description: str = ""
    created_at: datetime | None = None

    # Stats fields (populated by list_categories query, default to 0)
    open_count: int = 0
    done_count: int = 0
    epic_count: int = 0
    total_count: int = 0

    # ── Factory methods ───────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> Category:
        """Construct a Category from a full database row.

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
    def from_partial_row(cls, row: sqlite3.Row | dict[str, Any]) -> Category:
        """Construct a Category from a partial SELECT.

        Missing fields get their dataclass defaults. Functionally
        identical to ``from_row`` — both tolerate missing columns —
        but the separate name signals intent to callers.
        """
        return cls.from_row(row)

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> Category:
        """Internal: build a Category from a raw dict, parsing datetimes."""
        known = cls._field_names()
        kwargs: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known:
                continue
            if key in _CATEGORY_DATETIME_FIELDS and isinstance(value, str):
                kwargs[key] = parse_datetime(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)

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

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization.

        Datetime fields are formatted as ISO 8601 strings.
        """
        result = asdict(self)
        for key in _CATEGORY_DATETIME_FIELDS:
            val = result.get(key)
            if isinstance(val, datetime):
                result[key] = val.isoformat()
        return result
