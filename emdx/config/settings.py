"""Configuration utilities for emdx."""

import os
from pathlib import Path

# Re-export constants for backward compatibility
from .constants import EMDX_CONFIG_DIR


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable.

    When running tests, set EMDX_TEST_DB to a temp file path to prevent
    tests from polluting the real database.
    """
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"
