"""Tests for the maintain gaps subcommand."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.commands._gaps import (
    _find_link_sinks,
    _find_orphan_docs,
    _find_project_imbalances,
    _find_stale_topics,
    _find_tag_gaps,
    analyze_gaps,
)
from emdx.database import db
from emdx.main import app

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_tables() -> Generator[None, None, None]:
    """Clean relevant tables before each test."""
    with db.get_connection() as conn:
        conn.execute("DELETE FROM document_links")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM tags")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM documents")
        conn.commit()
    yield


def _create_doc(
    conn: sqlite3.Connection,
    title: str,
    project: str | None = None,
    days_ago: int = 0,
) -> int:
    """Helper to create a document directly via SQL."""
    cursor = conn.execute(
        """
        INSERT INTO documents (title, content, project,
                               created_at, updated_at)
        VALUES (?, 'test content', ?,
                datetime('now', ? || ' days'),
                datetime('now', ? || ' days'))
        """,
        (title, project, f"-{days_ago}", f"-{days_ago}"),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _add_tag(
    conn: sqlite3.Connection,
    doc_id: int,
    tag_name: str,
) -> None:
    """Helper to add a tag to a document."""
    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    row = cursor.fetchone()
    if row:
        tag_id = row[0]
    else:
        cursor = conn.execute(
            "INSERT INTO tags (name, usage_count) VALUES (?, 0)",
            (tag_name,),
        )
        tag_id = cursor.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
        (doc_id, tag_id),
    )
    conn.commit()


def _create_link(
    conn: sqlite3.Connection,
    source_id: int,
    target_id: int,
) -> None:
    """Helper to create a document link."""
    conn.execute(
        "INSERT OR IGNORE INTO document_links "
        "(source_doc_id, target_doc_id, similarity_score, link_type) "
        "VALUES (?, ?, 0.8, 'auto')",
        (source_id, target_id),
    )
    conn.commit()


def _create_task(
    conn: sqlite3.Connection,
    title: str,
    project: str | None = None,
    status: str = "open",
) -> int:
    """Helper to create a task."""
    cursor = conn.execute(
        "INSERT INTO tasks (title, project, status) VALUES (?, ?, ?)",
        (title, project, status),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


class TestTagGaps:
    """Tests for tag coverage gap detection."""

    def test_no_tags_returns_empty(self) -> None:
        result = _find_tag_gaps(10)
        assert result == []

    def test_uniform_tags_no_gaps(self) -> None:
        """Tags with similar counts produce no gaps."""
        with db.get_connection() as conn:
            for i in range(3):
                doc_id = _create_doc(conn, f"Doc {i}")
                _add_tag(conn, doc_id, "alpha")
                _add_tag(conn, doc_id, "beta")

        result = _find_tag_gaps(10)
        assert result == []

    def test_sparse_tag_detected(self) -> None:
        """Tag with much fewer docs than average is flagged."""
        with db.get_connection() as conn:
            # Create 5 docs with "popular" tag
            for i in range(5):
                doc_id = _create_doc(conn, f"Popular {i}")
                _add_tag(conn, doc_id, "popular")

            # Create 5 docs with "also-popular" tag
            for i in range(5):
                doc_id = _create_doc(conn, f"Also Popular {i}")
                _add_tag(conn, doc_id, "also-popular")

            # Create 1 doc with "sparse" tag
            doc_id = _create_doc(conn, "Sparse Doc")
            _add_tag(conn, doc_id, "sparse")

        result = _find_tag_gaps(10)
        assert len(result) >= 1
        tag_names = [g["tag_name"] for g in result]
        assert "sparse" in tag_names

    def test_severity_high_for_single_doc(self) -> None:
        """Tags with only 1 doc get high severity."""
        with db.get_connection() as conn:
            for i in range(6):
                doc_id = _create_doc(conn, f"Doc {i}")
                _add_tag(conn, doc_id, "common")
            doc_id = _create_doc(conn, "Lonely")
            _add_tag(conn, doc_id, "rare")

        result = _find_tag_gaps(10)
        rare_gaps = [g for g in result if g["tag_name"] == "rare"]
        assert len(rare_gaps) == 1
        assert rare_gaps[0]["severity"] == "high"

    def test_top_limits_results(self) -> None:
        """--top parameter limits output."""
        with db.get_connection() as conn:
            # Create many common docs
            for i in range(10):
                doc_id = _create_doc(conn, f"Common {i}")
                _add_tag(conn, doc_id, "common")
            # Create several sparse tags
            for i in range(5):
                doc_id = _create_doc(conn, f"Sparse {i}")
                _add_tag(conn, doc_id, f"sparse-{i}")

        result = _find_tag_gaps(2)
        assert len(result) <= 2


class TestLinkSinks:
    """Tests for link dead-end detection."""

    def test_no_links_returns_empty(self) -> None:
        result = _find_link_sinks(10)
        assert result == []

    def test_sink_detected(self) -> None:
        """Document with 2+ incoming but 0 outgoing is flagged."""
        with db.get_connection() as conn:
            sink = _create_doc(conn, "Sink Doc")
            src1 = _create_doc(conn, "Source 1")
            src2 = _create_doc(conn, "Source 2")
            _create_link(conn, src1, sink)
            _create_link(conn, src2, sink)

        result = _find_link_sinks(10)
        assert len(result) == 1
        assert result[0]["doc_id"] == sink
        assert result[0]["incoming_count"] == 2
        assert result[0]["outgoing_count"] == 0

    def test_bidirectional_not_sink(self) -> None:
        """Doc with both incoming and outgoing is not a sink."""
        with db.get_connection() as conn:
            a = _create_doc(conn, "Doc A")
            b = _create_doc(conn, "Doc B")
            c = _create_doc(conn, "Doc C")
            _create_link(conn, a, b)
            _create_link(conn, c, b)
            _create_link(conn, b, a)  # outgoing from b

        result = _find_link_sinks(10)
        assert len(result) == 0

    def test_single_incoming_not_sink(self) -> None:
        """Doc with only 1 incoming link is not flagged (threshold 2)."""
        with db.get_connection() as conn:
            target = _create_doc(conn, "Target")
            source = _create_doc(conn, "Source")
            _create_link(conn, source, target)

        result = _find_link_sinks(10)
        assert len(result) == 0

    def test_high_severity_for_many_incoming(self) -> None:
        """5+ incoming links gets high severity."""
        with db.get_connection() as conn:
            sink = _create_doc(conn, "Big Sink")
            for i in range(5):
                src = _create_doc(conn, f"Source {i}")
                _create_link(conn, src, sink)

        result = _find_link_sinks(10)
        assert len(result) == 1
        assert result[0]["severity"] == "high"


class TestOrphanDocs:
    """Tests for orphan document detection."""

    def test_no_docs_returns_empty(self) -> None:
        result = _find_orphan_docs(10)
        assert result == []

    def test_orphan_detected(self) -> None:
        """Document with no links is flagged."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Lonely Doc", project="test")

        result = _find_orphan_docs(10)
        assert len(result) == 1
        assert result[0]["doc_id"] == doc_id
        assert result[0]["doc_title"] == "Lonely Doc"
        assert result[0]["project"] == "test"
        assert result[0]["severity"] == "low"

    def test_linked_doc_not_orphan(self) -> None:
        """Document with links is not flagged."""
        with db.get_connection() as conn:
            a = _create_doc(conn, "Doc A")
            b = _create_doc(conn, "Doc B")
            _create_link(conn, a, b)

        result = _find_orphan_docs(10)
        assert len(result) == 0

    def test_target_link_not_orphan(self) -> None:
        """Document that is a target of a link is not orphan."""
        with db.get_connection() as conn:
            a = _create_doc(conn, "Source")
            b = _create_doc(conn, "Target")
            _create_link(conn, a, b)

        # Both a and b are in links, so neither is orphan
        result = _find_orphan_docs(10)
        assert len(result) == 0

    def test_deleted_docs_excluded(self) -> None:
        """Soft-deleted documents are not reported as orphans."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Deleted Doc")
            conn.execute(
                "UPDATE documents SET is_deleted = TRUE WHERE id = ?",
                (doc_id,),
            )
            conn.commit()

        result = _find_orphan_docs(10)
        assert len(result) == 0

    def test_top_limits_results(self) -> None:
        """--top parameter limits output."""
        with db.get_connection() as conn:
            for i in range(5):
                _create_doc(conn, f"Orphan {i}")

        result = _find_orphan_docs(2)
        assert len(result) == 2


class TestStaleTopics:
    """Tests for stale topic detection."""

    def test_no_tags_returns_empty(self) -> None:
        result = _find_stale_topics(60, 10)
        assert result == []

    def test_fresh_topic_not_stale(self) -> None:
        """Tag with recent docs is not stale."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Fresh Doc", days_ago=5)
            _add_tag(conn, doc_id, "fresh-topic")

        result = _find_stale_topics(60, 10)
        assert len(result) == 0

    def test_stale_topic_detected(self) -> None:
        """Tag where newest doc is >60 days old is flagged."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Old Doc", days_ago=90)
            _add_tag(conn, doc_id, "old-topic")

        result = _find_stale_topics(60, 10)
        assert len(result) == 1
        assert result[0]["tag_name"] == "old-topic"
        assert result[0]["newest_doc_days"] >= 89

    def test_mixed_fresh_and_stale(self) -> None:
        """Tag with one fresh doc among old ones is not stale."""
        with db.get_connection() as conn:
            old_id = _create_doc(conn, "Old Doc", days_ago=90)
            _add_tag(conn, old_id, "mixed-topic")
            fresh_id = _create_doc(conn, "Fresh Doc", days_ago=5)
            _add_tag(conn, fresh_id, "mixed-topic")

        result = _find_stale_topics(60, 10)
        assert len(result) == 0

    def test_severity_high_over_120_days(self) -> None:
        """Topics stale >120 days get high severity."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Very Old Doc", days_ago=150)
            _add_tag(conn, doc_id, "ancient-topic")

        result = _find_stale_topics(60, 10)
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_custom_stale_days(self) -> None:
        """Custom stale_days threshold works."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Aging Doc", days_ago=40)
            _add_tag(conn, doc_id, "aging-topic")

        # 60-day threshold -- not stale
        assert len(_find_stale_topics(60, 10)) == 0
        # 30-day threshold -- stale
        assert len(_find_stale_topics(30, 10)) == 1


class TestProjectImbalances:
    """Tests for project doc/task imbalance detection."""

    def test_no_projects_returns_empty(self) -> None:
        result = _find_project_imbalances(10)
        assert result == []

    def test_balanced_project_not_flagged(self) -> None:
        """Project with reasonable doc/task ratio is fine."""
        with db.get_connection() as conn:
            _create_doc(conn, "Doc 1", project="my-project")
            _create_doc(conn, "Doc 2", project="my-project")
            _create_task(conn, "Task 1", project="my-project")

        result = _find_project_imbalances(10)
        assert len(result) == 0

    def test_imbalanced_project_detected(self) -> None:
        """Project with many tasks but few docs is flagged."""
        with db.get_connection() as conn:
            _create_doc(conn, "Solo Doc", project="busy-project")
            for i in range(10):
                _create_task(conn, f"Task {i}", project="busy-project")

        result = _find_project_imbalances(10)
        assert len(result) == 1
        assert result[0]["project"] == "busy-project"
        assert result[0]["doc_count"] == 1
        assert result[0]["task_count"] == 10
        assert result[0]["ratio"] < 0.5

    def test_project_without_tasks_not_flagged(self) -> None:
        """Project with docs but no tasks is not flagged."""
        with db.get_connection() as conn:
            _create_doc(conn, "Doc", project="docs-only")

        result = _find_project_imbalances(10)
        assert len(result) == 0

    def test_null_project_excluded(self) -> None:
        """Documents and tasks with null project are excluded."""
        with db.get_connection() as conn:
            _create_doc(conn, "No Project Doc")
            _create_task(conn, "No Project Task")

        result = _find_project_imbalances(10)
        assert len(result) == 0


class TestAnalyzeGaps:
    """Tests for the full gap analysis."""

    def test_empty_db_no_gaps(self) -> None:
        report = analyze_gaps(top=10, stale_days=60)
        assert report["tag_gaps"] == []
        assert report["link_sinks"] == []
        assert report["orphan_docs"] == []
        assert report["stale_topics"] == []
        assert report["project_imbalances"] == []

    def test_mixed_gaps(self) -> None:
        """Multiple gap types detected together."""
        with db.get_connection() as conn:
            # Orphan doc
            _create_doc(conn, "Lonely Doc")

            # Stale topic
            old_doc = _create_doc(conn, "Old Topic Doc", days_ago=90)
            _add_tag(conn, old_doc, "stale-tag")

        report = analyze_gaps(top=10, stale_days=60)
        assert len(report["orphan_docs"]) >= 1
        assert len(report["stale_topics"]) == 1


class TestGapsCLI:
    """Integration tests for the gaps CLI command."""

    def test_gaps_help(self) -> None:
        """Gaps command shows help."""
        result = runner.invoke(app, ["maintain", "gaps", "--help"])
        assert result.exit_code == 0
        plain = _strip_ansi(result.output)
        assert "gaps" in plain.lower()
        assert "--top" in plain

    def test_gaps_no_results(self) -> None:
        """No gaps shows friendly message."""
        result = runner.invoke(app, ["maintain", "gaps"])
        assert result.exit_code == 0
        assert "No knowledge gaps detected" in result.output

    def test_gaps_with_orphan_doc(self) -> None:
        """Orphan doc appears in output."""
        with db.get_connection() as conn:
            _create_doc(conn, "Isolated Document")

        result = runner.invoke(app, ["maintain", "gaps"])
        assert result.exit_code == 0
        assert "Isolated Document" in result.output
        assert "Orphan Documents" in result.output

    def test_gaps_custom_top(self) -> None:
        """Custom --top parameter works."""
        with db.get_connection() as conn:
            for i in range(5):
                _create_doc(conn, f"Orphan {i}")

        result = runner.invoke(app, ["maintain", "gaps", "--top", "2"])
        assert result.exit_code == 0
        assert "Orphan Documents" in result.output

    def test_gaps_json_output(self) -> None:
        """JSON output produces valid JSON."""
        result = runner.invoke(app, ["maintain", "gaps", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tag_gaps" in data
        assert "link_sinks" in data
        assert "orphan_docs" in data
        assert "stale_topics" in data
        assert "project_imbalances" in data

    def test_gaps_json_with_data(self) -> None:
        """JSON output includes gap data."""
        with db.get_connection() as conn:
            _create_doc(conn, "JSON Test Doc")

        result = runner.invoke(app, ["maintain", "gaps", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["orphan_docs"]) >= 1
        titles = [d["doc_title"] for d in data["orphan_docs"]]
        assert "JSON Test Doc" in titles

    def test_gaps_stale_days_option(self) -> None:
        """Custom --stale-days threshold works."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Semi-Stale Doc", days_ago=40)
            _add_tag(conn, doc_id, "semi-stale")

        # Default 60 days -- not stale
        result = runner.invoke(app, ["maintain", "gaps"])
        assert "Stale Topics" not in result.output

        # 30-day threshold -- stale
        result = runner.invoke(
            app,
            ["maintain", "gaps", "--stale-days", "30"],
        )
        assert "Stale Topics" in result.output
        assert "semi-stale" in result.output
