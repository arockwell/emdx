"""Unit tests for smart priming feature (emdx prime --smart)."""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import subprocess

import pytest
from typer.testing import CliRunner

from emdx.main import app
from emdx.commands.prime import (
    _format_relative_time,
    _get_git_context,
    _get_recent_activity,
    _get_key_docs,
    _get_knowledge_map,
    _get_stale_docs,
    _output_smart_text,
    _output_smart_json,
)

runner = CliRunner()


class TestFormatRelativeTime:
    """Test the _format_relative_time helper function."""

    def test_today(self):
        """Test 'today' for timestamps within 24 hours."""
        now = datetime.now()
        result = _format_relative_time(now.isoformat())
        assert result == "today"

    def test_yesterday(self):
        """Test 'yesterday' for timestamps 1 day ago."""
        yesterday = datetime.now() - timedelta(days=1)
        result = _format_relative_time(yesterday.isoformat())
        assert result == "yesterday"

    def test_days_ago(self):
        """Test 'N days ago' for timestamps 2-6 days ago."""
        three_days_ago = datetime.now() - timedelta(days=3)
        result = _format_relative_time(three_days_ago.isoformat())
        assert result == "3 days ago"

    def test_weeks_ago(self):
        """Test 'N week(s) ago' for timestamps 7-29 days ago."""
        two_weeks_ago = datetime.now() - timedelta(days=14)
        result = _format_relative_time(two_weeks_ago.isoformat())
        assert result == "2 weeks ago"

    def test_months_ago(self):
        """Test 'N month(s) ago' for timestamps 30+ days ago."""
        two_months_ago = datetime.now() - timedelta(days=60)
        result = _format_relative_time(two_months_ago.isoformat())
        assert result == "2 months ago"

    def test_invalid_input_returns_unknown(self):
        """Test that invalid input returns 'unknown'."""
        assert _format_relative_time("invalid") == "unknown"
        assert _format_relative_time(None) == "unknown"
        assert _format_relative_time("") == "unknown"


class TestGetGitContext:
    """Test the _get_git_context function."""

    @patch("emdx.commands.prime.subprocess.run")
    def test_returns_branch_and_commits(self, mock_run):
        """Test that git context includes branch and commits."""
        # Setup mock responses
        def run_side_effect(args, **kwargs):
            mock_result = MagicMock()
            if "branch" in args:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "log" in args:
                mock_result.returncode = 0
                mock_result.stdout = "abc123 First commit\ndef456 Second commit\n"
            elif "gh" in args:
                mock_result.returncode = 0
                mock_result.stdout = "[]"
            else:
                mock_result.returncode = 1
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        context = _get_git_context()

        assert context["branch"] == "main"
        assert len(context["recent_commits"]) == 2
        assert "abc123" in context["recent_commits"][0]

    @patch("emdx.commands.prime.subprocess.run")
    def test_graceful_degradation_without_gh_cli(self, mock_run):
        """Test that missing gh CLI doesn't break the function."""
        def run_side_effect(args, **kwargs):
            mock_result = MagicMock()
            if "branch" in args:
                mock_result.returncode = 0
                mock_result.stdout = "feature-branch\n"
            elif "log" in args:
                mock_result.returncode = 0
                mock_result.stdout = "abc123 commit\n"
            elif "gh" in args:
                # Simulate gh CLI not found
                raise FileNotFoundError("gh not found")
            else:
                mock_result.returncode = 1
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        context = _get_git_context()

        # Should still return valid context without PRs
        assert context["branch"] == "feature-branch"
        assert context["open_prs"] == []

    @patch("emdx.commands.prime.subprocess.run")
    def test_gh_cli_timeout_handled(self, mock_run):
        """Test that gh CLI timeout is handled gracefully."""
        def run_side_effect(args, **kwargs):
            mock_result = MagicMock()
            if "branch" in args:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "log" in args:
                mock_result.returncode = 0
                mock_result.stdout = "abc123 commit\n"
            elif "gh" in args:
                raise subprocess.TimeoutExpired(cmd="gh", timeout=10)
            else:
                mock_result.returncode = 1
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        context = _get_git_context()

        # Should still return valid context
        assert context["branch"] == "main"
        assert context["open_prs"] == []


class TestSmartPrimingTextOutput:
    """Test smart priming text output."""

    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_recent_activity")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_knowledge_map")
    @patch("emdx.commands.prime._get_stale_docs")
    def test_smart_text_output_structure(
        self,
        mock_stale,
        mock_knowledge,
        mock_key_docs,
        mock_recent,
        mock_git,
        capsys,
    ):
        """Test that smart text output has expected structure."""
        mock_git.return_value = {
            "branch": "main",
            "recent_commits": ["abc123 commit"],
            "open_prs": [{"number": 1, "title": "Test PR"}],
        }
        mock_recent.return_value = [
            {"id": 1, "title": "Recent Doc", "accessed_at": datetime.now().isoformat(), "views": 5}
        ]
        mock_key_docs.return_value = [
            {"id": 2, "title": "Key Doc", "views": 10}
        ]
        mock_knowledge.return_value = {
            "tags": {"gameplan": 3, "active": 2},
            "covered_topics": [],
            "potential_gaps": ["security", "testing"],
        }
        mock_stale.return_value = []

        _output_smart_text("test-project")

        captured = capsys.readouterr()
        output = captured.out

        # Check expected sections
        assert "EMDX CONTEXT" in output
        assert "test-project" in output
        assert "Branch: main" in output
        assert "📅 Recent activity" in output
        assert "🔑 Key docs" in output
        assert "🏷️ Active tags" in output


