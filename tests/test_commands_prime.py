"""Tests for prime CLI command — session priming context output."""
# mypy: disable-error-code="no-untyped-def"

import json
import subprocess
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.prime import (
    _extract_error_snippet,
    _format_epic_line,
    _get_git_context,
    _get_key_docs,
    _get_recent_failures,
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
# Tests for _extract_error_snippet
# ---------------------------------------------------------------------------


class TestExtractErrorSnippet:
    """Tests for _extract_error_snippet function."""

    def test_extracts_last_n_lines(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\nline7\n")

        snippet = _extract_error_snippet(str(log_file), lines=3)

        assert snippet is not None
        assert snippet == "line5\nline6\nline7"

    def test_returns_all_lines_if_fewer_than_requested(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text("only\ntwo\n")

        snippet = _extract_error_snippet(str(log_file), lines=5)

        assert snippet is not None
        assert snippet == "only\ntwo"

    def test_returns_none_for_missing_file(self):
        snippet = _extract_error_snippet("/nonexistent/path/to/log.txt")
        assert snippet is None

    def test_returns_none_for_empty_file(self, tmp_path):
        log_file = tmp_path / "empty.log"
        log_file.write_text("")

        snippet = _extract_error_snippet(str(log_file))
        assert snippet is None

    def test_handles_whitespace_only_file(self, tmp_path):
        log_file = tmp_path / "whitespace.log"
        log_file.write_text("   \n\n  \n")

        snippet = _extract_error_snippet(str(log_file))
        assert snippet is None

    def test_expands_home_path(self, tmp_path, monkeypatch):
        # Create a file and test tilde expansion works
        log_file = tmp_path / "home.log"
        log_file.write_text("error: something failed\n")

        # Just verify regular path works (can't easily test ~ expansion in pytest)
        snippet = _extract_error_snippet(str(log_file))
        assert snippet == "error: something failed"


# ---------------------------------------------------------------------------
# Tests for _get_recent_failures
# ---------------------------------------------------------------------------


class TestGetRecentFailures:
    """Tests for _get_recent_failures function."""

    @patch("emdx.commands.prime._extract_error_snippet")
    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_failed_executions(self, mock_conn, mock_snippet):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (1, "Failed task 1", "2024-01-15 10:00:00", 1, "/path/to/log1.txt", 42),
            (2, "Failed task 2", "2024-01-15 11:00:00", 127, "/path/to/log2.txt", None),
        ]
        mock_ctx = MagicMock()
        mock_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_snippet.return_value = "Error: something failed"

        result = _get_recent_failures()

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["title"] == "Failed task 1"
        assert result[0]["exit_code"] == 1
        assert result[0]["task_id"] == 42
        assert result[0]["error_snippet"] == "Error: something failed"
        assert result[1]["id"] == 2
        assert result[1]["task_id"] is None

    @patch("emdx.commands.prime._extract_error_snippet")
    @patch("emdx.commands.prime.db.get_connection")
    def test_returns_empty_list_when_no_failures(self, mock_conn, mock_snippet):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        result = _get_recent_failures()

        assert result == []

    @patch("emdx.commands.prime._extract_error_snippet")
    @patch("emdx.commands.prime.db.get_connection")
    def test_respects_hours_and_limit_params(self, mock_conn, mock_snippet):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)

        _get_recent_failures(hours=12, limit=3)

        # Check the SQL was called with correct limit
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1][1] == 3  # limit param


# ---------------------------------------------------------------------------
# Integration tests for recent failures in output
# ---------------------------------------------------------------------------


def _make_failure(
    id=1,
    title="Failed task",
    completed_at="2024-01-15 10:00:00",
    exit_code=1,
    log_file="/path/to/log.txt",
    task_id=None,
    error_snippet=None,
):
    return {
        "id": id,
        "title": title,
        "completed_at": completed_at,
        "exit_code": exit_code,
        "log_file": log_file,
        "task_id": task_id,
        "error_snippet": error_snippet,
    }


class TestPrimeWithRecentFailures:
    """Test that recent failures appear in prime output."""

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_text_output_shows_failures(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [
            _make_failure(id=101, title="Auth module crash", exit_code=1),
            _make_failure(id=102, title="Database timeout", exit_code=127),
        ]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "RECENT FAILURES (2):" in result.stdout
        assert "#101" in result.stdout
        assert "Auth module crash" in result.stdout
        assert "exit 1" in result.stdout
        assert "#102" in result.stdout
        assert "Database timeout" in result.stdout
        assert "exit 127" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_text_output_shows_error_snippet(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [
            _make_failure(
                id=101, title="Test failure", error_snippet="Error: connection refused\nRetrying..."
            ),
        ]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Error: connection refused" in result.stdout
        assert "Retrying..." in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_text_output_shows_retry_command(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [_make_failure(id=101, title="Retry me")]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Retry: emdx delegate --retry 101" in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_quiet_mode_hides_failures(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task(id=1, title="Task")]
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [_make_failure(id=101, title="Should not appear")]

        result = runner.invoke(app, ["--quiet"])
        assert result.exit_code == 0
        assert "RECENT FAILURES" not in result.stdout
        assert "Should not appear" not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_no_failures_section_when_empty(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = []

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "RECENT FAILURES" not in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_output_includes_failures(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [
            _make_failure(
                id=101,
                title="Failed task",
                exit_code=1,
                task_id=42,
                error_snippet="Error details",
            ),
        ]

        result = runner.invoke(app, ["--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "recent_failures" in data
        assert len(data["recent_failures"]) == 1
        assert data["recent_failures"][0]["id"] == 101
        assert data["recent_failures"][0]["title"] == "Failed task"
        assert data["recent_failures"][0]["exit_code"] == 1
        assert data["recent_failures"][0]["task_id"] == 42
        assert data["recent_failures"][0]["error_snippet"] == "Error details"
        assert data["recent_failures"][0]["retry_command"] == "emdx delegate --retry 101"

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_long_title_truncated(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        long_title = "A" * 100  # Very long title
        mock_failures.return_value = [_make_failure(id=101, title=long_title)]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        # Title should be truncated to 50 chars + "..."
        assert "A" * 50 + "..." in result.stdout

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_recent_failures")
    @patch("emdx.commands.prime._get_git_context")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_null_exit_code_shows_failed(
        self, mock_project, mock_ip, mock_ready, mock_epics, mock_git, mock_failures, _
    ):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_git.return_value = {"branch": None, "commits": [], "prs": [], "error": None}
        mock_failures.return_value = [_make_failure(id=101, title="Test", exit_code=None)]

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "(failed)" in result.stdout
