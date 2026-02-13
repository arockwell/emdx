"""Tests for emdx utils module."""

from unittest.mock import patch

from emdx.utils.git import get_git_project


def _mock_subprocess_run(toplevel=None, origin_url=None):
    """
    Helper to create a mock for subprocess.run that simulates git commands.

    Args:
        toplevel: The git repo root path, or None to simulate not-in-repo.
        origin_url: The origin remote URL, or None to simulate no origin.
    """
    from unittest.mock import Mock

    def side_effect(cmd, **kwargs):
        result = Mock()
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            if toplevel is not None:
                result.returncode = 0
                result.stdout = toplevel + "\n"
            else:
                result.returncode = 128
                result.stdout = ""
                result.stderr = "fatal: not a git repository"
        elif cmd[:4] == ["git", "remote", "get-url", "origin"]:
            if origin_url is not None:
                result.returncode = 0
                result.stdout = origin_url + "\n"
            else:
                result.returncode = 2
                result.stdout = ""
                result.stderr = "error: No such remote 'origin'"
        else:
            result.returncode = 1
            result.stdout = ""
        return result

    return side_effect


def test_get_git_project_with_origin_https():
    """Test getting project name from HTTPS git remote."""
    mock = _mock_subprocess_run(
        toplevel="/path/to/emdx",
        origin_url="https://github.com/arockwell/emdx.git",
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_with_origin_ssh():
    """Test getting project name from SSH git remote."""
    mock = _mock_subprocess_run(
        toplevel="/path/to/emdx",
        origin_url="git@github.com:arockwell/emdx.git",
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_no_git_extension():
    """Test getting project name from URL without .git extension."""
    mock = _mock_subprocess_run(
        toplevel="/path/to/emdx",
        origin_url="https://github.com/arockwell/emdx",
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result == "emdx"


def test_get_git_project_no_remotes(tmp_path):
    """Test getting project name when repo has no remotes."""
    mock = _mock_subprocess_run(
        toplevel=str(tmp_path / "my-project"),
        origin_url=None,
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result == "my-project"


def test_get_git_project_not_in_repo():
    """Test behavior when not in a git repository."""
    mock = _mock_subprocess_run(toplevel=None)
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result is None


def test_get_git_project_with_custom_path(tmp_path):
    """Test getting project name with a custom path."""
    mock = _mock_subprocess_run(
        toplevel=str(tmp_path / "custom-repo"),
        origin_url="https://github.com/user/custom-repo.git",
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project(tmp_path)
        assert result == "custom-repo"


def test_get_git_project_exception_handling():
    """Test that exceptions are handled gracefully."""
    with patch("emdx.utils.git.subprocess.run", side_effect=Exception("Unexpected error")):
        result = get_git_project()
        assert result is None


def test_get_git_project_no_origin_remote():
    """Test behavior when there's a remote but not named 'origin'."""
    mock = _mock_subprocess_run(
        toplevel="/path/to/local-repo",
        origin_url=None,
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        # Should fall back to directory name
        assert result == "local-repo"


def test_get_git_project_bitbucket_url():
    """Test with Bitbucket URL format."""
    mock = _mock_subprocess_run(
        toplevel="/path/to/myrepo",
        origin_url="git@bitbucket.org:user/myrepo.git",
    )
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result == "myrepo"


def test_get_git_project_no_such_path():
    """Test handling when path doesn't exist (git fails)."""
    mock = _mock_subprocess_run(toplevel=None)
    with patch("emdx.utils.git.subprocess.run", side_effect=mock):
        result = get_git_project()
        assert result is None


def test_get_git_project_git_not_found():
    """Test handling when git binary is not found."""
    with patch("emdx.utils.git.subprocess.run", side_effect=FileNotFoundError("git not found")):
        result = get_git_project()
        assert result is None
