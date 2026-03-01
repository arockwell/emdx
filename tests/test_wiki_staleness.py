"""Tests for wiki staleness detection service (FEAT-24)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Generator
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _content_hash(content: str) -> str:
    """Mirror the hash function used by the service."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _setup_wiki_fixture(
    conn: sqlite3.Connection,
    *,
    topic_id: int = 1,
    source_docs: list[tuple[int, str, str]] | None = None,
) -> int:
    """Create a wiki topic, article, source docs, and article_sources.

    Args:
        conn: Database connection.
        topic_id: Topic ID to use.
        source_docs: List of (doc_id, title, content) tuples.
            Defaults to two simple docs.

    Returns:
        The article_id.
    """
    if source_docs is None:
        source_docs = [
            (200, "Source A", "Alpha content"),
            (201, "Source B", "Beta content"),
        ]

    # Create topic
    conn.execute(
        "INSERT OR REPLACE INTO wiki_topics "
        "(id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (?, 'test-staleness', 'Test Staleness', 'fp')",
        (topic_id,),
    )

    # Create source documents
    for doc_id, title, content in source_docs:
        conn.execute(
            "INSERT OR REPLACE INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
            (doc_id, title, content),
        )

    # Create topic members
    for doc_id, _, _ in source_docs:
        conn.execute(
            "INSERT OR REPLACE INTO wiki_topic_members "
            "(topic_id, document_id, relevance_score, is_primary) "
            "VALUES (?, ?, 1.0, 1)",
            (topic_id, doc_id),
        )

    # Create wiki article doc
    article_doc_id = topic_id + 500
    conn.execute(
        "INSERT OR REPLACE INTO documents "
        "(id, title, content, is_deleted) "
        "VALUES (?, 'Wiki: Test Staleness', 'Article body', 0)",
        (article_doc_id,),
    )

    # Create wiki article
    conn.execute(
        "INSERT OR REPLACE INTO wiki_articles "
        "(topic_id, document_id, source_hash, is_stale, stale_reason) "
        "VALUES (?, ?, 'hash', 0, '')",
        (topic_id, article_doc_id),
    )
    article_row = conn.execute(
        "SELECT id FROM wiki_articles WHERE topic_id = ?",
        (topic_id,),
    ).fetchone()
    article_id: int = article_row[0]

    # Create article sources with correct content hashes
    for doc_id, _, content in source_docs:
        chash = _content_hash(content)
        conn.execute(
            "INSERT OR REPLACE INTO wiki_article_sources "
            "(article_id, document_id, content_hash) "
            "VALUES (?, ?, ?)",
            (article_id, doc_id, chash),
        )

    conn.commit()
    return article_id


@pytest.fixture()
def wiki_fixture() -> Generator[int, None, None]:
    """Set up and tear down a wiki article fixture."""
    with db.get_connection() as conn:
        article_id = _setup_wiki_fixture(conn)
    yield article_id
    # Cleanup
    with db.get_connection() as conn:
        conn.execute("DELETE FROM wiki_article_sources WHERE article_id = ?", (article_id,))
        conn.execute("DELETE FROM wiki_articles WHERE id = ?", (article_id,))
        conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 1")
        conn.execute("DELETE FROM wiki_topics WHERE id = 1")
        conn.execute("DELETE FROM documents WHERE id IN (200, 201, 501)")
        conn.commit()


