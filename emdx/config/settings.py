"""Configuration utilities for emdx."""

import os
import sys
from pathlib import Path

# Re-export constants for backward compatibility
from .constants import EMDX_CONFIG_DIR


def _is_dev_checkout() -> bool:
    """Detect if running from an editable install (dev checkout).

    Checks if the emdx package source lives inside a directory with
    pyproject.toml — i.e., running via `poetry run emdx` from the repo.
    """
    try:
        # config/ → emdx/ → project root
        project_root = Path(__file__).resolve().parent.parent
        return (project_root / "pyproject.toml").is_file()
    except Exception:
        return False


def get_db_path() -> Path:
    """Get the database path with environment and dev-checkout awareness.

    Priority:
    1. EMDX_TEST_DB — test isolation (unchanged)
    2. EMDX_DB — explicit override
    3. Dev checkout detection → <project-root>/.emdx/dev.db
    4. Production default → ~/.config/emdx/knowledge.db
    """
    # 1. Test isolation
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    # 2. Explicit override
    explicit_db = os.environ.get("EMDX_DB")
    if explicit_db:
        path = Path(explicit_db)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # 3. Dev checkout → local .emdx/dev.db
    if _is_dev_checkout():
        project_root = Path(__file__).resolve().parent.parent
        dev_dir = project_root / ".emdx"
        dev_db = dev_dir / "dev.db"
        if not dev_db.exists():
            dev_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using dev database at {dev_db}", file=sys.stderr)
        return dev_db

    # 4. Production default
    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"
