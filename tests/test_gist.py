"""Tests for gist module."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestGistAuth:
    """Test GitHub authentication methods."""

    @patch.dict(os.environ, {"GITHUB_TOKEN": "test_token"})
    def test_get_github_auth_from_env(self):
        """Test getting GitHub token from environment variable."""
        from emdx import gist
        token = gist.get_github_auth()
        assert token == "test_token"

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run")
    def test_get_github_auth_from_gh_cli(self, mock_run):
        """Test getting GitHub token from gh CLI."""
        from emdx import gist
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "gh_cli_token\n"
        
        token = gist.get_github_auth()
        assert token == "gh_cli_token"

    @patch.dict(os.environ, {}, clear=True)
    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh"))
    def test_get_github_auth_no_token(self, mock_run):
        """Test when no GitHub token is available."""
        from emdx import gist
        token = gist.get_github_auth()
        assert token is None


class TestGistUtilities:
    """Test gist utility functions."""

    @patch("subprocess.run")
    def test_copy_to_clipboard_success(self, mock_run):
        """Test successful clipboard copy."""
        from emdx import gist
        mock_run.return_value = MagicMock()
        
        result = gist.copy_to_clipboard("test text")
        assert result is True

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "pbcopy"))
    def test_copy_to_clipboard_failure(self, mock_run):
        """Test clipboard copy failure."""
        from emdx import gist
        result = gist.copy_to_clipboard("test text")
        assert result is False

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        from emdx import gist
        
        # Test normal title
        assert gist.sanitize_filename("My Document") == "My Document.md"
        
        # Test title with invalid characters
        assert gist.sanitize_filename("File<>:\"/\\|?*Name") == "File----------Name.md"
        
        # Test title already with .md extension
        assert gist.sanitize_filename("Document.md") == "Document.md"


class TestGistCreation:
    """Test gist creation methods."""

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("os.unlink")
    def test_create_gist_with_gh_success(self, mock_unlink, mock_run, mock_temp):
        """Test successful gist creation with gh CLI."""
        from emdx import gist
        
        # Setup temp file mock
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        
        # Setup subprocess mock
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "https://gist.github.com/user/abc123\n"
        
        result = gist.create_gist_with_gh("test content", "test.md", "test description")
        
        assert result == {"id": "abc123", "url": "https://gist.github.com/user/abc123"}

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh"))
    def test_create_gist_with_gh_failure(self, mock_run):
        """Test gist creation failure with gh CLI."""
        from emdx import gist
        result = gist.create_gist_with_gh("test content", "test.md", "test description")
        assert result is None


class TestGistAPI:
    """Test gist API methods."""

    @patch("github.Github")
    def test_create_gist_with_api_success(self, mock_github):
        """Test successful gist creation with GitHub API."""
        from emdx import gist
        
        # Setup GitHub API mock
        mock_gist = MagicMock()
        mock_gist.id = "abc123"
        mock_gist.html_url = "https://gist.github.com/user/abc123"
        
        mock_user = MagicMock()
        mock_user.create_gist.return_value = mock_gist
        mock_github.return_value.get_user.return_value = mock_user
        
        result = gist.create_gist_with_api("test content", "test.md", "test description", False, "token")
        
        assert result == {"id": "abc123", "url": "https://gist.github.com/user/abc123"}

    def test_create_gist_with_api_no_token(self):
        """Test gist creation with no token."""
        from emdx import gist
        result = gist.create_gist_with_api("test content", "test.md", "test description")
        assert result is None