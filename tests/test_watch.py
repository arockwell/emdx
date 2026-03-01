"""Tests for standing queries (emdx find --watch) feature."""

import json
import time
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_standing_queries_and_docs(
    isolate_test_database: Path,
) -> Generator[None, None, None]:
    """Clean standing_queries and documents tables before/after each test."""
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM standing_queries")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()

    yield

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM standing_queries")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()


# =========================================================================
# CRUD Operations
# =========================================================================


class TestCreateStandingQuery:
    """Test creating standing queries."""

    def test_create_returns_positive_id(self) -> None:
        from emdx.commands._watch import create_standing_query

        sq_id = create_standing_query("test query")
        assert isinstance(sq_id, int)
        assert sq_id > 0

    def test_create_with_tags(self) -> None:
        from emdx.commands._watch import create_standing_query, get_standing_query

        sq_id = create_standing_query("", tags="python,testing")
        sq = get_standing_query(sq_id)
        assert sq is not None
        assert sq["tags"] == "python,testing"

    def test_create_with_project(self) -> None:
        from emdx.commands._watch import create_standing_query, get_standing_query

        sq_id = create_standing_query("auth", project="my-project")
        sq = get_standing_query(sq_id)
        assert sq is not None
        assert sq["project"] == "my-project"

    def test_create_sets_defaults(self) -> None:
        from emdx.commands._watch import create_standing_query, get_standing_query

        sq_id = create_standing_query("test")
        sq = get_standing_query(sq_id)
        assert sq is not None
        assert sq["notify_count"] == 0
        assert sq["created_at"] is not None
        assert sq["last_checked_at"] is not None

    def test_create_multiple(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            list_standing_queries,
        )

        create_standing_query("query one")
        create_standing_query("query two")
        create_standing_query("query three")
        queries = list_standing_queries()
        assert len(queries) == 3


class TestListStandingQueries:
    """Test listing standing queries."""

    def test_list_empty(self) -> None:
        from emdx.commands._watch import list_standing_queries

        queries = list_standing_queries()
        assert queries == []

    def test_list_returns_all(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            list_standing_queries,
        )

        create_standing_query("alpha")
        create_standing_query("beta")
        queries = list_standing_queries()
        assert len(queries) == 2
        query_texts = {sq["query"] for sq in queries}
        assert query_texts == {"alpha", "beta"}

    def test_list_ordered_by_created_desc(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            list_standing_queries,
        )

        create_standing_query("first")
        time.sleep(1.1)  # SQLite CURRENT_TIMESTAMP has 1-second resolution
        create_standing_query("second")
        queries = list_standing_queries()
        # Most recent first (ORDER BY created_at DESC)
        assert queries[0]["query"] == "second"
        assert queries[1]["query"] == "first"


class TestRemoveStandingQuery:
    """Test removing standing queries."""

    def test_remove_existing(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            list_standing_queries,
            remove_standing_query,
        )

        sq_id = create_standing_query("to delete")
        assert remove_standing_query(sq_id) is True
        assert list_standing_queries() == []

    def test_remove_nonexistent(self) -> None:
        from emdx.commands._watch import remove_standing_query

        assert remove_standing_query(999) is False

    def test_remove_only_target(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            list_standing_queries,
            remove_standing_query,
        )

        id1 = create_standing_query("keep")
        id2 = create_standing_query("delete")
        remove_standing_query(id2)
        queries = list_standing_queries()
        assert len(queries) == 1
        assert queries[0]["id"] == id1


class TestGetStandingQuery:
    """Test getting a single standing query."""

    def test_get_existing(self) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            get_standing_query,
        )

        sq_id = create_standing_query("my query", tags="python", project="proj")
        sq = get_standing_query(sq_id)
        assert sq is not None
        assert sq["query"] == "my query"
        assert sq["tags"] == "python"
        assert sq["project"] == "proj"

    def test_get_nonexistent(self) -> None:
        from emdx.commands._watch import get_standing_query

        assert get_standing_query(999) is None


# =========================================================================
# Check for New Matches
# =========================================================================


