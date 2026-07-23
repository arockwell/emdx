"""Tests for get_input_content — stdin, --file, and positional content."""

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from emdx.commands.core import get_input_content


class TestStdinInput:
    """Stdin is the fallback source when no explicit content is given."""

    def test_positional_arg_wins_over_stdin(self):
        """Explicit positional content skips stdin entirely (#1034).

        Probing an open non-TTY stdin with no data blocks forever under
        backgrounded/tool-invoked callers, so a positional arg must never
        touch stdin.
        """
        mock_stdin = io.StringIO("# From stdin\n\nMust be ignored.")

        with patch("sys.stdin", mock_stdin):
            with patch("sys.stdin.isatty", return_value=False):
                result = get_input_content("positional text")

        assert result.source_type == "direct"
        assert result.content == "positional text"

    def test_stdin_used_when_no_other_source(self):
        stdin_content = "# From stdin\n\nOnly source available."
        mock_stdin = io.StringIO(stdin_content)

        with patch("sys.stdin", mock_stdin):
            with patch("sys.stdin.isatty", return_value=False):
                result = get_input_content(None)

        assert result.source_type == "stdin"
        assert "From stdin" in result.content

    def test_file_flag_wins_over_stdin(self):
        """--file takes priority over stdin (#732: explicit intent beats implicit pipe)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("file content")
            fpath = f.name

        try:
            mock_stdin = io.StringIO("stdin content")
            with patch("sys.stdin", mock_stdin):
                with patch("sys.stdin.isatty", return_value=False):
                    result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file content"
        finally:
            Path(fpath).unlink()

    def test_whitespace_only_stdin_errors_when_sole_source(self):
        import typer

        with patch("sys.stdin", io.StringIO("   \n\t  \n  ")):
            with patch("sys.stdin.isatty", return_value=False):
                with pytest.raises(typer.Exit):
                    get_input_content(None)


class TestFileInput:
    """--file flag reads from an explicit file path."""

    def test_file_flag_skips_stdin_entirely(self):
        """Regression test for #732: --file must not attempt stdin.read().

        When stdin is non-TTY but has no data (e.g., running from a script or
        IDE), sys.stdin.read() blocks forever. --file must bypass stdin entirely.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("file content")
            fpath = f.name

        try:
            # Simulate non-TTY stdin that would block on read()
            blocking_stdin = io.StringIO()  # empty — read() returns "" immediately
            # but in real bug, read() would block forever on a real fd
            with patch("sys.stdin", blocking_stdin):
                with patch("sys.stdin.isatty", return_value=False):
                    # If stdin were checked first, this could hang
                    result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file content"
        finally:
            Path(fpath).unlink()

    def test_file_flag_reads_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Hello\n\nWorld")
            fpath = f.name

        try:
            with patch("sys.stdin.isatty", return_value=True):
                result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "# Hello\n\nWorld"
            assert result.source_path == Path(fpath)
        finally:
            Path(fpath).unlink()

    def test_file_flag_missing_file_exits(self):
        import typer

        with patch("sys.stdin.isatty", return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None, file_path="/nonexistent/path.md")

    def test_file_flag_takes_priority_over_positional_arg(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("file wins")
            fpath = f.name

        try:
            with patch("sys.stdin.isatty", return_value=True):
                result = get_input_content("positional text", file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "file wins"
        finally:
            Path(fpath).unlink()


class TestDirectContentInput:
    """Positional argument is always treated as content, never as a file path."""

    def test_positional_arg_is_direct_content(self):
        with patch("sys.stdin.isatty", return_value=True):
            result = get_input_content("just some text")

        assert result.source_type == "direct"
        assert result.content == "just some text"
        assert result.source_path is None

    def test_string_that_looks_like_file_path_is_still_content(self):
        """Positional arg that looks like a path is NOT treated as a file."""
        with patch("sys.stdin.isatty", return_value=True):
            result = get_input_content("some_file.md")

        assert result.source_type == "direct"
        assert result.content == "some_file.md"

    def test_long_content_works(self):
        """Regression test for #714: any length content works as positional arg."""
        long_content = "A" * 300

        with patch("sys.stdin.isatty", return_value=True):
            result = get_input_content(long_content)

        assert result.source_type == "direct"
        assert result.content == long_content

    def test_multiline_content_works(self):
        content = "line 1\nline 2\nline 3"

        with patch("sys.stdin.isatty", return_value=True):
            result = get_input_content(content)

        assert result.source_type == "direct"
        assert result.content == content


class TestPathLikePositionalGuard:
    """Positional args that are existing file paths are refused (#1051).

    Passing a path positionally (instead of via -f/--file) used to silently
    save the literal path string as the document body — permanent content
    loss once the file at that path was cleaned up.
    """

    def test_existing_file_path_positionally_exits(self):
        import typer

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("real content that would be lost")
            fpath = f.name

        try:
            with patch("sys.stdin.isatty", return_value=True):
                with pytest.raises(typer.Exit):
                    get_input_content(fpath)
        finally:
            Path(fpath).unlink()

    def test_multiline_content_containing_existing_path_is_saved(self):
        """Only single-line args are path-checked — real content passes through."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("file content")
            fpath = f.name

        try:
            content = f"{fpath}\nplus a second line"
            with patch("sys.stdin.isatty", return_value=True):
                result = get_input_content(content)

            assert result.source_type == "direct"
            assert result.content == content
        finally:
            Path(fpath).unlink()

    def test_nonexistent_path_like_arg_warns_but_saves(self):
        """A path-looking string with no file behind it saves as literal content."""
        with patch("sys.stdin.isatty", return_value=True):
            result = get_input_content("/no/such/file/anywhere.md")

        assert result.source_type == "direct"
        assert result.content == "/no/such/file/anywhere.md"

    def test_directory_path_is_not_refused(self):
        """Directories aren't files — arg is kept as literal content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdin.isatty", return_value=True):
                result = get_input_content(tmpdir)

            assert result.source_type == "direct"
            assert result.content == tmpdir

    def test_file_flag_still_reads_the_same_path(self):
        """The refused path works fine when passed explicitly via --file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("real content")
            fpath = f.name

        try:
            with patch("sys.stdin.isatty", return_value=True):
                result = get_input_content(None, file_path=fpath)

            assert result.source_type == "file"
            assert result.content == "real content"
        finally:
            Path(fpath).unlink()


class TestNoInput:
    """No input at all raises an error."""

    def test_no_input_raises_exit(self):
        import typer

        with patch("sys.stdin.isatty", return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None)

    def test_no_input_no_file_raises_exit(self):
        import typer

        with patch("sys.stdin.isatty", return_value=True):
            with pytest.raises(typer.Exit):
                get_input_content(None, file_path=None)
