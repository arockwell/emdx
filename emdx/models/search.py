"""Search result domain model for emdx.

Wraps a Document with search-specific metadata (snippet, rank).
Forwards attribute access to the inner Document via __getattr__.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .document import Document


@dataclass(slots=True)
class SearchHit:
    """A search result: a Document plus search metadata.

    Access document fields via attributes: ``hit.title``, ``hit.id``.
    Attribute access is forwarded to the inner Document via __getattr__.
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
