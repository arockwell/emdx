"""Tests for browse commands."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.browse import app

runner = CliRunner()


class TestBrowseCommands:
    """Test browse command-line interface."""

    @patch("emdx.browse.db")
    def test_list_command_empty_database(self, mock_db):
        """Test list command with empty database."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No documents found" in result.stdout
        mock_db.list_documents.assert_called_once()

    @patch("emdx.browse.db")
    def test_list_command_with_documents(self, mock_db):
        """Test list command with documents."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = [
            {
                "id": 1,
                "title": "Test Document",
                "project": "test-project",
                "created_at": "2024-01-01 12:00:00",
                "view_count": 5,
            }
        ]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "Test Document" in result.stdout
        mock_db.list_documents.assert_called_once()

    @patch("emdx.browse.db")
    def test_list_command_with_project_filter(self, mock_db):
        """Test list command with project filter."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = []

        result = runner.invoke(app, ["list", "--project", "test-project"])

        assert result.exit_code == 0
        mock_db.list_documents.assert_called_once_with(project="test-project", limit=50)

    @patch("emdx.browse.db")
    def test_list_command_json_format(self, mock_db):
        """Test list command with JSON format."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = [{"id": 1, "title": "Test", "project": "test"}]

        result = runner.invoke(app, ["list", "--format", "json"])

        assert result.exit_code == 0
        assert "[" in result.stdout  # JSON array
        assert '"id": 1' in result.stdout

    @patch("emdx.browse.db")
    def test_recent_command(self, mock_db):
        """Test recent command."""
        mock_db.ensure_schema = Mock()
        mock_db.get_recently_accessed.return_value = [
            {
                "id": 1,
                "title": "Recent Doc",
                "project": "test",
                "last_accessed": "2024-01-01 14:00:00",
                "view_count": 10,
            }
        ]

        result = runner.invoke(app, ["recent"])

        assert result.exit_code == 0
        assert "Recent Doc" in result.stdout
        mock_db.get_recently_accessed.assert_called_once()

    @patch("emdx.browse.db")
    def test_stats_command(self, mock_db):
        """Test stats command."""
        mock_db.ensure_schema = Mock()
        mock_db.get_stats.return_value = {
            "total_documents": 100,
            "total_projects": 10,
            "total_size": 1048576,
            "most_viewed": [{"title": "Popular Doc", "view_count": 50}],
            "project_stats": [{"project": "main", "count": 30}],
        }

        result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "100" in result.stdout  # total documents
        assert "Popular Doc" in result.stdout
        mock_db.get_stats.assert_called_once()

    @patch("emdx.browse.db")
    def test_projects_command(self, mock_db):
        """Test projects command."""
        mock_db.ensure_schema = Mock()
        mock_db.get_projects.return_value = [
            {"project": "project-a", "count": 10},
            {"project": "project-b", "count": 5},
            {"project": None, "count": 3},
        ]

        result = runner.invoke(app, ["projects"])

        assert result.exit_code == 0
        assert "project-a" in result.stdout
        assert "10" in result.stdout
        mock_db.get_projects.assert_called_once()

    @patch("emdx.browse.db")
    def test_projects_command_empty(self, mock_db):
        """Test projects command with no projects."""
        mock_db.ensure_schema = Mock()
        mock_db.get_projects.return_value = []

        result = runner.invoke(app, ["projects"])

        assert result.exit_code == 0
        assert "No projects found" in result.stdout
