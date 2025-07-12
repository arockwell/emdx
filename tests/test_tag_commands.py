"""Tests for tag_commands module."""

from unittest.mock import MagicMock, patch

import pytest
import typer

from emdx import tag_commands
from test_fixtures import TestDatabase


class TestTagCommands:
    """Test tag command functions."""

    def setup_method(self):
        """Set up test database and sample data."""
        self.db = TestDatabase(":memory:")
        self.doc_id = self.db.save_document("Test Document", "Test content", "test-project")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.add_tags_to_document")
    @patch("emdx.tag_commands.get_document_tags")
    def test_tag_command_add_tags(self, mock_get_tags, mock_add_tags, mock_db):
        """Test adding tags to a document."""
        # Setup mocks
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "Test content"
        }
        mock_add_tags.return_value = ["python", "testing"]
        mock_get_tags.return_value = ["python", "testing", "existing"]
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit"):
                try:
                    tag_commands.tag(1, ["python", "testing"])
                except:
                    pass  # Expected due to mocking
        
        mock_add_tags.assert_called_once_with(1, ["python", "testing"])
        mock_get_tags.assert_called()

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.get_document_tags")
    def test_tag_command_show_tags(self, mock_get_tags, mock_db):
        """Test showing current tags for a document."""
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "Test content"
        }
        mock_get_tags.return_value = ["python", "testing"]
        
        with patch("emdx.tag_commands.console") as mock_console:
            tag_commands.tag(1, [])
        
        mock_get_tags.assert_called_once_with(1)
        mock_console.print.assert_called()

    @patch("emdx.tag_commands.db")
    def test_tag_command_document_not_found(self, mock_db):
        """Test tagging non-existent document."""
        mock_db.get_document.return_value = None
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.tag(999, ["tag"])
                mock_exit.assert_called_with(1)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.add_tags_to_document")
    def test_tag_command_exception_handling(self, mock_add_tags, mock_db):
        """Test exception handling in tag command."""
        mock_db.get_document.return_value = {"id": 1, "title": "Test"}
        mock_add_tags.side_effect = Exception("Database error")
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.tag(1, ["tag"])
                mock_exit.assert_called_with(1)


class TestUntagCommands:
    """Test untag command functions."""

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.remove_tags_from_document")
    @patch("emdx.tag_commands.get_document_tags")
    def test_untag_command_remove_tags(self, mock_get_tags, mock_remove_tags, mock_db):
        """Test removing tags from a document."""
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "Test content"
        }
        mock_remove_tags.return_value = ["python"]
        mock_get_tags.return_value = ["testing"]
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit"):
                try:
                    tag_commands.untag(1, ["python"])
                except:
                    pass  # Expected due to mocking
        
        mock_remove_tags.assert_called_once_with(1, ["python"])
        mock_get_tags.assert_called()

    @patch("emdx.tag_commands.db")
    def test_untag_command_document_not_found(self, mock_db):
        """Test untagging non-existent document."""
        mock_db.get_document.return_value = None
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.untag(999, ["tag"])
                mock_exit.assert_called_with(1)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.remove_tags_from_document")
    def test_untag_command_no_tags_removed(self, mock_remove_tags, mock_db):
        """Test when no tags are removed."""
        mock_db.get_document.return_value = {"id": 1, "title": "Test"}
        mock_remove_tags.return_value = []
        
        with patch("emdx.tag_commands.console") as mock_console:
            with patch("emdx.tag_commands.get_document_tags", return_value=[]):
                try:
                    tag_commands.untag(1, ["nonexistent"])
                except:
                    pass
        
        mock_console.print.assert_called()


class TestTagsListCommand:
    """Test tags listing command."""

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_tags_command_with_tags(self, mock_list_tags, mock_db):
        """Test listing tags when tags exist."""
        from datetime import datetime
        
        mock_list_tags.return_value = [
            {
                "name": "python",
                "count": 5,
                "created_at": datetime(2024, 1, 1),
                "last_used": datetime(2024, 1, 15)
            },
            {
                "name": "testing",
                "count": 3,
                "created_at": datetime(2024, 1, 2),
                "last_used": datetime(2024, 1, 10)
            }
        ]
        
        with patch("emdx.tag_commands.console") as mock_console:
            tag_commands.tags(sort="usage", limit=50)
        
        mock_list_tags.assert_called_once_with(sort_by="usage")
        mock_console.print.assert_called()

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_tags_command_no_tags(self, mock_list_tags, mock_db):
        """Test listing tags when no tags exist."""
        mock_list_tags.return_value = []
        
        with patch("emdx.tag_commands.console") as mock_console:
            tag_commands.tags()
        
        mock_console.print.assert_called_with("[yellow]No tags found[/yellow]")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_tags_command_with_limit(self, mock_list_tags, mock_db):
        """Test listing tags with limit."""
        from datetime import datetime
        
        # Create more tags than the limit
        tags = []
        for i in range(15):
            tags.append({
                "name": f"tag{i}",
                "count": i + 1,
                "created_at": datetime(2024, 1, 1),
                "last_used": datetime(2024, 1, 15)
            })
        
        mock_list_tags.return_value = tags
        
        with patch("emdx.tag_commands.console") as mock_console:
            tag_commands.tags(limit=10)
        
        # Should show limit message
        mock_console.print.assert_called()

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_tags_command_exception(self, mock_list_tags, mock_db):
        """Test exception handling in tags command."""
        mock_list_tags.side_effect = Exception("Database error")
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.tags()
                mock_exit.assert_called_with(1)


