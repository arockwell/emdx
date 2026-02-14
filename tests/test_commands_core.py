"""Tests for core CRUD commands (save, view, edit, delete, restore, etc.)."""

import re
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import typer
from typer.testing import CliRunner

from emdx.commands.core import app, get_input_content, generate_title, InputContent

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# get_input_content helper
# ---------------------------------------------------------------------------
class TestGetInputContent:
    """Tests for the get_input_content helper."""

    @patch("sys.stdin")
    def test_reads_file_path(self, mock_stdin, tmp_path):
        """File path argument returns file content."""
        mock_stdin.isatty.return_value = True
        f = tmp_path / "note.md"
        f.write_text("hello world")

        result = get_input_content(str(f))
        assert result.content == "hello world"
        assert result.source_type == "file"
        assert result.source_path == f

    @patch("sys.stdin")
    def test_direct_text_when_not_a_file(self, mock_stdin):
        """Non-file string is treated as direct content."""
        mock_stdin.isatty.return_value = True
        result = get_input_content("just some text")
        assert result.content == "just some text"
        assert result.source_type == "direct"

    @patch("sys.stdin")
    def test_no_input_exits(self, mock_stdin):
        """No input at all raises typer.Exit."""
        import pytest
        from click.exceptions import Exit

        mock_stdin.isatty.return_value = True
        with pytest.raises(Exit):
            get_input_content(None)

    @patch("sys.stdin")
    def test_reads_from_stdin(self, mock_stdin):
        """Stdin content is read when available."""
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "piped content"

        result = get_input_content(None)
        assert result.content == "piped content"
        assert result.source_type == "stdin"


# ---------------------------------------------------------------------------
# generate_title helper
# ---------------------------------------------------------------------------
class TestGenerateTitle:
    """Tests for title generation."""

    def test_provided_title_wins(self):
        ic = InputContent(content="anything", source_type="file")
        assert generate_title(ic, "My Title") == "My Title"

    def test_file_source_uses_stem(self, tmp_path):
        f = tmp_path / "readme.md"
        ic = InputContent(content="x", source_type="file", source_path=f)
        assert generate_title(ic, None) == "readme"

    def test_stdin_source_generates_timestamp_title(self):
        ic = InputContent(content="piped data", source_type="stdin")
        title = generate_title(ic, None)
        assert "Piped content" in title

    def test_direct_source_uses_first_line(self):
        ic = InputContent(content="First line\nSecond line", source_type="direct")
        title = generate_title(ic, None)
        assert "First line" in title


