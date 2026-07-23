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
        conn.execute("DELETE FROM task_deps")
        conn.execute("DELETE FROM task_log")
        conn.execute("DELETE FROM tasks")
        conn.commit()

    yield

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM knowledge_events")
        conn.execute("DELETE FROM document_versions")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM task_deps")
        conn.execute("DELETE FROM task_log")
        conn.execute("DELETE FROM tasks")
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
        assert "task_create" in EVENT_TYPES
        assert "task_status" in EVENT_TYPES
        assert "task_delete" in EVENT_TYPES


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


def _task_events(event_type: str) -> list[dict[str, object]]:
    """Fetch metadata dicts for all events of the given type."""
    import json

    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        rows = conn.execute(
            "SELECT metadata_json, doc_id FROM knowledge_events WHERE event_type = ?",
            (event_type,),
        ).fetchall()
    result = []
    for row in rows:
        meta = json.loads(row[0]) if row[0] else {}
        meta["_doc_id"] = row[1]
        result.append(meta)
    return result


class TestTaskLifecycleEvents:
    """Task lifecycle changes are recorded to knowledge_events (#1012)."""

    def test_create_task_records_event(self) -> None:
        from emdx.models.tasks import create_task

        task_id = create_task("Test task")

        events = _task_events("task_create")
        matching = [e for e in events if e["task_id"] == task_id]
        assert len(matching) == 1
        assert matching[0]["status"] == "open"
        assert matching[0]["epic_key"] is None
        # doc_id references documents, not tasks — must stay NULL
        assert matching[0]["_doc_id"] is None

    def test_create_task_with_epic_records_epic_key(self) -> None:
        from emdx.models.tasks import create_task

        task_id = create_task("Epic task", epic_key="EVT")

        events = _task_events("task_create")
        matching = [e for e in events if e["task_id"] == task_id]
        assert len(matching) == 1
        assert matching[0]["epic_key"] == "EVT"

    def test_status_change_records_transition(self) -> None:
        from emdx.models.tasks import create_task, update_task

        task_id = create_task("Test task")
        update_task(task_id, status="active")
        update_task(task_id, status="done")

        transitions = [
            (e["old_status"], e["new_status"])
            for e in _task_events("task_status")
            if e["task_id"] == task_id
        ]
        assert transitions == [("open", "active"), ("active", "done")]

    def test_same_status_records_no_event(self) -> None:
        from emdx.models.tasks import create_task, update_task

        task_id = create_task("Test task")
        update_task(task_id, status="open")

        assert [e for e in _task_events("task_status") if e["task_id"] == task_id] == []

    def test_non_status_update_records_no_event(self) -> None:
        from emdx.models.tasks import create_task, update_task

        task_id = create_task("Test task")
        update_task(task_id, title="Renamed")

        assert [e for e in _task_events("task_status") if e["task_id"] == task_id] == []

    def test_update_missing_task_records_no_event(self) -> None:
        from emdx.models.tasks import update_task

        assert update_task(999999, status="done") is False
        assert [e for e in _task_events("task_status") if e["task_id"] == 999999] == []

    def test_delete_task_records_event(self) -> None:
        from emdx.models.tasks import create_task, delete_task

        task_id = create_task("Doomed task")
        assert delete_task(task_id) is True

        events = _task_events("task_delete")
        assert [e for e in events if e["task_id"] == task_id]

    def test_delete_missing_task_records_no_event(self) -> None:
        from emdx.models.tasks import delete_task

        assert delete_task(999999) is False
        assert [e for e in _task_events("task_delete") if e["task_id"] == 999999] == []

    def test_delete_epic_records_event(self) -> None:
        from emdx.models.tasks import create_epic, delete_epic

        epic_id = create_epic("Test epic", "EVT")
        delete_epic(epic_id)

        events = _task_events("task_delete")
        assert [e for e in events if e["task_id"] == epic_id]


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
