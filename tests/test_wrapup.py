"""Tests for the emdx wrapup command."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.commands.wrapup import (
    _build_synthesis_prompt,
    _collect_activity,
    _print_dry_run_summary,
)
from emdx.main import app


@pytest.fixture
def runner() -> CliRunner:
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_activity() -> dict[str, Any]:
    """Sample activity data for testing."""
    return {
        "window_hours": 4,
        "tasks": [
            {"id": 1, "title": "Fix auth bug", "status": "done"},
            {"id": 2, "title": "Add tests", "status": "active"},
            {"id": 3, "title": "Waiting on API", "status": "blocked"},
        ],
        "docs": [
            {"id": 101, "title": "Auth Analysis", "project": "emdx"},
            {"id": 102, "title": "Test Plan", "project": "emdx"},
        ],
        "delegate_tasks": [
            {
                "id": 201,
                "title": "Review code",
                "status": "done",
                "output_doc_id": 103,
            },
        ],
        "execution_stats": {
            "total": 5,
            "completed": 4,
            "failed": 1,
            "running": 0,
            "total_cost_usd": 0.0234,
            "total_tokens": 5000,
        },
    }


class TestBuildSynthesisPrompt:
    """Tests for _build_synthesis_prompt helper."""

    def test_empty_activity_produces_minimal_prompt(self) -> None:
        """Empty activity produces a prompt with no sections."""
        activity: dict[str, Any] = {
            "window_hours": 4,
            "tasks": [],
            "docs": [],
            "delegate_tasks": [],
            "execution_stats": {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "running": 0,
                "total_cost_usd": 0,
                "total_tokens": 0,
            },
        }
        prompt = _build_synthesis_prompt(activity)
        assert "4 hours" in prompt
        assert "accomplishments" in prompt.lower()

    def test_includes_completed_tasks(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes completed tasks section."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "Completed Tasks" in prompt
        assert "Fix auth bug" in prompt

    def test_includes_active_tasks(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes in-progress tasks section."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "In-Progress Tasks" in prompt
        assert "Add tests" in prompt

    def test_includes_blocked_tasks(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes blocked tasks section."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "Blocked Tasks" in prompt
        assert "Waiting on API" in prompt

    def test_includes_documents(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes documents section."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "Documents Created" in prompt
        assert "Auth Analysis" in prompt

    def test_includes_delegate_activity(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes delegate execution stats."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "Delegate Activity" in prompt
        assert "5" in prompt  # total executions
        assert "4" in prompt  # completed

    def test_includes_cost_when_nonzero(self, mock_activity: dict[str, Any]) -> None:
        """Prompt includes cost when there were paid executions."""
        prompt = _build_synthesis_prompt(mock_activity)
        assert "$" in prompt
        assert "0.0234" in prompt


class TestPrintDryRunSummary:
    """Tests for _print_dry_run_summary helper."""

    def test_prints_summary_counts(
        self, mock_activity: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry run prints counts of all activity types."""
        _print_dry_run_summary(mock_activity)
        captured = capsys.readouterr()

        assert "4 hours" in captured.out
        assert "3 total" in captured.out  # tasks
        assert "Done: 1" in captured.out
        assert "Active: 1" in captured.out
        assert "Blocked: 1" in captured.out
        assert "2 created" in captured.out  # docs
        assert "5 total" in captured.out  # executions


class TestCollectActivity:
    """Tests for _collect_activity helper."""

    @patch("emdx.commands.wrapup.get_tasks_in_window")
    @patch("emdx.commands.wrapup.get_docs_in_window")
    @patch("emdx.commands.wrapup.get_delegate_tasks_in_window")
    @patch("emdx.commands.wrapup.get_execution_stats_in_window")
    def test_collects_all_activity_types(
        self,
        mock_exec_stats: MagicMock,
        mock_delegate: MagicMock,
        mock_docs: MagicMock,
        mock_tasks: MagicMock,
    ) -> None:
        """Activity collection queries all data sources."""
        mock_tasks.return_value = [{"id": 1, "title": "Task", "status": "done"}]
        mock_docs.return_value = [{"id": 2, "title": "Doc"}]
        mock_delegate.return_value = [{"id": 3, "title": "Delegate"}]
        mock_exec_stats.return_value = {"total": 1, "completed": 1}

        activity = _collect_activity(4)

        mock_tasks.assert_called_once_with(4)
        mock_docs.assert_called_once_with(4)
        mock_delegate.assert_called_once_with(4)
        mock_exec_stats.assert_called_once_with(4)

        assert activity["window_hours"] == 4
        assert len(activity["tasks"]) == 1
        assert len(activity["docs"]) == 1


