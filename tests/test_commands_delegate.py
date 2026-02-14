"""Tests for delegate command helper functions."""

from unittest.mock import patch, MagicMock
import subprocess

import click
import pytest
import typer

from emdx.commands.delegate import _slugify_title, _resolve_task, _run_discovery, PR_INSTRUCTION


class TestSlugifyTitle:
    """Tests for _slugify_title — converts document titles to git branch slugs."""

    def test_simple_title(self):
        assert _slugify_title("Fix auth bug") == "fix-auth-bug"

    def test_strips_gameplan_prefix(self):
        assert _slugify_title("Gameplan #1: Contextual Save") == "contextual-save"

    def test_strips_feature_prefix(self):
        assert _slugify_title("Feature: Dark Mode Toggle") == "dark-mode-toggle"

    def test_strips_plan_prefix(self):
        assert _slugify_title("Plan #42: Refactor Database") == "refactor-database"

    def test_strips_doc_prefix(self):
        assert _slugify_title("Document: API Design") == "api-design"

    def test_removes_special_characters(self):
        assert _slugify_title("Smart Priming (context-aware)") == "smart-priming-context-aware"

    def test_collapses_whitespace(self):
        assert _slugify_title("fix   the   thing") == "fix-the-thing"

    def test_truncates_long_slugs(self):
        result = _slugify_title("A" * 100)
        assert len(result) <= 50

    def test_empty_after_strip_returns_feature(self):
        assert _slugify_title("Gameplan #1:") == "feature"

    def test_only_special_chars_returns_feature(self):
        assert _slugify_title("!!!???") == "feature"

    def test_no_trailing_hyphens(self):
        result = _slugify_title("test - ")
        assert not result.endswith("-")


class TestResolveTask:
    """Tests for _resolve_task — resolves doc IDs to content."""

    @patch("emdx.commands.delegate.get_document")
    def test_numeric_id_loads_doc(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Hello world",
        }
        result = _resolve_task("42")
        assert "Hello world" in result
        assert "Test Doc" in result
        mock_get.assert_called_once_with(42)

    @patch("emdx.commands.delegate.get_document")
    def test_numeric_id_with_pr_adds_instructions(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Fix Auth",
            "content": "Fix the authentication bug",
        }
        result = _resolve_task("42", pr=True)
        assert "Fix the authentication bug" in result
        assert "pull request" in result.lower() or "PR" in result

    def test_text_task_returned_as_is(self):
        result = _resolve_task("analyze the auth module")
        assert result == "analyze the auth module"

    @patch("emdx.commands.delegate.get_document")
    def test_missing_doc_falls_back(self, mock_get):
        mock_get.return_value = None
        result = _resolve_task("99999")
        # Should return the string as-is when doc not found
        assert "99999" in result


class TestPRInstruction:
    """Tests for PR instruction constant."""

    def test_pr_instruction_mentions_branch(self):
        assert "branch" in PR_INSTRUCTION.lower()

    def test_pr_instruction_mentions_pr_create(self):
        assert "gh pr create" in PR_INSTRUCTION


class TestRunDiscovery:
    """Tests for _run_discovery — runs shell commands safely."""

    @patch("emdx.commands.delegate.subprocess.run")
    def test_basic_discovery(self, mock_run):
        """Test that a simple command returns output lines."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\nfile2.py\nfile3.py\n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py", "file3.py"]
        # Verify shell=False is used (security fix)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["shell"] is False

    @patch("emdx.commands.delegate.subprocess.run")
    def test_uses_shlex_split(self, mock_run):
        """Test that command is parsed with shlex.split (not shell=True)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="result\n",
            stderr="",
        )
        _run_discovery('echo "hello world"')
        # Should be called with a list of args
        call_args = mock_run.call_args.args[0]
        assert isinstance(call_args, list)
        assert call_args == ["echo", "hello world"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_handles_quoted_strings(self, mock_run):
        """Test that quoted strings in command are handled correctly."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test.py\n",
            stderr="",
        )
        _run_discovery('fd -e py "src dir"')
        call_args = mock_run.call_args.args[0]
        assert call_args == ["fd", "-e", "py", "src dir"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Test that empty lines are filtered from output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\n\nfile2.py\n   \nfile3.py\n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py", "file3.py"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_command_failure_exits(self, mock_run):
        """Test that a failing command raises click.exceptions.Exit."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: command failed",
        )
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("bad-command")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_empty_output_exits(self, mock_run):
        """Test that empty output raises click.exceptions.Exit."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\n\n",
            stderr="",
        )
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd --no-results")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_timeout_exits(self, mock_run):
        """Test that timeout raises click.exceptions.Exit."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow-cmd", timeout=30)
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("slow-cmd")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_command_not_found_exits(self, mock_run):
        """Test that missing command raises click.exceptions.Exit."""
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("nonexistent-cmd")

    def test_invalid_syntax_exits(self):
        """Test that invalid command syntax raises click.exceptions.Exit."""
        # Unclosed quote is invalid shlex syntax
        with pytest.raises(click.exceptions.Exit):
            _run_discovery('fd "unclosed')

    def test_empty_command_exits(self):
        """Test that empty command raises click.exceptions.Exit."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_security_no_shell_metacharacters(self, mock_run):
        """Security: shell metacharacters should NOT be interpreted.

        With shell=False and shlex.split(), shell metacharacters like ;, &&, ||,
        $(), backticks etc. are treated as literal strings, not shell operators.
        """
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file.py\n",
            stderr="",
        )
        # This would be dangerous with shell=True
        # With shell=False, the semicolon is just a literal argument
        _run_discovery("echo foo; rm -rf /")
        call_args = mock_run.call_args.args[0]
        # With shlex.split and shell=False, these are just literal args
        assert call_args == ["echo", "foo;", "rm", "-rf", "/"]
        # The key security property: shell=False
        assert mock_run.call_args.kwargs["shell"] is False

    @patch("emdx.commands.delegate.subprocess.run")
    def test_security_no_command_substitution(self, mock_run):
        """Security: command substitution should NOT be executed."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file.py\n",
            stderr="",
        )
        # This would execute 'whoami' with shell=True
        _run_discovery("echo $(whoami)")
        call_args = mock_run.call_args.args[0]
        # With shlex.split, this is a literal string argument
        assert call_args == ["echo", "$(whoami)"]
        assert mock_run.call_args.kwargs["shell"] is False
