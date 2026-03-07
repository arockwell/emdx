"""Tests for the Document dataclass domain model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from emdx.models.document import _DATETIME_FIELDS, Document
from emdx.models.search import SearchHit

# ── Construction ──────────────────────────────────────────────────────


class TestDocumentConstruction:
    def test_minimal_construction(self) -> None:
        doc = Document(id=1, title="Hello")
        assert doc.id == 1
        assert doc.title == "Hello"
        assert doc.content == ""
        assert doc.project is None
        assert doc.access_count == 0
        assert doc.is_deleted is False
        assert doc.doc_type == "user"

    def test_full_construction(self) -> None:
        now = datetime.now()
        doc = Document(
            id=42,
            title="Full doc",
            content="body",
            project="emdx",
            created_at=now,
            updated_at=now,
            accessed_at=now,
            access_count=5,
            deleted_at=None,
            is_deleted=False,
            parent_id=10,
            relationship="supersedes",
            archived_at=None,
            stage="draft",
            doc_type="wiki",
        )
        assert doc.id == 42
        assert doc.project == "emdx"
        assert doc.parent_id == 10
        assert doc.stage == "draft"
        assert doc.doc_type == "wiki"


# ── from_row / from_partial_row ───────────────────────────────────────


class TestFromRow:
    def test_from_dict_full_row(self) -> None:
        raw = {
            "id": 1,
            "title": "Test",
            "content": "body",
            "project": "proj",
            "created_at": "2025-01-15 10:30:00",
            "updated_at": "2025-01-16T12:00:00",
            "accessed_at": None,
            "access_count": 3,
            "deleted_at": None,
            "is_deleted": 0,
            "parent_id": None,
            "relationship": None,
            "archived_at": None,
            "stage": None,
            "doc_type": "user",
        }
        doc = Document.from_row(raw)
        assert doc.id == 1
        assert doc.title == "Test"
        assert isinstance(doc.created_at, datetime)
        assert doc.created_at.year == 2025
        assert doc.created_at.month == 1
        assert doc.created_at.day == 15
        assert isinstance(doc.updated_at, datetime)
        assert doc.is_deleted is False

    def test_from_dict_parses_sqlite_datetime(self) -> None:
        raw = {"id": 1, "title": "T", "created_at": "2025-03-07 14:30:00"}
        doc = Document.from_row(raw)
        assert isinstance(doc.created_at, datetime)
        assert doc.created_at.hour == 14

    def test_from_dict_parses_iso_datetime(self) -> None:
        raw = {"id": 1, "title": "T", "created_at": "2025-03-07T14:30:00Z"}
        doc = Document.from_row(raw)
        assert isinstance(doc.created_at, datetime)
        assert doc.created_at.tzinfo == timezone.utc

    def test_from_dict_is_deleted_bool_coercion(self) -> None:
        doc_false = Document.from_row({"id": 1, "title": "T", "is_deleted": 0})
        assert doc_false.is_deleted is False

        doc_true = Document.from_row({"id": 1, "title": "T", "is_deleted": 1})
        assert doc_true.is_deleted is True

    def test_from_dict_ignores_unknown_columns(self) -> None:
        raw = {"id": 1, "title": "T", "some_extra_column": "ignored"}
        doc = Document.from_row(raw)
        assert doc.id == 1
        assert doc.title == "T"

    def test_from_partial_row_fills_defaults(self) -> None:
        raw = {"id": 1, "title": "T"}
        doc = Document.from_partial_row(raw)
        assert doc.content == ""
        assert doc.project is None
        assert doc.access_count == 0
        assert doc.is_deleted is False
        assert doc.doc_type == "user"

    def test_from_row_defensive_copy(self) -> None:
        """from_row should not mutate the input dict."""
        raw = {"id": 1, "title": "T", "created_at": "2025-01-01 00:00:00"}
        original_val = raw["created_at"]
        Document.from_row(raw)
        assert raw["created_at"] == original_val

    def test_from_dict_datetime_already_parsed(self) -> None:
        """If a datetime field is already a datetime object, pass through."""
        now = datetime.now()
        raw = {"id": 1, "title": "T", "created_at": now}
        doc = Document.from_row(raw)
        assert doc.created_at is now


# ── Dict compatibility ────────────────────────────────────────────────


class TestDictCompat:
    @pytest.fixture()
    def doc(self) -> Document:
        return Document(
            id=42,
            title="My Doc",
            content="body",
            project="emdx",
            access_count=5,
        )

    def test_getitem(self, doc: Document) -> None:
        assert doc["id"] == 42
        assert doc["title"] == "My Doc"
        assert doc["content"] == "body"
        assert doc["project"] == "emdx"

    def test_getitem_raises_keyerror(self, doc: Document) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            doc["nonexistent"]

    def test_get_with_default(self, doc: Document) -> None:
        assert doc.get("title") == "My Doc"
        assert doc.get("nonexistent") is None
        assert doc.get("nonexistent", "fallback") == "fallback"

    def test_contains(self, doc: Document) -> None:
        assert "title" in doc
        assert "id" in doc
        assert "nonexistent" not in doc
        assert 42 not in doc  # type: ignore[operator]  # non-string

    def test_keys(self, doc: Document) -> None:
        k = doc.keys()
        assert "id" in k
        assert "title" in k
        assert "content" in k
        assert "doc_type" in k
        assert len(k) == 15  # all fields

    def test_items(self, doc: Document) -> None:
        pairs = dict(doc.items())
        assert pairs["id"] == 42
        assert pairs["title"] == "My Doc"
        assert pairs["project"] == "emdx"
        assert pairs["access_count"] == 5

    def test_values(self, doc: Document) -> None:
        vals = list(doc.values())
        assert 42 in vals
        assert "My Doc" in vals


# ── Serialization ─────────────────────────────────────────────────────


class TestSerialization:
    def test_to_dict_basic(self) -> None:
        doc = Document(id=1, title="T", content="body", project="p")
        d = doc.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == 1
        assert d["title"] == "T"
        assert d["project"] == "p"

    def test_to_dict_serializes_datetimes(self) -> None:
        now = datetime(2025, 3, 7, 14, 30, 0)
        doc = Document(id=1, title="T", created_at=now, updated_at=now)
        d = doc.to_dict()
        assert d["created_at"] == "2025-03-07T14:30:00"
        assert d["updated_at"] == "2025-03-07T14:30:00"

    def test_to_dict_none_datetimes(self) -> None:
        doc = Document(id=1, title="T")
        d = doc.to_dict()
        assert d["created_at"] is None
        assert d["updated_at"] is None

    def test_roundtrip_dict(self) -> None:
        """from_row(to_dict()) should produce an equivalent Document."""
        now = datetime(2025, 3, 7, 14, 30, 0)
        original = Document(
            id=1,
            title="Roundtrip",
            content="body",
            project="p",
            created_at=now,
            access_count=5,
            doc_type="wiki",
        )
        rebuilt = Document.from_row(original.to_dict())
        assert rebuilt.id == original.id
        assert rebuilt.title == original.title
        assert rebuilt.created_at == original.created_at
        assert rebuilt.access_count == original.access_count
        assert rebuilt.doc_type == original.doc_type


# ── SearchHit ─────────────────────────────────────────────────────────


class TestSearchHit:
    def test_from_row(self) -> None:
        raw = {
            "id": 1,
            "title": "Found",
            "project": "p",
            "created_at": "2025-01-01 00:00:00",
            "updated_at": None,
            "snippet": "...match...",
            "rank": -2.5,
            "doc_type": "user",
        }
        hit = SearchHit.from_row(raw)
        assert hit.doc.id == 1
        assert hit.doc.title == "Found"
        assert hit.snippet == "...match..."
        assert hit.rank == -2.5

    def test_bracket_access_document_fields(self) -> None:
        doc = Document(id=1, title="T")
        hit = SearchHit(doc=doc, snippet="snip", rank=-1.0)
        assert hit["id"] == 1
        assert hit["title"] == "T"
        assert hit["snippet"] == "snip"
        assert hit["rank"] == -1.0

    def test_get_fallthrough(self) -> None:
        doc = Document(id=1, title="T", project="p")
        hit = SearchHit(doc=doc)
        assert hit.get("project") == "p"
        assert hit.get("snippet") is None
        assert hit.get("nonexistent", "fb") == "fb"

    def test_contains(self) -> None:
        doc = Document(id=1, title="T")
        hit = SearchHit(doc=doc)
        assert "title" in hit
        assert "snippet" in hit
        assert "rank" in hit
        assert "nonexistent" not in hit

    def test_keys_includes_search_fields(self) -> None:
        doc = Document(id=1, title="T")
        hit = SearchHit(doc=doc)
        k = hit.keys()
        assert "snippet" in k
        assert "rank" in k
        assert "id" in k

    def test_to_dict(self) -> None:
        doc = Document(id=1, title="T", project="p")
        hit = SearchHit(doc=doc, snippet="snip", rank=-1.5)
        d = hit.to_dict()
        assert d["id"] == 1
        assert d["title"] == "T"
        assert d["snippet"] == "snip"
        assert d["rank"] == -1.5

    def test_from_row_null_rank(self) -> None:
        raw = {"id": 1, "title": "T", "snippet": None, "rank": None}
        hit = SearchHit.from_row(raw)
        assert hit.rank == 0.0
        assert hit.snippet is None


# ── Edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_datetime_fields_constant(self) -> None:
        """Verify _DATETIME_FIELDS covers the expected fields."""
        assert _DATETIME_FIELDS == {
            "created_at",
            "updated_at",
            "accessed_at",
            "deleted_at",
            "archived_at",
        }

    def test_field_names_cached(self) -> None:
        """_field_names should be cached after first call."""
        names1 = Document._field_names()
        names2 = Document._field_names()
        assert names1 is names2

    def test_slots_prevent_arbitrary_attrs(self) -> None:
        doc = Document(id=1, title="T")
        with pytest.raises(AttributeError):
            doc.arbitrary_thing = "nope"  # type: ignore[attr-defined]
