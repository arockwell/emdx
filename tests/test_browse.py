"""Tests for browse commands."""

from datetime import datetime
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.commands.browse import app

runner = CliRunner()


class TestBrowseCommands:
    """Test browse command-line interface."""

    @patch("emdx.commands.browse.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_empty_database(self, mock_list_docs, mock_db):
        """Test list command with empty database."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No documents found" in result.stdout
        mock_list_docs.assert_called_once()

    @patch("emdx.commands.browse.db")
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

    @patch("emdx.commands.browse.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command_with_project_filter(self, mock_list_docs, mock_db):
        """Test list command with project filter."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list", "--project", "test-project"])

        assert result.exit_code == 0
        mock_list_docs.assert_called_once_with(project="test-project", limit=50)

    @patch("emdx.commands.browse.db")
    def test_list_command_json_format(self, mock_db):
        """Test list command with JSON format."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = [{"id": 1, "title": "Test", "project": "test"}]

        result = runner.invoke(app, ["list", "--format", "json"])

        assert result.exit_code == 0
        assert "[" in result.stdout  # JSON array
        assert '"id": 1' in result.stdout

    @patch("emdx.commands.browse.db")
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

    @patch("emdx.commands.browse.db")
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

    @patch("emdx.commands.browse.db")
    def test_projects_command(self, mock_db):
        """Test projects command."""
        mock_db.ensure_schema = Mock()
        
        # Mock the connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            ("project-a", 10),
            ("project-b", 5),
            (None, 3),
        ]
        mock_conn.execute.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        result = runner.invoke(app, ["projects"])

        assert result.exit_code == 0
        assert "project-a" in result.stdout
        assert "10" in result.stdout

    @patch("emdx.commands.browse.db")
    def test_projects_command_empty(self, mock_db):
        """Test projects command with no projects."""
        mock_db.ensure_schema = Mock()
        mock_db.get_projects.return_value = []

        result = runner.invoke(app, ["projects"])

        assert result.exit_code == 0
        assert "No projects found" in result.stdout