class TestWrapupCommand:
    """Tests for the wrapup CLI command."""

    @patch("emdx.commands.wrapup._collect_activity")
    def test_json_output_returns_raw_data(
        self, mock_collect: MagicMock, runner: CliRunner, mock_activity: dict[str, Any]
    ) -> None:
        """--json returns structured activity data without synthesis."""
        mock_collect.return_value = mock_activity

        result = runner.invoke(app, ["wrapup", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tasks" in data
        assert "docs" in data
        assert "execution_stats" in data
        assert data["window_hours"] == 4

    @patch("emdx.commands.wrapup._collect_activity")
    def test_dry_run_shows_counts(
        self, mock_collect: MagicMock, runner: CliRunner, mock_activity: dict[str, Any]
    ) -> None:
        """--dry-run shows activity counts without synthesizing."""
        mock_collect.return_value = mock_activity

        result = runner.invoke(app, ["wrapup", "--dry-run"])

        assert result.exit_code == 0
        assert "Would summarize" in result.output
        assert "4 hours" in result.output

    @patch("emdx.commands.wrapup._collect_activity")
    def test_empty_activity_shows_message(self, mock_collect: MagicMock, runner: CliRunner) -> None:
        """No activity in window gives friendly message."""
        mock_collect.return_value = {
            "window_hours": 4,
            "tasks": [],
            "docs": [],
            "delegate_tasks": [],
            "execution_stats": {"total": 0, "completed": 0, "failed": 0, "running": 0},
        }

        result = runner.invoke(app, ["wrapup"])

        assert result.exit_code == 0
        assert "No activity" in result.output

    @patch("emdx.commands.wrapup._collect_activity")
    @patch("emdx.commands.wrapup._run_synthesis")
    def test_synthesis_prints_content(
        self,
        mock_synth: MagicMock,
        mock_collect: MagicMock,
        runner: CliRunner,
        mock_activity: dict[str, Any],
    ) -> None:
        """Synthesis output is printed to stdout."""
        mock_collect.return_value = mock_activity
        mock_synth.return_value = "Summary content here"

        result = runner.invoke(app, ["wrapup"])

        assert result.exit_code == 0
        assert "Summary content here" in result.output
        mock_synth.assert_called_once()

    @patch("emdx.commands.wrapup._collect_activity")
    @patch("emdx.commands.wrapup._run_synthesis")
    @patch("emdx.commands.wrapup.save_document")
    def test_save_flag_persists_with_correct_tags(
        self,
        mock_save: MagicMock,
        mock_synth: MagicMock,
        mock_collect: MagicMock,
        runner: CliRunner,
        mock_activity: dict[str, Any],
    ) -> None:
        """--save flag saves output with session-summary,active tags."""
        mock_collect.return_value = mock_activity
        mock_synth.return_value = "Summary content here"
        mock_save.return_value = 999

        result = runner.invoke(app, ["wrapup", "--save"])

        assert result.exit_code == 0
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert "session-summary" in call_args.kwargs["tags"]
        assert "active" in call_args.kwargs["tags"]

    @patch("emdx.commands.wrapup._collect_activity")
    def test_hours_option_passed_correctly(
        self, mock_collect: MagicMock, runner: CliRunner
    ) -> None:
        """--hours option controls the time window."""
        mock_collect.return_value = {
            "window_hours": 8,
            "tasks": [],
            "docs": [],
            "delegate_tasks": [],
            "execution_stats": {"total": 0},
        }

        runner.invoke(app, ["wrapup", "--hours", "8", "--dry-run"])

        mock_collect.assert_called_once_with(8)


class TestDataQueries:
    """Integration tests for the data query functions."""

    def test_get_tasks_in_window_returns_list(self) -> None:
        """get_tasks_in_window returns a list."""
        from emdx.models.tasks import get_tasks_in_window

        result = get_tasks_in_window(4)
        assert isinstance(result, list)

    def test_get_docs_in_window_returns_list(self) -> None:
        """get_docs_in_window returns a list."""
        from emdx.database.documents import get_docs_in_window

        result = get_docs_in_window(4)
        assert isinstance(result, list)

    def test_get_delegate_tasks_in_window_returns_list(self) -> None:
        """get_delegate_tasks_in_window returns a list."""
        from emdx.models.tasks import get_delegate_tasks_in_window

        result = get_delegate_tasks_in_window(4)
        assert isinstance(result, list)

    def test_get_execution_stats_in_window_returns_dict(self) -> None:
        """get_execution_stats_in_window returns a dict with expected keys."""
        from emdx.models.executions import get_execution_stats_in_window

        result = get_execution_stats_in_window(4)
        assert isinstance(result, dict)
        assert "total" in result
        assert "completed" in result
        assert "failed" in result
        assert "running" in result
