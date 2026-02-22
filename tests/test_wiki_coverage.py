"""Tests for the wiki coverage command (emdx maintain wiki coverage)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)


@pytest.fixture
def clean_wiki_db(isolate_test_database: Any) -> Any:
    """Ensure clean database with wiki tables for each test."""

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM wiki_topic_members")
            conn.execute("DELETE FROM wiki_topics")
            conn.execute("DELETE FROM documents")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    db.ensure_schema()
    yield
    cleanup()


def _create_user_doc(doc_id: int, title: str) -> int:
    """Insert a user document and return its ID."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
            "VALUES (?, ?, 'test content', 0, 'user')",
            (doc_id, title),
        )
        conn.commit()
    return doc_id


def _create_wiki_doc(doc_id: int, title: str) -> int:
    """Insert a wiki document (should be excluded from coverage)."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
            "VALUES (?, ?, 'wiki content', 0, 'wiki')",
            (doc_id, title),
        )
        conn.commit()
    return doc_id


def _create_deleted_doc(doc_id: int, title: str) -> int:
    """Insert a deleted document (should be excluded from coverage)."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
            "VALUES (?, ?, 'deleted content', 1, 'user')",
            (doc_id, title),
        )
        conn.commit()
    return doc_id


def _create_topic(topic_id: int, label: str) -> int:
    """Insert a wiki topic."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO wiki_topics (id, topic_slug, topic_label, status) "
            "VALUES (?, ?, ?, 'active')",
            (topic_id, label.lower().replace(" ", "-"), label),
        )
        conn.commit()
    return topic_id


def _add_member(topic_id: int, document_id: int) -> None:
    """Add a document to a topic cluster."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (?, ?)",
            (topic_id, document_id),
        )
        conn.commit()


class TestWikiCoverageEmpty:
    """Tests with empty database."""

    def test_coverage_empty_db(self, clean_wiki_db: Any) -> None:
        """Empty database shows 100% coverage (0/0)."""
        result = runner.invoke(app, ["maintain", "wiki", "coverage"])
        assert result.exit_code == 0
        assert "All user documents are covered" in result.output

    def test_coverage_empty_json(self, clean_wiki_db: Any) -> None:
        """Empty database JSON output has correct structure."""
        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_docs"] == 0
        assert data["covered_docs"] == 0
        assert data["uncovered_docs"] == 0
        assert data["coverage_percent"] == 0
        assert data["uncovered"] == []


class TestWikiCoverageWithDocs:
    """Tests with documents and topics."""

    def test_all_covered(self, clean_wiki_db: Any) -> None:
        """All docs covered shows 100%."""
        _create_user_doc(1, "Doc A")
        _create_user_doc(2, "Doc B")
        _create_topic(1, "Topic 1")
        _add_member(1, 1)
        _add_member(1, 2)

        result = runner.invoke(app, ["maintain", "wiki", "coverage"])
        assert result.exit_code == 0
        assert "All user documents are covered" in result.output

    def test_some_uncovered(self, clean_wiki_db: Any) -> None:
        """Partially covered shows uncovered docs."""
        _create_user_doc(1, "Covered Doc")
        _create_user_doc(2, "Uncovered Doc")
        _create_topic(1, "Topic 1")
        _add_member(1, 1)

        result = runner.invoke(app, ["maintain", "wiki", "coverage"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "Uncovered:        1" in output
        assert "Uncovered Doc" in output

    def test_none_covered(self, clean_wiki_db: Any) -> None:
        """No topics at all shows 0% coverage."""
        _create_user_doc(1, "Doc A")
        _create_user_doc(2, "Doc B")
        _create_user_doc(3, "Doc C")

        result = runner.invoke(app, ["maintain", "wiki", "coverage"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "Uncovered:        3" in output
        assert "0.0%" in output

    def test_excludes_wiki_docs(self, clean_wiki_db: Any) -> None:
        """Wiki-type docs are excluded from coverage count."""
        _create_user_doc(1, "User Doc")
        _create_wiki_doc(2, "Wiki Article")

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_docs"] == 1  # Only user doc counted

    def test_excludes_deleted_docs(self, clean_wiki_db: Any) -> None:
        """Deleted docs are excluded from coverage count."""
        _create_user_doc(1, "Active Doc")
        _create_deleted_doc(2, "Deleted Doc")

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_docs"] == 1  # Only non-deleted counted

    def test_json_output_structure(self, clean_wiki_db: Any) -> None:
        """JSON output has all expected fields."""
        _create_user_doc(1, "Covered Doc")
        _create_user_doc(2, "Uncovered Doc")
        _create_topic(1, "Topic 1")
        _add_member(1, 1)

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["total_docs"] == 2
        assert data["covered_docs"] == 1
        assert data["uncovered_docs"] == 1
        assert data["coverage_percent"] == 50.0
        assert len(data["uncovered"]) == 1
        assert data["uncovered"][0]["id"] == 2
        assert data["uncovered"][0]["title"] == "Uncovered Doc"

    def test_limit_option(self, clean_wiki_db: Any) -> None:
        """--limit restricts number of uncovered docs shown."""
        for i in range(1, 6):
            _create_user_doc(i, f"Doc {i}")

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--limit", "2"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "and 3 more" in output

    def test_limit_json(self, clean_wiki_db: Any) -> None:
        """--limit restricts JSON output too."""
        for i in range(1, 6):
            _create_user_doc(i, f"Doc {i}")

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json", "--limit", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["uncovered_docs"] == 5  # Total count still correct
        assert len(data["uncovered"]) == 2  # But list is limited

    def test_doc_in_multiple_topics_counted_once(self, clean_wiki_db: Any) -> None:
        """A doc in multiple topics is only counted as covered once."""
        _create_user_doc(1, "Multi-topic Doc")
        _create_user_doc(2, "Uncovered Doc")
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _add_member(1, 1)
        _add_member(2, 1)

        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["covered_docs"] == 1
        assert data["uncovered_docs"] == 1


class TestWikiCoverageHelp:
    """Test help output."""

    def test_help(self) -> None:
        """Help text shows expected content."""
        result = runner.invoke(app, ["maintain", "wiki", "coverage", "--help"])
        assert result.exit_code == 0
        assert "coverage" in result.output.lower()
