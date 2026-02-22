"""Tests for wiki topic rename command (emdx maintain wiki rename)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _setup_wiki_topic(
    conn: sqlite3.Connection,
    topic_id: int = 1,
    label: str = "Test Topic",
    slug: str = "test-topic",
    with_article: bool = False,
) -> int | None:
    """Insert a wiki topic and optionally a document + article. Returns doc id if created."""
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (?, ?, ?, 'fp')",
        (topic_id, slug, label),
    )
    doc_id = None
    if with_article:
        doc_id = topic_id + 100
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted) "
            "VALUES (?, ?, 'Article body', 0)",
            (doc_id, f"Wiki: {label}"),
        )
        conn.execute(
            "INSERT INTO wiki_articles (topic_id, document_id, source_hash) VALUES (?, ?, 'hash')",
            (topic_id, doc_id),
        )
    conn.commit()
    return doc_id


def _cleanup_topic(conn: sqlite3.Connection, topic_id: int) -> None:
    """Remove wiki topic and related rows."""
    doc_id = topic_id + 100
    conn.execute("DELETE FROM wiki_articles WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = ?", (topic_id,))
    conn.execute("DELETE FROM wiki_topics WHERE id = ?", (topic_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()


class TestWikiRenameCommand:
    """Test 'emdx maintain wiki rename' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=70, label="Old Name", slug="old-name")
        yield
        with db.get_connection() as conn:
            _cleanup_topic(conn, 70)

    def test_rename_updates_label_and_slug(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "70", "New Name"])
        assert result.exit_code == 0
        assert "Old Name" in result.output
        assert "New Name" in result.output
        assert "old-name" in result.output
        assert "new-name" in result.output

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 70"
            ).fetchone()
            assert row[0] == "New Name"
            assert row[1] == "new-name"

    def test_rename_auto_generates_slug(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "70", "Database Architecture"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            row = conn.execute("SELECT topic_slug FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] == "database-architecture"

    def test_rename_slug_strips_special_chars(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "70", "Auth / OAuth / JWT"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            row = conn.execute("SELECT topic_slug FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] == "auth-oauth-jwt"

    def test_rename_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "999", "Anything"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_rename_shows_old_and_new(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "70", "Brand New"])
        assert result.exit_code == 0
        assert "Old Name" in result.output
        assert "Brand New" in result.output
        assert "Renamed topic 70" in result.output


class TestWikiRenameWithArticle:
    """Test rename also updates the associated wiki document title."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(
                conn,
                topic_id=71,
                label="Old Article",
                slug="old-article",
                with_article=True,
            )
        yield
        with db.get_connection() as conn:
            _cleanup_topic(conn, 71)

    def test_rename_updates_document_title(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rename", "71", "New Article Title"])
        assert result.exit_code == 0
        assert "Document #171 title updated" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT title FROM documents WHERE id = 171").fetchone()
            assert row[0] == "New Article Title"

    def test_rename_without_article_skips_doc_update(self) -> None:
        """Topic without a generated article should still rename cleanly."""
        with db.get_connection() as conn:
            _setup_wiki_topic(
                conn,
                topic_id=72,
                label="No Article",
                slug="no-article",
                with_article=False,
            )
        try:
            result = runner.invoke(app, ["maintain", "wiki", "rename", "72", "Still No Article"])
            assert result.exit_code == 0
            assert "Document #" not in result.output

            with db.get_connection() as conn:
                row = conn.execute("SELECT topic_label FROM wiki_topics WHERE id = 72").fetchone()
                assert row[0] == "Still No Article"
        finally:
            with db.get_connection() as conn:
                _cleanup_topic(conn, 72)


class TestWikiRenameSlugConflict:
    """Test rename rejects duplicate slugs."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=73, label="Topic A", slug="topic-a")
            _setup_wiki_topic(conn, topic_id=74, label="Topic B", slug="topic-b")
        yield
        with db.get_connection() as conn:
            _cleanup_topic(conn, 73)
            _cleanup_topic(conn, 74)

    def test_rename_rejects_conflicting_slug(self) -> None:
        # Try to rename topic 73 to a label that would produce slug "topic-b"
        result = runner.invoke(app, ["maintain", "wiki", "rename", "73", "Topic B"])
        assert result.exit_code == 1
        assert "already in use" in result.output

    def test_rename_allows_same_slug_on_same_topic(self) -> None:
        # Renaming topic 73 to a different label that produces the same slug should work
        result = runner.invoke(app, ["maintain", "wiki", "rename", "73", "TOPIC A!"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 73"
            ).fetchone()
            assert row[0] == "TOPIC A!"
            assert row[1] == "topic-a"
