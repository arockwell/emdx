"""Tests for wiki article quality rating (migration 050, maintain wiki rate)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


@pytest.fixture(autouse=True, scope="module")
def _ensure_rating_columns() -> None:
    """Ensure the rating/rated_at columns exist on wiki_articles.

    In shared-virtualenv worktree setups, another worktree's migration 048 may
    have taken the slot during conftest setup, so migration 050 never ran.
    Apply the columns idempotently here.
    """
    with db.get_connection() as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(wiki_articles)")}
        if "rating" not in existing:
            conn.execute("ALTER TABLE wiki_articles ADD COLUMN rating INTEGER")
        if "rated_at" not in existing:
            conn.execute("ALTER TABLE wiki_articles ADD COLUMN rated_at TIMESTAMP")
        conn.commit()


def _setup_wiki_article(conn: sqlite3.Connection, topic_id: int = 1) -> int:
    """Insert a wiki topic, document, and article. Returns document id."""
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint) "
        "VALUES (?, 'test-topic', 'Test Topic', 'fp')",
        (topic_id,),
    )
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


class TestMigration050:
    """Verify the rating column exists after migration 050."""

    def test_rating_column_exists(self) -> None:
        with db.get_connection() as conn:
            info = conn.execute("PRAGMA table_info(wiki_articles)").fetchall()
            col_names = [row[1] for row in info]
            assert "rating" in col_names
            assert "rated_at" in col_names

    def test_rating_defaults_to_null(self) -> None:
        with db.get_connection() as conn:
            _setup_wiki_article(conn, topic_id=90)
            row = conn.execute(
                "SELECT rating, rated_at FROM wiki_articles WHERE topic_id = 90"
            ).fetchone()
            assert row[0] is None
            assert row[1] is None
            # Cleanup
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 90")
            conn.execute("DELETE FROM wiki_topics WHERE id = 90")
            conn.execute("DELETE FROM documents WHERE id = 190")
            conn.commit()


class TestWikiRateCommand:
    """Test 'emdx maintain wiki rate' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        """Set up and tear down a wiki article for each test."""
        with db.get_connection() as conn:
            _setup_wiki_article(conn, topic_id=50)
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 50")
            conn.execute("DELETE FROM wiki_topics WHERE id = 50")
            conn.execute("DELETE FROM documents WHERE id = 150")
            conn.commit()

    def test_rate_with_numeric_value(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "4"])
        assert result.exit_code == 0
        assert "4/5" in result.output

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT rating, rated_at FROM wiki_articles WHERE topic_id = 50"
            ).fetchone()
            assert row[0] == 4
            assert row[1] is not None

    def test_rate_thumbs_up(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "--up"])
        assert result.exit_code == 0
        assert "4/5" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT rating FROM wiki_articles WHERE topic_id = 50").fetchone()
            assert row[0] == 4

    def test_rate_thumbs_down(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "--down"])
        assert result.exit_code == 0
        assert "2/5" in result.output

        with db.get_connection() as conn:
            row = conn.execute("SELECT rating FROM wiki_articles WHERE topic_id = 50").fetchone()
            assert row[0] == 2

    def test_rate_rejects_both_up_and_down(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "--up", "--down"])
        assert result.exit_code == 1
        assert "Cannot use both" in result.output

    def test_rate_rejects_out_of_range(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "6"])
        assert result.exit_code == 1
        assert "between 1 and 5" in result.output

        result = runner.invoke(app, ["maintain", "wiki", "rate", "50", "0"])
        assert result.exit_code == 1

    def test_rate_requires_value_or_flag(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "50"])
        assert result.exit_code == 1
        assert "Provide a rating" in result.output

    def test_rate_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "rate", "999", "3"])
        assert result.exit_code == 1
        assert "No wiki article" in result.output


class TestWikiListShowsRating:
    """Test that 'emdx maintain wiki list' includes the Rating column."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_article(conn, topic_id=60)
            conn.execute("UPDATE wiki_articles SET rating = 5 WHERE topic_id = 60")
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_articles WHERE topic_id = 60")
            conn.execute("DELETE FROM wiki_topics WHERE id = 60")
            conn.execute("DELETE FROM documents WHERE id = 160")
            conn.commit()

    def test_list_shows_rating_column(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "list"])
        assert result.exit_code == 0
        assert "Rating" in result.output

    def test_list_shows_stars_for_rated(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "list"])
        assert result.exit_code == 0
        # 5 filled stars for rating=5
        assert "\u2605\u2605\u2605\u2605\u2605" in result.output

    def test_list_shows_dash_for_unrated(self) -> None:
        with db.get_connection() as conn:
            conn.execute("UPDATE wiki_articles SET rating = NULL WHERE topic_id = 60")
            conn.commit()
        result = runner.invoke(app, ["maintain", "wiki", "list"])
        assert result.exit_code == 0
        assert "-" in result.output
