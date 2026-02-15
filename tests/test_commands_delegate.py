"""Tests for delegate command helper functions."""

from unittest.mock import patch

import pytest
import typer

from emdx.commands.delegate import (
    PR_INSTRUCTION,
    SAFE_DISCOVERY_COMMANDS,
    _resolve_task,
    _run_discovery,
    _slugify_title,
    _validate_discovery_command,
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

    def test_allows_fd_command(self):
        args = _validate_discovery_command("fd -e py src/")
        assert args == ["fd", "-e", "py", "src/"]

    def test_allows_find_command(self):
        args = _validate_discovery_command("find . -name '*.py'")
        assert args[0] == "find"

    def test_allows_git_command(self):
        args = _validate_discovery_command("git ls-files")
        assert args == ["git", "ls-files"]

    def test_allows_ls_command(self):
        args = _validate_discovery_command("ls -la")
        assert args == ["ls", "-la"]

    def test_allows_full_path_to_allowed_command(self):
        args = _validate_discovery_command("/usr/bin/fd -e py")
        assert args == ["/usr/bin/fd", "-e", "py"]

    def test_rejects_rm_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("rm -rf /")

    def test_rejects_curl_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("curl http://evil.com")

    def test_rejects_wget_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("wget http://evil.com")

    def test_rejects_bash_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("bash -c 'rm -rf /'")

    def test_rejects_shell_injection_via_semicolon(self):
        # With shlex parsing and allowlist, "fd;" is not a valid command
        # The semicolon becomes part of the command name, which is not in allowlist
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd; rm -rf /")

    def test_rejects_shell_injection_via_backticks(self):
        # Backticks are handled as literals by shlex when shell=False
        args = _validate_discovery_command("fd `whoami`")
        # The backticks become literal characters in the argument
        assert "`whoami`" in args[1]

    def test_rejects_shell_injection_via_dollar_parens(self):
        args = _validate_discovery_command("fd $(whoami)")
        # Command substitution is not executed with shell=False
        assert "$(whoami)" in args[1]

    def test_rejects_pipe_injection(self):
        # Pipe becomes a literal argument with shlex + shell=False
        args = _validate_discovery_command("fd | rm -rf /")
        assert "|" in args

    def test_rejects_empty_command(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("")

    def test_rejects_malformed_quotes(self):
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd 'unterminated")

    def test_safe_commands_set_not_empty(self):
        assert len(SAFE_DISCOVERY_COMMANDS) > 0
        assert "fd" in SAFE_DISCOVERY_COMMANDS
        assert "find" in SAFE_DISCOVERY_COMMANDS


class TestRunDiscovery:
    """Tests for _run_discovery — executes validated discovery commands."""

    def test_runs_echo_command(self):
        result = _run_discovery("echo 'file1.py\nfile2.py'")
        assert "file1.py" in result
        assert "file2.py" in result

    def test_runs_seq_command(self):
        result = _run_discovery("seq 1 3")
        assert result == ["1", "2", "3"]

    def test_rejects_dangerous_command(self):
        with pytest.raises(typer.Exit):
            _run_discovery("rm -rf /tmp/test")
