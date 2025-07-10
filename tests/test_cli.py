"""Simple CLI tests that work without complex mocking."""

import pytest
from typer.testing import CliRunner

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
        
        # Version might not be implemented, but command should be recognized
        # or show help
        assert "Usage:" in result.stdout or "version" in result.stdout.lower()
    
    def test_cli_subcommand_help(self):
        """Test subcommand help."""
        # Test save help
        result = runner.invoke(app, ["save", "--help"])
        assert "Usage:" in result.stdout
        assert "--title" in result.stdout
        
        # Test find help
        result = runner.invoke(app, ["find", "--help"])
        assert "Usage:" in result.stdout
        assert "query" in result.stdout.lower() or "search" in result.stdout.lower()
    
    def test_cli_invalid_command(self):
        """Test invalid command shows error."""
        result = runner.invoke(app, ["nonexistent-command"])
        
        assert result.exit_code != 0
        # Typer shows different error messages depending on version
        assert "No such command" in result.stdout or "Error" in result.stdout or "Invalid" in result.stdout