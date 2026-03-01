"""Tests for the maintain drift subcommand."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.commands._drift import (
    _find_burst_epics,
    _find_orphaned_active_tasks,
    _find_stale_epics,
    _find_stale_linked_docs,
    analyze_drift,
)
from emdx.database import db
from emdx.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_tasks() -> Generator[None, None, None]:
    """Clean tasks and documents tables before each test."""
    with db.get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM documents")
        conn.commit()
    yield


def _ensure_category(conn: sqlite3.Connection, key: str = "TEST") -> None:
    """Ensure a category exists for FK constraints."""
    conn.execute(
        """
        INSERT OR IGNORE INTO categories (key, name)
        VALUES (?, ?)
        """,
        (key, key),
    )
    conn.commit()


def _create_epic(
    conn: sqlite3.Connection,
    title: str,
    epic_key: str = "TEST",
    status: str = "open",
) -> int:
    """Helper to create an epic task directly via SQL."""
    _ensure_category(conn, epic_key)
    cursor = conn.execute(
        """
        INSERT INTO tasks (title, type, epic_key, status)
        VALUES (?, 'epic', ?, ?)
        """,
        (title, epic_key, status),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _create_task(
    conn: sqlite3.Connection,
    title: str,
    parent_task_id: int | None = None,
    status: str = "open",
    epic_key: str | None = None,
    days_ago: int = 0,
    source_doc_id: int | None = None,
) -> int:
    """Helper to create a task directly via SQL."""
    if epic_key:
        _ensure_category(conn, epic_key)
    cursor = conn.execute(
        """
        INSERT INTO tasks (
            title, parent_task_id, status, epic_key,
            created_at, updated_at,
            source_doc_id
        )
        VALUES (
            ?, ?, ?, ?,
            datetime('now', ? || ' days'),
            datetime('now', ? || ' days'),
            ?
        )
        """,
        (
            title,
            parent_task_id,
            status,
            epic_key,
            f"-{days_ago}",
            f"-{days_ago}",
            source_doc_id,
        ),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _create_doc(conn: sqlite3.Connection, title: str) -> int:
    """Helper to create a document directly via SQL."""
    cursor = conn.execute(
        "INSERT INTO documents (title, content) VALUES (?, ?)",
        (title, "test content"),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


class TestStaleEpics:
    """Tests for stale epic detection."""

    def test_no_epics_returns_empty(self) -> None:
        result = _find_stale_epics(30)
        assert result == []

    def test_active_epic_not_stale(self) -> None:
        """Epic with recent child activity is not stale."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Active Epic")
            _create_task(
                conn,
                "Recent task",
                parent_task_id=epic_id,
                days_ago=5,
            )

        result = _find_stale_epics(30)
        assert len(result) == 0

    def test_stale_epic_detected(self) -> None:
        """Epic with old child activity is detected."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Stale Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

        result = _find_stale_epics(30)
        assert len(result) == 1
        assert result[0]["title"] == "Stale Epic"
        assert result[0]["days_silent"] >= 44

    def test_done_epic_not_included(self) -> None:
        """Completed epics are excluded."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Done Epic", status="done")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

        result = _find_stale_epics(30)
        assert len(result) == 0

    def test_custom_days_threshold(self) -> None:
        """Custom days threshold works."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Test Epic")
            _create_task(
                conn,
                "Task",
                parent_task_id=epic_id,
                days_ago=10,
            )

        # Should not be stale at 30 days
        assert len(_find_stale_epics(30)) == 0
        # Should be stale at 7 days
        assert len(_find_stale_epics(7)) == 1

    def test_only_open_children_counted(self) -> None:
        """Only open/active/blocked children trigger staleness."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Mixed Epic")
            # All children are done -- no open tasks
            _create_task(
                conn,
                "Done task",
                parent_task_id=epic_id,
                status="done",
                days_ago=45,
            )

        result = _find_stale_epics(30)
        assert len(result) == 0


class TestOrphanedActiveTasks:
    """Tests for orphaned active task detection."""

    def test_no_tasks_returns_empty(self) -> None:
        result = _find_orphaned_active_tasks(30)
        assert result == []

    def test_recently_active_task_not_orphaned(self) -> None:
        """Task active and recently updated is not orphaned."""
        with db.get_connection() as conn:
            _create_task(
                conn,
                "Active task",
                status="active",
                days_ago=3,
            )

        result = _find_orphaned_active_tasks(30)
        assert len(result) == 0

    def test_orphaned_active_task_detected(self) -> None:
        """Task active but idle is detected."""
        with db.get_connection() as conn:
            _create_task(
                conn,
                "Orphaned task",
                status="active",
                days_ago=20,
            )

        result = _find_orphaned_active_tasks(30)
        assert len(result) == 1
        assert result[0]["title"] == "Orphaned task"
        assert result[0]["days_idle"] >= 19

    def test_open_task_not_included(self) -> None:
        """Open (not active) tasks are not included."""
        with db.get_connection() as conn:
            _create_task(
                conn,
                "Open task",
                status="open",
                days_ago=60,
            )

        result = _find_orphaned_active_tasks(30)
        assert len(result) == 0


