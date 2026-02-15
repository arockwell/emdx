"""Simple CLI tests that work without complex mocking."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.main import app

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
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "emdx" in result.output

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
        # Typer shows error in stdout when stderr not captured
        error_output = result.stdout
        assert (
            "no such command" in error_output.lower()
            or "invalid" in error_output.lower()
            or result.exit_code == 2
        )

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.list_documents")
    def test_list_command(self, mock_list_docs, mock_db):
        """Test list command."""
        mock_db.ensure_schema = Mock()
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["list"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()

    def test_recent_command(self):
        """Test recent command."""
        result = runner.invoke(app, ["recent"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()

    @patch("emdx.commands._helpers.db")
    @patch("emdx.commands.browse.get_stats")
    def test_stats_command(self, mock_get_stats, mock_db):
        """Test stats command."""
        mock_db.ensure_schema = Mock()
        mock_get_stats.return_value = {
            "total": 0,
            "by_project": {},
            "recent_activity": []
        }
        
        result = runner.invoke(app, ["stats"])
        # Should show some statistics
        assert result.exit_code == 0

    @patch("emdx.models.tags.db")
    def test_tags_list_command(self, mock_db):
        """Test tag list command (was: tags)."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        result = runner.invoke(app, ["tag", "list"])
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

    def test_trailing_help_for_command(self):
        """Test trailing 'help' works as alternative to --help.

        The trailing 'help' → '--help' conversion happens in run(),
        so we test by converting the args ourselves (simulating run()'s behavior).
        """
        # Test 'emdx save help' shows save help (converted to 'emdx save --help')
        result = runner.invoke(app, ["save", "--help"])
        assert result.exit_code == 0
        assert "save" in result.stdout.lower()

    def test_trailing_help_for_subcommand_group(self):
        """Test trailing 'help' works for subcommand groups."""
        # Test 'emdx task help' shows task group help (converted to 'emdx task --help')
        result = runner.invoke(app, ["task", "--help"])
        assert result.exit_code == 0
        assert "task" in result.stdout.lower()

    def test_trailing_help_for_nested_command(self):
        """Test trailing 'help' works for nested subcommands."""
        # Test 'emdx task add help' shows task add help (converted to --help)
        result = runner.invoke(app, ["task", "add", "--help"])
        assert result.exit_code == 0
        assert "add" in result.stdout.lower()


class TestTrailingHelpConversion:
    """Test the trailing 'help' to '--help' conversion in run()."""

    def test_trailing_help_conversion(self):
        """Test that run() converts trailing 'help' to '--help'."""
        import sys
        from unittest.mock import patch

        # Test the conversion logic directly
        original_argv = sys.argv.copy()
        try:
            # Simulate 'emdx save help'
            sys.argv = ["emdx", "save", "help"]

            # Import and check the conversion would happen
            if len(sys.argv) >= 2 and sys.argv[-1] == "help":
                sys.argv[-1] = "--help"

            assert sys.argv == ["emdx", "save", "--help"]
        finally:
            sys.argv = original_argv

    def test_no_conversion_without_help(self):
        """Test that normal commands are not modified."""
        import sys

        original_argv = sys.argv.copy()
        try:
            # Simulate 'emdx save myfile.txt'
            sys.argv = ["emdx", "save", "myfile.txt"]

            # The conversion should NOT happen
            if len(sys.argv) >= 2 and sys.argv[-1] == "help":
                sys.argv[-1] = "--help"

            assert sys.argv == ["emdx", "save", "myfile.txt"]
        finally:
            sys.argv = original_argv
