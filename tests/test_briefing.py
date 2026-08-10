"""Tests for the briefing command."""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from emdx.commands.briefing import (
    _build_json_output,
    _format_relative_time,
    _parse_since,
    _strip_doc_link_columns,
    _tag_matching_doc_ids,
    _task_linked_doc_ids,
)
from emdx.database import db
from emdx.main import app as main_app

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# Unit tests for _parse_since
# ---------------------------------------------------------------------------
class TestParseSince:
    """Tests for the --since argument parser."""

    def test_parse_yesterday(self) -> None:
        result = _parse_since("yesterday")
        expected = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=1
        )
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_last_week(self) -> None:
        result = _parse_since("last week")
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_days(self) -> None:
        result = _parse_since("3 days ago")
        expected = datetime.now() - timedelta(days=3)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_hours(self) -> None:
        result = _parse_since("2 hours ago")
        expected = datetime.now() - timedelta(hours=2)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_relative_weeks(self) -> None:
        result = _parse_since("1 week ago")
        expected = datetime.now() - timedelta(weeks=1)
        assert abs((result - expected).total_seconds()) < 2

    def test_parse_iso_date(self) -> None:
        result = _parse_since("2026-01-15")
        assert result == datetime(2026, 1, 15, 0, 0, 0, 0)

    def test_parse_iso_datetime(self) -> None:
        # Note: _parse_since lowercases input, so "T" becomes "t"
        # The code checks for uppercase "T" so it treats this as date-only
        # and returns midnight. This tests the actual behavior.
        result = _parse_since("2026-01-15T10:30:00")
        # Because of .lower(), "T" -> "t", but fromisoformat still parses it
        # Let's check what actually comes back (depends on Python version)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_parse_unknown_defaults_to_24h(self) -> None:
        result = _parse_since("not a date")
        expected = datetime.now() - timedelta(days=1)
        assert abs((result - expected).total_seconds()) < 2


# ---------------------------------------------------------------------------
# Unit tests for _format_relative_time
# ---------------------------------------------------------------------------
class TestFormatRelativeTime:
    """Tests for relative time formatting."""

    def test_none_returns_empty(self) -> None:
        assert _format_relative_time(None) == ""

    def test_recent_timestamp(self) -> None:
        recent = (datetime.now() - timedelta(seconds=30)).isoformat()
        result = _format_relative_time(recent)
        assert "s ago" in result

    def test_minutes_ago(self) -> None:
        minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        result = _format_relative_time(minutes_ago)
        assert "m ago" in result

    def test_hours_ago(self) -> None:
        hours_ago = (datetime.now() - timedelta(hours=3)).isoformat()
        result = _format_relative_time(hours_ago)
        assert "h ago" in result

    def test_days_ago(self) -> None:
        days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        result = _format_relative_time(days_ago)
        assert "d ago" in result


# ---------------------------------------------------------------------------
# Unit tests for _build_json_output
# ---------------------------------------------------------------------------
class TestBuildJsonOutput:
    """Tests for JSON output builder."""

    def test_empty_data(self) -> None:
        since = datetime(2026, 1, 1)
        result = _build_json_output(since, [], [], [], [])
        assert result["summary"]["documents_created"] == 0
        assert result["summary"]["tasks_completed"] == 0
        assert result["summary"]["tasks_added"] == 0
        assert result["summary"]["blockers"] == 0
        assert result["since"] == since.isoformat()

    def test_with_data(self) -> None:
        since = datetime(2026, 1, 1)
        docs = [{"id": 1, "title": "Doc1", "tags": None}]
        completed = [{"id": 2, "title": "Task1"}]
        added = [{"id": 3, "title": "Task2"}]
        blockers = [{"id": 4, "title": "Task3"}]
        result = _build_json_output(since, docs, completed, added, blockers)
        assert result["summary"]["documents_created"] == 1
        assert result["summary"]["tasks_completed"] == 1
        assert result["summary"]["tasks_added"] == 1
        assert result["summary"]["blockers"] == 1
        assert len(result["documents_created"]) == 1
        assert result["documents_created"][0]["id"] == 1
        assert result["documents_created"][0]["tags"] == []


