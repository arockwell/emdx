"""Tests for task CLI commands (add, list, ready, done, delete)."""

import re
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.tasks import app

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestTaskAdd:
    """Tests for task add command."""

    @patch("emdx.commands.tasks.tasks")
    def test_add_simple_task(self, mock_tasks):
        mock_tasks.create_task.return_value = 1
        result = runner.invoke(app, ["add", "Fix the auth bug"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Task #1" in out
        assert "Fix the auth bug" in out
        mock_tasks.create_task.assert_called_once_with(
            "Fix the auth bug",
            description="",
            source_doc_id=None,
            parent_task_id=None,
            epic_key=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_add_task_with_doc_id(self, mock_tasks):
        mock_tasks.create_task.return_value = 2
        result = runner.invoke(app, ["add", "Implement this", "--doc", "42"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Task #2" in out
        assert "Implement this" in out
        assert "doc #42" in out
        mock_tasks.create_task.assert_called_once_with(
            "Implement this",
            description="",
            source_doc_id=42,
            parent_task_id=None,
            epic_key=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_add_task_with_doc_id_short_flag(self, mock_tasks):
        mock_tasks.create_task.return_value = 3
        result = runner.invoke(app, ["add", "Another task", "-d", "99"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Task #3" in out
        assert "doc #99" in out
        mock_tasks.create_task.assert_called_once_with(
            "Another task",
            description="",
            source_doc_id=99,
            parent_task_id=None,
            epic_key=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_add_task_with_description(self, mock_tasks):
        mock_tasks.create_task.return_value = 4
        result = runner.invoke(
            app, ["add", "Refactor tests", "--description", "Split into unit and integration"]
        )
        assert result.exit_code == 0
        out = _out(result)
        assert "Task #4" in out
        assert "Refactor tests" in out
        mock_tasks.create_task.assert_called_once_with(
            "Refactor tests",
            description="Split into unit and integration",
            source_doc_id=None,
            parent_task_id=None,
            epic_key=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_add_task_with_description_short_flag(self, mock_tasks):
        mock_tasks.create_task.return_value = 5
        result = runner.invoke(app, ["add", "Task", "-D", "Details here"])
        assert result.exit_code == 0
        mock_tasks.create_task.assert_called_once_with(
            "Task",
            description="Details here",
            source_doc_id=None,
            parent_task_id=None,
            epic_key=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_add_task_with_all_options(self, mock_tasks):
        mock_tasks.create_task.return_value = 6
        result = runner.invoke(
            app, ["add", "Full task", "-d", "10", "-D", "Full description"]
        )
        assert result.exit_code == 0
        out = _out(result)
        assert "Task #6" in out
        assert "doc #10" in out
        mock_tasks.create_task.assert_called_once_with(
            "Full task",
            description="Full description",
            source_doc_id=10,
            parent_task_id=None,
            epic_key=None,
        )

    def test_add_task_requires_title(self):
        result = runner.invoke(app, ["add"])
        assert result.exit_code != 0


class TestTaskReady:
    """Tests for task ready command."""

    @patch("emdx.commands.tasks.tasks")
    def test_ready_no_tasks(self, mock_tasks):
        mock_tasks.get_ready_tasks.return_value = []
        result = runner.invoke(app, ["ready"])
        assert result.exit_code == 0
        assert "No ready tasks" in _out(result)

    @patch("emdx.commands.tasks.tasks")
    def test_ready_shows_tasks(self, mock_tasks):
        mock_tasks.get_ready_tasks.return_value = [
            {"id": 1, "title": "First task", "epic_key": None, "epic_seq": None},
            {"id": 2, "title": "Second task", "epic_key": "SEC", "epic_seq": 1},
        ]
        result = runner.invoke(app, ["ready"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Ready (2)" in out
        assert "#1" in out
        assert "First task" in out
        assert "SEC-1" in out
        assert "Second task" in out

    @patch("emdx.commands.tasks.tasks")
    def test_ready_shows_epic_label(self, mock_tasks):
        mock_tasks.get_ready_tasks.return_value = [
            {"id": 1, "title": "QW-3: Task", "epic_key": "QW", "epic_seq": 3},
        ]
        result = runner.invoke(app, ["ready"])
        out = _out(result)
        # ID column shows epic label, title has prefix stripped
        assert "QW-3" in out
        assert "Task" in out


class TestTaskDone:
    """Tests for task done command."""

    @patch("emdx.commands.tasks.tasks")
    def test_done_marks_task_complete(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Test task"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["done", "1"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Done" in out
        assert "#1" in out
        assert "Test task" in out
        mock_tasks.update_task.assert_called_once_with(1, status="done")

    @patch("emdx.commands.tasks.tasks")
    def test_done_with_note(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 2, "title": "Bug fix"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["done", "2", "--note", "Fixed in PR #123"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Done" in out
        assert "#2" in out
        mock_tasks.log_progress.assert_called_once_with(2, "Fixed in PR #123")

    @patch("emdx.commands.tasks.tasks")
    def test_done_with_note_short_flag(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 3, "title": "Feature"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["done", "3", "-n", "Completed"])
        assert result.exit_code == 0
        mock_tasks.log_progress.assert_called_once_with(3, "Completed")

    @patch("emdx.commands.tasks.tasks")
    def test_done_task_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["done", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_done_requires_task_id(self):
        result = runner.invoke(app, ["done"])
        assert result.exit_code != 0


class TestTaskList:
    """Tests for task list command."""

    @patch("emdx.commands.tasks.tasks")
    def test_list_empty(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No tasks" in _out(result)

    @patch("emdx.commands.tasks.tasks")
    def test_list_shows_tasks(self, mock_tasks):
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": "Open task", "status": "open",
             "epic_key": None, "epic_seq": None},
            {"id": 2, "title": "Active task", "status": "active",
             "epic_key": None, "epic_seq": None},
            {"id": 3, "title": "Blocked task", "status": "blocked",
             "epic_key": None, "epic_seq": None},
        ]
        mock_tasks.get_dependencies.return_value = []
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Open task" in out
        assert "Active task" in out
        assert "Blocked task" in out
        assert "Tasks (3)" in out

    @patch("emdx.commands.tasks.tasks")
    def test_list_shows_status_text(self, mock_tasks):
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": "Task", "status": "active",
             "epic_key": None, "epic_seq": None},
        ]
        result = runner.invoke(app, ["list"])
        out = _out(result)
        assert "active" in out

    @patch("emdx.commands.tasks.tasks")
    def test_list_shows_epic_label_and_strips_prefix(self, mock_tasks):
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": "SEC-1: Harden auth", "status": "open",
             "epic_key": "SEC", "epic_seq": 1},
        ]
        result = runner.invoke(app, ["list"])
        out = _out(result)
        # ID column has epic label, title prefix stripped
        assert "SEC-1" in out
        assert "Harden auth" in out

    @patch("emdx.commands.tasks.tasks")
    def test_list_defaults_to_actionable_statuses(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active", "blocked"], limit=20, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_done_flag_shows_all_statuses(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--done"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=20, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_includes_delegate_with_all_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--all"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active", "blocked"], limit=20, exclude_delegate=False,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_all_short_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-a"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active", "blocked"], limit=20, exclude_delegate=False,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_status_filter(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--status", "open"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open"], limit=20, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_multiple_status_filter(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-s", "open,active"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active"], limit=20, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_limit(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--limit", "5"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active", "blocked"], limit=5, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_limit_short_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-n", "10"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active", "blocked"], limit=10, exclude_delegate=True,
            epic_key=None, parent_task_id=None,
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_displays_status_as_text(self, mock_tasks):
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": "Open", "status": "open",
             "epic_key": None, "epic_seq": None},
            {"id": 2, "title": "Active", "status": "active",
             "epic_key": None, "epic_seq": None},
            {"id": 3, "title": "Done", "status": "done",
             "epic_key": None, "epic_seq": None},
            {"id": 4, "title": "Failed", "status": "failed",
             "epic_key": None, "epic_seq": None},
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "open" in out
        assert "active" in out
        assert "done" in out
        assert "failed" in out

    @patch("emdx.commands.tasks.tasks")
    def test_list_does_not_truncate_title(self, mock_tasks):
        long_title = (
            "This is a very long task title that exceeds fifty"
            " characters by quite a bit"
        )
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": long_title, "status": "open",
             "epic_key": None, "epic_seq": None},
        ]
        result = runner.invoke(app, ["list"])
        out = _out(result)
        assert "quite a bit" in out


class TestTaskDelete:
    """Tests for task delete command."""

    @patch("emdx.commands.tasks.tasks")
    def test_delete_with_force(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Task to delete"}
        mock_tasks.delete_task.return_value = True
        result = runner.invoke(app, ["delete", "1", "--force"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Deleted #1" in out
        mock_tasks.delete_task.assert_called_once_with(1)

    @patch("emdx.commands.tasks.tasks")
    def test_delete_with_force_short_flag(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 2, "title": "Another task"}
        mock_tasks.delete_task.return_value = True
        result = runner.invoke(app, ["delete", "2", "-f"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Deleted #2" in out
        mock_tasks.delete_task.assert_called_once_with(2)

    @patch("emdx.commands.tasks.tasks")
    def test_delete_task_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["delete", "999", "--force"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    @patch("emdx.commands.tasks.tasks")
    def test_delete_with_confirmation(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 3, "title": "Confirm delete"}
        mock_tasks.delete_task.return_value = True
        result = runner.invoke(app, ["delete", "3"], input="y\n")
        assert result.exit_code == 0
        out = _out(result)
        assert "Deleted #3" in out

    @patch("emdx.commands.tasks.tasks")
    def test_delete_cancelled(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 4, "title": "Cancel delete"}
        result = runner.invoke(app, ["delete", "4"], input="n\n")
        assert result.exit_code == 0
        out = _out(result)
        assert "Cancelled" in out
        mock_tasks.delete_task.assert_not_called()

    def test_delete_requires_task_id(self):
        result = runner.invoke(app, ["delete"])
        assert result.exit_code != 0


class TestTaskView:
    """Tests for task view command."""

    @patch("emdx.commands.tasks.tasks")
    def test_view_shows_basic_info(self, mock_tasks):
        mock_tasks.get_task.return_value = {
            "id": 42, "title": "Fix auth bug", "status": "open",
            "description": "The auth middleware has a race condition",
            "epic_key": None, "epic_seq": None, "parent_task_id": None,
            "source_doc_id": None, "priority": 3, "created_at": "2026-01-15",
        }
        mock_tasks.get_dependencies.return_value = []
        mock_tasks.get_dependents.return_value = []
        mock_tasks.get_task_log.return_value = []

        result = runner.invoke(app, ["view", "42"])
        assert result.exit_code == 0
        out = _out(result)
        assert "#42" in out
        assert "Fix auth bug" in out
        assert "open" in out
        assert "race condition" in out

    @patch("emdx.commands.tasks.tasks")
    def test_view_shows_epic_label(self, mock_tasks):
        mock_tasks.get_task.return_value = {
            "id": 10, "title": "SEC-1: Harden auth", "status": "active",
            "description": "", "epic_key": "SEC", "epic_seq": 1,
            "parent_task_id": 500, "source_doc_id": 99, "priority": 1,
            "created_at": "2026-01-15",
        }
        mock_tasks.get_dependencies.return_value = []
        mock_tasks.get_dependents.return_value = []
        mock_tasks.get_task_log.return_value = []

        result = runner.invoke(app, ["view", "10"])
        out = _out(result)
        assert "SEC-1" in out
        assert "Category: SEC" in out
        assert "Epic: #500" in out
        assert "Doc: #99" in out
        assert "Priority: 1" in out

    @patch("emdx.commands.tasks.tasks")
    def test_view_shows_dependencies(self, mock_tasks):
        mock_tasks.get_task.return_value = {
            "id": 5, "title": "Task with deps", "status": "blocked",
            "description": "", "epic_key": None, "epic_seq": None,
            "parent_task_id": None, "source_doc_id": None, "priority": 3,
            "created_at": "2026-01-15",
        }
        mock_tasks.get_dependencies.return_value = [
            {"id": 3, "title": "Blocker task", "status": "active"},
        ]
        mock_tasks.get_dependents.return_value = [
            {"id": 8, "title": "Waiting task", "status": "open"},
        ]
        mock_tasks.get_task_log.return_value = []

        result = runner.invoke(app, ["view", "5"])
        out = _out(result)
        assert "Blocked by:" in out
        assert "#3" in out
        assert "Blocker task" in out
        assert "Blocks:" in out
        assert "#8" in out
        assert "Waiting task" in out

    @patch("emdx.commands.tasks.tasks")
    def test_view_shows_work_log(self, mock_tasks):
        mock_tasks.get_task.return_value = {
            "id": 7, "title": "Some task", "status": "active",
            "description": "", "epic_key": None, "epic_seq": None,
            "parent_task_id": None, "source_doc_id": None, "priority": 3,
            "created_at": "2026-01-15",
        }
        mock_tasks.get_dependencies.return_value = []
        mock_tasks.get_dependents.return_value = []
        mock_tasks.get_task_log.return_value = [
            {"message": "Started investigation", "created_at": "2026-01-15 10:00"},
            {"message": "Found root cause", "created_at": "2026-01-15 11:00"},
        ]

        result = runner.invoke(app, ["view", "7"])
        out = _out(result)
        assert "Work log:" in out
        assert "Started investigation" in out
        assert "Found root cause" in out

    @patch("emdx.commands.tasks.tasks")
    def test_view_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["view", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_view_requires_task_id(self):
        result = runner.invoke(app, ["view"])
        assert result.exit_code != 0


class TestTaskActive:
    """Tests for task active command."""

    @patch("emdx.commands.tasks.tasks")
    def test_active_marks_task(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Test task"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["active", "1"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Active" in out
        assert "#1" in out
        assert "Test task" in out
        mock_tasks.update_task.assert_called_once_with(1, status="active")

    @patch("emdx.commands.tasks.tasks")
    def test_active_with_note(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 2, "title": "Auth fix"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["active", "2", "--note", "Starting work"])
        assert result.exit_code == 0
        mock_tasks.update_task.assert_called_once_with(2, status="active")
        mock_tasks.log_progress.assert_called_once_with(2, "Starting work")

    @patch("emdx.commands.tasks.tasks")
    def test_active_with_note_short_flag(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 3, "title": "Feature"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["active", "3", "-n", "On it"])
        assert result.exit_code == 0
        mock_tasks.log_progress.assert_called_once_with(3, "On it")

    @patch("emdx.commands.tasks.tasks")
    def test_active_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["active", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_active_requires_task_id(self):
        result = runner.invoke(app, ["active"])
        assert result.exit_code != 0


class TestTaskLog:
    """Tests for task log command."""

    @patch("emdx.commands.tasks.tasks")
    def test_log_add_message(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Test task"}
        mock_tasks.log_progress.return_value = 1
        result = runner.invoke(app, ["log", "1", "Found the root cause"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Logged" in out
        assert "#1" in out
        assert "Found the root cause" in out
        mock_tasks.log_progress.assert_called_once_with(1, "Found the root cause")

    @patch("emdx.commands.tasks.tasks")
    def test_log_view_entries(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 5, "title": "Bug fix"}
        mock_tasks.get_task_log.return_value = [
            {"message": "Started debugging", "created_at": "2026-01-15 10:00"},
            {"message": "Identified issue in middleware", "created_at": "2026-01-15 11:00"},
        ]
        result = runner.invoke(app, ["log", "5"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Log for #5" in out
        assert "Bug fix" in out
        assert "Started debugging" in out
        assert "Identified issue in middleware" in out

    @patch("emdx.commands.tasks.tasks")
    def test_log_view_empty(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 3, "title": "Clean task"}
        mock_tasks.get_task_log.return_value = []
        result = runner.invoke(app, ["log", "3"])
        assert result.exit_code == 0
        assert "No log entries" in _out(result)

    @patch("emdx.commands.tasks.tasks")
    def test_log_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["log", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_log_requires_task_id(self):
        result = runner.invoke(app, ["log"])
        assert result.exit_code != 0


class TestTaskNote:
    """Tests for task note command."""

    @patch("emdx.commands.tasks.tasks")
    def test_note_logs_message(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Test task"}
        mock_tasks.log_progress.return_value = 1
        result = runner.invoke(app, ["note", "1", "Tried approach X"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Logged" in out
        assert "#1" in out
        assert "Tried approach X" in out
        mock_tasks.log_progress.assert_called_once_with(1, "Tried approach X")

    @patch("emdx.commands.tasks.tasks")
    def test_note_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["note", "999", "some note"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_note_requires_task_id_and_message(self):
        result = runner.invoke(app, ["note"])
        assert result.exit_code != 0

    def test_note_requires_message(self):
        result = runner.invoke(app, ["note", "1"])
        assert result.exit_code != 0


class TestTaskBlocked:
    """Tests for task blocked command."""

    @patch("emdx.commands.tasks.tasks")
    def test_blocked_marks_task(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 1, "title": "Test task"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["blocked", "1"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Blocked" in out
        assert "#1" in out
        assert "Test task" in out
        mock_tasks.update_task.assert_called_once_with(1, status="blocked")
        mock_tasks.log_progress.assert_not_called()

    @patch("emdx.commands.tasks.tasks")
    def test_blocked_with_reason(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 2, "title": "Auth fix"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["blocked", "2", "--reason", "Waiting on API key"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Blocked" in out
        assert "#2" in out
        assert "Waiting on API key" in out
        mock_tasks.update_task.assert_called_once_with(2, status="blocked")
        mock_tasks.log_progress.assert_called_once_with(2, "Blocked: Waiting on API key")

    @patch("emdx.commands.tasks.tasks")
    def test_blocked_with_reason_short_flag(self, mock_tasks):
        mock_tasks.get_task.return_value = {"id": 3, "title": "Feature"}
        mock_tasks.update_task.return_value = True
        result = runner.invoke(app, ["blocked", "3", "-r", "Needs review"])
        assert result.exit_code == 0
        mock_tasks.log_progress.assert_called_once_with(3, "Blocked: Needs review")

    @patch("emdx.commands.tasks.tasks")
    def test_blocked_not_found(self, mock_tasks):
        mock_tasks.get_task.return_value = None
        result = runner.invoke(app, ["blocked", "999"])
        assert result.exit_code == 1
        assert "not found" in _out(result)

    def test_blocked_requires_task_id(self):
        result = runner.invoke(app, ["blocked"])
        assert result.exit_code != 0
