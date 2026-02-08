"""Tests for emdx config module."""

import os
from unittest.mock import patch

from emdx.config import get_db_path
from emdx.config.constants import EMDX_CONFIG_DIR


def test_get_db_path_creates_directory():
    """Test that get_db_path returns the correct default path."""
    # Temporarily clear EMDX_TEST_DB so we test the default path logic
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("EMDX_TEST_DB", None)
        db_path = get_db_path()
        expected_path = EMDX_CONFIG_DIR / "knowledge.db"
        assert db_path == expected_path
        assert db_path.parent.exists()
        assert db_path.parent.is_dir()


def test_get_db_path_respects_test_db_env(tmp_path):
    """Test that EMDX_TEST_DB env var overrides default path."""
    test_db = tmp_path / "test.db"
    with patch.dict(os.environ, {"EMDX_TEST_DB": str(test_db)}):
        db_path = get_db_path()
        assert db_path == test_db


def test_get_db_path_returns_consistent_path():
    """Test that get_db_path returns the same path on multiple calls."""
    path1 = get_db_path()
    path2 = get_db_path()
    assert path1 == path2
