"""Tests for --task and --done flags in emdx save command (PR #649)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner, Result

from emdx.commands.core import app
from emdx.models import tasks as tasks_model
from emdx.models.task import Task

runner = CliRunner()


def _out(result: Result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestSaveTaskFlag:
    """Tests for the --task flag in save command."""

    @patch("emdx.models.tasks.resolve_task_id")
    @patch("emdx.models.tasks.update_task")
    @patch("emdx.models.tasks.get_task")
    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_task_flag_links_document_to_task(
        self,
        mock_detect: MagicMock,
        mock_create: MagicMock,
        mock_tags: MagicMock,
        mock_display: MagicMock,
        mock_get_task: MagicMock,
        mock_update_task: MagicMock,
        mock_resolve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--task flag links saved document to task via output_doc_id."""
        f = tmp_path / "doc.md"
        f.write_text("# Task output\nContent here")

        mock_detect.return_value = "test-proj"
        mock_create.return_value = 42
        mock_tags.return_value = []
        mock_resolve.return_value = 10
        mock_get_task.return_value = Task(id=10, title="Some task", status="active")
        mock_update_task.return_value = True

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "10"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Task:" in out or "#10" in out

        # Verify the raw --task value was resolved before use
        mock_resolve.assert_called_once_with("10")
        # Verify update_task was called with output_doc_id
        mock_update_task.assert_called_once_with(10, output_doc_id=42)

    @patch("emdx.models.tasks.resolve_task_id")
    @patch("emdx.models.tasks.update_task")
    @patch("emdx.models.tasks.get_task")
    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_task_flag_with_stdin(
        self,
        mock_detect: MagicMock,
        mock_create: MagicMock,
        mock_tags: MagicMock,
        mock_display: MagicMock,
        mock_get_task: MagicMock,
        mock_update_task: MagicMock,
        mock_resolve: MagicMock,
    ) -> None:
        """--task flag works with stdin input."""
        mock_detect.return_value = None
        mock_create.return_value = 99
        mock_tags.return_value = []
        mock_resolve.return_value = 5
        mock_get_task.return_value = Task(id=5, title="Research task", status="open")
        mock_update_task.return_value = True

        result = runner.invoke(
            app,
            ["save", "--task", "5", "--title", "Research findings"],
            input="Analysis results here\n",
        )
        assert result.exit_code == 0

        # Verify update_task was called with output_doc_id
        mock_update_task.assert_called_once_with(5, output_doc_id=99)

    @patch("emdx.models.tasks.update_task")
    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_task_flag_accepts_epic_key_alias(
        self,
        mock_detect: MagicMock,
        mock_create: MagicMock,
        mock_tags: MagicMock,
        mock_display: MagicMock,
        mock_update_task: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--task accepts a KEY-N alias (e.g. COLO-1), same as --epic already does (#1128)."""
        f = tmp_path / "doc.md"
        f.write_text("# Task output\nContent here")

        task_id = tasks_model.create_task("Real task", epic_key="SAVK")
        task = tasks_model.get_task(task_id)
        assert task is not None
        alias = f"{task.epic_key}-{task.epic_seq}"

        mock_detect.return_value = "test-proj"
        mock_create.return_value = 42
        mock_tags.return_value = []
        mock_update_task.return_value = True

        result = runner.invoke(app, ["save", "--file", str(f), "--task", alias])
        assert result.exit_code == 0
        out = _out(result)
        assert alias in out

        mock_update_task.assert_called_once_with(task_id, output_doc_id=42)


class TestSaveDoneFlag:
    """Tests for the --done flag in save command."""

    @patch("emdx.models.tasks.resolve_task_id")
    @patch("emdx.models.tasks.update_task")
    @patch("emdx.models.tasks.get_task")
    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_done_flag_marks_linked_task_as_done(
        self,
        mock_detect: MagicMock,
        mock_create: MagicMock,
        mock_tags: MagicMock,
        mock_display: MagicMock,
        mock_get_task: MagicMock,
        mock_update_task: MagicMock,
        mock_resolve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--done flag marks linked task as done."""
        f = tmp_path / "complete.md"
        f.write_text("# Completed work\nAll done")

        mock_detect.return_value = "proj"
        mock_create.return_value = 77
        mock_tags.return_value = []
        mock_resolve.return_value = 15
        mock_get_task.return_value = Task(id=15, title="Implementation task", status="active")
        mock_update_task.return_value = True

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "15", "--done"])
        assert result.exit_code == 0
        out = _out(result)
        assert "(done)" in out or "done" in out.lower()

        # Verify update_task was called with both output_doc_id and status
        mock_update_task.assert_called_once_with(15, output_doc_id=77, status="done")

    @patch("emdx.models.tasks.resolve_task_id")
    @patch("emdx.models.tasks.update_task")
    @patch("emdx.models.tasks.get_task")
    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_done_flag_shows_done_status_in_output(
        self,
        mock_detect: MagicMock,
        mock_create: MagicMock,
        mock_tags: MagicMock,
        mock_display: MagicMock,
        mock_get_task: MagicMock,
        mock_update_task: MagicMock,
        mock_resolve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--done flag shows done status in the output."""
        f = tmp_path / "final.md"
        f.write_text("Final results")

        mock_detect.return_value = None
        mock_create.return_value = 100
        mock_tags.return_value = []
        mock_resolve.return_value = 20
        mock_get_task.return_value = Task(id=20, title="Final task", status="active")
        mock_update_task.return_value = True

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "20", "--done"])
        assert result.exit_code == 0
        out = _out(result)
        # Output should indicate task is marked done
        assert "(done)" in out


class TestSaveDoneWithoutTask:
    """Tests for --done flag error when used without --task."""

    def test_done_without_task_shows_error(self, tmp_path: Path) -> None:
        """--done without --task shows error."""
        f = tmp_path / "doc.md"
        f.write_text("content")

        result = runner.invoke(app, ["save", "--file", str(f), "--done"])
        assert result.exit_code != 0
        out = _out(result)
        assert "--done requires --task" in out

    def test_done_without_task_via_stdin(self) -> None:
        """--done without --task shows error even with stdin input."""
        result = runner.invoke(app, ["save", "--done", "--title", "Test"], input="some content\n")
        assert result.exit_code != 0
        out = _out(result)
        assert "--done requires --task" in out


class TestSaveTaskNotFound:
    """Tests for error when --task references non-existent task."""

    @patch("emdx.models.tasks.resolve_task_id")
    def test_task_not_found_shows_error(self, mock_resolve: MagicMock, tmp_path: Path) -> None:
        """--task with non-existent task ID shows error."""
        f = tmp_path / "doc.md"
        f.write_text("content")

        mock_resolve.return_value = None

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "999"])
        assert result.exit_code != 0
        out = _out(result)
        assert "Task not found: 999" in out

    @patch("emdx.models.tasks.resolve_task_id")
    def test_task_not_found_with_done_shows_error(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """--task with --done and non-existent task ID shows error."""
        f = tmp_path / "doc.md"
        f.write_text("content")

        mock_resolve.return_value = None

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "123", "--done"])
        assert result.exit_code != 0
        out = _out(result)
        assert "Task not found: 123" in out

    @patch("emdx.models.tasks.resolve_task_id")
    def test_task_validation_happens_before_document_creation(
        self, mock_resolve: MagicMock, tmp_path: Path
    ) -> None:
        """Task validation happens before document is created."""
        f = tmp_path / "doc.md"
        f.write_text("content")

        mock_resolve.return_value = None

        # If document creation was attempted, we'd see different behavior
        # This test ensures validation is upfront
        with patch("emdx.commands.core.create_document") as mock_create:
            result = runner.invoke(app, ["save", "--file", str(f), "--task", "456"])
            assert result.exit_code != 0
            # Document should NOT be created if task doesn't exist
            mock_create.assert_not_called()
