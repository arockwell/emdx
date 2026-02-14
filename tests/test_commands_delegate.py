"""Tests for delegate command helper functions."""

from unittest.mock import patch

import click.exceptions
import pytest

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
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


class TestValidateDiscoveryCommand:
    """Tests for _validate_discovery_command — security validation for --each."""

    def test_safe_fd_command(self):
        """fd is in the allowlist and should be accepted."""
        args = _validate_discovery_command("fd -e py src/")
        assert args[0] == "fd"
        assert "-e" in args
        assert "py" in args

    def test_safe_find_command(self):
        """find is in the allowlist and should be accepted."""
        args = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_safe_git_command(self):
        """git is in the allowlist and should be accepted."""
        args = _validate_discovery_command("git ls-files '*.py'")
        assert args[0] == "git"

    def test_safe_rg_command(self):
        """rg is in the allowlist and should be accepted."""
        args = _validate_discovery_command("rg -l 'TODO' src/")
        assert args[0] == "rg"

    def test_safe_command_with_path(self):
        """Commands specified with full path should work."""
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert args[0] == "/usr/bin/fd"

    def test_rejects_unlisted_command(self):
        """Commands not in allowlist should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("curl http://evil.com")

    def test_rejects_rm_command(self):
        """Dangerous commands like rm should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("rm -rf /")

    def test_rejects_command_with_semicolon(self):
        """Command chaining with semicolon should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py; rm -rf /")

    def test_rejects_command_with_pipe(self):
        """Command chaining with pipe should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_rejects_command_with_ampersand(self):
        """Command chaining with && should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("fd -e py && rm -rf /")

    def test_rejects_command_with_backticks(self):
        """Command substitution with backticks should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("echo `rm -rf /`")

    def test_rejects_command_with_dollar_paren(self):
        """Command substitution with $() should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("echo $(rm -rf /)")

    def test_rejects_command_with_variable_expansion(self):
        """Variable expansion should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("echo ${PATH}")

    def test_rejects_empty_command(self):
        """Empty commands should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("")

    def test_safe_commands_allowlist_populated(self):
        """The allowlist should contain expected safe commands."""
        assert "fd" in SAFE_DISCOVERY_COMMANDS
        assert "find" in SAFE_DISCOVERY_COMMANDS
        assert "git" in SAFE_DISCOVERY_COMMANDS
        assert "rg" in SAFE_DISCOVERY_COMMANDS
        assert "grep" in SAFE_DISCOVERY_COMMANDS
        # Dangerous commands should NOT be in allowlist
        assert "rm" not in SAFE_DISCOVERY_COMMANDS
        assert "curl" not in SAFE_DISCOVERY_COMMANDS
        assert "wget" not in SAFE_DISCOVERY_COMMANDS
        assert "bash" not in SAFE_DISCOVERY_COMMANDS
        assert "sh" not in SAFE_DISCOVERY_COMMANDS
