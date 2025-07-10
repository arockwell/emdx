"""Tests for emdx config module."""

from pathlib import Path
from unittest.mock import patch
import pytest

from emdx.config import get_db_path


def test_get_db_path_creates_directory(tmp_path):
    """Test that get_db_path creates the config directory if it doesn't exist."""
    # Use tmp_path fixture to avoid touching real filesystem
    with patch('pathlib.Path.home', return_value=tmp_path):
        db_path = get_db_path()
        
        # Check that the path is correct
        expected_path = tmp_path / '.config' / 'emdx' / 'knowledge.db'
        assert db_path == expected_path
        
        # Check that the directory was created
        assert db_path.parent.exists()
        assert db_path.parent.is_dir()


def test_get_db_path_returns_consistent_path(tmp_path):
    """Test that get_db_path returns the same path on multiple calls."""
    with patch('pathlib.Path.home', return_value=tmp_path):
        path1 = get_db_path()
        path2 = get_db_path()
        assert path1 == path2