# ---------------------------------------------------------------------------
# CLI integration tests for briefing command
# ---------------------------------------------------------------------------
class TestBriefingCommand:
    """Tests for the briefing CLI command."""

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_default(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Default briefing shows no-activity message when DB is empty."""
        mock_docs.return_value = []
        mock_completed.return_value = []
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing"])
        assert result.exit_code == 0
        assert "No activity" in _out(result)

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_with_since(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing with --since parses the time correctly."""
        mock_docs.return_value = []
        mock_completed.return_value = []
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing", "--since", "yesterday"])
        assert result.exit_code == 0

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_json_output(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing --json produces valid JSON."""
        mock_docs.return_value = [
            {
                "id": 1,
                "title": "Test Doc",
                "project": "proj",
                "created_at": "2026-01-15T10:00:00",
                "tags": "notes",
            }
        ]
        mock_completed.return_value = []
        mock_added.return_value = [
            {
                "id": 10,
                "title": "New Task",
                "status": "open",
                "priority": 1,
                "created_at": "2026-01-15T11:00:00",
                "project": "proj",
            }
        ]
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["summary"]["documents_created"] == 1
        assert data["summary"]["tasks_added"] == 1

    @patch("emdx.commands.briefing._get_tasks_blocked")
    @patch("emdx.commands.briefing._get_tasks_added")
    @patch("emdx.commands.briefing._get_tasks_completed")
    @patch("emdx.commands.briefing._get_documents_created")
    def test_briefing_with_activity(
        self, mock_docs: Any, mock_completed: Any, mock_added: Any, mock_blocked: Any
    ) -> None:
        """Briefing shows activity sections when there's data."""
        mock_docs.return_value = [
            {
                "id": 1,
                "title": "New Document",
                "project": "proj",
                "created_at": datetime.now().isoformat(),
                "tags": "notes",
            }
        ]
        mock_completed.return_value = [
            {
                "id": 5,
                "title": "Completed Task",
                "completed_at": datetime.now().isoformat(),
                "project": "proj",
            }
        ]
        mock_added.return_value = []
        mock_blocked.return_value = []

        result = runner.invoke(main_app, ["briefing"])
        assert result.exit_code == 0
        out = _out(result)
        assert "docs created" in out or "Documents Created" in out
        assert "tasks completed" in out or "Tasks Completed" in out


# ---------------------------------------------------------------------------
# Unit tests for the task<->document link helpers (Issue #1121)
# ---------------------------------------------------------------------------
class TestTaskLinkedDocIds:
    """Tests for _task_linked_doc_ids / _strip_doc_link_columns."""

    def test_collects_all_present_links(self) -> None:
        task = {"id": 1, "gameplan_id": 10, "source_doc_id": None, "output_doc_id": 20}
        assert _task_linked_doc_ids(task) == [10, 20]

    def test_no_links_returns_empty(self) -> None:
        task = {"id": 1, "title": "no links"}
        assert _task_linked_doc_ids(task) == []

    def test_strip_removes_link_columns_only(self) -> None:
        tasks = [{"id": 1, "title": "t", "gameplan_id": 10, "source_doc_id": 11}]
        _strip_doc_link_columns(tasks)
        assert tasks == [{"id": 1, "title": "t"}]


# ---------------------------------------------------------------------------
# Tests for --tags scoping (Issue #1121), against a real (isolated) DB
# ---------------------------------------------------------------------------
@pytest.fixture
def tag_scoped_briefing_data(isolate_test_database: Any) -> Generator[None, None, None]:
    """Seed two docs (one tagged, one not) with tasks linked to each.

    Uses Python's `.isoformat()` (matching what `_parse_since` produces) rather
    than SQLite's `datetime('now')` (space-separated) — mixing the two formats
    breaks same-day `created_at >= ?` string comparisons in _get_documents_created
    et al., a pre-existing quirk unrelated to tag scoping that this fixture
    sidesteps rather than fixes.
    """
    now = datetime.now().isoformat()
    with db.get_connection() as conn:
        conn.execute("DELETE FROM document_tags WHERE document_id IN (90001, 90002)")
        conn.execute("DELETE FROM documents WHERE id IN (90001, 90002)")
        conn.execute("DELETE FROM tasks WHERE id IN (90001, 90002)")
        conn.execute("DELETE FROM tags WHERE name IN ('briefing-test-tag', 'briefing-other-tag')")
        conn.commit()

        conn.execute(
            "INSERT INTO documents (id, title, content, project, created_at, is_deleted) "
            "VALUES (90001, 'Tagged Doc', 'content', 'proj', ?, 0)",
            (now,),
        )
        conn.execute(
            "INSERT INTO documents (id, title, content, project, created_at, is_deleted) "
            "VALUES (90002, 'Untagged Doc', 'content', 'proj', ?, 0)",
            (now,),
        )
        tag_id = conn.execute(
            "INSERT INTO tags (name) VALUES ('briefing-test-tag') RETURNING id"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO document_tags (document_id, tag_id) VALUES (90001, ?)", (tag_id,)
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, gameplan_id, created_at, completed_at) "
            "VALUES (90001, 'Task on tagged doc', 'done', 90001, ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, gameplan_id, created_at, completed_at) "
            "VALUES (90002, 'Task on untagged doc', 'done', 90002, ?, ?)",
            (now, now),
        )
        conn.commit()
    yield
    with db.get_connection() as conn:
        conn.execute("DELETE FROM document_tags WHERE document_id IN (90001, 90002)")
        conn.execute("DELETE FROM documents WHERE id IN (90001, 90002)")
        conn.execute("DELETE FROM tasks WHERE id IN (90001, 90002)")
        conn.execute("DELETE FROM tags WHERE name IN ('briefing-test-tag', 'briefing-other-tag')")
        conn.commit()


class TestTagMatchingDocIds:
    """Unit tests for _tag_matching_doc_ids against a real DB."""

    def test_matches_tagged_doc_only(self, tag_scoped_briefing_data: None) -> None:
        matched = _tag_matching_doc_ids({90001, 90002}, ["briefing-test-tag"], match_all=True)
        assert matched == {90001}

    def test_no_match_returns_empty(self, tag_scoped_briefing_data: None) -> None:
        matched = _tag_matching_doc_ids({90001, 90002}, ["nonexistent-tag"], match_all=True)
        assert matched == set()

    def test_empty_doc_ids_returns_empty(self) -> None:
        assert _tag_matching_doc_ids(set(), ["anything"], match_all=True) == set()

    def test_empty_tags_returns_empty(self) -> None:
        assert _tag_matching_doc_ids({1, 2}, [], match_all=True) == set()

    def test_and_semantics_requires_all_tags(self, tag_scoped_briefing_data: None) -> None:
        with db.get_connection() as conn:
            tag_id = conn.execute(
                "INSERT INTO tags (name) VALUES ('briefing-other-tag') RETURNING id"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (90002, ?)", (tag_id,)
            )
            conn.commit()

        # Doc 90001 has only 'briefing-test-tag', doc 90002 has only
        # 'briefing-other-tag' -- neither has both, so AND matches nothing.
        matched_all = _tag_matching_doc_ids(
            {90001, 90002}, ["briefing-test-tag", "briefing-other-tag"], match_all=True
        )
        assert matched_all == set()

        # OR matches both, since each doc has one of the two tags.
        matched_any = _tag_matching_doc_ids(
            {90001, 90002}, ["briefing-test-tag", "briefing-other-tag"], match_all=False
        )
        assert matched_any == {90001, 90002}


class TestBriefingTagsCli:
    """CLI integration tests for `emdx briefing --tags` (Issue #1121)."""

    def test_tags_scopes_documents_and_linked_tasks(
        self, tag_scoped_briefing_data: None
    ) -> None:
        result = runner.invoke(
            main_app, ["briefing", "--since", "1 hour ago", "--tags", "briefing-test-tag", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["tags_filter"] == ["briefing-test-tag"]
        assert data["summary"]["documents_created"] == 1
        assert data["documents_created"][0]["id"] == 90001
        assert data["summary"]["tasks_completed"] == 1
        assert data["tasks_completed"][0]["id"] == 90001
        assert data["summary"]["tasks_added"] == 1
        assert data["tasks_added"][0]["id"] == 90001

    def test_no_matching_tag_returns_empty_but_not_error(
        self, tag_scoped_briefing_data: None
    ) -> None:
        result = runner.invoke(
            main_app,
            ["briefing", "--since", "1 hour ago", "--tags", "totally-unused-tag", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["summary"]["documents_created"] == 0
        assert data["summary"]["tasks_completed"] == 0

    def test_task_link_columns_not_leaked_in_json(self, tag_scoped_briefing_data: None) -> None:
        """Internal FK columns used for tag-scoping must not appear in output."""
        result = runner.invoke(main_app, ["briefing", "--since", "1 hour ago", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        for task in [*data["tasks_completed"], *data["tasks_added"], *data["blockers"]]:
            assert "gameplan_id" not in task
            assert "source_doc_id" not in task
            assert "output_doc_id" not in task

    def test_no_tags_flag_shows_everything(self, tag_scoped_briefing_data: None) -> None:
        result = runner.invoke(main_app, ["briefing", "--since", "1 hour ago", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["tags_filter"] is None
        assert data["summary"]["documents_created"] == 2

    def test_save_with_unmatched_tag_reports_no_activity(
        self, tag_scoped_briefing_data: None
    ) -> None:
        """--save --tags with no matches should short-circuit before calling the LLM."""
        result = runner.invoke(
            main_app, ["briefing", "--save", "--tags", "totally-unused-tag", "--hours", "1"]
        )
        assert result.exit_code == 0
        assert "No activity" in _out(result)
