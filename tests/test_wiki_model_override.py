"""Tests for per-topic wiki model override (migration 051, maintain wiki model)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


@pytest.fixture(autouse=True, scope="module")
def _ensure_model_override_column() -> None:
    """Ensure the model_override column exists on wiki_topics.

    In shared-virtualenv worktree setups, migration 051 may not have run.
    Apply the column idempotently here.
    """
    with db.get_connection() as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(wiki_topics)")}
        if "model_override" not in existing:
            conn.execute("ALTER TABLE wiki_topics ADD COLUMN model_override TEXT")
        conn.commit()


def _setup_wiki_topic(conn: sqlite3.Connection, topic_id: int = 1) -> None:
    """Insert a wiki topic, document, and article."""
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (?, 'test-model-topic', 'Test Model Topic', 'fp')",
        (topic_id,),
    )
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) "
        "VALUES (?, 'Wiki: Test Model Topic', 'Article body', 0)",
        (topic_id + 200,),
    )
    conn.execute(
        "INSERT INTO wiki_articles (topic_id, document_id, source_hash) VALUES (?, ?, 'hash')",
        (topic_id, topic_id + 200),
    )
    conn.commit()


class TestMigration051:
    """Verify the model_override column exists after migration 051."""

    def test_model_override_column_exists(self) -> None:
        with db.get_connection() as conn:
            info = conn.execute("PRAGMA table_info(wiki_topics)").fetchall()
            col_names = [row[1] for row in info]
            assert "model_override" in col_names

    def test_model_override_defaults_to_null(self) -> None:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=80)
            row = conn.execute("SELECT model_override FROM wiki_topics WHERE id = 80").fetchone()
            assert row[0] is None
            # Cleanup
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 80")
            conn.execute("DELETE FROM wiki_topics WHERE id = 80")
            conn.execute("DELETE FROM documents WHERE id = 280")
            conn.commit()


class TestWikiModelCommand:
    """Test 'emdx maintain wiki model' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        """Set up and tear down a wiki topic for each test."""
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=70)
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 70")
            conn.execute("DELETE FROM wiki_topics WHERE id = 70")
            conn.execute("DELETE FROM documents WHERE id = 270")
            conn.commit()

    def test_set_model_override(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "model", "70", "claude-opus-4-5-20250514"])
        assert result.exit_code == 0
        assert "claude-opus-4-5-20250514" in result.output
        assert "Set model override" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT model_override FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] == "claude-opus-4-5-20250514"

    def test_clear_model_override(self) -> None:
        # First set an override
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE wiki_topics SET model_override = 'claude-opus-4-5-20250514' WHERE id = 70"
            )
            conn.commit()

        result = runner.invoke(app, ["maintain", "wiki", "model", "70", "--clear"])
        assert result.exit_code == 0
        assert "Cleared model override" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT model_override FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] is None

    def test_model_requires_name_or_clear(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "model", "70"])
        assert result.exit_code == 1
        assert "Provide a model name or use --clear" in result.output

    def test_model_rejects_both_name_and_clear(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "model", "70", "some-model", "--clear"])
        assert result.exit_code == 1
        assert "Cannot use both" in result.output

    def test_model_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "model", "999", "some-model"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestGenerateArticleUsesModelOverride:
    """Test that generate_article() respects per-topic model_override."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            # Insert a topic with a model override
            conn.execute(
                "INSERT INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint, model_override) "
                "VALUES (75, 'override-topic', 'Override Topic', 'fp', "
                "'claude-opus-4-5-20250514')"
            )
            # Insert a topic member document
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (275, 'Source Doc', 'Some content here', 0)"
            )
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (75, 275)")
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
            conn.execute("DELETE FROM documents WHERE id = 275")
            conn.commit()

    @patch("emdx.services.wiki_synthesis_service._synthesize_article")
    def test_override_model_used_when_no_explicit_model(self, mock_synth: MagicMock) -> None:
        """When no model arg is given, topic's model_override is used."""
        mock_synth.return_value = ("# Article\nContent", 100, 50, 0.001)

        from emdx.services.wiki_synthesis_service import generate_article

        result = generate_article(topic_id=75, model=None)

        assert not result.skipped
        assert result.model == "claude-opus-4-5-20250514"
        # Verify the synthesize call used the override model
        call_kwargs = mock_synth.call_args
        assert (
            call_kwargs[1].get("model") == "claude-opus-4-5-20250514"
            or call_kwargs[0][3] == "claude-opus-4-5-20250514"
        )

    @patch("emdx.services.wiki_synthesis_service._synthesize_article")
    def test_explicit_model_overrides_topic_override(self, mock_synth: MagicMock) -> None:
        """When an explicit model arg is given, it takes priority over topic override."""
        mock_synth.return_value = ("# Article\nContent", 100, 50, 0.001)

        from emdx.services.wiki_synthesis_service import generate_article

        result = generate_article(topic_id=75, model="claude-haiku-4-5-20251001")

        assert not result.skipped
        assert result.model == "claude-haiku-4-5-20251001"


class TestGetTopicsIncludesModelOverride:
    """Test that get_topics() returns model_override field."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO wiki_topics "
                "(id, topic_slug, topic_label, entity_fingerprint, model_override) "
                "VALUES (85, 'model-test', 'Model Test', 'fp', 'claude-opus-4-5-20250514')"
            )
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 85")
            conn.commit()

    def test_get_topics_returns_model_override(self) -> None:
        from emdx.services.wiki_clustering_service import get_topics

        topics = get_topics()
        topic = next((t for t in topics if t["id"] == 85), None)
        assert topic is not None
        assert topic["model_override"] == "claude-opus-4-5-20250514"

    def test_get_topics_returns_none_for_no_override(self) -> None:
        # Clear the override
        with db.get_connection() as conn:
            conn.execute("UPDATE wiki_topics SET model_override = NULL WHERE id = 85")
            conn.commit()

        from emdx.services.wiki_clustering_service import get_topics

        topics = get_topics()
        topic = next((t for t in topics if t["id"] == 85), None)
        assert topic is not None
        assert topic["model_override"] is None
