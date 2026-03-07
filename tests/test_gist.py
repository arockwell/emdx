"""Tests for the gist command."""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.gist import sanitize_filename
from emdx.main import app as main_app
from emdx.models.document import Document

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# Unit tests for sanitize_filename
# ---------------------------------------------------------------------------
class TestSanitizeFilename:
    """Tests for the filename sanitizer."""

    def test_basic_title(self) -> None:
        assert sanitize_filename("My Document") == "My Document.md"

    def test_already_has_md_extension(self) -> None:
        assert sanitize_filename("readme.md") == "readme.md"

    def test_invalid_characters_replaced(self) -> None:
        result = sanitize_filename('My <doc>: "title"')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert result.endswith(".md")

    def test_pipe_character(self) -> None:
        result = sanitize_filename("A | B")
        assert "|" not in result

    def test_backslash(self) -> None:
        result = sanitize_filename("path\\to\\doc")
        assert "\\" not in result


# ---------------------------------------------------------------------------
# Unit tests for get_github_auth
# ---------------------------------------------------------------------------
class TestGetGithubAuth:
    """Tests for GitHub authentication detection."""

    @patch("subprocess.run")
    def test_auth_via_gh_cli(self, mock_run: Any) -> None:
        """Authentication via gh CLI returns token."""
        from emdx.commands.gist import get_github_auth

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="ghp_test_token_123\n",
        )

        token = get_github_auth()
        assert token == "ghp_test_token_123"

    @patch("subprocess.run", side_effect=FileNotFoundError("gh not found"))
    @patch.dict("os.environ", {"GITHUB_TOKEN": "env_token_456"})
    def test_auth_via_env_var(self, mock_run: Any) -> None:
        """Falls back to GITHUB_TOKEN env var when gh CLI unavailable."""
        from emdx.commands.gist import get_github_auth

        token = get_github_auth()
        assert token == "env_token_456"

    @patch("subprocess.run", side_effect=FileNotFoundError("gh not found"))
    @patch.dict("os.environ", {}, clear=True)
    def test_auth_none_when_unavailable(self, mock_run: Any) -> None:
        """Returns None when no authentication is available."""
        # Remove GITHUB_TOKEN if present
        import os

        from emdx.commands.gist import get_github_auth

        os.environ.pop("GITHUB_TOKEN", None)

        token = get_github_auth()
        assert token is None


# ---------------------------------------------------------------------------
# CLI integration tests for gist command
# ---------------------------------------------------------------------------
class TestGistCommand:
    """Tests for the gist CLI command."""

    @patch("emdx.commands.gist.get_document")
    def test_gist_document_not_found(self, mock_get_doc: Any) -> None:
        """Gist with nonexistent document shows error."""
        mock_get_doc.return_value = None

        result = runner.invoke(main_app, ["gist", "999"])
        assert result.exit_code != 0
        out = _out(result)
        assert "not found" in out.lower() or "Error" in out

    @patch("emdx.commands.gist.get_github_auth")
    @patch("emdx.commands.gist.get_document")
    def test_gist_no_auth(self, mock_get_doc: Any, mock_auth: Any) -> None:
        """Gist without GitHub auth shows authentication error."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Test Doc",
                "content": "Hello world",
                "project": "test",
            }
        )
        mock_auth.return_value = None

        result = runner.invoke(main_app, ["gist", "1"])
        assert result.exit_code != 0
        out = _out(result)
        assert "authentication" in out.lower() or "auth" in out.lower()

    @patch("emdx.commands.gist.db")
    @patch("emdx.commands.gist.create_gist_with_gh")
    @patch("emdx.commands.gist.get_github_auth")
    @patch("emdx.commands.gist.get_document")
    def test_gist_create_success(
        self, mock_get_doc: Any, mock_auth: Any, mock_create: Any, mock_db: Any
    ) -> None:
        """Successful gist creation shows URL."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Test Doc",
                "content": "Hello world",
                "project": "test",
            }
        )
        mock_auth.return_value = "ghp_test_token"
        mock_create.return_value = {
            "id": "abc123",
            "url": "https://gist.github.com/abc123",
        }
        # Mock the database connection so INSERT INTO gists doesn't fail
        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = lambda s: mock_conn
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(main_app, ["gist", "1"])
        assert result.exit_code == 0
        out = _out(result)
        assert "abc123" in out or "gist.github.com" in out

    @patch("emdx.commands.gist.create_gist_with_gh")
    @patch("emdx.commands.gist.get_github_auth")
    @patch("emdx.commands.gist.get_document")
    def test_gist_create_failure(self, mock_get_doc: Any, mock_auth: Any, mock_create: Any) -> None:
        """Failed gist creation shows error."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Test Doc",
                "content": "Hello world",
                "project": None,
            }
        )
        mock_auth.return_value = "ghp_test_token"
        mock_create.return_value = None

        result = runner.invoke(main_app, ["gist", "1"])
        assert result.exit_code != 0
        out = _out(result)
        assert "Failed" in out or "Error" in out

    def test_gist_public_and_secret_conflict(self) -> None:
        """Using both --public and --secret should error."""
        result = runner.invoke(main_app, ["gist", "1", "--public", "--secret"])
        assert result.exit_code != 0
        out = _out(result)
        assert "Cannot use both" in out or "Error" in out

    @patch("emdx.commands.gist.db")
    @patch("emdx.commands.gist.update_gist_with_gh")
    @patch("emdx.commands.gist.get_github_auth")
    @patch("emdx.commands.gist.get_document")
    def test_gist_update_success(
        self, mock_get_doc: Any, mock_auth: Any, mock_update: Any, mock_db: Any
    ) -> None:
        """Updating an existing gist succeeds."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Test Doc",
                "content": "Updated content",
                "project": None,
            }
        )
        mock_auth.return_value = "ghp_test_token"
        mock_update.return_value = True
        # Mock the database connection so UPDATE gists doesn't fail
        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = lambda s: mock_conn
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(main_app, ["gist", "1", "--update", "abc123"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Updated" in out or "abc123" in out

    @patch("emdx.commands.gist.update_gist_with_gh")
    @patch("emdx.commands.gist.get_github_auth")
    @patch("emdx.commands.gist.get_document")
    def test_gist_update_failure(self, mock_get_doc: Any, mock_auth: Any, mock_update: Any) -> None:
        """Failed gist update shows error."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Test Doc",
                "content": "Content",
                "project": None,
            }
        )
        mock_auth.return_value = "ghp_test_token"
        mock_update.return_value = False

        result = runner.invoke(main_app, ["gist", "1", "--update", "abc123"])
        assert result.exit_code != 0
        out = _out(result)
        assert "Failed" in out or "Error" in out


# ---------------------------------------------------------------------------
# Unit tests for copy_to_clipboard
# ---------------------------------------------------------------------------
class TestCopyToClipboard:
    """Tests for the clipboard helper."""

    @patch("subprocess.run")
    def test_copy_success_macos(self, mock_run: Any) -> None:
        """Clipboard copy succeeds on macOS (pbcopy)."""
        from emdx.commands.gist import copy_to_clipboard

        mock_run.return_value = MagicMock(returncode=0)

        result = copy_to_clipboard("test text")
        assert result is True

    @patch(
        "subprocess.run",
        side_effect=FileNotFoundError("pbcopy not found"),
    )
    def test_copy_failure_no_tools(self, mock_run: Any) -> None:
        """Clipboard copy fails gracefully when no tools available."""
        from emdx.commands.gist import copy_to_clipboard

        result = copy_to_clipboard("test text")
        assert result is False
