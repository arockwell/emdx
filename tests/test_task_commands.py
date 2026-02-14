"""Tests for task CLI commands (add, list, ready, done, delete)."""

import re
from unittest.mock import patch, MagicMock

import typer
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
            {"id": 1, "title": "First task", "source_doc_id": None},
            {"id": 2, "title": "Second task", "source_doc_id": 42},
        ]
        result = runner.invoke(app, ["ready"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Ready (2)" in out
        assert "#1" in out
        assert "First task" in out
        assert "#2" in out
        assert "Second task" in out
        assert "doc #42" in out

    @patch("emdx.commands.tasks.tasks")
    def test_ready_task_without_doc(self, mock_tasks):
        mock_tasks.get_ready_tasks.return_value = [
            {"id": 3, "title": "No doc task"},
        ]
        result = runner.invoke(app, ["ready"])
        assert result.exit_code == 0
        out = _out(result)
        assert "#3" in out
        assert "No doc task" in out
        assert "doc #" not in out


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
            {"id": 1, "title": "Open task", "status": "open", "source_doc_id": None},
            {"id": 2, "title": "Active task", "status": "active", "source_doc_id": 10},
            {"id": 3, "title": "Done task", "status": "done", "source_doc_id": None},
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "1" in out
        assert "Open task" in out
        assert "2" in out
        assert "Active task" in out
        assert "3" in out
        assert "Done task" in out
        assert "3 task(s)" in out

    @patch("emdx.commands.tasks.tasks")
    def test_list_excludes_delegate_by_default(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=20, exclude_delegate=True
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_includes_delegate_with_all_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--all"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=20, exclude_delegate=False
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_all_short_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-a"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=20, exclude_delegate=False
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_status_filter(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--status", "open"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open"], limit=20, exclude_delegate=True
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_multiple_status_filter(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-s", "open,active"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=["open", "active"], limit=20, exclude_delegate=True
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_limit(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "--limit", "5"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=5, exclude_delegate=True
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_with_limit_short_flag(self, mock_tasks):
        mock_tasks.list_tasks.return_value = []
        result = runner.invoke(app, ["list", "-n", "10"])
        assert result.exit_code == 0
        mock_tasks.list_tasks.assert_called_once_with(
            status=None, limit=10, exclude_delegate=True
        )

    @patch("emdx.commands.tasks.tasks")
    def test_list_displays_status_icons(self, mock_tasks):
        mock_tasks.list_tasks.return_value = [
            {"id": 1, "title": "Open", "status": "open", "source_doc_id": None},
            {"id": 2, "title": "Active", "status": "active", "source_doc_id": None},
            {"id": 3, "title": "Done", "status": "done", "source_doc_id": None},
            {"id": 4, "title": "Failed", "status": "failed", "source_doc_id": None},
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        # Status icons should be present (○ open, ● active, ✓ done, ✗ failed)
        assert "○" in out or "●" in out or "✓" in out or "✗" in out


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
