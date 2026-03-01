"""Tests for knowledge_events table and event recording."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_events_table(isolate_test_database: Path) -> Generator[None, None, None]:
    """Clean up events and documents tables before each test."""
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM knowledge_events")
        conn.execute("DELETE FROM document_versions")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()

    yield

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM knowledge_events")
        conn.execute("DELETE FROM document_versions")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()


class TestRecordEvent:
    """Test the record_event helper."""

    def test_record_search_event(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.events import record_event

        event_id = record_event("search", query="test query")
        assert event_id is not None
        assert event_id > 0

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT event_type, query, doc_id FROM knowledge_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        assert row[0] == "search"
        assert row[1] == "test query"
        assert row[2] is None

    def test_record_view_event(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.events import record_event

        event_id = record_event("view", doc_id=42)
        assert event_id is not None

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT event_type, doc_id, query FROM knowledge_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        assert row[0] == "view"
        assert row[1] == 42
        assert row[2] is None

    def test_record_create_event(self) -> None:
        from emdx.models.events import record_event

        event_id = record_event("create", doc_id=1)
        assert event_id is not None

    def test_record_update_event(self) -> None:
        from emdx.models.events import record_event

        event_id = record_event("update", doc_id=1)
        assert event_id is not None

    def test_record_event_with_metadata(self) -> None:
        import json

        from emdx.database.connection import db_connection
        from emdx.models.events import record_event

        meta: dict[str, str | int | float | bool | None] = {
            "result_count": 5,
            "mode": "hybrid",
        }
        event_id = record_event("search", query="auth", metadata=meta)
        assert event_id is not None

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM knowledge_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        parsed = json.loads(row[0])
        assert parsed["result_count"] == 5
        assert parsed["mode"] == "hybrid"

    def test_unknown_event_type_returns_none(self) -> None:
        from emdx.models.events import record_event

        result = record_event("unknown_type")
        assert result is None

    def test_event_types_constant(self) -> None:
        from emdx.models.events import EVENT_TYPES

        assert "search" in EVENT_TYPES
        assert "view" in EVENT_TYPES
        assert "create" in EVENT_TYPES
        assert "update" in EVENT_TYPES
        assert "delete" in EVENT_TYPES
        assert "ask" in EVENT_TYPES


class TestSaveDocumentEvent:
    """Test that save_document records a create event."""

    def test_save_records_create_event(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT event_type, doc_id "
                "FROM knowledge_events "
                "WHERE doc_id = ? AND event_type = 'create'",
                (doc_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "create"
        assert row[1] == doc_id


class TestUpdateDocumentEvent:
    """Test that update_document records an update event."""

    def test_update_records_update_event(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Original content")
        update_document(doc_id, "Test Updated", "New content")

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT event_type, doc_id "
                "FROM knowledge_events "
                "WHERE doc_id = ? AND event_type = 'update'",
                (doc_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "update"
        assert row[1] == doc_id
