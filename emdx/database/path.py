"""Database path resolution for emdx.

This module is intentionally minimal with no internal imports to avoid
circular dependencies. It's the canonical source for get_db_path().
"""

import os
from pathlib import Path


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable.

    When running tests, set EMDX_TEST_DB to a temp file path to prevent
    tests from polluting the real database.

    Returns:
        Path to the SQLite database file
    """
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    config_dir = Path.home() / ".config" / "emdx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "knowledge.db"
