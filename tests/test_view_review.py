"""Tests for the emdx view --review flag."""

from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.core import app

runner = CliRunner()


def _out(result) -> str:  # type: ignore[no-untyped-def]
    """Strip ANSI escape sequences from CliRunner output."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


_DOC = {
    "id": 42,
    "title": "Architecture Plan",
    "content": "We currently use REST. Today the API handles 1000 rps.",
    "project": "acme",
    "created_at": datetime(2024, 6, 1),
    "access_count": 3,
}


class TestViewReviewFlag:
    """Tests for emdx view <id> --review."""

    @patch("emdx.commands.core._view_review")
    @patch("emdx.commands.core.get_document")
    def test_review_flag_calls_helper(
        self, mock_get_doc: MagicMock, mock_review: MagicMock
    ) -> None:
        """--review delegates to _view_review helper."""
        mock_get_doc.return_value = _DOC

        result = runner.invoke(app, ["view", "42", "--review"])
        assert result.exit_code == 0
        mock_review.assert_called_once_with(_DOC)

    def test_review_and_raw_mutually_exclusive(self) -> None:
        """--review and --raw together should error."""
        result = runner.invoke(app, ["view", "42", "--review", "--raw"])
        assert result.exit_code != 0
        assert "mutually exclusive" in _out(result)

    @patch("emdx.commands.core.get_document")
    def test_review_doc_not_found(self, mock_get_doc: MagicMock) -> None:
        """--review with nonexistent doc shows error."""
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["view", "999", "--review"])
        assert result.exit_code != 0
        assert "not found" in _out(result)


class TestViewReviewHelper:
    """Tests for the _view_review helper function."""

    @patch("emdx.services.ask_service._execute_claude_prompt")
    @patch("emdx.services.embedding_service.EmbeddingService")
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_review_with_similar_docs(
        self,
        _mock_which: MagicMock,
        mock_embed_cls: MagicMock,
        mock_execute: MagicMock,
    ) -> None:
        """Review with embeddings includes similar doc context."""
        from emdx.commands.core import _view_review

        mock_match = MagicMock()
        mock_match.doc_id = 10
        mock_match.title = "Related Doc"
        mock_match.similarity = 0.85
        mock_match.snippet = "Some related content..."

        mock_svc = MagicMock()
        mock_svc.find_similar.return_value = [mock_match]
        mock_embed_cls.return_value = mock_svc

        mock_execute.return_value = "Finding 1: contradiction found."

        _view_review(_DOC)

        mock_svc.find_similar.assert_called_once_with(42, limit=10)
        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args
        assert "contradictions" in call_kwargs[1]["system_prompt"]
        assert "#10" in call_kwargs[1]["user_message"]
        assert "Related Doc" in call_kwargs[1]["user_message"]

    @patch("emdx.services.ask_service._execute_claude_prompt")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        side_effect=ImportError("no embeddings"),
    )
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_review_without_embeddings_falls_back(
        self,
        _mock_which: MagicMock,
        _mock_embed_cls: MagicMock,
        mock_execute: MagicMock,
    ) -> None:
        """Review without embeddings still works (isolated review)."""
        from emdx.commands.core import _view_review

        mock_execute.return_value = "The document looks fine in isolation."

        _view_review(_DOC)

        mock_execute.assert_called_once()
        call_kwargs = mock_execute.call_args
        assert "in isolation" in call_kwargs[1]["user_message"]

    @patch("shutil.which", return_value=None)
    def test_review_no_claude_cli(self, _mock_which: MagicMock) -> None:
        """Review without Claude CLI prints installation hint."""
        import typer

        from emdx.commands.core import _view_review

        try:
            _view_review(_DOC)
            assert False, "Expected typer.Exit"  # noqa: B011
        except (SystemExit, typer.Exit):
            pass  # Either exit type is acceptable

    @patch("emdx.services.ask_service._execute_claude_prompt")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        side_effect=ImportError("no embeddings"),
    )
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_review_uses_sonnet_model(
        self,
        _mock_which: MagicMock,
        _mock_embed_cls: MagicMock,
        mock_execute: MagicMock,
    ) -> None:
        """Review uses claude-sonnet model."""
        from emdx.commands.core import _view_review

        mock_execute.return_value = "Review text."

        _view_review(_DOC)

        call_kwargs = mock_execute.call_args
        assert call_kwargs[1]["model"] == "claude-sonnet-4-5-20250929"

    @patch(
        "emdx.services.ask_service._execute_claude_prompt",
        side_effect=RuntimeError("fail"),
    )
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        side_effect=ImportError("no embeddings"),
    )
    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_review_runtime_error_exits(
        self,
        _mock_which: MagicMock,
        _mock_embed_cls: MagicMock,
        _mock_execute: MagicMock,
    ) -> None:
        """RuntimeError from LLM execution results in exit code 1."""
        import typer

        from emdx.commands.core import _view_review

        try:
            _view_review(_DOC)
            assert False, "Expected typer.Exit"  # noqa: B011
        except (SystemExit, typer.Exit):
            pass  # Either exit type is acceptable
