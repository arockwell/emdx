"""Tests for emdx utils module."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
import git

from emdx.utils import get_git_project


def test_get_git_project_with_origin_https():
    """Test getting project name from HTTPS git remote."""
    mock_remote = Mock()
    mock_remote.name = 'origin'
    mock_remote.url = 'https://github.com/arockwell/emdx.git'
    
    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]
    
    with patch('git.Repo', return_value=mock_repo):
        result = get_git_project()
        assert result == 'emdx'


def test_get_git_project_with_origin_ssh():
    """Test getting project name from SSH git remote."""
    mock_remote = Mock()
    mock_remote.name = 'origin'
    mock_remote.url = 'git@github.com:arockwell/emdx.git'
    
    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]
    
    with patch('git.Repo', return_value=mock_repo):
        result = get_git_project()
        assert result == 'emdx'


def test_get_git_project_no_git_extension():
    """Test getting project name from URL without .git extension."""
    mock_remote = Mock()
    mock_remote.name = 'origin'
    mock_remote.url = 'https://github.com/arockwell/emdx'
    
    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]
    
    with patch('git.Repo', return_value=mock_repo):
        result = get_git_project()
        assert result == 'emdx'


def test_get_git_project_no_remotes(tmp_path):
    """Test getting project name when repo has no remotes."""
    mock_repo = Mock()
    mock_repo.remotes = []
    mock_repo.working_dir = str(tmp_path / 'my-project')
    
    with patch('git.Repo', return_value=mock_repo):
        result = get_git_project()
        assert result == 'my-project'


def test_get_git_project_not_in_repo():
    """Test behavior when not in a git repository."""
    with patch('git.Repo', side_effect=git.InvalidGitRepositoryError):
        result = get_git_project()
        assert result is None


def test_get_git_project_with_custom_path(tmp_path):
    """Test getting project name with a custom path."""
    mock_remote = Mock()
    mock_remote.name = 'origin'
    mock_remote.url = 'https://github.com/user/custom-repo.git'
    
    mock_repo = Mock()
    mock_repo.remotes = [mock_remote]
    
    with patch('git.Repo', return_value=mock_repo):
        result = get_git_project(tmp_path)
        assert result == 'custom-repo'
        
        assert result == 'custom-repo'