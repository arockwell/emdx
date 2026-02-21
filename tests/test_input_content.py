"""Tests for get_input_content — stdin, --file, and positional content."""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from emdx.commands.core import get_input_content


class TestStdinInput:
    """Stdin takes highest priority when it has content."""

    def test_stdin_with_content_wins_over_positional_arg(self):
        stdin_content = "# From stdin\n\nShould take priority."
        mock_stdin = io.StringIO(stdin_content)

        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content("positional text")

        assert result.source_type == "stdin"
        assert "From stdin" in result.content

    def test_file_flag_wins_over_stdin(self):
        """--file takes priority over stdin (#732: explicit intent beats implicit pipe)."""
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

    def test_whitespace_only_stdin_falls_through(self):
        with patch('sys.stdin', io.StringIO("   \n\t  \n  ")):
            with patch('sys.stdin.isatty', return_value=False):
                result = get_input_content("direct text")

        assert result.source_type == "direct"
        assert result.content == "direct text"


class TestFileInput:
    """--file flag reads from an explicit file path."""

    def test_file_flag_skips_stdin_entirely(self):
        """Regression test for #732: --file must not attempt stdin.read().

        When stdin is non-TTY but has no data (e.g., running from a script or
        IDE), sys.stdin.read() blocks forever. --file must bypass stdin entirely.
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("file content")
            fpath = f.name

        try:
            # Simulate non-TTY stdin that would block on read()
            blocking_stdin = io.StringIO()  # empty — read() returns "" immediately
            # but in real bug, read() would block forever on a real fd
            with patch('sys.stdin', blocking_stdin):
                with patch('sys.stdin.isatty', return_value=False):
                    # If stdin were checked first, this could hang
                    result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file content"
        finally:
            Path(fpath).unlink()

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
