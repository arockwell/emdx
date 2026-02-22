"""Tests for wiki article diff on regeneration (Issue #1251)."""

from __future__ import annotations

import sqlite3
from typing import Any

from emdx.services.wiki_synthesis_service import get_article_diff


def _setup_wiki_tables(conn: sqlite3.Connection) -> None:
    """Ensure wiki tables and a test topic exist."""
    # Insert a test topic
    conn.execute(
        "INSERT OR IGNORE INTO wiki_topics "
        "(id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (1, 'test-topic', 'Test Topic', 'fp1')"
    )
    conn.commit()


def _create_doc(conn: sqlite3.Connection, doc_id: int, title: str, content: str) -> None:
    """Insert a test document."""
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
        (doc_id, title, content),
    )
    conn.commit()


def _create_article(
    conn: sqlite3.Connection,
    article_id: int,
    topic_id: int,
    document_id: int,
    previous_content: str = "",
) -> None:
    """Insert a wiki article row."""
    conn.execute(
        "INSERT INTO wiki_articles "
        "(id, topic_id, document_id, article_type, source_hash, previous_content) "
        "VALUES (?, ?, ?, 'topic_article', 'hash123', ?)",
        (article_id, topic_id, document_id, previous_content),
    )
    conn.commit()


class TestMigration048:
    """Test that migration 048 adds previous_content column."""

    def test_previous_content_column_exists(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(wiki_articles)")
            columns = {row[1] for row in cursor.fetchall()}

        assert "previous_content" in columns

    def test_previous_content_defaults_to_empty(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_wiki_tables(conn)
            _create_doc(conn, 7001, "Test Article", "Article content")
            _create_article(conn, 1, 1, 7001)

            row = conn.execute("SELECT previous_content FROM wiki_articles WHERE id = 1").fetchone()

        assert row is not None
        assert row[0] == ""


class TestSaveArticleStashesContent:
    """Test that _save_article stashes previous content on regeneration."""

    def test_regeneration_stashes_old_content(self, isolate_test_database: Any) -> None:
        from emdx.database import db
        from emdx.services.wiki_synthesis_service import (
            ArticleSource,
            SynthesisOutline,
            _save_article,
        )

        with db.get_connection() as conn:
            # Use unique topic 10 for this test
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (10, 'regen-topic', 'Regen Topic', 'fp10')"
            )
            _create_doc(conn, 7010, "Original Title", "Original content here")
            _create_article(conn, 10, 10, 7010)
            conn.commit()

        outline = SynthesisOutline(
            topic_label="Regen Topic",
            topic_slug="regen-topic",
            suggested_title="Updated Title",
            section_hints=["Overview"],
            entity_focus=["test"],
            strategy="stuff",
        )
        sources = [
            ArticleSource(
                doc_id=7010,
                title="Updated Title",
                content="New content here",
                content_hash="newhash",
                char_count=16,
            )
        ]

        doc_id, article_id = _save_article(
            topic_id=10,
            content="New content here",
            outline=outline,
            sources=sources,
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

        # Verify previous content was stashed
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT previous_content FROM wiki_articles WHERE id = ?",
                (article_id,),
            ).fetchone()

        assert row is not None
        assert row[0] == "Original content here"

    def test_first_generation_has_no_previous(self, isolate_test_database: Any) -> None:
        from emdx.database import db
        from emdx.services.wiki_synthesis_service import (
            ArticleSource,
            SynthesisOutline,
            _save_article,
        )

        with db.get_connection() as conn:
            # Create topic 11 for this test (unique)
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (11, 'new-topic', 'New Topic', 'fp11')"
            )
            # Create a source document that _save_article can reference
            _create_doc(conn, 7015, "Source Doc", "Source content")
            conn.commit()

        outline = SynthesisOutline(
            topic_label="New Topic",
            topic_slug="new-topic",
            suggested_title="Brand New Article",
            section_hints=["Overview"],
            entity_focus=["new"],
            strategy="stuff",
        )
        sources = [
            ArticleSource(
                doc_id=7015,
                title="Source Doc",
                content="Source content",
                content_hash="srchash",
                char_count=14,
            )
        ]

        doc_id, article_id = _save_article(
            topic_id=11,
            content="Brand new article content",
            outline=outline,
            sources=sources,
            model="test-model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
        )

        # First generation should have empty previous_content
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT previous_content FROM wiki_articles WHERE id = ?",
                (article_id,),
            ).fetchone()

        assert row is not None
        assert row[0] == ""


class TestGetArticleDiff:
    """Test the get_article_diff function."""

    def test_returns_diff_when_previous_exists(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (20, 'diff-topic', 'Diff Topic', 'fp20')"
            )
            _create_doc(conn, 7020, "My Article", "Line 1\nLine 2\nLine 3\n")
            _create_article(conn, 20, 20, 7020, previous_content="Line 1\nOld line 2\nLine 3\n")
            conn.commit()

        diff = get_article_diff(20)

        assert diff is not None
        assert "---" in diff
        assert "+++" in diff
        assert "-Old line 2" in diff
        assert "+Line 2" in diff

    def test_returns_none_when_no_previous(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            # Use topic 3 to avoid conflicts
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (3, 'no-prev', 'No Previous', 'fp3')"
            )
            _create_doc(conn, 7030, "Fresh Article", "Current content")
            _create_article(conn, 30, 3, 7030, previous_content="")
            conn.commit()

        diff = get_article_diff(3)
        assert diff is None

    def test_returns_none_when_topic_not_found(self, isolate_test_database: Any) -> None:
        diff = get_article_diff(99999)
        assert diff is None

    def test_diff_includes_title_in_filenames(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (4, 'titled', 'Titled Topic', 'fp4')"
            )
            _create_doc(conn, 7040, "My Cool Article", "new line\n")
            _create_article(conn, 40, 4, 7040, previous_content="old line\n")
            conn.commit()

        diff = get_article_diff(4)

        assert diff is not None
        assert "My Cool Article (previous)" in diff
        assert "My Cool Article (current)" in diff

    def test_diff_empty_when_content_identical(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (5, 'same', 'Same Content', 'fp5')"
            )
            _create_doc(conn, 7050, "Same Article", "identical content\n")
            _create_article(conn, 50, 5, 7050, previous_content="identical content\n")
            conn.commit()

        diff = get_article_diff(5)

        # unified_diff produces empty output when inputs are identical
        assert diff is not None
        assert diff == ""
