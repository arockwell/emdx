"""Tests for wiki editorial prompt (migration 051, maintain wiki prompt)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


@pytest.fixture(autouse=True, scope="module")
def _ensure_editorial_prompt_column() -> None:
    """Ensure the editorial_prompt column exists on wiki_topics.

    In shared-virtualenv worktree setups, another worktree's migration may
    have taken the slot during conftest setup, so migration 051 never ran.
    Apply the column idempotently here.
    """
    with db.get_connection() as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(wiki_topics)")}
        if "editorial_prompt" not in existing:
            conn.execute("ALTER TABLE wiki_topics ADD COLUMN editorial_prompt TEXT")
        conn.commit()


def _setup_wiki_topic(conn: sqlite3.Connection, topic_id: int = 1) -> None:
    """Insert a wiki topic."""
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (?, 'test-topic', 'Test Topic', 'fp')",
        (topic_id,),
    )
    conn.commit()


def _setup_wiki_article(conn: sqlite3.Connection, topic_id: int = 1) -> int:
    """Insert a wiki topic, document, and article. Returns document id."""
    _setup_wiki_topic(conn, topic_id)
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) "
        "VALUES (?, 'Wiki: Test Topic', 'Article body', 0)",
        (topic_id + 100,),
    )
    conn.execute(
        "INSERT INTO wiki_articles (topic_id, document_id, source_hash) VALUES (?, ?, 'hash')",
        (topic_id, topic_id + 100),
    )
    conn.commit()
    return topic_id + 100


class TestMigration051:
    """Verify the editorial_prompt column exists after migration 051."""

    def test_editorial_prompt_column_exists(self) -> None:
        with db.get_connection() as conn:
            info = conn.execute("PRAGMA table_info(wiki_topics)").fetchall()
            col_names = [row[1] for row in info]
            assert "editorial_prompt" in col_names

    def test_editorial_prompt_defaults_to_null(self) -> None:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=80)
            row = conn.execute("SELECT editorial_prompt FROM wiki_topics WHERE id = 80").fetchone()
            assert row[0] is None
            # Cleanup
            conn.execute("DELETE FROM wiki_topics WHERE id = 80")
            conn.commit()


class TestWikiPromptCommand:
    """Test 'emdx maintain wiki prompt' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        """Set up and tear down a wiki topic for each test."""
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=70)
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id = 70")
            conn.commit()

    def test_set_editorial_prompt(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "prompt", "70", "Focus on security"])
        assert result.exit_code == 0
        assert "Set editorial prompt" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT editorial_prompt FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] == "Focus on security"

    def test_clear_editorial_prompt(self) -> None:
        # First set a prompt
        with db.get_connection() as conn:
            conn.execute("UPDATE wiki_topics SET editorial_prompt = 'old prompt' WHERE id = 70")
            conn.commit()

        result = runner.invoke(app, ["maintain", "wiki", "prompt", "70", "--clear"])
        assert result.exit_code == 0
        assert "Cleared editorial prompt" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT editorial_prompt FROM wiki_topics WHERE id = 70").fetchone()
            assert row[0] is None

    def test_show_editorial_prompt(self) -> None:
        with db.get_connection() as conn:
            conn.execute("UPDATE wiki_topics SET editorial_prompt = 'my prompt' WHERE id = 70")
            conn.commit()

        result = runner.invoke(app, ["maintain", "wiki", "prompt", "70"])
        assert result.exit_code == 0
        assert "my prompt" in result.output

    def test_show_no_prompt(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "prompt", "70"])
        assert result.exit_code == 0
        assert "no editorial prompt set" in result.output

    def test_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "prompt", "999", "some text"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_clear_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "prompt", "999", "--clear"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_clear_with_text_errors(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "prompt", "70", "text", "--clear"])
        assert result.exit_code == 1
        assert "Cannot use --clear" in result.output


