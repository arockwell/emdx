"""Tests for tag management CLI commands."""

import re
from datetime import datetime
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.commands.tags import app

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# tag add command (and bare `tag` shorthand via callback)
# ---------------------------------------------------------------------------
class TestTagAddCommand:
    """Tests for the tag add command."""

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.add_tags_to_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_add_tags_explicit(self, mock_db, mock_get_doc, mock_add_tags, mock_get_tags):
        """Add tags via explicit 'add' subcommand."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_add_tags.return_value = ["python", "testing"]
        mock_get_tags.return_value = ["python", "testing"]

        result = runner.invoke(app, ["add", "1", "python", "testing"])
        assert result.exit_code == 0
        assert "Added tags" in _out(result)
        mock_add_tags.assert_called_once_with(1, ["python", "testing"])

    def test_tag_shorthand_rewrite(self):
        """The _rewrite_tag_shorthand helper inserts 'add' for bare `emdx tag 42 active`."""
        from emdx.main import _rewrite_tag_shorthand

        # Shorthand: `emdx tag 42 active` → `emdx tag add 42 active`
        argv = ["emdx", "tag", "42", "active"]
        _rewrite_tag_shorthand(argv)
        assert argv == ["emdx", "tag", "add", "42", "active"]

        # Explicit subcommand should not be rewritten
        argv = ["emdx", "tag", "add", "42", "active"]
        _rewrite_tag_shorthand(argv)
        assert argv == ["emdx", "tag", "add", "42", "active"]

        # Other subcommands should not be rewritten
        for subcmd in ("remove", "list", "rename", "merge", "batch"):
            argv = ["emdx", "tag", subcmd]
            _rewrite_tag_shorthand(argv)
            assert argv[2] == subcmd

        # Bare `emdx tag` (no args) should not be rewritten
        argv = ["emdx", "tag"]
        _rewrite_tag_shorthand(argv)
        assert argv == ["emdx", "tag"]

        # Flags after tag should trigger add insertion
        argv = ["emdx", "tag", "42", "--auto"]
        _rewrite_tag_shorthand(argv)
        assert argv == ["emdx", "tag", "add", "42", "--auto"]

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_show_current(self, mock_db, mock_get_doc, mock_get_tags):
        """Tag with no tag arguments shows current tags."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["add", "1"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Tags for #1" in out

    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_doc_not_found(self, mock_db, mock_get_doc):
        """Tag a nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["add", "999", "test"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.add_tags_to_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_already_exists(self, mock_db, mock_get_doc, mock_add_tags, mock_get_tags):
        """Adding a tag that already exists shows message."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_add_tags.return_value = []  # no new tags added
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["add", "1", "python"])
        assert result.exit_code == 0
        assert "No new tags added" in _out(result)


# ---------------------------------------------------------------------------
# tag remove command (was: untag)
# ---------------------------------------------------------------------------
class TestTagRemoveCommand:
    """Tests for the tag remove command."""

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.remove_tags_from_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_remove(self, mock_db, mock_get_doc, mock_remove_tags, mock_get_tags):
        """Remove tags from a document."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_remove_tags.return_value = ["python"]
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["remove", "1", "python"])
        assert result.exit_code == 0
        assert "Removed tags" in _out(result)

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.remove_tags_from_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_remove_not_on_doc(self, mock_db, mock_get_doc, mock_remove_tags, mock_get_tags):
        """Removing a tag that doesn't exist shows message."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_remove_tags.return_value = []
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["remove", "1", "nonexistent"])
        assert result.exit_code == 0
        assert "No tags removed" in _out(result)

    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_remove_doc_not_found(self, mock_db, mock_get_doc):
        """Remove tags from a nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["remove", "999", "tag"])
        assert result.exit_code != 0
        assert "not found" in _out(result)


# ---------------------------------------------------------------------------
# tag list command (was: tags)
# ---------------------------------------------------------------------------
class TestTagListCommand:
    """Tests for the tag list command."""

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_tags_list(self, mock_db, mock_list_all):
        """List all tags."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {
                "name": "python",
                "count": 10,
                "created_at": datetime(2024, 1, 1),
                "last_used": datetime(2024, 6, 1),
            },
            {
                "name": "testing",
                "count": 5,
                "created_at": datetime(2024, 2, 1),
                "last_used": datetime(2024, 5, 15),
            },
        ]

        result = runner.invoke(app, ["list"])
        out = _out(result)
        assert result.exit_code == 0
        assert "python" in out
        assert "testing" in out

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_tags_list_empty(self, mock_db, mock_list_all):
        """No tags shows message."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No tags found" in _out(result)

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_tags_sort_option(self, mock_db, mock_list_all):
        """Tags with --sort option."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        runner.invoke(app, ["list", "--sort", "name"])
        mock_list_all.assert_called_once_with(sort_by="name")


# ---------------------------------------------------------------------------
# tag rename command (was: retag)
# ---------------------------------------------------------------------------
class TestTagRenameCommand:
    """Tests for the tag rename command."""

    @patch("emdx.commands.tags.rename_tag")
    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_rename_with_force(self, mock_db, mock_list_all, mock_rename):
        """Rename a tag with --force."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {"name": "old-tag", "count": 3, "created_at": None, "last_used": None},
        ]
        mock_rename.return_value = True

        result = runner.invoke(app, ["rename", "old-tag", "new-tag", "--force"])
        assert result.exit_code == 0
        assert "Renamed" in _out(result)
        mock_rename.assert_called_once_with("old-tag", "new-tag")

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_rename_not_found(self, mock_db, mock_list_all):
        """Rename a tag that doesn't exist shows error."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        result = runner.invoke(app, ["rename", "nope", "new", "--force"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.tags.rename_tag")
    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_rename_failure(self, mock_db, mock_list_all, mock_rename):
        """Rename that fails (e.g. target already exists) shows error."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {"name": "old", "count": 1, "created_at": None, "last_used": None},
        ]
        mock_rename.return_value = False

        result = runner.invoke(app, ["rename", "old", "existing", "--force"])
        assert result.exit_code != 0
        assert "Could not rename" in _out(result)


# ---------------------------------------------------------------------------
# tag merge command (was: merge-tags)
# ---------------------------------------------------------------------------
class TestTagMergeCommand:
    """Tests for the tag merge command."""

    @patch("emdx.commands.tags.merge_tags")
    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_merge_tags_with_force(self, mock_db, mock_list_all, mock_merge):
        """Merge tags with --force."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {"name": "tag1", "count": 3, "created_at": None, "last_used": None},
            {"name": "tag2", "count": 5, "created_at": None, "last_used": None},
        ]
        mock_merge.return_value = 8

        result = runner.invoke(app, [
            "merge", "tag1", "tag2", "--into", "combined", "--force",
        ])
        assert result.exit_code == 0
        assert "Merged" in _out(result)

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_merge_tags_no_valid_sources(self, mock_db, mock_list_all):
        """Merge with no valid source tags shows error."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        result = runner.invoke(app, [
            "merge", "nope1", "nope2", "--into", "target", "--force",
        ])
        assert result.exit_code != 0
        assert "No valid source tags" in _out(result)
