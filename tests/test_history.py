"""Tests for document versioning, history, and diff commands."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from click.exceptions import Exit as ClickExit


@pytest.fixture(autouse=True)
def clean_tables(isolate_test_database: Path) -> Generator[None, None, None]:
    """Clean up tables before each test."""
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_versions")
        conn.execute("DELETE FROM knowledge_events")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()

    yield

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_versions")
        conn.execute("DELETE FROM knowledge_events")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()


class TestVersionSnapshot:
    """Test that update_document creates version snapshots."""

    def test_update_creates_version(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Original content")
        update_document(doc_id, "Test Updated", "New content")

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT version_number, title, content, "
                "content_hash, char_delta, change_source "
                "FROM document_versions "
                "WHERE document_id = ?",
                (doc_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == 1  # version_number
        assert row[1] == "Test"  # old title
        assert row[2] == "Original content"  # old content
        assert row[3] is not None  # content_hash
        assert row[4] == len("New content") - len("Original content")
        assert row[5] == "manual"

    def test_multiple_updates_increment_version(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "v0 content")
        update_document(doc_id, "Test v1", "v1 content")
        update_document(doc_id, "Test v2", "v2 content longer")

        with db_connection.get_connection() as conn:
            rows = conn.execute(
                "SELECT version_number, content "
                "FROM document_versions "
                "WHERE document_id = ? ORDER BY version_number",
                (doc_id,),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == 1
        assert rows[0][1] == "v0 content"
        assert rows[1][0] == 2
        assert rows[1][1] == "v1 content"

    def test_content_hash_is_sha256(self) -> None:
        import hashlib

        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document, update_document

        original = "Hash me please"
        doc_id = save_document("Test", original)
        update_document(doc_id, "Test", "Updated")

        expected_hash = hashlib.sha256(original.encode()).hexdigest()

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT content_hash FROM document_versions WHERE document_id = ?",
                (doc_id,),
            ).fetchone()
        assert row[0] == expected_hash

    def test_char_delta_calculation(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "short")
        update_document(doc_id, "Test", "much longer content here")

        with db_connection.get_connection() as conn:
            row = conn.execute(
                "SELECT char_delta FROM document_versions WHERE document_id = ?",
                (doc_id,),
            ).fetchone()
        expected = len("much longer content here") - len("short")
        assert row[0] == expected


class TestHistoryCommand:
    """Test the emdx history command."""

    def test_history_no_versions(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands.history import history
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")

        history(doc_id=doc_id)
        captured = capsys.readouterr()
        assert "No version history" in captured.out

    def test_history_shows_versions(self) -> None:
        from emdx.commands.history import history
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Original")
        update_document(doc_id, "Test v1", "Updated content")

        # Just verify it doesn't raise -- Rich Table goes to console
        history(doc_id=doc_id)

    def test_history_json_output(self) -> None:
        import io
        import json
        import sys

        from emdx.commands.history import history
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Original")
        update_document(doc_id, "Test v1", "Updated")

        # Capture stdout via StringIO (capsys can miss output when
        # collected alongside modules that import Rich Console).
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            history(doc_id=doc_id, json_output=True)
        finally:
            sys.stdout = old_stdout

        data = json.loads(buf.getvalue())
        assert data["doc_id"] == doc_id
        assert len(data["versions"]) == 1
        assert data["versions"][0]["version"] == 1

    def test_history_nonexistent_doc(self) -> None:
        from emdx.commands.history import history

        with pytest.raises(ClickExit):
            history(doc_id=99999)


class TestDiffCommand:
    """Test the emdx diff command."""

    def test_diff_no_versions(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands.history import diff
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")

        diff(doc_id=doc_id)
        captured = capsys.readouterr()
        assert "No version history" in captured.out

    def test_diff_shows_changes(self) -> None:
        from emdx.commands.history import diff
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "line one\nline two\n")
        update_document(doc_id, "Test", "line one\nline changed\nline three\n")

        # Run with no_color to get plain text output
        diff(doc_id=doc_id, no_color=True)

    def test_diff_specific_version(self) -> None:
        from emdx.commands.history import diff
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "v0")
        update_document(doc_id, "Test", "v1")
        update_document(doc_id, "Test", "v2")

        # Diff against version 1
        diff(doc_id=doc_id, version=1, no_color=True)

    def test_diff_nonexistent_doc(self) -> None:
        from emdx.commands.history import diff

        with pytest.raises(ClickExit):
            diff(doc_id=99999)

    def test_diff_nonexistent_version(self) -> None:
        from emdx.commands.history import diff
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Content")
        update_document(doc_id, "Test", "Updated")

        with pytest.raises(ClickExit):
            diff(doc_id=doc_id, version=999)

    def test_diff_no_changes(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands.history import diff
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Test", "Same content")
        update_document(doc_id, "Test", "Same content")

        diff(doc_id=doc_id, no_color=True)
        captured = capsys.readouterr()
        assert "No differences found" in captured.out
