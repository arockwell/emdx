"""Tests for browse commands."""

from datetime import datetime
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.commands.browse import app

runner = CliRunner()


class TestBrowseCommands:
    """Test browse command-line interface."""

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_empty_database(self, mock_list_docs, mock_db):
        """Test list command with empty database."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No documents found" in result.stdout
        mock_list_docs.assert_called_once()

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_with_documents(self, mock_list_docs, mock_db):
        """Test list command with documents."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = [
            {
                "id": 1,
                "title": "Test Document",
                "project": "test-project",
                "created_at": datetime(2024, 1, 1, 12, 0, 0),
                "access_count": 5,
            }
        ]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "Test Document" in result.stdout
        mock_list_docs.assert_called_once()

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_with_project_filter(self, mock_list_docs, mock_db):
        """Test list command with project filter."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list", "--project", "test-project"])

        assert result.exit_code == 0
        mock_list_docs.assert_called_once_with(
            project="test-project", limit=50
        )

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_json_format(self, mock_list_docs, mock_db):
        """Test list command with JSON format."""
        from datetime import datetime
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = [{"id": 1, "title": "Test", "project": "test", "created_at": datetime.now(), "access_count": 0}]  # noqa: E501

        result = runner.invoke(app, ["list", "--format", "json"])

        if result.exit_code != 0:
            print(f"Command failed with exit code {result.exit_code}")
            print(f"stdout: {result.stdout}")
            if result.exception:
                print(f"exception: {result.exception}")
        assert result.exit_code == 0
        assert "[" in result.stdout  # JSON array
        assert '"id": 1' in result.stdout

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.get_recent_documents")
    def test_recent_command(self, mock_get_recent_docs, mock_db):
        """Test recent command."""
        mock_db.ensure_schema = Mock()
        mock_get_recent_docs.return_value = [
            {
                "id": 1,
                "title": "Recent Doc",
                "project": "test",
                "accessed_at": datetime(2024, 1, 1, 14, 0, 0),
                "access_count": 10,
            }
        ]

        result = runner.invoke(app, ["recent"])

        assert result.exit_code == 0
        assert "Recent Doc" in result.stdout
        mock_get_recent_docs.assert_called_once_with(limit=10)

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.get_stats")
    def test_stats_command(self, mock_get_stats, mock_db):
        """Test stats command."""
        mock_db.ensure_schema = Mock()
        mock_get_stats.return_value = {
            "total_documents": 100,
            "total_projects": 10,
            "total_views": 1000,
            "avg_views": 10.0,
            "table_size": "1.0 MB",
            "most_viewed": {"title": "Popular Doc", "access_count": 50},
            "newest_doc": "2024-01-01",
        }

        result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "100" in result.stdout  # total documents
        assert "Popular Doc" in result.stdout
        mock_get_stats.assert_called_once_with(project=None)

