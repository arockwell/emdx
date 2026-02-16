"""Tests for prime CLI command — session priming context output."""
# mypy: disable-error-code="no-untyped-def"

import json
import subprocess
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.prime import (
    _format_epic_line,
    _get_git_context,
    _get_key_docs,
    _get_recent_failures,
    _get_recent_failures_json,
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


# Patch ensure_schema globally for all CLI tests since we mock the data queries
_SCHEMA_PATCH = "emdx.commands.prime.db.ensure_schema"


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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_header_and_project(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = "myproject"
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "EMDX WORK CONTEXT" in result.stdout
        assert "Project: myproject" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_usage_instructions(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "EMDX COMMANDS:" in result.stdout
        assert "emdx save" in result.stdout
        assert "emdx find" in result.stdout
        assert "emdx delegate" in result.stdout
        assert "emdx task ready" in result.stdout
        assert "emdx task view" in result.stdout
        assert "emdx task active" in result.stdout
        assert "emdx task log" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_ready_tasks(self, mock_project, mock_ip, mock_ready, mock_epics, _):
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_doc_reference(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task(id=1, title="Task", source_doc_id=42)]
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "doc #42" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_active_epics(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = [_make_epic(epic_key="SEC", title="Security Hardening")]
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "ACTIVE EPICS" in result.stdout
        assert "SEC" in result.stdout
        assert "Security Hardening" in result.stdout
        assert "2/5 done" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_in_progress(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = [_make_task(id=3, title="Work in progress", status="active")]

        result = runner.invoke(app, [])
        assert "IN-PROGRESS (1)" in result.stdout
        assert "#3" in result.stdout
        assert "Work in progress" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_no_ready_tasks_message(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, [])
        assert "No ready tasks" in result.stdout


class TestPrimeQuiet:
    """Test --quiet flag."""

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_quiet_omits_header_and_instructions(self, mock_project, mock_ip, mock_ready, _):
        mock_project.return_value = "proj"
        mock_ready.return_value = [_make_task(id=1, title="A task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--quiet"])
        assert result.exit_code == 0
        assert "EMDX WORK CONTEXT" not in result.stdout
        assert "Project:" not in result.stdout
        assert "EMDX COMMANDS:" not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_quiet_still_shows_tasks(self, mock_project, mock_ip, mock_ready, _):
        mock_project.return_value = None
        mock_ready.return_value = [_make_task(id=5, title="Quiet task")]
        mock_ip.return_value = []

        result = runner.invoke(app, ["--quiet"])
        assert "READY TASKS" in result.stdout
        assert "Quiet task" in result.stdout


class TestPrimeVerbose:
    """Test --verbose flag."""

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_recent_docs(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs, _
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_cascade_status")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_cascade_status(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs, mock_cascade, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_docs.return_value = []
        mock_cascade.return_value = {"idea": 3, "prompt": 1, "analyzed": 0, "planned": 0, "done": 5}

        result = runner.invoke(app, ["--verbose"])
        assert "CASCADE QUEUE" in result.stdout
        assert "idea: 3" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_task_descriptions(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs, _
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_output_structure(self, mock_project, mock_ip, mock_ready, mock_epics, _):
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_verbose_includes_extras(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_docs, _
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_non_verbose_excludes_extras(
        self, mock_project, mock_ip, mock_ready, mock_epics, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json"])
        data = json.loads(result.stdout)
        assert "execution_methods" not in data
        assert "recent_docs" not in data
        assert "cascade_status" not in data


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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_text_output_shows_git_context(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, _
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_output_includes_git_context(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, _
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

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_cascade_status")
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
        mock_cascade,
        mock_key_docs,
        _,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_recent.return_value = []
        mock_cascade.return_value = {}
        mock_key_docs.return_value = [
            {"id": 1, "title": "Important Doc", "access_count": 100},
            {"id": 2, "title": "Another Doc", "access_count": 50},
        ]

        result = runner.invoke(app, ["--verbose"])
        assert result.exit_code == 0
        assert "KEY DOCS (most accessed):" in result.stdout
        assert '#1 "Important Doc" — 100 views' in result.stdout
        assert '#2 "Another Doc" — 50 views' in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_key_docs")
    @patch("emdx.commands.prime._get_cascade_status")
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
        mock_cascade,
        mock_key_docs,
        _,
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_recent.return_value = []
        mock_cascade.return_value = {}
        mock_key_docs.return_value = [{"id": 1, "title": "Doc", "access_count": 10}]

        result = runner.invoke(app, ["--format", "json", "--verbose"])
        data = json.loads(result.stdout)
        assert "key_docs" in data
        assert len(data["key_docs"]) == 1
        assert data["key_docs"][0]["access_count"] == 10


# ---------------------------------------------------------------------------
# Helper for failed tasks
# ---------------------------------------------------------------------------


def _make_failed_task(
    id=1,
    title="Failed task",
    error="Something went wrong",
    prompt="do something",
    updated_at="2026-02-16T12:00:00",
    epic_key=None,
    epic_seq=None,
):
    return {
        "id": id,
        "title": title,
        "error": error,
        "prompt": prompt,
        "updated_at": updated_at,
        "status": "failed",
        "epic_key": epic_key,
        "epic_seq": epic_seq,
    }


# ---------------------------------------------------------------------------
# Tests for _get_recent_failures and _get_recent_failures_json
# ---------------------------------------------------------------------------


class TestGetRecentFailures:
    """Tests for _get_recent_failures helper."""

    @patch("emdx.models.tasks.get_recent_failures")
    def test_calls_model_function(self, mock_get_failures):
        mock_get_failures.return_value = [_make_failed_task()]

        result = _get_recent_failures()

        mock_get_failures.assert_called_once_with(hours=24, limit=5)
        assert len(result) == 1
        assert result[0]["id"] == 1

    @patch("emdx.models.tasks.get_recent_failures")
    def test_returns_empty_list_when_no_failures(self, mock_get_failures):
        mock_get_failures.return_value = []

        result = _get_recent_failures()

        assert result == []


class TestGetRecentFailuresJson:
    """Tests for _get_recent_failures_json helper."""

    @patch("emdx.models.tasks.get_recent_failures")
    def test_formats_failures_for_json(self, mock_get_failures):
        mock_get_failures.return_value = [
            _make_failed_task(
                id=42,
                title="DB Migration failed",
                error="Connection refused",
                prompt="run migrations",
            )
        ]

        result = _get_recent_failures_json()

        assert len(result) == 1
        assert result[0]["id"] == 42
        assert result[0]["title"] == "DB Migration failed"
        assert result[0]["error"] == "Connection refused"
        assert result[0]["prompt"] == "run migrations"
        assert result[0]["retry_command"] == 'emdx delegate "run migrations"'

    @patch("emdx.models.tasks.get_recent_failures")
    def test_retry_command_is_none_when_no_prompt(self, mock_get_failures):
        mock_get_failures.return_value = [_make_failed_task(id=1, prompt=None)]

        result = _get_recent_failures_json()

        assert result[0]["retry_command"] is None

    @patch("emdx.models.tasks.get_recent_failures")
    def test_returns_empty_list_when_no_failures(self, mock_get_failures):
        mock_get_failures.return_value = []

        result = _get_recent_failures_json()

        assert result == []


# ---------------------------------------------------------------------------
# Tests for recent failures in text output
# ---------------------------------------------------------------------------


class TestPrimeWithRecentFailures:
    """Tests for RECENT FAILURES section in prime output."""

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_shows_recent_failures_section(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [
            _make_failed_task(
                id=38,
                title="Check database migrations",
                error="Connection refused to localhost:5432",
                prompt="Check database migrations",
            )
        ]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "RECENT FAILURES (1)" in result.stdout
        assert "#38" in result.stdout
        assert "Check database migrations" in result.stdout
        assert "error: Connection refused" in result.stdout
        assert 'retry: emdx delegate "Check database migrations"' in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_truncates_long_error_messages(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        long_error = "A" * 100  # Error longer than 60 chars
        mock_failures.return_value = [_make_failed_task(id=1, title="Task", error=long_error)]

        result = runner.invoke(app, [])
        # Should be truncated with ...
        assert "AAAAAAA..." in result.stdout
        assert long_error not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_truncates_multiline_error_messages(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        multiline_error = "Line one\nLine two\nLine three"
        mock_failures.return_value = [_make_failed_task(id=1, title="Task", error=multiline_error)]

        result = runner.invoke(app, [])
        # Should only show first line with ...
        assert "error: Line one..." in result.stdout
        assert "Line two" not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_no_section_when_no_failures(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = []

        result = runner.invoke(app, [])
        assert "RECENT FAILURES" not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_escapes_quotes_in_retry_command(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [_make_failed_task(id=1, title="Task", prompt='fix "bug"')]

        result = runner.invoke(app, [])
        assert 'retry: emdx delegate "fix \\"bug\\""' in result.stdout


# ---------------------------------------------------------------------------
# Tests for recent failures in JSON output
# ---------------------------------------------------------------------------


class TestPrimeJsonWithRecentFailures:
    """Tests for recent_failures in JSON output."""

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures_json")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_includes_recent_failures(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures_json, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures_json.return_value = [
            {
                "id": 38,
                "title": "DB Migration failed",
                "error": "Connection refused",
                "prompt": "run migrations",
                "retry_command": 'emdx delegate "run migrations"',
                "updated_at": "2026-02-16T12:00:00",
            }
        ]

        result = runner.invoke(app, ["--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "recent_failures" in data
        assert len(data["recent_failures"]) == 1
        assert data["recent_failures"][0]["id"] == 38
        assert data["recent_failures"][0]["retry_command"] == 'emdx delegate "run migrations"'

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures_json")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_empty_failures_is_empty_list(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures_json, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures_json.return_value = []

        result = runner.invoke(app, ["--format", "json"])
        data = json.loads(result.stdout)
        assert "recent_failures" in data
        assert data["recent_failures"] == []