class TestSmartPrimingJsonOutput:
    """Test smart priming JSON output."""

    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_recent_activity")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_knowledge_map")
    @patch("emdx.commands.prime._get_stale_docs")
    def test_smart_json_output_is_valid_json(
        self,
        mock_stale,
        mock_knowledge,
        mock_key_docs,
        mock_recent,
        mock_git,
        capsys,
    ):
        """Test that smart JSON output is valid JSON."""
        mock_git.return_value = {
            "branch": "main",
            "recent_commits": [],
            "open_prs": [],
        }
        mock_recent.return_value = []
        mock_key_docs.return_value = []
        mock_knowledge.return_value = {"tags": {}, "covered_topics": [], "potential_gaps": []}
        mock_stale.return_value = []

        _output_smart_json("test-project")

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON
        data = json.loads(output)

        assert data["project"] == "test-project"
        assert "timestamp" in data
        assert "git_context" in data
        assert "recent_activity" in data
        assert "key_docs" in data
        assert "knowledge_map" in data
        assert "stale_docs" in data

    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_recent_activity")
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_knowledge_map")
    @patch("emdx.commands.prime._get_stale_docs")
    def test_smart_json_output_contains_data(
        self,
        mock_stale,
        mock_knowledge,
        mock_key_docs,
        mock_recent,
        mock_git,
        capsys,
    ):
        """Test that smart JSON output contains expected data."""
        mock_git.return_value = {
            "branch": "feature-x",
            "recent_commits": ["abc123 Fix bug"],
            "open_prs": [{"number": 42, "title": "Fix things"}],
        }
        mock_recent.return_value = [
            {"id": 1, "title": "Doc 1", "accessed_at": "2024-01-01T12:00:00", "views": 3}
        ]
        mock_key_docs.return_value = [
            {"id": 2, "title": "Important Doc", "views": 15}
        ]
        mock_knowledge.return_value = {
            "tags": {"analysis": 5},
            "covered_topics": ["testing"],
            "potential_gaps": ["security"],
        }
        mock_stale.return_value = [
            {"id": 3, "title": "Old Doc", "views": 8, "days_stale": 30}
        ]

        _output_smart_json("my-project")

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["git_context"]["branch"] == "feature-x"
        assert len(data["git_context"]["open_prs"]) == 1
        assert data["recent_activity"][0]["id"] == 1
        assert data["key_docs"][0]["views"] == 15
        assert "analysis" in data["knowledge_map"]["tags"]
        assert len(data["stale_docs"]) == 1


class TestSmartPrimingCLI:
    """Test the smart priming CLI integration."""

    @patch("emdx.commands.prime.db")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.utils.git.get_git_project")
    def test_prime_smart_flag_exists(self, mock_git_project, mock_git_context, mock_db):
        """Test that --smart flag is recognized."""
        mock_git_project.return_value = "test-project"
        mock_git_context.return_value = {"branch": "main", "recent_commits": [], "open_prs": []}

        # Mock db connection
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value = mock_conn

        result = runner.invoke(app, ["prime", "--smart"])

        # Should not error out
        assert result.exit_code == 0

    def test_prime_help_shows_smart_option(self):
        """Test that --smart is documented in help."""
        result = runner.invoke(app, ["prime", "--help"])

        assert result.exit_code == 0
        assert "--smart" in result.stdout


class TestGracefulDegradation:
    """Test graceful degradation when dependencies are unavailable."""

    @patch("emdx.commands.prime.subprocess.run")
    def test_all_git_commands_fail_gracefully(self, mock_run):
        """Test that complete git failure still returns valid context."""
        mock_run.side_effect = FileNotFoundError("git not found")

        context = _get_git_context()

        assert context["branch"] is None
        assert context["recent_commits"] == []
        assert context["open_prs"] == []

    @patch("emdx.commands.prime.subprocess.run")
    def test_gh_pr_list_returns_invalid_json(self, mock_run):
        """Test handling of malformed JSON from gh CLI."""
        def run_side_effect(args, **kwargs):
            mock_result = MagicMock()
            if "branch" in args:
                mock_result.returncode = 0
                mock_result.stdout = "main\n"
            elif "log" in args:
                mock_result.returncode = 0
                mock_result.stdout = "abc commit\n"
            elif "gh" in args:
                mock_result.returncode = 0
                mock_result.stdout = "not valid json {{"  # Malformed
            else:
                mock_result.returncode = 1
                mock_result.stdout = ""
            return mock_result

        mock_run.side_effect = run_side_effect

        context = _get_git_context()

        # Should handle the JSON error gracefully
        assert context["branch"] == "main"
        assert context["open_prs"] == []
