"""Tests for emdx utils module."""

from unittest.mock import Mock, patch

import git

from emdx.utils.git import get_git_project


def test_get_git_project_with_origin_https():
    """Test getting project name from HTTPS git remote."""
    mock_remote = Mock()
    mock_remote.name = "origin"
    mock_remote.url = "https://github.com/arockwell/emdx.git"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_with_origin_ssh():
    """Test getting project name from SSH git remote."""
    mock_remote = Mock()
    mock_remote.name = "origin"
    mock_remote.url = "git@github.com:arockwell/emdx.git"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_no_git_extension():
    """Test getting project name from URL without .git extension."""
    mock_remote = Mock()
    mock_remote.name = "origin"
    mock_remote.url = "https://github.com/arockwell/emdx"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_no_remotes(tmp_path):
    """Test getting project name when repo has no remotes."""
    mock_repo = Mock()
    mock_repo.remotes = []
    mock_repo.working_dir = str(tmp_path / "my-project")

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        assert result == "my-project"


def test_get_git_project_not_in_repo():
    """Test behavior when not in a git repository."""
    with patch("git.Repo", side_effect=git.InvalidGitRepositoryError):
        result = get_git_project()
        assert result is None


def test_get_git_project_with_custom_path(tmp_path):
    """Test getting project name with a custom path."""
    mock_remote = Mock()
    mock_remote.name = "origin"
    mock_remote.url = "https://github.com/user/custom-repo.git"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project(tmp_path)
        assert result == "custom-repo"


def test_get_git_project_exception_handling():
    """Test that exceptions are handled gracefully."""
    with patch("git.Repo", side_effect=Exception("Unexpected error")):
        result = get_git_project()
        assert result is None


def test_get_git_project_no_origin_remote():
    """Test behavior when there's a remote but not named 'origin'."""
    mock_remote = Mock()
    mock_remote.name = "upstream"
    mock_remote.url = "https://github.com/user/upstream-repo.git"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]
    mock_repo.working_dir = "/path/to/local-repo"

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        # Should fall back to directory name
        assert result == "local-repo"


def test_get_git_project_bitbucket_url():
    """Test with Bitbucket URL format."""
    mock_remote = Mock()
    mock_remote.name = "origin"
    mock_remote.url = "git@bitbucket.org:user/myrepo.git"

    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]

    with patch("git.Repo", return_value=mock_repo):
        result = get_git_project()
        assert result == "myrepo"


def test_get_git_project_no_such_path():
    """Test handling of NoSuchPathError."""
    with patch("git.Repo", side_effect=git.NoSuchPathError):
        result = get_git_project()
        assert result is None
