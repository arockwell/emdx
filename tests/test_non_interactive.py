"""Tests for non-interactive terminal detection and auto-confirmation behavior.

Verifies that commands with confirmation prompts automatically skip them
when stdin is not a TTY (e.g. running inside Claude Code or piped input).
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.utils.output import is_non_interactive

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# is_non_interactive() unit tests
# ---------------------------------------------------------------------------
class TestIsNonInteractive:
    """Unit tests for the is_non_interactive() utility function."""

    @patch("sys.stdin")
    def test_returns_true_when_not_tty(self, mock_stdin: Any) -> None:
        """Non-TTY stdin (piped, agent mode) returns True."""
        mock_stdin.isatty.return_value = False
        assert is_non_interactive() is True

    @patch("sys.stdin")
    def test_returns_false_when_tty(self, mock_stdin: Any) -> None:
        """Interactive TTY stdin returns False."""
        mock_stdin.isatty.return_value = True
        assert is_non_interactive() is False


# ---------------------------------------------------------------------------
# maintain index --clear non-interactive test
# ---------------------------------------------------------------------------
class TestMaintainIndexClearNonInteractive:
    """Tests for non-interactive auto-confirmation in maintain index --clear."""

    @patch("emdx.commands.maintain_index.is_non_interactive", return_value=True)
    def test_index_clear_auto_confirms_non_interactive(self, mock_ni: Any) -> None:
        """--clear skips confirmation when stdin is not a TTY."""
        mock_service = MagicMock()
        mock_service.clear_index.return_value = 42

        with patch(
            "emdx.services.embedding_service.EmbeddingService",
            return_value=mock_service,
        ):
            import typer

            from emdx.commands.maintain_index import index_embeddings

            test_app = typer.Typer()
            test_app.command()(index_embeddings)

            result = runner.invoke(test_app, ["--clear"])
            assert result.exit_code == 0
            out = _out(result)
            assert "Cleared 42 embeddings" in out
            mock_service.clear_index.assert_called_once()
