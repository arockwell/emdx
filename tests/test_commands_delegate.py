"""Tests for delegate command helper functions."""

import pytest
from unittest.mock import patch

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
    _run_discovery,
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
    """Tests for _validate_discovery_command — prevents command injection."""

    def test_safe_fd_command_allowed(self):
        """fd is in the allowlist and should work."""
        args = _validate_discovery_command("fd -e py src/")
        assert args[0] == "fd"
        assert "-e" in args
        assert "py" in args

    def test_safe_find_command_allowed(self):
        """find is in the allowlist and should work."""
        args = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_safe_git_command_allowed(self):
        """git is in the allowlist and should work."""
        args = _validate_discovery_command("git ls-files '*.py'")
        assert args[0] == "git"

    def test_safe_ls_command_allowed(self):
        """ls is in the allowlist and should work."""
        args = _validate_discovery_command("ls -la src/")
        assert args[0] == "ls"

    def test_safe_rg_command_allowed(self):
        """rg is in the allowlist and should work."""
        args = _validate_discovery_command("rg -l pattern")
        assert args[0] == "rg"

    def test_unsafe_rm_command_blocked(self):
        """rm is NOT in the allowlist and should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("rm -rf /")

    def test_unsafe_curl_command_blocked(self):
        """curl is NOT in the allowlist and should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("curl http://evil.com")

    def test_unsafe_bash_command_blocked(self):
        """bash is NOT in the allowlist and should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("bash -c 'echo pwned'")

    def test_unsafe_sh_command_blocked(self):
        """sh is NOT in the allowlist and should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("sh -c 'rm -rf /'")

    def test_command_chaining_with_semicolon_blocked(self):
        """Command chaining with ; should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("fd -e py; rm -rf /")

    def test_command_chaining_with_ampersand_blocked(self):
        """Command chaining with & should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("fd -e py & rm -rf /")

    def test_command_chaining_with_pipe_blocked(self):
        """Command chaining with | should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_command_substitution_backticks_blocked(self):
        """Command substitution with backticks should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("fd `rm -rf /`")

    def test_command_substitution_dollar_parens_blocked(self):
        """Command substitution with $() should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("fd $(rm -rf /)")

    def test_empty_command_blocked(self):
        """Empty command should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("")

    def test_full_path_to_allowed_command_works(self):
        """Full paths to allowed commands should work."""
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert "fd" in args[0]  # Path basename is fd

    def test_full_path_to_disallowed_command_blocked(self):
        """Full paths to disallowed commands should be blocked."""
        from click.exceptions import Exit
        with pytest.raises(Exit):
            _validate_discovery_command("/usr/bin/rm -rf /")


class TestRunDiscovery:
    """Tests for _run_discovery — secure command execution."""

    def test_discovery_uses_shell_false(self):
        """Discovery should use shell=False to prevent injection."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "file1.py\nfile2.py"
            mock_run.return_value.stderr = ""

            _run_discovery("fd -e py")

            # Verify shell=False is used
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["shell"] is False

    def test_discovery_passes_args_as_list(self):
        """Discovery should pass parsed args as a list, not string."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "file1.py\nfile2.py"
            mock_run.return_value.stderr = ""

            _run_discovery("fd -e py src/")

            # First positional arg should be a list
            call_args = mock_run.call_args[0][0]
            assert isinstance(call_args, list)
            assert call_args[0] == "fd"

    def test_safe_discovery_commands_constant(self):
        """Verify the allowlist contains expected safe commands."""
        assert "fd" in SAFE_DISCOVERY_COMMANDS
        assert "find" in SAFE_DISCOVERY_COMMANDS
        assert "git" in SAFE_DISCOVERY_COMMANDS
        assert "ls" in SAFE_DISCOVERY_COMMANDS
        assert "rg" in SAFE_DISCOVERY_COMMANDS
        # These should NOT be in the allowlist
        assert "rm" not in SAFE_DISCOVERY_COMMANDS
        assert "curl" not in SAFE_DISCOVERY_COMMANDS
        assert "bash" not in SAFE_DISCOVERY_COMMANDS
        assert "sh" not in SAFE_DISCOVERY_COMMANDS
        assert "python" not in SAFE_DISCOVERY_COMMANDS
