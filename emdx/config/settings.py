"""Configuration utilities for emdx."""

import os
import sys
from pathlib import Path

# Re-export constants for backward compatibility
from .constants import EMDX_CONFIG_DIR


def _project_root() -> Path:
    """Return the directory containing the emdx package.

    settings.py → config/ → emdx/ → project root (three .parent hops
    from the file itself). In a dev checkout this is the repo root; in
    an installed package it is site-packages (which has no pyproject.toml).
    """
    return Path(__file__).resolve().parent.parent.parent


def _is_dev_checkout() -> bool:
    """Detect if actually working inside the emdx dev checkout.

    Requires BOTH: the package source lives under a directory with
    pyproject.toml, AND the current working directory is inside that
    same checkout — i.e., running `poetry run emdx` (or an editable
    `uv tool install`) from within the repo. The pyproject.toml check
    alone is not enough: `uv tool install --editable <checkout>` makes
    every invocation of the globally-installed binary resolve its
    package source to the checkout, regardless of the caller's actual
    cwd, which silently redirected writes from unrelated projects into
    the checkout's throwaway .emdx/dev.db instead of the shared
    production database.
    """
    try:
        project_root = _project_root()
        if not (project_root / "pyproject.toml").is_file():
            return False
        cwd = Path.cwd().resolve()
        return cwd == project_root or project_root in cwd.parents
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
        dev_dir = _project_root() / ".emdx"
        dev_db = dev_dir / "dev.db"
        if not dev_db.exists():
            dev_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using dev database at {dev_db}", file=sys.stderr)
        return dev_db

    # 4. Production default
    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"