class TestCheckStandingQueries:
    """Test checking standing queries for new matches."""

    def _save_doc(
        self,
        title: str,
        content: str,
        project: str | None = None,
    ) -> int:
        """Helper to save a document using the real DB."""
        from emdx.database.documents import save_document

        return save_document(title, content, project=project)

    def test_check_no_queries(self) -> None:
        from emdx.commands._watch import check_standing_queries

        matches = check_standing_queries()
        assert matches == []

    def test_check_finds_new_doc_matching_query(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )

        # Create standing query
        create_standing_query("python")

        # Save a document that matches
        self._save_doc("Python Guide", "Learn python programming")

        # Check for new matches
        matches = check_standing_queries()
        assert len(matches) == 1
        assert matches[0]["doc_title"] == "Python Guide"
        assert matches[0]["query"] == "python"

    def test_check_no_match_for_unrelated_doc(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )

        create_standing_query("python")
        self._save_doc("Docker Guide", "Learn docker containers")

        matches = check_standing_queries()
        assert len(matches) == 0

    def test_check_does_not_re_alert(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )

        create_standing_query("python")
        self._save_doc("Python Guide", "Learn python programming")

        # First check finds the match
        matches1 = check_standing_queries()
        assert len(matches1) == 1

        # Second check with no new docs finds nothing
        matches2 = check_standing_queries()
        assert len(matches2) == 0

    def test_check_updates_notify_count(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
            get_standing_query,
        )

        sq_id = create_standing_query("python")
        self._save_doc("Python 1", "Learn python basics")
        self._save_doc("Python 2", "Advanced python topics")

        check_standing_queries()
        sq = get_standing_query(sq_id)
        assert sq is not None
        assert sq["notify_count"] == 2

    def test_check_updates_last_checked(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
            get_standing_query,
        )

        sq_id = create_standing_query("python")
        sq_before = get_standing_query(sq_id)
        assert sq_before is not None

        time.sleep(1.1)
        check_standing_queries()

        sq_after = get_standing_query(sq_id)
        assert sq_after is not None
        # last_checked_at should be updated even with no matches
        assert sq_after["last_checked_at"] != sq_before["last_checked_at"]

    def test_check_with_project_filter(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )

        create_standing_query("python", project="proj-a")
        self._save_doc("Python A", "python in project A", project="proj-a")
        self._save_doc("Python B", "python in project B", project="proj-b")

        matches = check_standing_queries()
        assert len(matches) == 1
        assert matches[0]["doc_title"] == "Python A"

    def test_check_tag_only_query(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )
        from emdx.database.connection import db_connection

        create_standing_query("", tags="urgent")

        doc_id = self._save_doc("Urgent Issue", "Something urgent happened")

        # Add tag directly via SQL
        with db_connection.get_connection() as conn:
            conn.execute(
                "INSERT INTO tags (name, usage_count) VALUES (?, 0)",
                ("urgent",),
            )
            tag_cursor = conn.execute("SELECT id FROM tags WHERE name = ?", ("urgent",))
            tag_id = tag_cursor.fetchone()[0]
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )
            conn.commit()

        matches = check_standing_queries()
        assert len(matches) == 1
        assert matches[0]["doc_title"] == "Urgent Issue"

    def test_check_multiple_queries(self) -> None:
        from emdx.commands._watch import (
            check_standing_queries,
            create_standing_query,
        )

        create_standing_query("python")
        create_standing_query("docker")

        self._save_doc("Python Guide", "Learn python")
        self._save_doc("Docker Guide", "Learn docker")

        matches = check_standing_queries()
        assert len(matches) == 2
        titles = {m["doc_title"] for m in matches}
        assert titles == {"Python Guide", "Docker Guide"}


# =========================================================================
# Display Helpers
# =========================================================================


class TestDisplayStandingQueriesList:
    """Test display_standing_queries_list output."""

    def test_display_empty_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_standing_queries_list

        display_standing_queries_list(json_output=True)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []

    def test_display_empty_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_standing_queries_list

        display_standing_queries_list(json_output=False)
        captured = capsys.readouterr()
        assert "No standing queries" in captured.out

    def test_display_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import (
            create_standing_query,
            display_standing_queries_list,
        )

        create_standing_query("test query", tags="python")
        display_standing_queries_list(json_output=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["query"] == "test query"
        assert data[0]["tags"] == "python"
        assert data[0]["notify_count"] == 0


class TestDisplayCheckResults:
    """Test display_check_results output."""

    def test_display_no_matches_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_check_results

        display_check_results([], json_output=False)
        captured = capsys.readouterr()
        assert "No new matches" in captured.out

    def test_display_no_matches_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_check_results

        display_check_results([], json_output=True)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []

    def test_display_matches_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_check_results
        from emdx.database.types import StandingQueryMatch

        matches = [
            StandingQueryMatch(
                query_id=1,
                query="python",
                doc_id=42,
                doc_title="Python Guide",
                doc_created_at="2025-01-01",
            )
        ]
        display_check_results(matches, json_output=True)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["doc_id"] == 42
        assert data[0]["query"] == "python"

    def test_display_matches_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        from emdx.commands._watch import display_check_results
        from emdx.database.types import StandingQueryMatch

        matches = [
            StandingQueryMatch(
                query_id=1,
                query="python",
                doc_id=42,
                doc_title="Python Guide",
                doc_created_at="2025-01-01",
            )
        ]
        display_check_results(matches, json_output=False)
        captured = capsys.readouterr()
        assert "#42" in captured.out
        assert "Python Guide" in captured.out
        assert "python" in captured.out


# =========================================================================
# Migration
# =========================================================================


class TestStandingQueriesMigration:
    """Test that the standing_queries table is created by migration."""

    def test_table_exists(self) -> None:
        from emdx.database.connection import db_connection

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='standing_queries'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "standing_queries"

    def test_table_has_expected_columns(self) -> None:
        from emdx.database.connection import db_connection

        with db_connection.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(standing_queries)")
            columns = {row[1] for row in cursor.fetchall()}

        expected = {
            "id",
            "query",
            "tags",
            "project",
            "created_at",
            "last_checked_at",
            "notify_count",
        }
        assert expected == columns
