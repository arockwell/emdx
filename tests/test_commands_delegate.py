"""Tests for delegate command helper functions."""

from unittest.mock import patch

import click.exceptions
import pytest

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
    """Tests for _run_discovery — security-critical command execution.

    The key security property is that shell=False + shlex.split() prevents
    command injection. Shell metacharacters like ; && || | > < ` $() are
    NOT interpreted by a shell - they're passed as literal arguments.
    """

    def test_simple_command_works(self):
        """Basic command execution should work."""
        result = _run_discovery("echo one two three")
        assert result == ["one two three"]

    def test_multiline_output(self):
        """Should split output into lines."""
        result = _run_discovery("printf 'a\\nb\\nc'")
        assert result == ["a", "b", "c"]

    def test_empty_lines_filtered(self):
        """Empty lines should be filtered out."""
        result = _run_discovery("printf 'a\\n\\nb\\n\\n'")
        assert result == ["a", "b"]

    def test_shell_injection_via_semicolon_prevented(self):
        """Shell injection via semicolon should fail safely.

        With shell=True this would execute 'touch /tmp/pwned'.
        With shell=False + shlex.split(), the semicolon and 'touch' become
        arguments to echo, so this outputs 'hello; touch /tmp/pwned'.
        """
        result = _run_discovery("echo hello; touch /tmp/pwned")
        # The semicolon is NOT interpreted as a command separator
        assert "hello" in result[0]
        assert "touch" in result[0]  # Literal 'touch' in the echo output

    def test_shell_injection_via_backticks_prevented(self):
        """Shell injection via backticks should be treated as literal."""
        # With shell=False, backticks are just literal characters
        result = _run_discovery("echo '`whoami`'")
        assert result == ["`whoami`"]

    def test_shell_injection_via_dollar_parens_prevented(self):
        """Shell injection via $() should be treated as literal."""
        result = _run_discovery("echo '$(whoami)'")
        assert result == ["$(whoami)"]

    def test_command_not_found_exits(self):
        """Non-existent command should exit cleanly."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("nonexistent_command_xyz123")

    def test_malformed_quotes_exits(self):
        """Malformed quotes should be caught by shlex."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("echo 'unclosed")

    def test_no_items_exits(self):
        """Empty output should exit."""
        with pytest.raises(click.exceptions.Exit):
            _run_discovery("echo ''")

    def test_fd_style_command(self):
        """Typical discovery commands like fd should work."""
        # Use a simple substitute since fd may not be installed
        result = _run_discovery("ls -1 /tmp")
        # Just verify it returns a list (contents vary)
        assert isinstance(result, list)

    def test_uses_shell_false(self):
        """Verify shell=False prevents pipe interpretation.

        With shell=True, 'echo hello | cat' would pipe through cat.
        With shell=False, it tries to echo the literal string '| cat'.
        """
        result = _run_discovery("echo hello | cat")
        # The pipe is NOT interpreted - it becomes part of echo's arguments
        assert "|" in result[0]
        assert "cat" in result[0]
