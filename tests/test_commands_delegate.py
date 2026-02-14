"""Tests for delegate command helper functions."""

import pytest
import typer
from unittest.mock import patch

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _validate_discovery_command,
    PR_INSTRUCTION,
    SAFE_DISCOVERY_COMMANDS,
    SHELL_METACHARACTERS,
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

    # === Safe commands that should be allowed ===

    def test_allows_fd_command(self):
        args = _validate_discovery_command("fd -e py src/")
        assert args == ["fd", "-e", "py", "src/"]

    def test_allows_find_command(self):
        args = _validate_discovery_command("find . -type f")
        assert args[0] == "find"

    def test_allows_git_ls_files(self):
        args = _validate_discovery_command("git ls-files")
        assert args == ["git", "ls-files"]

    def test_allows_git_diff_name_only(self):
        args = _validate_discovery_command("git diff --name-only HEAD~5")
        assert args[0] == "git"
        assert "--name-only" in args

    def test_allows_ls_command(self):
        args = _validate_discovery_command("ls -la")
        assert args == ["ls", "-la"]

    def test_allows_rg_files(self):
        args = _validate_discovery_command("rg --files src/")
        assert args[0] == "rg"

    def test_allows_eza_command(self):
        args = _validate_discovery_command("eza -1")
        assert args == ["eza", "-1"]

    def test_allows_tree_command(self):
        args = _validate_discovery_command("tree -fi")
        assert args[0] == "tree"

    def test_allows_locate_command(self):
        args = _validate_discovery_command("locate myfile")
        assert args == ["locate", "myfile"]

    def test_allows_absolute_path_to_safe_command(self):
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert args == ["/usr/bin/fd", "-e", "py"]

    # === Dangerous commands that should be blocked ===

    def test_blocks_rm_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("rm -rf /")

    def test_blocks_curl_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("curl http://evil.com")

    def test_blocks_wget_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("wget http://evil.com")

    def test_blocks_python_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("python -c evil")

    def test_blocks_bash_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("bash -c evil")

    def test_blocks_sh_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("sh -c evil")

    # === Shell injection attempts that should be blocked ===

    def test_blocks_semicolon_injection(self):
        """The classic ; rm -rf ~ attack."""
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py; rm -rf ~")

    def test_blocks_pipe_injection(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_blocks_and_injection(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py && rm -rf /")

    def test_blocks_or_injection(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py || rm -rf /")

    def test_blocks_backtick_substitution(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd `rm -rf /`")

    def test_blocks_dollar_substitution(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd $(rm -rf /)")

    def test_blocks_redirect_output(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd > /etc/passwd")

    def test_blocks_redirect_input(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd < /etc/passwd")

    def test_blocks_append_redirect(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd >> /etc/passwd")

    def test_blocks_newline_injection(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd\nrm -rf /")

    def test_blocks_carriage_return_injection(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd\rrm -rf /")

    # === Edge cases ===

    def test_blocks_empty_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("")

    def test_blocks_whitespace_only_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("   ")

    def test_handles_quoted_arguments(self):
        """Quoted arguments should be parsed correctly."""
        args = _validate_discovery_command('fd -e "test file.py"')
        assert args == ["fd", "-e", "test file.py"]

    def test_handles_single_quoted_arguments(self):
        """Single-quoted arguments should work (note: * is now allowed)."""
        args = _validate_discovery_command("fd test.py")
        assert args == ["fd", "test.py"]

    def test_allows_glob_star(self):
        """Glob pattern with * should be allowed since shell=False."""
        args = _validate_discovery_command("fd *.py")
        assert args == ["fd", "*.py"]

    def test_allows_glob_question(self):
        """Glob pattern with ? should be allowed since shell=False."""
        args = _validate_discovery_command("fd test?.py")
        assert args == ["fd", "test?.py"]


class TestShellMetacharacters:
    """Verify the SHELL_METACHARACTERS regex catches injection attempts."""

    def test_catches_semicolon(self):
        assert SHELL_METACHARACTERS.search(";")

    def test_catches_pipe(self):
        assert SHELL_METACHARACTERS.search("|")

    def test_catches_ampersand(self):
        assert SHELL_METACHARACTERS.search("&")

    def test_catches_backtick(self):
        assert SHELL_METACHARACTERS.search("`")

    def test_catches_dollar(self):
        assert SHELL_METACHARACTERS.search("$")

    def test_catches_parentheses(self):
        assert SHELL_METACHARACTERS.search("(")
        assert SHELL_METACHARACTERS.search(")")

    def test_catches_braces(self):
        assert SHELL_METACHARACTERS.search("{")
        assert SHELL_METACHARACTERS.search("}")

    def test_catches_redirect(self):
        assert SHELL_METACHARACTERS.search("<")
        assert SHELL_METACHARACTERS.search(">")

    def test_catches_newlines(self):
        assert SHELL_METACHARACTERS.search("\n")
        assert SHELL_METACHARACTERS.search("\r")

    def test_allows_safe_characters(self):
        """Normal file paths and arguments should pass."""
        assert not SHELL_METACHARACTERS.search("fd -e py src/commands/")
        assert not SHELL_METACHARACTERS.search("git ls-files")
        assert not SHELL_METACHARACTERS.search("find . -name test.py")

    def test_allows_glob_star(self):
        """Glob * is allowed (safe with shell=False)."""
        assert not SHELL_METACHARACTERS.search("*.py")

    def test_allows_glob_question(self):
        """Glob ? is allowed (safe with shell=False)."""
        assert not SHELL_METACHARACTERS.search("test?.py")


class TestSafeDiscoveryCommands:
    """Verify the SAFE_DISCOVERY_COMMANDS allowlist."""

    def test_includes_fd(self):
        assert "fd" in SAFE_DISCOVERY_COMMANDS

    def test_includes_find(self):
        assert "find" in SAFE_DISCOVERY_COMMANDS

    def test_includes_git(self):
        assert "git" in SAFE_DISCOVERY_COMMANDS

    def test_includes_rg(self):
        assert "rg" in SAFE_DISCOVERY_COMMANDS

    def test_excludes_rm(self):
        assert "rm" not in SAFE_DISCOVERY_COMMANDS

    def test_excludes_curl(self):
        assert "curl" not in SAFE_DISCOVERY_COMMANDS

    def test_excludes_bash(self):
        assert "bash" not in SAFE_DISCOVERY_COMMANDS

    def test_excludes_python(self):
        assert "python" not in SAFE_DISCOVERY_COMMANDS
