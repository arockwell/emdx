"""Tests for prime CLI command — session priming context output."""
# mypy: disable-error-code="no-untyped-def"

import json
import subprocess
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.prime import (
    _format_epic_brief,
    _format_epic_line,
    _get_git_context,
    _get_key_docs,
    _task_label,
    app,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper data factories
# ---------------------------------------------------------------------------


def _make_task(
    id=1,
    title="Test task",
    description="",
    priority=5,
    status="open",
    source_doc_id=None,
    epic_key=None,
    epic_seq=None,
):
    return {
        "id": id,
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "source_doc_id": source_doc_id,
        "epic_key": epic_key,
        "epic_seq": epic_seq,
    }


def _make_epic(
    id=100, title="My Epic", status="active", epic_key="SEC", child_count=5, children_done=2
):
    return {
        "id": id,
        "title": title,
        "status": status,
        "epic_key": epic_key,
        "child_count": child_count,
        "children_done": children_done,
    }


# ---------------------------------------------------------------------------
# Unit tests for formatting helpers
# ---------------------------------------------------------------------------


class TestTaskLabel:
    def test_plain_task_shows_hash_id(self):
        label = _task_label(_make_task(id=42))
        assert label.strip() == "#42"

    def test_epic_task_shows_key_seq(self):
        label = _task_label(_make_task(id=449, epic_key="DEBT", epic_seq=10))
        assert label.strip() == "DEBT-10"

    def test_epic_key_without_seq_falls_back_to_id(self):
        label = _task_label(_make_task(id=500, epic_key="SEC", epic_seq=None))
        assert label.strip() == "#500"

    def test_label_is_padded(self):
        label = _task_label(_make_task(id=1))
        assert len(label) == 8


class TestFormatEpicLine:
    def test_partial_progress(self):
        line = _format_epic_line(_make_epic(child_count=5, children_done=2))
        assert "SEC" in line
        assert "My Epic" in line
        assert "2/5 done" in line
        assert "\u25a0" in line
        assert "\u25a1" in line

    def test_complete_epic_shows_checkmark(self):
        line = _format_epic_line(_make_epic(child_count=3, children_done=3))
        assert "3/3 done" in line
        assert "\u2713" in line

    def test_empty_epic(self):
        line = _format_epic_line(_make_epic(child_count=0, children_done=0))
        assert "no tasks" in line

    def test_zero_done(self):
        line = _format_epic_line(_make_epic(child_count=4, children_done=0))
        assert "0/4 done" in line
        assert "\u25a0" not in line


# ---------------------------------------------------------------------------
# Integration tests via CliRunner
# ---------------------------------------------------------------------------


class TestPrimeDefault:
    """Test default output (no flags)."""

    @patch("emdx.commands.prime._get_current_branch")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_header_with_project_and_branch(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_branch
    ):
        mock_project.return_value = "myproject"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_branch.return_value = "main"

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "● emdx — myproject (main)" in result.stdout
        # Old chrome should be gone
        assert "EMDX WORK CONTEXT" not in result.stdout
        assert "======" not in result.stdout
        assert "EMDX COMMANDS:" not in result.stdout

    @patch("emdx.commands.prime._get_current_branch")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_header_without_branch(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_branch
    ):
        mock_project.return_value = "myproject"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_branch.return_value = None

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "● emdx — myproject" in result.stdout
        assert "(" not in result.stdout.split("\n")[0]

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_ready_tasks(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            _make_task(id=10, title="Fix the bug"),
            _make_task(id=449, title="DEBT-10: Fix type safety", epic_key="DEBT", epic_seq=10),
        ]
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "READY TASKS (2)" in result.stdout
        assert "#10" in result.stdout
        assert "Fix the bug" in result.stdout
        assert "DEBT-10" in result.stdout
        assert "Fix type safety" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_doc_reference(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task(id=1, title="Task", source_doc_id=42)]
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "doc #42" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_active_epics(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = [_make_epic(epic_key="SEC", title="Security Hardening")]
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "ACTIVE EPICS" in result.stdout
        assert "SEC" in result.stdout
        assert "Security Hardening" in result.stdout
        assert "2/5 done" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_in_progress(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = [_make_task(id=3, title="Work in progress", status="active")]

        result = runner.invoke(app, [])
        assert "IN-PROGRESS (1)" in result.stdout
        assert "#3" in result.stdout
        assert "Work in progress" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_no_ready_tasks_message(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "No ready tasks" in result.stdout


class TestPrimeQuiet:
    """Test --quiet flag."""

    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_quiet_omits_header(self, mock_project, mock_ip, mock_ready):
        mock_project.return_value = "proj"
        mock_ready.return_value = [_make_task(id=1, title="A task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--quiet"])
        assert result.exit_code == 0
        assert "● emdx" not in result.stdout

    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_quiet_still_shows_tasks(self, mock_project, mock_ip, mock_ready):
        mock_project.return_value = None
        mock_ready.return_value = [_make_task(id=5, title="Quiet task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--quiet"])
        assert "READY TASKS" in result.stdout
        assert "Quiet task" in result.stdout


class TestPrimeVerbose:
    """Test --verbose flag."""

    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_recent_docs(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_docs.return_value = [{"id": 100, "title": "Design Doc", "project": "emdx"}]

        result = runner.invoke(app, ["--verbose"])
        assert result.exit_code == 0
        assert "RECENT DOCS" in result.stdout
        assert "#100" in result.stdout
        assert "Design Doc" in result.stdout

    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_task_descriptions(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            _make_task(id=1, title="Task", description="Detailed explanation")
        ]
        mock_ip.return_value = []
        mock_docs.return_value = []

        result = runner.invoke(app, ["--verbose"])
        assert "Detailed explanation" in result.stdout


class TestPrimeJson:
    """Test --format json output."""

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_output_structure(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = "myproject"
        mock_epics.return_value = [_make_epic()]
        mock_ready.return_value = [_make_task()]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project"] == "myproject"
        assert "active_epics" in data
        assert "ready_tasks" in data
        assert "in_progress_tasks" in data
        assert len(data["active_epics"]) == 1
        assert len(data["ready_tasks"]) == 1

    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_verbose_includes_extras(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_docs.return_value = [{"id": 1, "title": "Doc", "project": "p"}]

        result = runner.invoke(app, ["--format", "json", "--verbose"])
        data = json.loads(result.stdout)
        assert "execution_methods" in data
        assert "recent_docs" in data

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_non_verbose_excludes_extras(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json"])
        data = json.loads(result.stdout)
        assert "execution_methods" not in data
        assert "recent_docs" not in data


# ---------------------------------------------------------------------------
# Tests for _get_git_context
# ---------------------------------------------------------------------------


class TestGetGitContext:
    """Tests for _get_git_context function."""

    @patch("emdx.commands.prime.subprocess.run")
    def test_returns_branch_and_commits(self, mock_run):
        # Set up mock responses for each subprocess call
        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            if "branch" in cmd:
                mock_result.stdout = "feature/my-branch\n"
            elif "log" in cmd:
                mock_result.stdout = "abc1234 First commit\ndef5678 Second commit\nghi9012 Third"
            elif "gh" in cmd[0]:
                mock_result.stdout = '[{"number": 123, "title": "My PR", "headRefName": "my-pr"}]'
            return mock_result

        mock_run.side_effect = run_side_effect

        result = _get_git_context()

        assert result["branch"] == "feature/my-branch"
        assert len(result["commits"]) == 3
        assert result["commits"][0] == "abc1234 First commit"
        assert len(result["prs"]) == 1
        assert result["prs"][0]["number"] == 123
        assert result["error"] is None

    @patch("emdx.commands.prime.subprocess.run")
    def test_handles_git_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")

        result = _get_git_context()

        assert result["branch"] is None
        assert result["commits"] == []
        assert result["prs"] == []
        assert result["error"] == "git not installed"

    @patch("emdx.commands.prime.subprocess.run")
    def test_handles_git_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 5)

        result = _get_git_context()

        assert result["branch"] is None
        assert result["error"] == "git command timed out"

    @patch("emdx.commands.prime.subprocess.run")
    def test_handles_not_a_git_repo(self, mock_run):
        # Git command returns non-zero when not in a repo
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = _get_git_context()

        assert result["branch"] is None
        assert result["error"] is None  # Not an error, just not in a repo

    @patch("emdx.commands.prime.subprocess.run")
    def test_handles_gh_not_installed(self, mock_run):
        # Git works but gh is not installed
        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "gh":
                raise FileNotFoundError("gh not found")
            mock_result = MagicMock()
            mock_result.returncode = 0
            if "branch" in cmd:
                mock_result.stdout = "main\n"
            elif "log" in cmd:
                mock_result.stdout = "abc1234 Commit"
            return mock_result

        mock_run.side_effect = run_side_effect

        result = _get_git_context()

        assert result["branch"] == "main"
        assert len(result["commits"]) == 1
        assert result["prs"] == []  # gh not available but no error
        assert result["error"] is None

    @patch("emdx.commands.prime.subprocess.run")
    def test_handles_empty_branch_detached_head(self, mock_run):
        # Git returns empty for detached HEAD
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n"
        mock_run.return_value = mock_result

        result = _get_git_context()

        assert result["branch"] is None


# ---------------------------------------------------------------------------
# Tests for _get_key_docs
# ---------------------------------------------------------------------------


class TestGetKeyDocs:
    """Tests for _get_key_docs function."""

    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_top_accessed_docs(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "Most accessed doc", 100),
            (2, "Second doc", 50),
            (3, "Third doc", 25),
        ]
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_key_docs()

        assert len(result) == 3
        assert result[0]["id"] == 1
        assert result[0]["title"] == "Most accessed doc"
        assert result[0]["access_count"] == 100

    @patch("emdx.commands.prime.db.get_connection")
    def test_respects_limit(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1, "Doc", 10)]
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        _get_key_docs(limit=3)

        # Check the SQL was called with limit parameter
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (3,)

    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_empty_list_when_no_docs(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ctx = MagicMock(cursor=lambda: mock_cursor)
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_key_docs()

        assert result == []


# ---------------------------------------------------------------------------
# Integration tests for git context in output
# ---------------------------------------------------------------------------


class TestPrimeWithGitContext:
    """Test that git context appears in prime output."""

    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_text_output_shows_git_context(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git
    ):
        mock_project.return_value = "myproject"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {
            "branch": "feature/test",
            "commits": ["abc1234 Fix bug", "def5678 Add feature"],
            "prs": [{"number": 42, "title": "My PR", "headRefName": "my-pr"}],
            "error": None,
        }

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "GIT CONTEXT:" in result.stdout
        assert "Branch: feature/test" in result.stdout
        assert "Recent commits:" in result.stdout
        assert "abc1234 Fix bug" in result.stdout
        assert "Open PRs:" in result.stdout
        assert "#42 My PR (my-pr)" in result.stdout

    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_output_includes_git_context(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {
            "branch": "main",
            "commits": ["abc1234 Commit"],
            "prs": [],
            "error": None,
        }

        result = runner.invoke(app, ["--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "git_context" in data
        assert data["git_context"]["branch"] == "main"
        assert len(data["git_context"]["commits"]) == 1


class TestPrimeWithKeyDocs:
    """Test that key docs appear in verbose mode."""

    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_key_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_git,
        mock_recent,
        mock_key_docs,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_recent.return_value = []
        mock_key_docs.return_value = [
            {"id": 1, "title": "Important Doc", "access_count": 100},
            {"id": 2, "title": "Another Doc", "access_count": 50},
        ]

        result = runner.invoke(app, ["--verbose"])
        assert result.exit_code == 0
        assert "KEY DOCS (most accessed):" in result.stdout
        assert '#1 "Important Doc" — 100 views' in result.stdout
        assert '#2 "Another Doc" — 50 views' in result.stdout

    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_verbose_includes_key_docs(
        self,
        mock_project,
        mock_ip,
        mock_ready,
        mock_epics,
        mock_git,
        mock_recent,
        mock_key_docs,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_recent.return_value = []
        mock_key_docs.return_value = [{"id": 1, "title": "Doc", "access_count": 10}]

        result = runner.invoke(app, ["--format", "json", "--verbose"])
        data = json.loads(result.stdout)
        assert "key_docs" in data
        assert len(data["key_docs"]) == 1
        assert data["key_docs"][0]["access_count"] == 10


# ---------------------------------------------------------------------------
# Tests for _format_epic_brief
# ---------------------------------------------------------------------------


class TestFormatEpicBrief:
    def test_shows_key_and_progress(self):
        line = _format_epic_brief(
            _make_epic(epic_key="FEAT", title="Next Intelligence", child_count=18, children_done=3)
        )
        assert "FEAT: Next Intelligence" in line
        assert "3/18 done" in line

    def test_no_epic_key(self):
        epic = _make_epic(epic_key=None, title="Cleanup", child_count=5, children_done=2)
        line = _format_epic_brief(epic)
        assert "Cleanup" in line
        assert "2/5 done" in line
        # Should not have a dangling colon
        assert ": Cleanup" not in line


# ---------------------------------------------------------------------------
# Tests for --brief flag
# ---------------------------------------------------------------------------


class TestPrimeBrief:
    """Test --brief flag behavior."""

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_shows_header_without_branch(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = "myproject"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief"])
        assert result.exit_code == 0
        assert "● emdx — myproject" in result.stdout
        # Brief mode should NOT include branch in header
        assert "(" not in result.stdout.split("\n")[0]

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_shows_epics_compact(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = [
            _make_epic(
                epic_key="FEAT",
                title="Next Intelligence",
                child_count=18,
                children_done=3,
            )
        ]
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief"])
        assert "ACTIVE EPICS" in result.stdout
        assert "FEAT: Next Intelligence" in result.stdout
        assert "3/18 done" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_shows_ready_tasks_without_doc_ref(
        self, mock_project, mock_ip, mock_ready, mock_epics
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            _make_task(id=10, title="Fix auth", source_doc_id=42),
        ]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief"])
        assert "READY TASKS (1)" in result.stdout
        assert "Fix auth" in result.stdout
        # Brief should NOT show doc references
        assert "doc #42" not in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_shows_in_progress(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = [
            _make_task(id=3, title="Working on it", status="active"),
        ]

        result = runner.invoke(app, ["--brief"])
        assert "IN-PROGRESS (1)" in result.stdout
        assert "Working on it" in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_skips_git_context(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task(id=1, title="Task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief"])
        assert "GIT CONTEXT" not in result.stdout

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_plus_verbose_ignores_verbose(
        self, mock_project, mock_ip, mock_ready, mock_epics
    ):
        """--brief + --verbose should behave like --brief (ignore verbose)."""
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [
            _make_task(id=1, title="Task", description="Long description"),
        ]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief", "--verbose"])
        assert result.exit_code == 0
        # Should NOT show verbose additions
        assert "RECENT DOCS" not in result.stdout
        assert "KEY DOCS" not in result.stdout
        assert "GIT CONTEXT" not in result.stdout
        # Should NOT show task descriptions (verbose feature)
        assert "Long description" not in result.stdout

    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_brief_plus_quiet_quiet_wins(self, mock_project, mock_ip, mock_ready):
        """--brief + --quiet should produce quiet output (quiet wins)."""
        mock_project.return_value = "proj"
        mock_ready.return_value = [_make_task(id=1, title="Task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--brief", "--quiet"])
        assert result.exit_code == 0
        # Quiet omits header
        assert "● emdx" not in result.stdout
        # Quiet omits epics
        assert "ACTIVE EPICS" not in result.stdout
        # Still shows tasks
        assert "READY TASKS" in result.stdout


class TestPrimeBriefJson:
    """Test --brief with JSON output."""

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_brief_has_tasks_and_epics(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = "myproject"
        mock_epics.return_value = [_make_epic()]
        mock_ready.return_value = [_make_task()]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json", "--brief"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project"] == "myproject"
        assert "active_epics" in data
        assert "ready_tasks" in data
        assert "in_progress_tasks" in data

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_brief_excludes_git_context(self, mock_project, mock_ip, mock_ready, mock_epics):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json", "--brief"])
        data = json.loads(result.stdout)
        assert "git_context" not in data

    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_brief_plus_verbose_ignores_verbose(
        self, mock_project, mock_ip, mock_ready, mock_epics
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json", "--brief", "--verbose"])
        data = json.loads(result.stdout)
        assert "git_context" not in data
        assert "execution_methods" not in data
        assert "recent_docs" not in data
        assert "key_docs" not in data