class TestRetagCommand:
    """Test retag (rename) command."""

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.rename_tag")
    def test_retag_command_success(self, mock_rename, mock_list_tags, mock_db):
        """Test successful tag renaming."""
        mock_list_tags.return_value = [
            {"name": "oldtag", "count": 3}
        ]
        mock_rename.return_value = True
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", return_value=True):
                tag_commands.retag("oldtag", "newtag", force=False)
        
        mock_rename.assert_called_once_with("oldtag", "newtag")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_retag_command_tag_not_found(self, mock_list_tags, mock_db):
        """Test renaming non-existent tag."""
        mock_list_tags.return_value = []
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.retag("nonexistent", "newtag", force=False)
                mock_exit.assert_called_with(1)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.rename_tag")
    def test_retag_command_force(self, mock_rename, mock_list_tags, mock_db):
        """Test tag renaming with force flag."""
        mock_list_tags.return_value = [
            {"name": "oldtag", "count": 3}
        ]
        mock_rename.return_value = True
        
        with patch("emdx.tag_commands.console"):
            tag_commands.retag("oldtag", "newtag", force=True)
        
        mock_rename.assert_called_once_with("oldtag", "newtag")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.rename_tag")
    def test_retag_command_rename_failed(self, mock_rename, mock_list_tags, mock_db):
        """Test failed tag renaming."""
        mock_list_tags.return_value = [
            {"name": "oldtag", "count": 3}
        ]
        mock_rename.return_value = False
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", return_value=True):
                with patch("typer.Exit") as mock_exit:
                    tag_commands.retag("oldtag", "newtag", force=False)
                    mock_exit.assert_called_with(1)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_retag_command_cancelled(self, mock_list_tags, mock_db):
        """Test cancelled tag renaming."""
        mock_list_tags.return_value = [
            {"name": "oldtag", "count": 3}
        ]
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", side_effect=typer.Abort()):
                with patch("typer.Exit") as mock_exit:
                    tag_commands.retag("oldtag", "newtag", force=False)
                    mock_exit.assert_called_with(0)


class TestMergeTagsCommand:
    """Test merge tags command."""

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.merge_tags")
    def test_merge_tags_success(self, mock_merge, mock_list_tags, mock_db):
        """Test successful tag merging."""
        mock_list_tags.return_value = [
            {"name": "tag1", "count": 2},
            {"name": "tag2", "count": 3}
        ]
        mock_merge.return_value = 5
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", return_value=True):
                tag_commands.merge_tags_cmd(["tag1", "tag2"], target="merged", force=False)
        
        mock_merge.assert_called_once_with(["tag1", "tag2"], "merged")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_merge_tags_no_valid_source(self, mock_list_tags, mock_db):
        """Test merging with no valid source tags."""
        mock_list_tags.return_value = []
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.Exit") as mock_exit:
                tag_commands.merge_tags_cmd(["nonexistent"], target="merged", force=False)
                mock_exit.assert_called_with(1)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.merge_tags")
    def test_merge_tags_force(self, mock_merge, mock_list_tags, mock_db):
        """Test tag merging with force flag."""
        mock_list_tags.return_value = [
            {"name": "tag1", "count": 2}
        ]
        mock_merge.return_value = 2
        
        with patch("emdx.tag_commands.console"):
            tag_commands.merge_tags_cmd(["tag1"], target="merged", force=True)
        
        mock_merge.assert_called_once_with(["tag1"], "merged")

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    def test_merge_tags_cancelled(self, mock_list_tags, mock_db):
        """Test cancelled tag merging."""
        mock_list_tags.return_value = [
            {"name": "tag1", "count": 2}
        ]
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", side_effect=typer.Abort()):
                with patch("typer.Exit") as mock_exit:
                    tag_commands.merge_tags_cmd(["tag1"], target="merged", force=False)
                    mock_exit.assert_called_with(0)

    @patch("emdx.tag_commands.db")
    @patch("emdx.tag_commands.list_all_tags")
    @patch("emdx.tag_commands.merge_tags")
    def test_merge_tags_exception(self, mock_merge, mock_list_tags, mock_db):
        """Test exception handling in merge tags command."""
        mock_list_tags.return_value = [
            {"name": "tag1", "count": 2}
        ]
        mock_merge.side_effect = Exception("Database error")
        
        with patch("emdx.tag_commands.console"):
            with patch("typer.confirm", return_value=True):
                with patch("typer.Exit") as mock_exit:
                    tag_commands.merge_tags_cmd(["tag1"], target="merged", force=False)
                    mock_exit.assert_called_with(1)