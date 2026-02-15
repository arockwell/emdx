"""Tests for prime CLI command — session priming context output."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.prime import (
    app,
    _task_label,
    _format_epic_line,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper data factories
# ---------------------------------------------------------------------------

def _make_task(id=1, title="Test task", description="", priority=5,
               status="open", source_doc_id=None, epic_key=None, epic_seq=None):
    return {
        "id": id, "title": title, "description": description,
        "priority": priority, "status": status, "source_doc_id": source_doc_id,
        "epic_key": epic_key, "epic_seq": epic_seq,
    }


def _make_epic(id=100, title="My Epic", status="active", epic_key="SEC",
               child_count=5, children_done=2):
    return {
        "id": id, "title": title, "status": status, "epic_key": epic_key,
        "child_count": child_count, "children_done": children_done,
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
    @patch("emdx.commands.prime._get_cascade_status")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_recent_docs(self, mock_project, mock_ip, mock_ready,
                                        mock_epics, mock_docs, mock_cascade, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_docs.return_value = [{"id": 100, "title": "Design Doc", "project": "emdx"}]
        mock_cascade.return_value = {"idea": 0, "prompt": 0, "analyzed": 0, "planned": 0, "done": 0}

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
    def test_verbose_shows_cascade_status(self, mock_project, mock_ip, mock_ready,
                                           mock_epics, mock_docs, mock_cascade, _):
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
    @patch("emdx.commands.prime._get_cascade_status")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_verbose_shows_task_descriptions(self, mock_project, mock_ip, mock_ready,
                                              mock_epics, mock_docs, mock_cascade, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = [_make_task(id=1, title="Task", description="Detailed explanation")]
        mock_ip.return_value = []
        mock_docs.return_value = []
        mock_cascade.return_value = {"idea": 0, "prompt": 0, "analyzed": 0, "planned": 0, "done": 0}

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
    @patch("emdx.commands.prime._get_cascade_status")
    @patch("emdx.commands.prime._get_recent_docs")
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_verbose_includes_extras(self, mock_project, mock_ip, mock_ready,
                                           mock_epics, mock_docs, mock_cascade, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []
        mock_docs.return_value = [{"id": 1, "title": "Doc", "project": "p"}]
        mock_cascade.return_value = {"idea": 1}

        result = runner.invoke(app, ["--format", "json", "--verbose"])
        data = json.loads(result.stdout)
        assert "execution_methods" in data
        assert "recent_docs" in data
        assert "cascade_status" in data

    @patch(_SCHEMA_PATCH)
    @patch("emdx.commands.prime._get_active_epics")
    @patch("emdx.commands.prime._get_ready_tasks")
    @patch("emdx.commands.prime._get_in_progress_tasks")
    @patch("emdx.commands.prime.get_git_project")
    def test_json_non_verbose_excludes_extras(self, mock_project, mock_ip, mock_ready, mock_epics, _):
        mock_project.return_value = None
        mock_epics.return_value = []
        mock_ready.return_value = []
        mock_ip.return_value = []

        result = runner.invoke(app, ["--format", "json"])
        data = json.loads(result.stdout)
        assert "execution_methods" not in data
        assert "recent_docs" not in data
        assert "cascade_status" not in data