class TestStaleLinkedDocs:
    """Tests for stale linked docs detection."""

    def test_no_linked_docs_returns_empty(self) -> None:
        result = _find_stale_linked_docs(30)
        assert result == []

    def test_stale_source_doc_detected(self) -> None:
        """Doc linked as source to a stale task is detected."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Source Doc")
            _create_task(
                conn,
                "Stale task",
                status="active",
                days_ago=40,
                source_doc_id=doc_id,
            )

        result = _find_stale_linked_docs(30)
        assert len(result) == 1
        assert result[0]["doc_title"] == "Source Doc"
        assert result[0]["link_type"] == "source"

    def test_recent_task_docs_not_included(self) -> None:
        """Docs linked to recent tasks are not included."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Fresh Doc")
            _create_task(
                conn,
                "Fresh task",
                status="open",
                days_ago=5,
                source_doc_id=doc_id,
            )

        result = _find_stale_linked_docs(30)
        assert len(result) == 0

    def test_done_task_docs_not_included(self) -> None:
        """Docs linked to completed tasks are not included."""
        with db.get_connection() as conn:
            doc_id = _create_doc(conn, "Done Doc")
            _create_task(
                conn,
                "Done task",
                status="done",
                days_ago=45,
                source_doc_id=doc_id,
            )

        result = _find_stale_linked_docs(30)
        assert len(result) == 0


class TestBurstEpics:
    """Tests for burst-then-stop epic detection."""

    def test_no_epics_returns_empty(self) -> None:
        result = _find_burst_epics(30)
        assert result == []

    def test_burst_epic_detected(self) -> None:
        """Epic with many tasks in short window then silence."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Burst Epic")
            # Create 4 tasks all on the same day, 45 days ago
            for i in range(4):
                _create_task(
                    conn,
                    f"Task {i}",
                    parent_task_id=epic_id,
                    days_ago=45,
                )

        result = _find_burst_epics(30)
        assert len(result) == 1
        assert result[0]["title"] == "Burst Epic"
        assert result[0]["total_tasks"] == 4

    def test_gradual_epic_not_burst(self) -> None:
        """Epic with tasks spread over weeks is not a burst."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Gradual Epic")
            # Create tasks spread across 30 days
            for i in range(4):
                _create_task(
                    conn,
                    f"Task {i}",
                    parent_task_id=epic_id,
                    days_ago=45 + (i * 10),
                )

        result = _find_burst_epics(30)
        # burst_days would be ~30, exceeding 7-day window
        assert len(result) == 0

    def test_too_few_tasks_not_burst(self) -> None:
        """Epic with only 2 tasks is not detected as burst."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Small Epic")
            for i in range(2):
                _create_task(
                    conn,
                    f"Task {i}",
                    parent_task_id=epic_id,
                    days_ago=45,
                )

        result = _find_burst_epics(30)
        assert len(result) == 0


class TestAnalyzeDrift:
    """Tests for the full drift analysis."""

    def test_empty_db_no_drift(self) -> None:
        report = analyze_drift(days=30)
        assert report["stale_epics"] == []
        assert report["orphaned_tasks"] == []
        assert report["stale_linked_docs"] == []
        assert report["burst_epics"] == []

    def test_mixed_drift(self) -> None:
        """Multiple drift types detected together."""
        with db.get_connection() as conn:
            # Stale epic
            epic_id = _create_epic(conn, "Stale Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

            # Orphaned active task
            _create_task(
                conn,
                "Orphaned",
                status="active",
                days_ago=20,
            )

        report = analyze_drift(days=30)
        assert len(report["stale_epics"]) == 1
        assert len(report["orphaned_tasks"]) == 1


class TestDriftCLI:
    """Integration tests for the drift CLI command."""

    def test_drift_help(self) -> None:
        """Drift command shows help."""
        import re

        result = runner.invoke(app, ["maintain", "drift", "--help"])
        assert result.exit_code == 0
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "drift" in plain.lower()
        assert "--days" in plain

    def test_drift_no_results(self) -> None:
        """No drift shows friendly message."""
        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        assert "No drift detected" in result.output

    def test_drift_with_stale_epic(self) -> None:
        """Stale epic appears in output."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Forgotten Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

        result = runner.invoke(app, ["maintain", "drift"])
        assert result.exit_code == 0
        assert "Forgotten Epic" in result.output
        assert "Stale Epics" in result.output

    def test_drift_custom_days(self) -> None:
        """Custom --days threshold works."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "Semi-Stale Epic")
            _create_task(
                conn,
                "Task",
                parent_task_id=epic_id,
                days_ago=10,
            )

        # Default 30 days -- not stale
        result = runner.invoke(app, ["maintain", "drift"])
        assert "No drift detected" in result.output

        # 7 days threshold -- stale
        result = runner.invoke(app, ["maintain", "drift", "--days", "7"])
        assert "Semi-Stale Epic" in result.output

    def test_drift_json_output(self) -> None:
        """JSON output produces valid JSON."""
        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "stale_epics" in data
        assert "orphaned_tasks" in data
        assert "stale_linked_docs" in data
        assert "burst_epics" in data

    def test_drift_json_with_data(self) -> None:
        """JSON output includes drift data."""
        with db.get_connection() as conn:
            epic_id = _create_epic(conn, "JSON Epic")
            _create_task(
                conn,
                "Old task",
                parent_task_id=epic_id,
                days_ago=45,
            )

        result = runner.invoke(app, ["maintain", "drift", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["stale_epics"]) == 1
        assert data["stale_epics"][0]["title"] == "JSON Epic"
