"""Tests for emdx config module."""

import os
from unittest.mock import patch

from emdx.config import get_db_path


def test_get_db_path_creates_directory(tmp_path):
    """Test that get_db_path creates the config directory if it doesn't exist."""
    # Clear EMDX_TEST_DB to test normal path resolution
    with patch.dict(os.environ, {}, clear=True):
        # Restore important env vars but not EMDX_TEST_DB
        env_copy = {k: v for k, v in os.environ.items() if k != "EMDX_TEST_DB"}
        with patch.dict(os.environ, env_copy, clear=True):
            with patch("emdx.database.path.Path.home", return_value=tmp_path):
                # Import fresh to pick up the patch
                from emdx.database.path import get_db_path as path_get_db_path
                db_path = path_get_db_path()

                expected_path = tmp_path / ".config" / "emdx" / "knowledge.db"
                assert db_path == expected_path

                assert db_path.parent.exists()
                assert db_path.parent.is_dir()


def test_get_db_path_returns_consistent_path(tmp_path):
    """Test that get_db_path returns the same path on multiple calls."""
    # Clear EMDX_TEST_DB to test normal path resolution
    with patch.dict(os.environ, {}, clear=True):
        env_copy = {k: v for k, v in os.environ.items() if k != "EMDX_TEST_DB"}
        with patch.dict(os.environ, env_copy, clear=True):
            with patch("emdx.database.path.Path.home", return_value=tmp_path):
                from emdx.database.path import get_db_path as path_get_db_path
                path1 = path_get_db_path()
                path2 = path_get_db_path()
                assert path1 == path2


def test_get_db_path_respects_emdx_test_db(tmp_path):
    """Test that get_db_path respects EMDX_TEST_DB environment variable."""
    test_db_path = tmp_path / "test.db"
    with patch.dict(os.environ, {"EMDX_TEST_DB": str(test_db_path)}):
        from emdx.database.path import get_db_path as path_get_db_path
        db_path = path_get_db_path()
        assert db_path == test_db_path
