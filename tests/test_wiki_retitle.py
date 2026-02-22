"""Tests for wiki topic retitle — auto-update labels from article H1 headings."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app
from emdx.services.wiki_synthesis_service import _extract_h1

runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────


def _setup_wiki_topic(
    conn: sqlite3.Connection,
    topic_id: int = 1,
    label: str = "Test Topic",
    slug: str = "test-topic",
    content: str = "# Test Topic\n\nBody text",
    status: str = "active",
) -> int:
    """Insert a wiki topic with article and document. Returns doc_id."""
    doc_id = topic_id + 100
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint, status) "
        "VALUES (?, ?, ?, 'fp', ?)",
        (topic_id, slug, label, status),
    )
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
        (doc_id, f"Wiki: {label}", content),
    )
    conn.execute(
        "INSERT INTO wiki_articles (topic_id, document_id, source_hash) VALUES (?, ?, 'hash')",
        (topic_id, doc_id),
    )
    conn.commit()
    return doc_id


def _cleanup_topics(conn: sqlite3.Connection, topic_ids: list[int]) -> None:
    """Remove wiki topics and related rows."""
    for tid in topic_ids:
        doc_id = tid + 100
        conn.execute("DELETE FROM wiki_articles WHERE topic_id = ?", (tid,))
        conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = ?", (tid,))
        conn.execute("DELETE FROM wiki_topics WHERE id = ?", (tid,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()


# ── _extract_h1 unit tests ──────────────────────────────────────────


class TestExtractH1:
    def test_basic(self) -> None:
        assert _extract_h1("# Title\n\nContent") == "Title"

    def test_no_heading(self) -> None:
        assert _extract_h1("Just plain text\nNo heading here") is None

    def test_with_prefix_text(self) -> None:
        content = "Some preamble\n\n# Actual Title\n\nBody"
        assert _extract_h1(content) == "Actual Title"

    def test_ignores_h2(self) -> None:
        assert _extract_h1("## Not H1\n\nBody") is None

    def test_strips_whitespace(self) -> None:
        assert _extract_h1("#   Spaced Title  \n") == "Spaced Title"

    def test_first_h1_wins(self) -> None:
        content = "# First\n\n# Second"
        assert _extract_h1(content) == "First"


# ── generate_article retitle integration ─────────────────────────────


class TestGenerateArticleRetitle:
    """Test that generate_article auto-retitles from H1."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (80, 'browsepy-trashpy-tagspy', "
                "'browse.py / trash.py / tags.py', 'fp')"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (980, 'Source', 'source content', 0)"
            )
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (80, 980)")
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute(
                "DELETE FROM wiki_article_sources WHERE article_id IN "
                "(SELECT id FROM wiki_articles WHERE topic_id = 80)"
            )
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 80")
            conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 80")
            conn.execute("DELETE FROM wiki_topics WHERE id = 80")
            conn.execute("DELETE FROM documents WHERE id = 980")
            conn.execute(
                "DELETE FROM documents WHERE id IN "
                "(SELECT document_id FROM wiki_articles WHERE topic_id = 80)"
            )
            # Clean generated article docs
            conn.execute("DELETE FROM documents WHERE title LIKE 'Wiki:%' AND id > 900")
            conn.commit()

    @patch("emdx.services.wiki_synthesis_service._synthesize_article")
    def test_retitles_topic(self, mock_synth: MagicMock) -> None:
        from emdx.services.wiki_synthesis_service import generate_article

        mock_synth.return_value = (
            "# CLI Module Architecture\n\nThis article covers...",
            100,
            200,
            0.01,
        )

        result = generate_article(topic_id=80)
        assert not result.skipped
        assert result.topic_label == "CLI Module Architecture"

        # Verify DB was updated
        with db.get_connection() as conn:
            topic_row = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 80"
            ).fetchone()
            assert topic_row[0] == "CLI Module Architecture"
            assert topic_row[1] == "cli-module-architecture"

            # Also check document title
            doc_row = conn.execute(
                "SELECT title FROM documents WHERE id = ?", (result.document_id,)
            ).fetchone()
            assert doc_row[0] == "CLI Module Architecture"

    @patch("emdx.services.wiki_synthesis_service._synthesize_article")
    def test_skips_retitle_on_slug_conflict(self, mock_synth: MagicMock) -> None:
        from emdx.services.wiki_synthesis_service import generate_article

        # Create a second topic that would conflict
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint) "
                "VALUES (81, 'cli-module-architecture', 'CLI Module Architecture', 'fp2')"
            )
            conn.commit()

        mock_synth.return_value = (
            "# CLI Module Architecture\n\nContent...",
            100,
            200,
            0.01,
        )

        result = generate_article(topic_id=80)
        assert not result.skipped
        # Label should NOT have changed due to slug conflict
        assert result.topic_label == "browse.py / trash.py / tags.py"

        with db.get_connection() as conn:
            row = conn.execute("SELECT topic_label FROM wiki_topics WHERE id = 80").fetchone()
            assert row[0] == "browse.py / trash.py / tags.py"

        # Clean up conflict topic
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 81")
            conn.commit()


# ── wiki retitle CLI command ─────────────────────────────────────────


class TestRetitleCommand:
    """Test 'emdx maintain wiki retitle' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(
                conn,
                topic_id=90,
                label="old-label-a",
                slug="old-label-a",
                content="# Better Title A\n\nBody",
            )
            _setup_wiki_topic(
                conn,
                topic_id=91,
                label="Better Title B",
                slug="better-title-b",
                content="# Better Title B\n\nAlready matches",
            )
            _setup_wiki_topic(
                conn,
                topic_id=92,
                label="old-label-c",
                slug="old-label-c",
                content="# Better Title C\n\nBody",
            )
        yield
        with db.get_connection() as conn:
            _cleanup_topics(conn, [90, 91, 92])

    def test_dry_run_shows_changes(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "retitle", "--dry-run"])
        assert result.exit_code == 0
        assert "old-label-a" in result.output
        assert "Better Title A" in result.output
        assert "Would retitle" in result.output

        # Verify DB was NOT updated
        with db.get_connection() as conn:
            row = conn.execute("SELECT topic_label FROM wiki_topics WHERE id = 90").fetchone()
            assert row[0] == "old-label-a"

    def test_updates_labels(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "retitle"])
        assert result.exit_code == 0
        assert "Retitled 2/" in result.output

        with db.get_connection() as conn:
            row_a = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 90"
            ).fetchone()
            assert row_a[0] == "Better Title A"
            assert row_a[1] == "better-title-a"

            row_c = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 92"
            ).fetchone()
            assert row_c[0] == "Better Title C"
            assert row_c[1] == "better-title-c"

            # Doc titles updated too
            doc_a = conn.execute("SELECT title FROM documents WHERE id = 190").fetchone()
            assert doc_a[0] == "Better Title A"

    def test_skips_matching(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "retitle"])
        assert result.exit_code == 0
        assert "1 already matching" in result.output

        # Topic 91 should be unchanged
        with db.get_connection() as conn:
            row = conn.execute("SELECT topic_label FROM wiki_topics WHERE id = 91").fetchone()
            assert row[0] == "Better Title B"
