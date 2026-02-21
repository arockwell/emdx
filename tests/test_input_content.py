"""Tests for get_input_content — --file, positional content, and stdin."""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from emdx.commands.core import get_input_content


class TestStdinInput:
    """Stdin is used as fallback when no explicit input is provided."""

    def test_stdin_used_when_no_explicit_input(self):
        stdin_content = "# From stdin\n\nPiped content."
        mock_stdin = io.StringIO(stdin_content)

        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content(None)

        assert result.source_type == "stdin"
        assert "From stdin" in result.content

    def test_positional_arg_wins_over_stdin(self):
        """Fix for #715: positional arg takes priority over stdin to avoid
        blocking on stdin.read() in non-TTY contexts (e.g., heredoc subshell)."""
        mock_stdin = io.StringIO("stdin content")

        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content("positional text")

        assert result.source_type == "direct"
        assert result.content == "positional text"

    def test_file_flag_wins_over_stdin(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("file content")
            fpath = f.name

        try:
            mock_stdin = io.StringIO("stdin content")
            with patch('sys.stdin', mock_stdin):
                with patch('sys.stdin.isatty', return_value=False):
                    result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file content"
        finally:
            Path(fpath).unlink()

    def test_empty_stdin_falls_through_to_error(self):
        import typer

        empty_stdin = io.StringIO("")
        with patch('sys.stdin', empty_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                with pytest.raises(typer.Exit):
                    get_input_content(None)

    def test_whitespace_only_stdin_falls_through_to_error(self):
        import typer

        with patch('sys.stdin', io.StringIO("   \n\t  \n  ")):
            with patch('sys.stdin.isatty', return_value=False):
                with pytest.raises(typer.Exit):
                    get_input_content(None)


class TestHeredocSubshell:
    """Regression tests for #715: heredoc subshell expansion must not hang."""

    def test_heredoc_content_as_positional_arg_non_tty(self):
        """Simulates: emdx save "$(cat <<'HEREDOC' ... HEREDOC)" in non-TTY."""
        heredoc_content = "# Analysis\n\nMulti-line heredoc content."

        # stdin.isatty() returns False but stdin has no data (empty)
        with patch('sys.stdin', io.StringIO("")):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content(heredoc_content)

        assert result.source_type == "direct"
        assert result.content == heredoc_content

    def test_long_heredoc_content_as_positional_arg(self):
        """Long heredoc content that triggered #714 still works."""
        long_content = "A" * 1000

        with patch('sys.stdin', io.StringIO("")):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content(long_content)

        assert result.source_type == "direct"
        assert result.content == long_content


class TestFileInput:
    """--file flag reads from an explicit file path."""

    def test_file_flag_reads_content(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("# Hello\n\nWorld")
            fpath = f.name

        try:
            with patch('sys.stdin.isatty', return_value=True):
                result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "# Hello\n\nWorld"
            assert result.source_path == Path(fpath)
        finally:
            Path(fpath).unlink()

    def test_file_flag_missing_file_exits(self):
        import typer

        with patch('sys.stdin.isatty', return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None, file_path="/nonexistent/path.md")

    def test_file_flag_takes_priority_over_positional_arg(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("file wins")
            fpath = f.name

        try:
            with patch('sys.stdin.isatty', return_value=True):
                result = get_input_content("positional text", file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file wins"
        finally:
            Path(fpath).unlink()


class TestDirectContentInput:
    """Positional argument is always treated as content, never as a file path."""

    def test_positional_arg_is_direct_content(self):
        with patch('sys.stdin.isatty', return_value=True):
            result = get_input_content("just some text")

        assert result.source_type == "direct"
        assert result.content == "just some text"
        assert result.source_path is None

    def test_string_that_looks_like_file_path_is_still_content(self):
        """Positional arg that looks like a path is NOT treated as a file."""
        with patch('sys.stdin.isatty', return_value=True):
            result = get_input_content("some_file.md")

        assert result.source_type == "direct"
        assert result.content == "some_file.md"

    def test_long_content_works(self):
        """Regression test for #714: any length content works as positional arg."""
        long_content = "A" * 300

        with patch('sys.stdin.isatty', return_value=True):
            result = get_input_content(long_content)

        assert result.source_type == "direct"
        assert result.content == long_content

    def test_multiline_content_works(self):
        content = "line 1\nline 2\nline 3"

        with patch('sys.stdin.isatty', return_value=True):
            result = get_input_content(content)

        assert result.source_type == "direct"
        assert result.content == content


class TestNoInput:
    """No input at all raises an error."""

    def test_no_input_raises_exit(self):
        import typer

        with patch('sys.stdin.isatty', return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None)

    def test_no_input_no_file_raises_exit(self):
        import typer

        with patch('sys.stdin.isatty', return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None, file_path=None)
