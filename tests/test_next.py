"""Tests for the emdx next command."""
# mypy: disable-error-code="no-untyped-def"

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.next import (
    _decide_next,
    _get_in_progress_tasks,
    _get_stale_gameplans,
    app,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_task(
    id=1,
    title="Test task",
    status="active",
    priority=5,
    parent_task_id=None,
    prompt=None,
    updated_at="2026-02-16T10:00:00",
):
    return {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "parent_task_id": parent_task_id,
        "prompt": prompt,
        "updated_at": updated_at,
    }


def _make_doc(
    id=100,
    title="My Gameplan",
    created_at="2026-01-01T10:00:00",
    project="emdx",
    access_count=3,
    tags="🗺️, 🟢",
):
    return {
        "id": id,
        "title": title,
        "created_at": created_at,
        "project": project,
        "access_count": access_count,
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# _decide_next tests
# ---------------------------------------------------------------------------


class TestDecideNext:
    """Test the priority decision logic."""

    @patch("emdx.commands.next._get_stale_gameplans", return_value=[])
    @patch("emdx.commands.next.get_ready_tasks", return_value=[])
    @patch("emdx.commands.next._get_in_progress_tasks")
    def test_in_progress_takes_priority(self, mock_ip, mock_ready, mock_stale):
        mock_ip.return_value = [_make_task(id=42, title="Fix auth bug")]
        action, reasoning, priority = _decide_next()
        assert action == "emdx task view 42"
        assert priority == "in_progress"
        assert "42" in reasoning

    @patch("emdx.commands.next._get_stale_gameplans", return_value=[])
    @patch("emdx.commands.next.get_ready_tasks")
    @patch("emdx.commands.next._get_in_progress_tasks", return_value=[])
    def test_ready_when_no_in_progress(self, mock_ip, mock_ready, mock_stale):
        mock_ready.return_value = [_make_task(id=7, title="Add tests", status="open")]
        action, reasoning, priority = _decide_next()
        assert action == "emdx task active 7"
        assert priority == "ready"

    @patch("emdx.commands.next._get_stale_gameplans")
    @patch("emdx.commands.next.get_ready_tasks", return_value=[])
    @patch("emdx.commands.next._get_in_progress_tasks", return_value=[])
    def test_stale_gameplan_when_no_tasks(self, mock_ip, mock_ready, mock_stale):
        mock_stale.return_value = [_make_doc(id=200, title="Old Plan")]
        action, reasoning, priority = _decide_next()
        assert action == "emdx view 200"
        assert priority == "stale_gameplan"

    @patch("emdx.commands.next._get_stale_gameplans", return_value=[])
    @patch("emdx.commands.next.get_ready_tasks", return_value=[])
    @patch("emdx.commands.next._get_in_progress_tasks", return_value=[])
    def test_fallback_to_prime(self, mock_ip, mock_ready, mock_stale):
        action, reasoning, priority = _decide_next()
        assert action == "emdx prime"
        assert priority == "fallback"

    @patch("emdx.commands.next._get_stale_gameplans")
    @patch("emdx.commands.next.get_ready_tasks")
    @patch("emdx.commands.next._get_in_progress_tasks")
    def test_in_progress_beats_ready(self, mock_ip, mock_ready, mock_stale):
        """In-progress tasks should always take priority over ready tasks."""
        mock_ip.return_value = [_make_task(id=1, title="Active")]
        mock_ready.return_value = [_make_task(id=2, title="Ready", status="open")]
        mock_stale.return_value = [_make_doc(id=3, title="Stale")]
        action, _, priority = _decide_next()
        assert action == "emdx task view 1"
        assert priority == "in_progress"


# ---------------------------------------------------------------------------
# _get_in_progress_tasks tests
# ---------------------------------------------------------------------------


class TestGetInProgressTasks:
    """Test the in-progress task query."""

    @patch("emdx.commands.next.db")
    def test_returns_active_non_delegate_tasks(self, mock_db):
        mock_conn = mock_db.get_connection.return_value.__enter__.return_value
        mock_cursor = mock_conn.execute.return_value
        mock_cursor.fetchall.return_value = [
            {"id": 1, "title": "Task A", "status": "active", "prompt": None},
        ]
        result = _get_in_progress_tasks()
        assert len(result) == 1
        assert result[0]["id"] == 1
        # Verify the SQL filters for active, non-delegate, top-level
        sql = mock_conn.execute.call_args[0][0]
        assert "status = 'active'" in sql
        assert "prompt IS NULL" in sql
        assert "parent_task_id IS NULL" in sql

    @patch("emdx.commands.next.db")
    def test_returns_empty_when_none(self, mock_db):
        mock_conn = mock_db.get_connection.return_value.__enter__.return_value
        mock_cursor = mock_conn.execute.return_value
        mock_cursor.fetchall.return_value = []
        result = _get_in_progress_tasks()
        assert result == []


# ---------------------------------------------------------------------------
# _get_stale_gameplans tests
# ---------------------------------------------------------------------------


class TestGetStaleGameplans:
    """Test stale gameplan detection."""

    @patch("emdx.commands.next.search_by_tags")
    def test_filters_by_age(self, mock_search):
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        new_date = datetime.now().isoformat()
        mock_search.return_value = [
            _make_doc(id=1, title="Old", created_at=old_date),
            _make_doc(id=2, title="New", created_at=new_date),
        ]
        result = _get_stale_gameplans()
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch("emdx.commands.next.search_by_tags")
    def test_empty_when_no_stale(self, mock_search):
        new_date = datetime.now().isoformat()
        mock_search.return_value = [
            _make_doc(id=1, created_at=new_date),
        ]
        result = _get_stale_gameplans()
        assert result == []

    @patch("emdx.commands.next.search_by_tags")
    def test_empty_when_no_gameplans(self, mock_search):
        mock_search.return_value = []
        result = _get_stale_gameplans()
        assert result == []

    @patch("emdx.commands.next.search_by_tags")
    def test_calls_with_correct_tags(self, mock_search):
        mock_search.return_value = []
        _get_stale_gameplans()
        mock_search.assert_called_once_with(
            ["gameplan", "active"],
            mode="all",
            prefix_match=False,
            limit=10,
        )


# ---------------------------------------------------------------------------
# CLI output tests
# ---------------------------------------------------------------------------


class TestNextCLI:
    """Test CLI output formatting."""

    @patch("emdx.commands.next.db")
    @patch("emdx.commands.next._decide_next")
    def test_text_output_action_to_stdout(self, mock_decide, mock_db):
        mock_decide.return_value = ("emdx task view 42", "Continue task", "in_progress")
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "emdx task view 42" in result.output

    @patch("emdx.commands.next.db")
    @patch("emdx.commands.next._decide_next")
    def test_json_output(self, mock_decide, mock_db):
        mock_decide.return_value = (
            "emdx task active 7",
            "Start ready task",
            "ready",
        )
        result = runner.invoke(app, ["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "emdx task active 7"
        assert data["reasoning"] == "Start ready task"
        assert data["priority"] == "ready"

    @patch("emdx.commands.next.db")
    @patch("emdx.commands.next._decide_next")
    def test_verbose_output(self, mock_decide, mock_db):
        mock_decide.return_value = ("emdx prime", "No tasks found", "fallback")
        result = runner.invoke(app, ["--verbose"])
        assert result.exit_code == 0
        assert "emdx prime" in result.output

    @patch("emdx.commands.next.db")
    @patch("emdx.commands.next._decide_next")
    def test_fallback_output(self, mock_decide, mock_db):
        mock_decide.return_value = (
            "emdx prime",
            "No tasks or stale gameplans found. Run prime for full context.",
            "fallback",
        )
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "emdx prime" in result.output

    @patch("emdx.commands.next.db")
    @patch("emdx.commands.next._decide_next")
    def test_json_fallback(self, mock_decide, mock_db):
        mock_decide.return_value = ("emdx prime", "No tasks", "fallback")
        result = runner.invoke(app, ["--json"])
        data = json.loads(result.output)
        assert data["action"] == "emdx prime"
        assert data["priority"] == "fallback"
