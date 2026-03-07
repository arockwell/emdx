"""Search result domain model for emdx.

Wraps a Document with search-specific metadata (snippet, rank).
Supports the same dict-compat interface as Document.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .document import Document


@dataclass(slots=True)
class SearchHit:
    """A search result: a Document plus search metadata.

    Supports ``hit["title"]`` bracket access for backward compatibility
    with code that consumed SearchResult TypedDicts.
    """

    doc: Document
    snippet: str | None = None
    rank: float = 0.0

    # ── Attribute forwarding ──────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the inner Document."""
        try:
            return getattr(self.doc, name)
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from None

    # ── Dict-compatibility layer ──────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        """Access document fields or search metadata via bracket notation."""
        if key == "snippet":
            return self.snippet
        if key == "rank":
            return self.rank
        return self.doc[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-compat .get() that checks search fields then document fields."""
        if key == "snippet":
            return self.snippet
        if key == "rank":
            return self.rank
        return self.doc.get(key, default)

    def __contains__(self, key: object) -> bool:
        if key in ("snippet", "rank"):
            return True
        return key in self.doc

    def keys(self) -> list[str]:
        return self.doc.keys() + ["snippet", "rank"]

    def items(self) -> Iterator[tuple[str, Any]]:
        yield from self.doc.items()
        yield "snippet", self.snippet
        yield "rank", self.rank

    def values(self) -> Iterator[Any]:
        yield from self.doc.values()
        yield self.snippet
        yield self.rank

    # ── Factory ───────────────────────────────────────────────────────

    @classmethod
    def from_row(cls, row: sqlite3.Row | dict[str, Any]) -> SearchHit:
        """Construct from a search query row.

        Expects document fields plus ``snippet`` and ``rank`` columns.
        """
        if isinstance(row, sqlite3.Row):
            raw = dict(row)
        else:
            raw = dict(row)

        snippet = raw.pop("snippet", None)
        rank_val = raw.pop("rank", 0.0)
        rank = float(rank_val) if rank_val is not None else 0.0

        doc = Document.from_row(raw)
        return cls(doc=doc, snippet=snippet, rank=rank)

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Convert to plain dict for JSON serialization."""
        result = self.doc.to_dict()
        result["snippet"] = self.snippet
        result["rank"] = self.rank
        return result
