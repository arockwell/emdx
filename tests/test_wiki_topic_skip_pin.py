"""Tests for wiki topic skip/pin/unskip/unpin commands (Issue #1242)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _setup_wiki_topic(conn: sqlite3.Connection, topic_id: int = 1, status: str = "active") -> None:
    """Insert a wiki topic with the given status."""
    conn.execute(
        "INSERT INTO wiki_topics "
        "(id, topic_slug, topic_label, entity_fingerprint, status) "
        "VALUES (?, ?, 'Test Topic', 'fp', ?)",
        (topic_id, f"test-topic-{topic_id}", status),
    )
    conn.commit()


def _get_topic_status(conn: sqlite3.Connection, topic_id: int) -> str | None:
    """Read current status of a topic."""
    row = conn.execute("SELECT status FROM wiki_topics WHERE id = ?", (topic_id,)).fetchone()
    return row[0] if row else None


class TestWikiSkipCommand:
    """Test 'emdx maintain wiki skip' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=70, status="active")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 70")
            conn.commit()

    def test_skip_sets_status_to_skipped(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "skip", "70"])
        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "Test Topic" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 70) == "skipped"
        assert "Skipped" in result.output
        assert "Test Topic" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 70) == "skipped"

    def test_skip_shows_previous_status(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "skip", "70"])
        assert result.exit_code == 0
        assert "was: active" in result.output

    def test_skip_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "skip", "999"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestWikiUnskipCommand:
    """Test 'emdx maintain wiki unskip' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=71, status="skipped")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 71")
            conn.commit()

    def test_unskip_sets_status_to_active(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "unskip", "71"])
        assert result.exit_code == 0
        assert "Unskipped" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 71) == "active"

    def test_unskip_shows_previous_status(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "unskip", "71"])
        assert result.exit_code == 0
        assert "was: skipped" in result.output


class TestWikiPinCommand:
    """Test 'emdx maintain wiki pin' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=72, status="active")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 72")
            conn.commit()

    def test_pin_sets_status_to_pinned(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "pin", "72"])
        assert result.exit_code == 0
        assert "Pinned" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 72) == "pinned"

    def test_pin_shows_previous_status(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "pin", "72"])
        assert result.exit_code == 0
        assert "was: active" in result.output

    def test_pin_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "pin", "999"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestWikiUnpinCommand:
    """Test 'emdx maintain wiki unpin' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=73, status="pinned")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 73")
            conn.commit()

    def test_unpin_sets_status_to_active(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "unpin", "73"])
        assert result.exit_code == 0
        assert "Unpinned" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 73) == "active"

    def test_unpin_shows_previous_status(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "unpin", "73"])
        assert result.exit_code == 0
        assert "was: pinned" in result.output


class TestGenerateRespectsSkipStatus:
    """Test that generate_article skips topics with status='skipped'."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=74, status="skipped")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 74")
            conn.commit()

    def test_generate_skips_skipped_topic(self) -> None:
        from emdx.services.wiki_synthesis_service import generate_article

        result = generate_article(topic_id=74, dry_run=True)
        assert result.skipped is True
        assert "skipped" in result.skip_reason.lower()


class TestGenerateRespectsPinnedStatus:
    """Test that generate_article bypasses staleness check for pinned topics."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=75, status="pinned")
            # Add topic members so it has source docs
            conn.execute(
                "INSERT OR IGNORE INTO documents (id, title, content, is_deleted) "
                "VALUES (175, 'Source Doc', 'Some content here', 0)"
            )
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (75, 175)")
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute(
                "DELETE FROM wiki_article_sources WHERE article_id IN "
                "(SELECT id FROM wiki_articles WHERE topic_id = 75)"
            )
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 75")
            conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 75")
            conn.execute("DELETE FROM wiki_topics WHERE id = 75")
            conn.execute("DELETE FROM documents WHERE id = 175")
            conn.commit()

    def test_pinned_topic_not_skipped_as_skipped(self) -> None:
        """Pinned topics should not be skipped with 'Topic is skipped' reason."""
        from emdx.services.wiki_synthesis_service import generate_article

        result = generate_article(topic_id=75, dry_run=True)
        # Pinned topic should NOT be skipped for being "skipped"
        if result.skipped:
            assert "Topic is skipped" not in result.skip_reason

    def test_pinned_bypasses_staleness_check(self) -> None:
        """Pinned topics should regenerate even when source hash is unchanged."""
        from emdx.services.wiki_synthesis_service import (
            _compute_source_hash,
            _prepare_sources,
            generate_article,
        )

        # First, create an existing article with matching source hash
        sources = _prepare_sources([175])
        source_hash = _compute_source_hash(sources)

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
                "VALUES (275, 'Wiki: Test', 'article content', 0, 'wiki')"
            )
            conn.execute(
                "INSERT INTO wiki_articles "
                "(topic_id, document_id, source_hash, is_stale) "
                "VALUES (75, 275, ?, 0)",
                (source_hash,),
            )
            conn.commit()

        try:
            # For a pinned topic, it should NOT skip even though hash matches
            result = generate_article(topic_id=75, dry_run=True)
            # It should proceed to dry-run estimation, not skip as "up to date"
            if result.skipped:
                assert "source hash unchanged" not in result.skip_reason
        finally:
            with db.get_connection() as conn:
                conn.execute(
                    "DELETE FROM wiki_article_sources WHERE article_id IN "
                    "(SELECT id FROM wiki_articles WHERE topic_id = 75)"
                )
                conn.execute("DELETE FROM wiki_articles WHERE topic_id = 75")
                conn.execute("DELETE FROM documents WHERE id = 275")
                conn.commit()


class TestWikiStatusShowsStyledStatus:
    """Test that 'emdx maintain wiki status' shows topic statuses."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=76, status="skipped")
            _setup_wiki_topic(conn, topic_id=77, status="pinned")
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id IN (76, 77)")
            conn.commit()

    @patch("emdx.services.wiki_entity_service.get_entity_index_stats")
    def test_status_shows_skipped_and_pinned(self, mock_stats: MagicMock) -> None:
        mock_stats.return_value = MagicMock(tier_a_count=0, tier_b_count=0, tier_c_count=0)
        result = runner.invoke(app, ["maintain", "wiki", "status"])
        assert result.exit_code == 0
        assert "skipped" in result.output
        assert "pinned" in result.output