# ---------------------------------------------------------------------------
# save command
# ---------------------------------------------------------------------------
class TestSaveCommand:
    """Tests for the save command."""

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_file(self, mock_detect, mock_create, mock_tags, mock_display, tmp_path):
        """Save a real file via CLI."""
        f = tmp_path / "doc.md"
        f.write_text("# Hello\nWorld")

        mock_detect.return_value = "test-proj"
        mock_create.return_value = 42
        mock_tags.return_value = []

        result = runner.invoke(app, ["save", str(f)])
        assert result.exit_code == 0
        mock_create.assert_called_once()
        args = mock_create.call_args
        assert args[0][0] == "doc"  # title = file stem

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_with_title_and_project(self, mock_detect, mock_create, mock_tags, mock_display, tmp_path):
        """Save with explicit --title and --project."""
        f = tmp_path / "note.md"
        f.write_text("content")

        mock_detect.return_value = "override-proj"
        mock_create.return_value = 1
        mock_tags.return_value = []

        result = runner.invoke(app, [
            "save", str(f),
            "--title", "Custom Title",
            "--project", "my-project",
        ])
        assert result.exit_code == 0
        args = mock_create.call_args
        assert args[0][0] == "Custom Title"

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_with_tags(self, mock_detect, mock_create, mock_tags, mock_display, tmp_path):
        """Save with --tags."""
        f = tmp_path / "tagged.md"
        f.write_text("tagged content")

        mock_detect.return_value = None
        mock_create.return_value = 5
        mock_tags.return_value = ["python", "testing"]

        result = runner.invoke(app, [
            "save", str(f), "--tags", "python,testing",
        ])
        assert result.exit_code == 0
        mock_tags.assert_called_once_with(5, "python,testing")

    def test_save_no_input(self):
        """Save with no arguments should fail."""
        result = runner.invoke(app, ["save"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# find command
# ---------------------------------------------------------------------------
class TestFindCommand:
    """Tests for the find command."""

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    @patch("emdx.commands.core.db")
    def test_find_basic(self, mock_db, mock_search, mock_get_tags):
        """Basic search returns results."""
        mock_db.ensure_schema = Mock()
        mock_search.return_value = [
            {
                "id": 1,
                "title": "Found Doc",
                "project": "proj",
                "created_at": datetime(2024, 1, 1),
                "access_count": 3,
            }
        ]
        mock_get_tags.return_value = {1: ["python"]}

        result = runner.invoke(app, ["find", "hello"])
        assert result.exit_code == 0
        assert "Found Doc" in _out(result)

    @patch("emdx.commands.core.db")
    def test_find_no_args(self, mock_db):
        """Find with no search terms and no tags should error."""
        mock_db.ensure_schema = Mock()
        result = runner.invoke(app, ["find"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    @patch("emdx.commands.core.db")
    def test_find_no_results(self, mock_db, mock_search, mock_get_tags):
        """Search with no results shows appropriate message."""
        mock_db.ensure_schema = Mock()
        mock_search.return_value = []

        result = runner.invoke(app, ["find", "nonexistent"])
        assert result.exit_code == 0
        assert "No results" in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    @patch("emdx.commands.core.db")
    def test_find_ids_only(self, mock_db, mock_search, mock_get_tags):
        """--ids-only outputs just IDs."""
        mock_db.ensure_schema = Mock()
        mock_search.return_value = [
            {
                "id": 42,
                "title": "Doc",
                "project": None,
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        ]
        mock_get_tags.return_value = {}

        result = runner.invoke(app, ["find", "test", "--ids-only"])
        assert result.exit_code == 0
        assert "42" in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    @patch("emdx.commands.core.db")
    def test_find_json_output(self, mock_db, mock_search, mock_get_tags):
        """--json outputs JSON array."""
        mock_db.ensure_schema = Mock()
        mock_search.return_value = [
            {
                "id": 1,
                "title": "JSON Doc",
                "project": "p",
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 2),
                "access_count": 0,
            }
        ]
        mock_get_tags.return_value = {1: []}

        result = runner.invoke(app, ["find", "test", "--json"])
        assert result.exit_code == 0
        assert '"id": 1' in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_by_tags")
    @patch("emdx.commands.core.db")
    def test_find_by_tags(self, mock_db, mock_search_tags, mock_get_tags):
        """Find with --tags does tag-based search."""
        mock_db.ensure_schema = Mock()
        mock_search_tags.return_value = [
            {
                "id": 5,
                "title": "Tagged",
                "project": None,
                "created_at": datetime(2024, 6, 1),
                "access_count": 1,
            }
        ]
        mock_get_tags.return_value = {5: ["python"]}

        result = runner.invoke(app, ["find", "--tags", "python"])
        assert result.exit_code == 0
        assert "Tagged" in _out(result)


# ---------------------------------------------------------------------------
# view command
# ---------------------------------------------------------------------------
class TestViewCommand:
    """Tests for the view command."""

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_view_by_id(self, mock_db, mock_get_doc, mock_get_tags):
        """View a document by numeric ID."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "My Doc",
            "content": "Hello world",
            "project": "test",
            "created_at": datetime(2024, 1, 1),
            "access_count": 5,
        }
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["view", "1", "--no-pager"])
        assert result.exit_code == 0
        assert "My Doc" in _out(result)

    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_view_not_found(self, mock_db, mock_get_doc):
        """View nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["view", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_view_raw(self, mock_db, mock_get_doc, mock_get_tags):
        """View with --raw shows raw content."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Raw Doc",
            "content": "# Raw markdown",
            "project": None,
            "created_at": datetime(2024, 1, 1),
            "access_count": 0,
        }
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["view", "1", "--raw", "--no-pager"])
        assert result.exit_code == 0
        assert "# Raw markdown" in _out(result)

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_view_no_header(self, mock_db, mock_get_doc, mock_get_tags):
        """View with --no-header hides header."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "No Header",
            "content": "Just content",
            "project": None,
            "created_at": datetime(2024, 1, 1),
            "access_count": 0,
        }
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["view", "1", "--no-header", "--no-pager"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Project:" not in out
        assert "Views:" not in out

    def test_view_missing_id(self):
        """View with no ID should fail."""
        result = runner.invoke(app, ["view"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# edit command
# ---------------------------------------------------------------------------
class TestEditCommand:
    """Tests for the edit command."""

    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_edit_title_only(self, mock_db, mock_get_doc, mock_update):
        """Edit with --title updates title without opening editor."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Old Title",
            "content": "content",
            "project": "p",
            "created_at": datetime(2024, 1, 1),
        }
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "1", "--title", "New Title"])
        assert result.exit_code == 0
        assert "New Title" in _out(result)
        mock_update.assert_called_once_with(1, "New Title", "content")

    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_edit_doc_not_found(self, mock_db, mock_get_doc):
        """Edit nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["edit", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_edit_title_failure(self, mock_db, mock_get_doc, mock_update):
        """Edit that fails to update shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Title",
            "content": "c",
            "project": None,
            "created_at": datetime(2024, 1, 1),
        }
        mock_update.return_value = False

        result = runner.invoke(app, ["edit", "1", "--title", "New"])
        assert result.exit_code != 0
        assert "Error" in _out(result)

    def test_edit_missing_id(self):
        """Edit with no ID should fail."""
        result = runner.invoke(app, ["edit"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# delete command
# ---------------------------------------------------------------------------
class TestDeleteCommand:
    """Tests for the delete command."""

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_delete_soft(self, mock_db, mock_get_doc, mock_delete):
        """Soft delete with --force skips confirmation."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "To Delete",
            "project": "p",
            "created_at": datetime(2024, 1, 1),
            "access_count": 0,
        }
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Moved" in out or "trash" in out
        mock_delete.assert_called_once_with("1", hard_delete=False)

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_delete_hard_force(self, mock_db, mock_get_doc, mock_delete):
        """Hard delete with --force --hard."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Perm Delete",
            "project": None,
            "created_at": datetime(2024, 1, 1),
            "access_count": 0,
        }
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force", "--hard"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)
        mock_delete.assert_called_once_with("1", hard_delete=True)

    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_delete_not_found(self, mock_db, mock_get_doc):
        """Deleting a non-existent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["delete", "999", "--force"])
        out = _out(result)
        assert result.exit_code != 0
        assert "not found" in out.lower() or "No valid" in out

    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_delete_dry_run(self, mock_db, mock_get_doc):
        """--dry-run shows what would be deleted without deleting."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {
            "id": 1,
            "title": "Dry Run Doc",
            "project": "p",
            "created_at": datetime(2024, 1, 1),
            "access_count": 0,
        }

        result = runner.invoke(app, ["delete", "1", "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in _out(result).lower()

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.db")
    def test_delete_multiple(self, mock_db, mock_get_doc, mock_delete):
        """Delete multiple documents at once."""
        mock_db.ensure_schema = Mock()

        def side_effect(identifier, track_access=True):
            docs = {
                "1": {"id": 1, "title": "Doc 1", "project": None, "created_at": datetime(2024, 1, 1), "access_count": 0},
                "2": {"id": 2, "title": "Doc 2", "project": None, "created_at": datetime(2024, 1, 2), "access_count": 0},
            }
            return docs.get(identifier)

        mock_get_doc.side_effect = side_effect
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "2", "--force"])
        assert result.exit_code == 0
        assert mock_delete.call_count == 2

    def test_delete_missing_id(self):
        """Delete with no ID should fail."""
        result = runner.invoke(app, ["delete"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# trash command (now a subcommand group: emdx trash [list|restore|purge])
# Uses main_app since trash is registered as a typer subgroup there.
# ---------------------------------------------------------------------------
from emdx.main import app as main_app

class TestTrashCommand:
    """Tests for the trash command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.db")
    def test_trash_empty(self, mock_db, mock_list_deleted):
        """Empty trash shows message."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash"])
        assert result.exit_code == 0
        assert "No documents in trash" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.db")
    def test_trash_with_items(self, mock_db, mock_list_deleted):
        """Trash with items shows table."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = [
            {
                "id": 1,
                "title": "Deleted Doc",
                "project": "proj",
                "deleted_at": datetime(2024, 6, 1, 10, 0),
                "access_count": 3,
            }
        ]

        result = runner.invoke(main_app, ["trash"])
        assert result.exit_code == 0
        assert "Deleted Doc" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.db")
    def test_trash_with_days_filter(self, mock_db, mock_list_deleted):
        """Trash --days filters by age."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash", "--days", "7"])
        assert result.exit_code == 0
        mock_list_deleted.assert_called_once_with(days=7, limit=50)


# ---------------------------------------------------------------------------
# trash restore command
# ---------------------------------------------------------------------------
class TestRestoreCommand:
    """Tests for the trash restore command."""

    @patch("emdx.commands.trash.restore_document")
    @patch("emdx.commands.trash.db")
    def test_restore_by_id(self, mock_db, mock_restore):
        """Restore a specific document."""
        mock_db.ensure_schema = Mock()
        mock_restore.return_value = True

        result = runner.invoke(main_app, ["trash", "restore", "1"])
        assert result.exit_code == 0
        assert "Restored" in _out(result)

    @patch("emdx.commands.trash.restore_document")
    @patch("emdx.commands.trash.db")
    def test_restore_not_found(self, mock_db, mock_restore):
        """Restore a document not in trash."""
        mock_db.ensure_schema = Mock()
        mock_restore.return_value = False

        result = runner.invoke(main_app, ["trash", "restore", "999"])
        assert result.exit_code == 0
        assert "Could not restore" in _out(result)

    @patch("emdx.commands.trash.db")
    def test_restore_no_args(self, mock_db):
        """Restore with no ID and no --all should error."""
        mock_db.ensure_schema = Mock()

        result = runner.invoke(main_app, ["trash", "restore"])
        assert result.exit_code != 0

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.restore_document")
    @patch("emdx.commands.trash.db")
    def test_restore_all(self, mock_db, mock_restore, mock_list_deleted):
        """Restore --all restores all deleted documents."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = [
            {"id": 1, "title": "D1"},
            {"id": 2, "title": "D2"},
        ]
        mock_restore.return_value = True

        result = runner.invoke(main_app, ["trash", "restore", "--all"], input="y\n")
        assert result.exit_code == 0
        assert "Restored 2" in _out(result)


# ---------------------------------------------------------------------------
# trash purge command
# ---------------------------------------------------------------------------
class TestPurgeCommand:
    """Tests for the trash purge command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.db")
    def test_purge_empty_trash(self, mock_db, mock_list_deleted):
        """Purge with empty trash shows message."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash", "purge"])
        assert result.exit_code == 0
        assert "No documents in trash" in _out(result)

    @patch("emdx.commands.trash.purge_deleted_documents")
    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.db")
    def test_purge_with_force(self, mock_db, mock_list_deleted, mock_purge):
        """Purge --force skips confirmation."""
        mock_db.ensure_schema = Mock()
        mock_list_deleted.return_value = [{"id": 1, "title": "D", "deleted_at": datetime(2024, 1, 1)}]
        mock_purge.return_value = 1

        result = runner.invoke(main_app, ["trash", "purge", "--force"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)


