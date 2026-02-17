"""Tests for trash management commands (list, restore, purge)."""

import re
from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.commands.trash import app

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class TestTrashList:
    """Tests for trash list command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_list_empty_trash(self, mock_list):
        mock_list.return_value = []
        result = runner.invoke(app)
        assert result.exit_code == 0
        assert "No documents in trash" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_list_empty_trash_with_days(self, mock_list):
        mock_list.return_value = []
        result = runner.invoke(app, ["list", "--days", "7"])
        assert result.exit_code == 0
        assert "No documents deleted in the last 7 days" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_list_shows_documents(self, mock_list):
        mock_list.return_value = [
            {
                "id": 42,
                "title": "Test Document",
                "project": "test-project",
                "deleted_at": datetime(2026, 1, 15, 10, 30),
                "access_count": 5,
            }
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "42" in out
        assert "Test Document" in out
        assert "test-project" in out

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_list_truncates_long_titles(self, mock_list):
        mock_list.return_value = [
            {
                "id": 1,
                "title": "A" * 60,
                "project": None,
                "deleted_at": datetime(2026, 1, 15),
                "access_count": 0,
            }
        ]
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        out = _out(result)
        # Title gets truncated — either by our code ("...") or Rich table ("…")
        assert "..." in out or "…" in out

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_callback_invokes_list(self, mock_list):
        """Invoking `trash` without subcommand runs list."""
        mock_list.return_value = []
        result = runner.invoke(app)
        assert result.exit_code == 0
        mock_list.assert_called_once()


class TestTrashRestore:
    """Tests for trash restore command."""

    def test_restore_no_args_exits(self):
        result = runner.invoke(app, ["restore"])
        assert result.exit_code == 1
        assert "Provide document ID" in _out(result)

    @patch("emdx.commands.trash.restore_document")
    def test_restore_single_doc(self, mock_restore):
        mock_restore.return_value = True
        result = runner.invoke(app, ["restore", "42"])
        assert result.exit_code == 0
        assert "Restored 1 document" in _out(result)
        mock_restore.assert_called_once_with("42")

    @patch("emdx.commands.trash.restore_document")
    def test_restore_not_found(self, mock_restore):
        mock_restore.return_value = False
        result = runner.invoke(app, ["restore", "999"])
        assert result.exit_code == 0
        assert "Could not restore" in _out(result)
        assert "999" in _out(result)

    @patch("emdx.commands.trash.restore_document")
    def test_restore_multiple_docs(self, mock_restore):
        mock_restore.side_effect = [True, False, True]
        result = runner.invoke(app, ["restore", "1", "2", "3"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Restored 2 document" in out
        assert "Could not restore 1 document" in out

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_restore_all_empty(self, mock_list):
        mock_list.return_value = []
        result = runner.invoke(app, ["restore", "--all"])
        assert result.exit_code == 0
        assert "No documents to restore" in _out(result)


class TestTrashPurge:
    """Tests for trash purge command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_purge_empty_trash(self, mock_list):
        mock_list.return_value = []
        result = runner.invoke(app, ["purge"])
        assert result.exit_code == 0
        assert "No documents in trash to purge" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.purge_deleted_documents")
    def test_purge_with_force(self, mock_purge, mock_list):
        mock_list.return_value = [{"id": 1, "deleted_at": datetime(2026, 1, 1)}]
        mock_purge.return_value = 1
        result = runner.invoke(app, ["purge", "--force"])
        assert result.exit_code == 0
        assert "Permanently deleted 1 document" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_purge_cancelled(self, mock_list):
        mock_list.return_value = [{"id": 1, "deleted_at": datetime(2026, 1, 1)}]
        result = runner.invoke(app, ["purge"], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in _out(result).lower()