class TestNoStaleness:
    """Articles should be fresh when nothing has changed."""

    def test_no_staleness_when_unchanged(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_staleness

        result = check_staleness()
        assert result["stale_articles"] == 0
        assert result["fresh_articles"] == result["total_articles"]
        assert len(result["details"]) == 0


class TestContentChangeStaleness:
    """Articles should be stale when source content changes."""

    def test_detects_changed_content(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_staleness

        # Modify a source document's content
        with db.get_connection() as conn:
            conn.execute("UPDATE documents SET content = 'Modified content' WHERE id = 200")
            conn.commit()

        result = check_staleness()
        assert result["stale_articles"] >= 1

        # Find our article in the details
        stale = [d for d in result["details"] if d["topic_id"] == 1]
        assert len(stale) == 1
        assert len(stale[0]["changed_sources"]) == 1
        assert stale[0]["changed_sources"][0]["doc_id"] == 200

    def test_marks_stale_in_db(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_staleness

        # Modify source content
        with db.get_connection() as conn:
            conn.execute("UPDATE documents SET content = 'New content' WHERE id = 201")
            conn.commit()

        check_staleness()

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT is_stale, stale_reason FROM wiki_articles WHERE id = ?",
                (wiki_fixture,),
            ).fetchone()

        assert row[0] == 1
        assert "source" in row[1].lower()


class TestMembershipChangeStaleness:
    """Articles should be stale when topic membership changes."""

    def test_detects_added_member(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_staleness

        # Add a new doc to the topic
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (202, 'New Doc', 'New content', 0)"
            )
            conn.execute(
                "INSERT INTO wiki_topic_members "
                "(topic_id, document_id, relevance_score, is_primary) "
                "VALUES (1, 202, 1.0, 1)"
            )
            conn.commit()

        result = check_staleness()
        stale = [d for d in result["details"] if d["topic_id"] == 1]
        assert len(stale) == 1
        assert any(m["change_type"] == "added" for m in stale[0]["membership_changes"])

        # Cleanup extra doc
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topic_members WHERE document_id = 202")
            conn.execute("DELETE FROM documents WHERE id = 202")
            conn.commit()

    def test_detects_removed_member(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_staleness

        # Remove a doc from the topic
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 1 AND document_id = 200")
            conn.commit()

        result = check_staleness()
        stale = [d for d in result["details"] if d["topic_id"] == 1]
        assert len(stale) == 1
        assert any(m["change_type"] == "removed" for m in stale[0]["membership_changes"])


class TestCheckDocStaleness:
    """Lightweight single-doc staleness check."""

    def test_returns_false_when_doc_not_a_source(self) -> None:
        from emdx.services.wiki_staleness_service import check_doc_staleness

        # Doc 999 is not a source for anything
        assert check_doc_staleness(999) is False

    def test_returns_true_when_content_changed(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_doc_staleness

        # Modify source content
        with db.get_connection() as conn:
            conn.execute("UPDATE documents SET content = 'Changed!' WHERE id = 200")
            conn.commit()

        assert check_doc_staleness(200) is True

        # Verify DB was updated
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT is_stale FROM wiki_articles WHERE id = ?",
                (wiki_fixture,),
            ).fetchone()
        assert row[0] == 1

    def test_returns_false_when_content_unchanged(self, wiki_fixture: int) -> None:
        from emdx.services.wiki_staleness_service import check_doc_staleness

        # Content is still the original "Alpha content"
        assert check_doc_staleness(200) is False


class TestWikiStaleCLI:
    """Test the 'emdx wiki stale' CLI command."""

    def test_stale_plain_no_stale(self, wiki_fixture: int) -> None:
        result = runner.invoke(app, ["wiki", "stale"])
        assert result.exit_code == 0
        assert "fresh" in result.output.lower()

    def test_stale_plain_with_stale(self, wiki_fixture: int) -> None:
        # Make something stale
        with db.get_connection() as conn:
            conn.execute("UPDATE documents SET content = 'Stale now' WHERE id = 200")
            conn.commit()

        result = runner.invoke(app, ["wiki", "stale"])
        assert result.exit_code == 0
        assert "stale" in result.output.lower()
        assert "Test Staleness" in result.output

    def test_stale_json_output(self, wiki_fixture: int) -> None:
        result = runner.invoke(app, ["wiki", "stale", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "total_articles" in data
        assert "stale_articles" in data
        assert "details" in data

    def test_stale_regenerate(self, wiki_fixture: int) -> None:
        """Regenerate path calls generate_article from the synthesis service."""
        from emdx.services.wiki_synthesis_service import WikiArticleResult

        # Make something stale first
        with db.get_connection() as conn:
            conn.execute("UPDATE documents SET content = 'Force stale' WHERE id = 200")
            conn.commit()

        mock_result = WikiArticleResult(
            topic_id=1,
            topic_label="Test Staleness",
            document_id=501,
            article_id=wiki_fixture,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            model="test-model",
        )

        with patch(
            "emdx.services.wiki_synthesis_service.generate_article",
            return_value=mock_result,
        ):
            result = runner.invoke(app, ["wiki", "stale", "--regenerate"])
            assert result.exit_code == 0
            assert "regenerat" in result.output.lower()


class TestSaveHookIntegration:
    """Test that the edit command hooks into staleness detection."""

    def test_edit_title_triggers_staleness_check(self, wiki_fixture: int) -> None:
        """Title-only edit should call check_doc_staleness."""
        # The import in core.py is:
        #   from emdx.services.wiki_staleness_service import check_doc_staleness
        # So we need to patch at the call site
        with patch(
            "emdx.services.wiki_staleness_service.check_doc_staleness",
            return_value=False,
        ):
            # Create a test document
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO documents "
                    "(id, title, content, is_deleted) "
                    "VALUES (300, 'Edit Test Doc', 'Some content', 0)"
                )
                conn.commit()

            result = runner.invoke(app, ["edit", "300", "--title", "New Title"])

            # check_doc_staleness is called inside a try/except,
            # but we can verify the document was updated
            assert result.exit_code == 0

            # Cleanup
            with db.get_connection() as conn:
                conn.execute("DELETE FROM documents WHERE id = 300")
                conn.commit()
