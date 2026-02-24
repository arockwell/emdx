"""Tests for the wiki progress command (emdx maintain wiki progress)."""

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
            conn.execute("DELETE FROM wiki_articles")
            conn.execute("DELETE FROM wiki_topic_members")
            conn.execute("DELETE FROM wiki_topics")
            conn.execute("DELETE FROM documents")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    db.ensure_schema()
    yield
    cleanup()


def _create_topic(topic_id: int, label: str, status: str = "active") -> int:
    """Insert a wiki topic."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO wiki_topics (id, topic_slug, topic_label, status) VALUES (?, ?, ?, ?)",
            (topic_id, label.lower().replace(" ", "-"), label, status),
        )
        conn.commit()
    return topic_id


def _create_article(
    article_id: int,
    topic_id: int,
    doc_id: int,
    cost_usd: float = 0.10,
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> int:
    """Insert a wiki article with cost data, creating the backing document."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
            "VALUES (?, ?, 'wiki content', 0, 'wiki')",
            (doc_id, f"Article {article_id}"),
        )
        conn.execute(
            "INSERT INTO wiki_articles "
            "(id, topic_id, document_id, cost_usd, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (article_id, topic_id, doc_id, cost_usd, input_tokens, output_tokens),
        )
        conn.commit()
    return article_id


class TestWikiProgressEmpty:
    """Tests with empty database."""

    def test_progress_empty_db(self, clean_wiki_db: Any) -> None:
        """Empty database shows 0/0 with 0% progress."""
        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "0/0 generated" in output

    def test_progress_empty_json(self, clean_wiki_db: Any) -> None:
        """Empty database JSON output has correct structure."""
        result = runner.invoke(app, ["maintain", "wiki", "progress", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total_topics"] == 0
        assert data["generated"] == 0
        assert data["pending"] == 0
        assert data["skipped"] == 0
        assert data["percent_complete"] == 0.0
        assert data["cost_usd"] == 0.0
        assert data["est_remaining_cost_usd"] == 0.0


class TestWikiProgressWithData:
    """Tests with topics and articles."""

    def test_all_generated(self, clean_wiki_db: Any) -> None:
        """All topics generated shows 100%."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _create_article(1, 1, 101)
        _create_article(2, 2, 102)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "2/2 generated" in output
        assert "0 pending" in output
        assert "100.0%" in output

    def test_partial_progress(self, clean_wiki_db: Any) -> None:
        """Partially generated shows correct counts."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _create_topic(3, "Topic C")
        _create_article(1, 1, 101, cost_usd=0.25)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "1/3 generated" in output
        assert "2 pending" in output
        assert "0 skipped" in output

    def test_skipped_topics(self, clean_wiki_db: Any) -> None:
        """Skipped topics are counted separately."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B", status="skipped")
        _create_topic(3, "Topic C", status="skipped")
        _create_article(1, 1, 101)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "1/3 generated" in output
        assert "0 pending" in output
        assert "2 skipped" in output

    def test_cost_display(self, clean_wiki_db: Any) -> None:
        """Cost is displayed with estimated remaining."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _create_topic(3, "Topic C")
        _create_article(1, 1, 101, cost_usd=0.50, input_tokens=5000, output_tokens=2000)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "$0.50" in output
        # 2 pending * $0.50 avg = $1.00 estimated remaining
        assert "Est. remaining: $1.00" in output

    def test_no_est_remaining_when_all_done(self, clean_wiki_db: Any) -> None:
        """No estimated remaining cost when all topics are generated."""
        _create_topic(1, "Topic A")
        _create_article(1, 1, 101, cost_usd=0.25)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "Est. remaining" not in output

    def test_json_output_structure(self, clean_wiki_db: Any) -> None:
        """JSON output has all expected fields with correct values."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _create_topic(3, "Topic C", status="skipped")
        _create_article(1, 1, 101, cost_usd=0.30, input_tokens=3000, output_tokens=1500)

        result = runner.invoke(app, ["maintain", "wiki", "progress", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["total_topics"] == 3
        assert data["generated"] == 1
        assert data["pending"] == 1
        assert data["skipped"] == 1
        assert data["percent_complete"] == 33.3
        assert data["cost_usd"] == 0.3
        assert data["avg_cost_per_article"] == 0.3
        assert data["est_remaining_cost_usd"] == 0.30
        assert data["total_input_tokens"] == 3000
        assert data["total_output_tokens"] == 1500

    def test_tokens_display(self, clean_wiki_db: Any) -> None:
        """Token counts are shown."""
        _create_topic(1, "Topic A")
        _create_article(1, 1, 101, input_tokens=10000, output_tokens=5000)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        assert "10,000 in" in output
        assert "5,000 out" in output

    def test_progress_bar_present(self, clean_wiki_db: Any) -> None:
        """Progress bar characters appear in output."""
        _create_topic(1, "Topic A")
        _create_topic(2, "Topic B")
        _create_article(1, 1, 101)

        result = runner.invoke(app, ["maintain", "wiki", "progress"])
        assert result.exit_code == 0
        output = _strip_ansi(result.output)
        # Progress bar uses block chars
        assert "\u2588" in output or "\u2591" in output


class TestWikiProgressHelp:
    """Test help output."""

    def test_help(self) -> None:
        """Help text shows expected content."""
        result = runner.invoke(app, ["maintain", "wiki", "progress", "--help"])
        assert result.exit_code == 0
        assert "progress" in result.output.lower()
