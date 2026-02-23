"""Tests for wiki article step-level timing (Issue #1250).

Tests migration 048, WikiArticleTimingDict, timing in generate_article(),
and timing display in wiki_list.

Uses the session-scoped isolate_test_database fixture from conftest.py
which runs all migrations including 048.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

from emdx.database import db
from emdx.database.types import WikiArticleTimingDict
from emdx.services.wiki_synthesis_service import (
    ArticleSource,
    SynthesisOutline,
    WikiArticleResult,
    _save_article,
    generate_article,
)

# ── Helpers ───────────────────────────────────────────────────────────


def _setup_topic(conn: sqlite3.Connection, topic_id: int = 1) -> None:
    """Insert a wiki_topics row for testing."""
    conn.execute(
        "INSERT OR IGNORE INTO wiki_topics "
        "(id, topic_slug, topic_label, description, entity_fingerprint) "
        "VALUES (?, ?, 'Test Topic', '[]', 'fp1')",
        (topic_id, f"test-topic-{topic_id}"),
    )
    conn.commit()


def _setup_source_doc(conn: sqlite3.Connection, doc_id: int = 100) -> None:
    """Insert a document to use as article source."""
    conn.execute(
        "INSERT OR IGNORE INTO documents (id, title, content, is_deleted) "
        "VALUES (?, 'Source Doc', 'Some content for testing', 0)",
        (doc_id,),
    )
    conn.commit()


def _setup_topic_member(conn: sqlite3.Connection, topic_id: int = 1, doc_id: int = 100) -> None:
    """Link a document to a topic."""
    conn.execute(
        "INSERT OR IGNORE INTO wiki_topic_members (topic_id, document_id) VALUES (?, ?)",
        (topic_id, doc_id),
    )
    conn.commit()


# ── Migration tests ──────────────────────────────────────────────────


class TestMigration048TimingColumns:
    """Verify migration 048 added the six timing columns."""

    def test_timing_columns_exist(self) -> None:
        """All six timing columns should exist on wiki_articles."""
        with db.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(wiki_articles)")
            col_names = {row[1] for row in cursor.fetchall()}

        expected = {
            "prepare_ms",
            "route_ms",
            "outline_ms",
            "write_ms",
            "validate_ms",
            "save_ms",
        }
        assert expected.issubset(col_names)

    def test_timing_columns_default_to_zero(self) -> None:
        """New rows should default timing columns to 0."""
        with db.get_connection() as conn:
            _setup_topic(conn, topic_id=900)
            _setup_source_doc(conn, doc_id=900)
            conn.execute(
                "INSERT INTO wiki_articles "
                "(topic_id, document_id, source_hash, model) "
                "VALUES (900, 900, 'hash', 'test-model')"
            )
            conn.commit()

            row = conn.execute(
                "SELECT prepare_ms, route_ms, outline_ms, "
                "write_ms, validate_ms, save_ms "
                "FROM wiki_articles WHERE topic_id = 900"
            ).fetchone()

        assert row is not None
        assert list(row) == [0, 0, 0, 0, 0, 0]


# ── TypedDict tests ─────────────────────────────────────────────────


class TestWikiArticleTimingDict:
    """Verify WikiArticleTimingDict shape."""

    def test_create_timing_dict(self) -> None:
        timing = WikiArticleTimingDict(
            prepare_ms=100,
            route_ms=1,
            outline_ms=5,
            write_ms=5000,
            validate_ms=10,
            save_ms=50,
        )
        assert timing["prepare_ms"] == 100
        assert timing["write_ms"] == 5000

    def test_all_keys_present(self) -> None:
        timing = WikiArticleTimingDict(
            prepare_ms=0,
            route_ms=0,
            outline_ms=0,
            write_ms=0,
            validate_ms=0,
            save_ms=0,
        )
        expected_keys = {
            "prepare_ms",
            "route_ms",
            "outline_ms",
            "write_ms",
            "validate_ms",
            "save_ms",
        }
        assert set(timing.keys()) == expected_keys


# ── _save_article with timing ───────────────────────────────────────


class TestSaveArticleWithTiming:
    """Test that _save_article stores timing data."""

    def test_save_article_stores_timing(self) -> None:
        """_save_article should persist timing columns."""
        with db.get_connection() as conn:
            _setup_topic(conn, topic_id=801)
            _setup_source_doc(conn, doc_id=801)

        sources = [
            ArticleSource(
                doc_id=801,
                title="Source",
                content="test",
                content_hash="abc123",
                char_count=4,
            )
        ]
        outline = SynthesisOutline(
            topic_label="Test",
            topic_slug="test",
            suggested_title="Test Article",
            section_hints=["Overview"],
            entity_focus=["test"],
            strategy="stuff",
        )
        timing = WikiArticleTimingDict(
            prepare_ms=120,
            route_ms=2,
            outline_ms=8,
            write_ms=4500,
            validate_ms=15,
            save_ms=45,
        )

        doc_id, article_id = _save_article(
            topic_id=801,
            content="# Test Article\n\nContent here.",
            outline=outline,
            sources=sources,
            model="test-model",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.01,
            timing=timing,
        )

        assert doc_id > 0
        assert article_id > 0

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT prepare_ms, route_ms, outline_ms, "
                "write_ms, validate_ms, save_ms "
                "FROM wiki_articles WHERE id = ?",
                (article_id,),
            ).fetchone()

        assert row is not None
        assert row[0] == 120  # prepare_ms
        assert row[1] == 2  # route_ms
        assert row[2] == 8  # outline_ms
        assert row[3] == 4500  # write_ms
        assert row[4] == 15  # validate_ms
        assert row[5] == 45  # save_ms

    def test_save_article_without_timing(self) -> None:
        """_save_article with no timing should leave defaults (0)."""
        with db.get_connection() as conn:
            _setup_topic(conn, topic_id=902)
            _setup_source_doc(conn, doc_id=902)

        sources = [
            ArticleSource(
                doc_id=902,
                title="Source",
                content="test",
                content_hash="def456",
                char_count=4,
            )
        ]
        outline = SynthesisOutline(
            topic_label="Test2",
            topic_slug="test2",
            suggested_title="Test Article 2",
            section_hints=["Overview"],
            entity_focus=["test"],
            strategy="stuff",
        )

        doc_id, article_id = _save_article(
            topic_id=902,
            content="# Test Article 2\n\nMore content.",
            outline=outline,
            sources=sources,
            model="test-model",
            input_tokens=100,
            output_tokens=200,
            cost_usd=0.01,
        )

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT prepare_ms, route_ms, outline_ms, "
                "write_ms, validate_ms, save_ms "
                "FROM wiki_articles WHERE id = ?",
                (article_id,),
            ).fetchone()

        assert row is not None
        assert list(row) == [0, 0, 0, 0, 0, 0]


# ── generate_article timing ─────────────────────────────────────────


class TestGenerateArticleTiming:
    """Test that generate_article populates timing on WikiArticleResult."""

    @patch("emdx.services.wiki_synthesis_service._synthesize_article")
    @patch("emdx.services.wiki_synthesis_service._validate_article")
    def test_generate_article_returns_timing(
        self, mock_validate: MagicMock, mock_synthesize: MagicMock
    ) -> None:
        """Full pipeline should produce non-None timing dict."""
        with db.get_connection() as conn:
            _setup_topic(conn, topic_id=903)
            _setup_source_doc(conn, doc_id=903)
            _setup_topic_member(conn, topic_id=903, doc_id=903)

        mock_synthesize.return_value = ("# Article\n\nContent", 500, 300, 0.005)
        mock_validate.return_value = ("# Article\n\nContent", [])

        result = generate_article(topic_id=903, model="test-model")

        assert not result.skipped
        assert result.timing is not None
        assert result.timing["prepare_ms"] >= 0
        assert result.timing["route_ms"] >= 0
        assert result.timing["outline_ms"] >= 0
        assert result.timing["write_ms"] >= 0
        assert result.timing["validate_ms"] >= 0
        assert result.timing["save_ms"] >= 0

    def test_generate_article_dry_run_has_timing(self) -> None:
        """Dry run should still populate timing for prepare/route/outline."""
        with db.get_connection() as conn:
            _setup_topic(conn, topic_id=904)
            _setup_source_doc(conn, doc_id=904)
            _setup_topic_member(conn, topic_id=904, doc_id=904)

        result = generate_article(topic_id=904, dry_run=True)

        assert result.skipped
        assert result.skip_reason == "dry run"
        assert result.timing is not None
        assert result.timing["prepare_ms"] >= 0
        assert result.timing["route_ms"] >= 0
        assert result.timing["outline_ms"] >= 0
        # Write/validate/save not executed in dry run
        assert result.timing["write_ms"] == 0
        assert result.timing["validate_ms"] == 0
        assert result.timing["save_ms"] == 0

    def test_skipped_result_has_no_timing(self) -> None:
        """Skipped results (topic not found) should have timing=None."""
        result = generate_article(topic_id=999999)
        assert result.skipped
        assert result.timing is None


# ── WikiArticleResult dataclass ──────────────────────────────────────


class TestWikiArticleResultTiming:
    """Test the timing field on WikiArticleResult."""

    def test_default_timing_is_none(self) -> None:
        result = WikiArticleResult(
            topic_id=1,
            topic_label="t",
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="m",
        )
        assert result.timing is None

    def test_timing_can_be_set(self) -> None:
        timing = WikiArticleTimingDict(
            prepare_ms=10,
            route_ms=1,
            outline_ms=2,
            write_ms=3000,
            validate_ms=5,
            save_ms=20,
        )
        result = WikiArticleResult(
            topic_id=1,
            topic_label="t",
            document_id=0,
            article_id=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            model="m",
            timing=timing,
        )
        assert result.timing is not None
        assert result.timing["write_ms"] == 3000


# ── _format_ms helper ───────────────────────────────────────────────


class TestFormatMs:
    """Test the _format_ms helper in maintain.py."""

    def test_milliseconds(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(500) == "500ms"

    def test_seconds(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(2500) == "2.5s"

    def test_minutes(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(90_000) == "1.5m"

    def test_zero(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(0) == "0ms"

    def test_exactly_one_second(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(1000) == "1.0s"

    def test_exactly_one_minute(self) -> None:
        from emdx.commands.wiki import _format_ms

        assert _format_ms(60_000) == "1.0m"
