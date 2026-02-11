"""Tests for tag management CLI commands."""

import re
from datetime import datetime
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.commands.tags import app, _is_completion_tag

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# _is_completion_tag helper
# ---------------------------------------------------------------------------
class TestIsCompletionTag:
    """Tests for _is_completion_tag helper."""

    def test_text_completion_tags(self):
        assert _is_completion_tag("done") is True
        assert _is_completion_tag("complete") is True
        assert _is_completion_tag("success") is True
        assert _is_completion_tag("finished") is True
        assert _is_completion_tag("check") is True

    def test_case_insensitive(self):
        assert _is_completion_tag("Done") is True
        assert _is_completion_tag("DONE") is True

    def test_non_completion_tags(self):
        assert _is_completion_tag("python") is False
        assert _is_completion_tag("active") is False
        assert _is_completion_tag("wip") is False

    def test_emoji_completion_tags(self):
        assert _is_completion_tag("\u2705") is True  # checkmark
        assert _is_completion_tag("\U0001f389") is True  # party popper


# ---------------------------------------------------------------------------
# tag command - add tags
# ---------------------------------------------------------------------------
class TestTagCommand:
    """Tests for the tag command."""

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.add_tags_to_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_add_tags(self, mock_db, mock_get_doc, mock_add_tags, mock_get_tags):
        """Add tags to a document."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_add_tags.return_value = ["python", "testing"]
        mock_get_tags.return_value = ["python", "testing"]

        result = runner.invoke(app, ["tag", "1", "python", "testing"])
        assert result.exit_code == 0
        assert "Added tags" in _out(result)
        mock_add_tags.assert_called_once_with(1, ["python", "testing"])

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_show_current(self, mock_db, mock_get_doc, mock_get_tags):
        """Tag with no tag arguments shows current tags."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["tag", "1"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Tags for #1" in out

    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_doc_not_found(self, mock_db, mock_get_doc):
        """Tag a nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["tag", "999", "test"])
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

        result = runner.invoke(app, ["tag", "1", "python"])
        assert result.exit_code == 0
        assert "No new tags added" in _out(result)

    @patch("emdx.commands.tags.archive_descendants")
    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.add_tags_to_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_tag_completion_auto_archives(self, mock_db, mock_get_doc, mock_add_tags, mock_get_tags, mock_archive):
        """Adding completion tag auto-archives descendants."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_add_tags.return_value = ["done"]
        mock_get_tags.return_value = ["done"]
        mock_archive.return_value = 2

        result = runner.invoke(app, ["tag", "1", "done"])
        assert result.exit_code == 0
        assert "Auto-archived 2" in _out(result)


# ---------------------------------------------------------------------------
# untag command
# ---------------------------------------------------------------------------
class TestUntagCommand:
    """Tests for the untag command."""

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.remove_tags_from_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_untag(self, mock_db, mock_get_doc, mock_remove_tags, mock_get_tags):
        """Remove tags from a document."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_remove_tags.return_value = ["python"]
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["untag", "1", "python"])
        assert result.exit_code == 0
        assert "Removed tags" in _out(result)

    @patch("emdx.commands.tags.get_document_tags")
    @patch("emdx.commands.tags.remove_tags_from_document")
    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_untag_not_on_doc(self, mock_db, mock_get_doc, mock_remove_tags, mock_get_tags):
        """Removing a tag that doesn't exist shows message."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = {"id": 1, "title": "Doc"}
        mock_remove_tags.return_value = []
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["untag", "1", "nonexistent"])
        assert result.exit_code == 0
        assert "No tags removed" in _out(result)

    @patch("emdx.commands.tags.get_document")
    @patch("emdx.commands.tags.db")
    def test_untag_doc_not_found(self, mock_db, mock_get_doc):
        """Untag a nonexistent document shows error."""
        mock_db.ensure_schema = Mock()
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["untag", "999", "tag"])
        assert result.exit_code != 0
        assert "not found" in _out(result)


# ---------------------------------------------------------------------------
# tags command (list all tags)
# ---------------------------------------------------------------------------
class TestTagsListCommand:
    """Tests for the tags command."""

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

        result = runner.invoke(app, ["tags"])
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

        result = runner.invoke(app, ["tags"])
        assert result.exit_code == 0
        assert "No tags found" in _out(result)

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_tags_sort_option(self, mock_db, mock_list_all):
        """Tags with --sort option."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        runner.invoke(app, ["tags", "--sort", "name"])
        mock_list_all.assert_called_once_with(sort_by="name")


# ---------------------------------------------------------------------------
# retag command
# ---------------------------------------------------------------------------
class TestRetagCommand:
    """Tests for the retag command."""

    @patch("emdx.commands.tags.rename_tag")
    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_retag_with_force(self, mock_db, mock_list_all, mock_rename):
        """Rename a tag with --force."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {"name": "old-tag", "count": 3, "created_at": None, "last_used": None},
        ]
        mock_rename.return_value = True

        result = runner.invoke(app, ["retag", "old-tag", "new-tag", "--force"])
        assert result.exit_code == 0
        assert "Renamed" in _out(result)
        mock_rename.assert_called_once_with("old-tag", "new-tag")

    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_retag_not_found(self, mock_db, mock_list_all):
        """Rename a tag that doesn't exist shows error."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = []

        result = runner.invoke(app, ["retag", "nope", "new", "--force"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.tags.rename_tag")
    @patch("emdx.commands.tags.list_all_tags")
    @patch("emdx.commands.tags.db")
    def test_retag_failure(self, mock_db, mock_list_all, mock_rename):
        """Rename that fails (e.g. target already exists) shows error."""
        mock_db.ensure_schema = Mock()
        mock_list_all.return_value = [
            {"name": "old", "count": 1, "created_at": None, "last_used": None},
        ]
        mock_rename.return_value = False

        result = runner.invoke(app, ["retag", "old", "existing", "--force"])
        assert result.exit_code != 0
        assert "Could not rename" in _out(result)


# ---------------------------------------------------------------------------
# merge-tags command
# ---------------------------------------------------------------------------
class TestMergeTagsCommand:
    """Tests for the merge-tags command."""

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
            "merge-tags", "tag1", "tag2", "--into", "combined", "--force",
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
            "merge-tags", "nope1", "nope2", "--into", "target", "--force",
        ])
        assert result.exit_code != 0
        assert "No valid source tags" in _out(result)


# ---------------------------------------------------------------------------
# legend command
# ---------------------------------------------------------------------------
class TestLegendCommand:
    """Tests for the legend command."""

    @patch("emdx.commands.tags.generate_legend")
    def test_legend(self, mock_legend):
        """Legend command displays emoji legend."""
        mock_legend.return_value = "# Emoji Legend\n- gameplan -> target"

        result = runner.invoke(app, ["legend"])
        assert result.exit_code == 0
