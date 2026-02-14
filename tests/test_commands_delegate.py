"""Tests for delegate command helper functions."""

from unittest.mock import patch

import pytest
import typer

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _run_discovery,
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


class TestSafeDiscoveryCommands:
    """Tests for command injection protection in _run_discovery."""

    def test_safe_commands_allowlist_exists(self):
        """Verify expected safe commands are in the allowlist."""
        assert "fd" in SAFE_DISCOVERY_COMMANDS
        assert "find" in SAFE_DISCOVERY_COMMANDS
        assert "git" in SAFE_DISCOVERY_COMMANDS
        assert "ls" in SAFE_DISCOVERY_COMMANDS
        assert "rg" in SAFE_DISCOVERY_COMMANDS

    def test_validate_rejects_unsafe_commands(self):
        """Commands not in allowlist should be rejected."""
        with pytest.raises(typer.Exit):
            _validate_discovery_command(["bash", "-c", "echo pwned"])

    def test_validate_rejects_shell_operators(self):
        """Semicolon injection attempts should fail parsing or validation."""
        # shlex.split handles this, but if someone passes a list directly
        with pytest.raises(typer.Exit):
            _validate_discovery_command(["rm", "-rf", "/"])

    def test_validate_accepts_safe_command(self):
        """Safe commands should pass validation."""
        # Should not raise
        _validate_discovery_command(["fd", "-e", "py", "src/"])

    def test_validate_accepts_absolute_paths_to_safe_commands(self):
        """Absolute paths to safe commands should pass."""
        # Should not raise
        _validate_discovery_command(["/usr/bin/fd", "-e", "py"])
        _validate_discovery_command(["/usr/bin/find", ".", "-name", "*.py"])

    def test_validate_rejects_empty_command(self):
        """Empty commands should be rejected."""
        with pytest.raises(typer.Exit):
            _validate_discovery_command([])

    @patch("subprocess.run")
    def test_run_discovery_uses_safe_parsing(self, mock_run):
        """_run_discovery should use shlex.split and shell=False by default."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "file1.py\nfile2.py"
        mock_run.return_value.stderr = ""

        result = _run_discovery("fd -e py src/")

        # Verify shell=False was used (secure mode)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is False

        # Verify command was parsed as list
        call_args = mock_run.call_args[0][0]
        assert isinstance(call_args, list)
        assert call_args == ["fd", "-e", "py", "src/"]

        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_run_discovery_allow_shell_uses_shell_true(self, mock_run):
        """With allow_shell=True, should use shell=True."""
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "result"
        mock_run.return_value.stderr = ""

        _run_discovery("some | piped | command", allow_shell=True)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is True

    def test_run_discovery_rejects_command_injection(self):
        """Attempted command injection should be blocked."""
        # These patterns would be dangerous with shell=True
        dangerous_commands = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "&& echo pwned",
            "$(evil_command)",
        ]
        for cmd in dangerous_commands:
            with pytest.raises(typer.Exit):
                _run_discovery(cmd)