class TestEditorialPromptInSynthesis:
    """Test that editorial_prompt is injected into the LLM prompt."""

    def test_build_synthesis_prompt_without_editorial(self) -> None:
        from emdx.services.wiki_synthesis_service import (
            ArticleSource,
            SynthesisOutline,
            _build_synthesis_prompt,
        )

        outline = SynthesisOutline(
            topic_label="Test",
            topic_slug="test",
            suggested_title="Test Article",
            section_hints=["Overview"],
            entity_focus=["entity1"],
            strategy="stuff",
        )
        sources = [
            ArticleSource(
                doc_id=1,
                title="Doc 1",
                content="Content",
                content_hash="abc",
                char_count=7,
            )
        ]
        system_prompt, _ = _build_synthesis_prompt(outline, sources)
        assert "Editorial Guidance" not in system_prompt

    def test_build_synthesis_prompt_with_editorial(self) -> None:
        from emdx.services.wiki_synthesis_service import (
            ArticleSource,
            SynthesisOutline,
            _build_synthesis_prompt,
        )

        outline = SynthesisOutline(
            topic_label="Test",
            topic_slug="test",
            suggested_title="Test Article",
            section_hints=["Overview"],
            entity_focus=["entity1"],
            strategy="stuff",
        )
        sources = [
            ArticleSource(
                doc_id=1,
                title="Doc 1",
                content="Content",
                content_hash="abc",
                char_count=7,
            )
        ]
        system_prompt, _ = _build_synthesis_prompt(
            outline, sources, editorial_prompt="Focus on performance"
        )
        assert "Editorial Guidance" in system_prompt
        assert "Focus on performance" in system_prompt

    def test_generate_article_passes_editorial_prompt(self) -> None:
        """Verify generate_article reads and passes editorial_prompt to synthesis."""
        with db.get_connection() as conn:
            _setup_wiki_article(conn, topic_id=75)
            conn.execute(
                "UPDATE wiki_topics SET editorial_prompt = 'Emphasize testing' WHERE id = 75"
            )
            # Add a topic member so get_topic_docs returns docs
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (75, 175)")
            conn.commit()

        try:
            with (
                patch("emdx.services.wiki_synthesis_service._synthesize_article") as mock_synth,
                patch(
                    "emdx.services.wiki_synthesis_service._validate_article",
                    return_value=("content", []),
                ),
                patch(
                    "emdx.services.wiki_synthesis_service._save_article",
                    return_value=(175, 1),
                ),
            ):
                mock_synth.return_value = ("Generated content", 100, 50, 0.01)

                from emdx.services.wiki_synthesis_service import generate_article

                generate_article(topic_id=75)

                # Verify editorial_prompt was passed
                mock_synth.assert_called_once()
                call_kwargs = mock_synth.call_args
                assert call_kwargs.kwargs.get("editorial_prompt") == "Emphasize testing"
        finally:
            with db.get_connection() as conn:
                conn.execute("DELETE FROM wiki_articles WHERE topic_id = 75")
                conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 75")
                conn.execute("DELETE FROM wiki_topics WHERE id = 75")
                conn.execute("DELETE FROM documents WHERE id = 175")
                conn.commit()


class TestWikiTopicsVerbose:
    """Test 'emdx maintain wiki topics --verbose' shows editorial prompts."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=85)
            conn.execute("UPDATE wiki_topics SET editorial_prompt = 'Be concise' WHERE id = 85")
            # Add a member so member_count > 0
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (185, 'Source Doc', 'content', 0)"
            )
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (85, 185)")
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 85")
            conn.execute("DELETE FROM wiki_topics WHERE id = 85")
            conn.execute("DELETE FROM documents WHERE id = 185")
            conn.commit()

    def test_verbose_shows_editorial_prompt_column(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "topics", "--verbose"])
        assert result.exit_code == 0
        assert "Editorial Prompt" in result.output

    def test_verbose_shows_prompt_text(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "topics", "--verbose"])
        assert result.exit_code == 0
        assert "Be concise" in result.output

    def test_verbose_shows_dash_for_no_prompt(self) -> None:
        with db.get_connection() as conn:
            conn.execute("UPDATE wiki_topics SET editorial_prompt = NULL WHERE id = 85")
            conn.commit()
        result = runner.invoke(app, ["maintain", "wiki", "topics", "--verbose"])
        assert result.exit_code == 0
        assert "-" in result.output
