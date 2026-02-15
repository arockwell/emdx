"""Tests for get_input_content function bug fix."""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from emdx.commands.core import get_input_content


class TestGetInputContent:
    """Test the get_input_content function, especially the stdin/file path bug fix."""

    def test_file_path_with_empty_stdin_in_subprocess_context(self):
        """Test that file paths work when stdin appears available but is empty (like in poetry run)."""  # noqa: E501
        # Create a temporary file with content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write("# Test Content\n\nThis should be read from file, not from empty stdin.")  # noqa: E501
            temp_file_path = temp_file.name

        try:
            # Mock subprocess context where stdin.isatty() returns False but stdin is empty
            empty_stdin = io.StringIO("")

            with patch('sys.stdin', empty_stdin):
                with patch('sys.stdin.isatty', return_value=False):
                    result = get_input_content(temp_file_path)

            # Should read from file, not empty stdin
            assert result.source_type == "file"
            assert "This should be read from file" in result.content
            assert result.source_path == Path(temp_file_path)

        finally:
            # Clean up
            Path(temp_file_path).unlink()

    def test_stdin_with_actual_content_takes_priority(self):
        """Test that stdin content is used when it actually contains data."""
        stdin_content = "# Stdin Content\n\nThis comes from stdin and should take priority."
        mock_stdin = io.StringIO(stdin_content)

        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content("some_file.md")

        # Should use stdin content, not file
        assert result.source_type == "stdin"
        assert "This comes from stdin" in result.content
        assert result.source_path is None

    def test_stdin_with_only_whitespace_falls_through_to_file(self):
        """Test that stdin with only whitespace falls through to file processing."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write("# File Content\n\nThis should be used when stdin has only whitespace.")
            temp_file_path = temp_file.name

        try:
            # Mock stdin with only whitespace
            whitespace_stdin = io.StringIO("   \n\t  \n  ")

            with patch('sys.stdin', whitespace_stdin):
                with patch('sys.stdin.isatty', return_value=False):
                    result = get_input_content(temp_file_path)

            # Should read from file since stdin only has whitespace
            assert result.source_type == "file"
            assert "This should be used when stdin" in result.content
            assert result.source_path == Path(temp_file_path)

        finally:
            Path(temp_file_path).unlink()

    def test_interactive_terminal_prioritizes_file_over_stdin(self):
        """Test that in interactive terminal (tty), file arguments take precedence."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write("# File Content\n\nThis should be used in interactive mode.")
            temp_file_path = temp_file.name

        try:
            # Mock interactive terminal (stdin.isatty() returns True)
            with patch('sys.stdin.isatty', return_value=True):
                result = get_input_content(temp_file_path)

            # Should read from file in interactive mode
            assert result.source_type == "file"
            assert "This should be used in interactive mode" in result.content
            assert result.source_path == Path(temp_file_path)

        finally:
            Path(temp_file_path).unlink()

    def test_nonexistent_file_returns_direct_input(self):
        """Test that nonexistent file path is treated as direct text input."""
        with patch('sys.stdin.isatty', return_value=True):
            result = get_input_content("This is direct text input")

        assert result.source_type == "direct"
        assert result.content == "This is direct text input"
        assert result.source_path is None

    def test_no_input_raises_exit(self):
        """Test that no input raises typer.Exit."""
        import typer

        with patch('sys.stdin.isatty', return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None)

    def test_regression_poetry_run_context(self):
        """
        Regression test for the specific bug: poetry run context with empty stdin.

        This simulates the exact conditions that caused the bug:
        - sys.stdin.isatty() returns False (subprocess context)
        - sys.stdin.read() returns empty string
        - File path argument provided

        Before fix: would return empty content from stdin
        After fix: should fall through to file reading
        """
        # Create test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as temp_file:
            temp_file.write("# Regression Test\n\nThis content should be saved, not empty string.")
            temp_file_path = temp_file.name

        try:
            # Exact conditions from poetry run that caused the bug
            empty_stdin = io.StringIO("")

            with patch('sys.stdin', empty_stdin):
                with patch('sys.stdin.isatty', return_value=False):  # subprocess context
                    result = get_input_content(temp_file_path)

            # After fix: should read file content, not empty stdin
            assert result.source_type == "file"
            assert len(result.content.strip()) > 0  # Not empty!
            assert "This content should be saved" in result.content
            assert result.source_path == Path(temp_file_path)

        finally:
            Path(temp_file_path).unlink()
