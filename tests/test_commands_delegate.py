"""Tests for delegate command helper functions."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest
import typer

from emdx.commands.delegate import _slugify_title, _resolve_task, _run_discovery, PR_INSTRUCTION


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


class TestRunDiscovery:
    """Tests for _run_discovery — security hardened command execution."""

    @patch("subprocess.run")
    def test_simple_command_succeeds(self, mock_run):
        """Basic command execution works."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\nfile2.py\n",
            stderr="",
        )
        result = _run_discovery("echo test")
        assert result == ["file1.py", "file2.py"]
        # Verify shell=False is used (security fix)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is False

    @patch("subprocess.run")
    def test_uses_shlex_split(self, mock_run):
        """Command is parsed with shlex.split for security."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="result\n",
            stderr="",
        )
        _run_discovery('fd -e py "src dir"')
        # Should be split into ['fd', '-e', 'py', 'src dir']
        call_args = mock_run.call_args[0][0]
        assert call_args == ["fd", "-e", "py", "src dir"]

    def test_rejects_empty_command(self):
        """Empty command raises exit."""
        with pytest.raises(typer.Exit):
            _run_discovery("")

    def test_rejects_malformed_quotes(self):
        """Malformed quotes in command raise exit."""
        with pytest.raises(typer.Exit):
            _run_discovery('echo "unterminated')

    @patch("subprocess.run")
    def test_command_not_found_exits(self, mock_run):
        """Non-existent command raises exit."""
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(typer.Exit):
            _run_discovery("nonexistent_command")

    @patch("subprocess.run")
    def test_timeout_exits(self, mock_run):
        """Command timeout raises exit."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=30)
        with pytest.raises(typer.Exit):
            _run_discovery("slow_command")

    @patch("subprocess.run")
    def test_nonzero_exit_code_exits(self, mock_run):
        """Non-zero return code raises exit."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("failing_command")

    @patch("subprocess.run")
    def test_empty_output_exits(self, mock_run):
        """Empty output raises exit."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="\n\n",
            stderr="",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("empty_command")
