"""Simple CLI tests that work without complex mocking."""

import pytest
from typer.testing import CliRunner
from unittest.mock import Mock, patch

from emdx.cli import app


runner = CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""
    
    def test_cli_help(self):
        """Test help command works."""
        result = runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "Usage:" in result.stdout
        assert "Command" in result.stdout or "Usage:" in result.stdout
    
    def test_cli_version(self):
        """Test version command."""
        result = runner.invoke(app, ["--version"])
        
        # Version is not implemented, so it should show an error
        assert result.exit_code != 0
    
    def test_cli_subcommand_help(self):
        """Test subcommand help."""
        # Test save help
        result = runner.invoke(app, ["save", "--help"])
        assert result.exit_code == 0
        assert "save" in result.stdout.lower()
        
        # Test find help
        result = runner.invoke(app, ["find", "--help"])
        assert result.exit_code == 0
        assert "find" in result.stdout.lower()
    
    def test_cli_invalid_command(self):
        """Test invalid command shows error."""
        result = runner.invoke(app, ["nonexistent-command"])
        
        assert result.exit_code != 0
        # Typer shows error in stderr or stdout
        error_output = result.stdout + result.stderr
        assert "no such command" in error_output.lower() or "invalid" in error_output.lower() or result.exit_code == 2
    
    @patch('emdx.database.db')
    def test_list_command(self, mock_db):
        """Test list command."""
        mock_db.ensure_schema = Mock()
        mock_db.list_documents.return_value = []
        
        result = runner.invoke(app, ["list"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()
    
    def test_recent_command(self):
        """Test recent command."""
        result = runner.invoke(app, ["recent"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()
    
    def test_stats_command(self):
        """Test stats command."""
        result = runner.invoke(app, ["stats"])
        # Should show some statistics
        assert result.exit_code == 0
    
    @patch('emdx.tags.db')
    def test_tags_list_command(self, mock_db):
        """Test tags list command."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn
        
        result = runner.invoke(app, ["tags", "list"])
        # Should work even with no tags
        assert result.exit_code == 0
    
    def test_save_command_missing_file(self):
        """Test save command with missing file."""
        result = runner.invoke(app, ["save"])
        # Should show error about missing file
        assert result.exit_code != 0
    
    def test_find_command_missing_query(self):
        """Test find command with missing query."""
        result = runner.invoke(app, ["find"])
        # Should show error about missing query
        assert result.exit_code != 0
    
    def test_view_command_missing_id(self):
        """Test view command with missing document ID."""
        result = runner.invoke(app, ["view"])
        # Should show error about missing ID
        assert result.exit_code != 0
    
    def test_delete_command_missing_id(self):
        """Test delete command with missing document ID."""
        result = runner.invoke(app, ["delete"])
        # Should show error about missing ID
        assert result.exit_code != 0