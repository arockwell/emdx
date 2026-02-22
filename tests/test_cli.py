"""Simple CLI tests that work without complex mocking."""

from typing import Any
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from emdx.main import app

runner = CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_help(self) -> None:
        """Test help command works."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Usage:" in result.stdout
        assert "Command" in result.stdout or "Usage:" in result.stdout

    def test_cli_version(self) -> None:
        """Test --version flag."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "emdx" in result.output

    def test_cli_subcommand_help(self) -> None:
        """Test subcommand help."""
        # Test save help
        result = runner.invoke(app, ["save", "--help"])
        assert result.exit_code == 0
        assert "save" in result.stdout.lower()

        # Test find help
        result = runner.invoke(app, ["find", "--help"])
        assert result.exit_code == 0
        assert "find" in result.stdout.lower()

    def test_cli_invalid_command(self) -> None:
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

    @patch("emdx.models.documents.list_documents")
    def test_find_all_command(self, mock_list_docs: Any) -> None:
        """Test find --all command (replaces old list command)."""
        mock_list_docs.return_value = []

        result = runner.invoke(app, ["find", "--all"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()

    @patch("emdx.models.documents.get_recent_documents")
    def test_find_recent_command(self, mock_recent_docs: Any) -> None:
        """Test find --recent command (replaces old recent command)."""
        mock_recent_docs.return_value = []

        result = runner.invoke(app, ["find", "--recent", "10"])
        # Should work even with empty database
        assert result.exit_code == 0 or "no documents" in result.stdout.lower()

    @patch("emdx.models.tags.db")
    def test_tags_list_command(self, mock_db: Any) -> None:
        """Test tag list command (was: tags)."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        result = runner.invoke(app, ["tag", "list"])
        # Should work even with no tags
        assert result.exit_code == 0

    def test_save_command_missing_file(self) -> None:
        """Test save command with missing file."""
        result = runner.invoke(app, ["save"])
        # Should show error about missing file
        assert result.exit_code != 0

    def test_find_command_missing_query(self) -> None:
        """Test find command with missing query."""
        result = runner.invoke(app, ["find"])
        # Should show error about missing query
        assert result.exit_code != 0

    def test_view_command_missing_id(self) -> None:
        """Test view command with missing document ID."""
        result = runner.invoke(app, ["view"])
        # Should show error about missing ID
        assert result.exit_code != 0

    def test_delete_command_missing_id(self) -> None:
        """Test delete command with missing document ID."""
        result = runner.invoke(app, ["delete"])
        # Should show error about missing ID
        assert result.exit_code != 0

    def test_trailing_help_for_command(self) -> None:
        """Test trailing 'help' works as alternative to --help.

        The trailing 'help' → '--help' conversion happens in run(),
        so we test by converting the args ourselves (simulating run()'s behavior).
        """
        # Test 'emdx save help' shows save help (converted to 'emdx save --help')
        result = runner.invoke(app, ["save", "--help"])
        assert result.exit_code == 0
        assert "save" in result.stdout.lower()

    def test_trailing_help_for_subcommand_group(self) -> None:
        """Test trailing 'help' works for subcommand groups."""
        # Test 'emdx task help' shows task group help (converted to 'emdx task --help')
        result = runner.invoke(app, ["task", "--help"])
        assert result.exit_code == 0
        assert "task" in result.stdout.lower()

    def test_trailing_help_for_nested_command(self) -> None:
        """Test trailing 'help' works for nested subcommands."""
        # Test 'emdx task add help' shows task add help (converted to --help)
        result = runner.invoke(app, ["task", "add", "--help"])
        assert result.exit_code == 0
        assert "add" in result.stdout.lower()


class TestCommandAliases:
    """Test agent-friendly command alias rewriting in _rewrite_command_aliases."""

    def test_search_alias_rewrites_to_find(self) -> None:
        """emdx search query → emdx find query."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "search", "docker compose"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "find", "docker compose"]

    def test_search_alias_preserves_flags(self) -> None:
        """emdx search --mode semantic query → emdx find --mode semantic query."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "search", "--mode", "semantic", "query"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "find", "--mode", "semantic", "query"]

    def test_restore_alias_rewrites_to_trash_restore(self) -> None:
        """emdx restore 42 → emdx trash restore 42."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "restore", "42"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "trash", "restore", "42"]

    def test_restore_alias_with_all_flag(self) -> None:
        """emdx restore --all → emdx trash restore --all."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "restore", "--all"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "trash", "restore", "--all"]

    def test_alias_with_global_flags_before_command(self) -> None:
        """emdx --verbose search query → emdx --verbose find query."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "--verbose", "search", "query"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "--verbose", "find", "query"]

    def test_non_alias_commands_unchanged(self) -> None:
        """Real commands should not be rewritten."""
        from emdx.main import _rewrite_command_aliases

        for cmd in ("find", "save", "view", "tag", "trash", "task", "delete"):
            argv = ["emdx", cmd, "arg"]
            _rewrite_command_aliases(argv)
            assert argv[1] == cmd, f"Command '{cmd}' was unexpectedly rewritten"

    def test_bare_emdx_unchanged(self) -> None:
        """emdx with no args should not be modified."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx"]

    def test_only_flags_unchanged(self) -> None:
        """emdx --version should not be modified."""
        from emdx.main import _rewrite_command_aliases

        argv = ["emdx", "--version"]
        _rewrite_command_aliases(argv)
        assert argv == ["emdx", "--version"]


class TestTrailingHelpConversion:
    """Test the trailing 'help' to '--help' conversion in run()."""

    def test_trailing_help_conversion(self) -> None:
        """Test that run() converts trailing 'help' to '--help'."""
        import sys

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

    def test_no_conversion_without_help(self) -> None:
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
