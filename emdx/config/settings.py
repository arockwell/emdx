"""Configuration utilities for emdx."""

import os
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class DatabaseSelection:
    """Effective destination; overrides need not correspond to a named KB."""

    name: str | None
    path: Path
    reason: str


def resolve_database(*, require_exists: bool = True) -> DatabaseSelection:
    """Resolve the effective database without creating files or directories.

    Test/explicit paths and checkout isolation precede named KB selectors.
    Inspection commands may report a missing named KB so it can be repaired.
    """
    for variable in ("EMDX_TEST_DB", "EMDX_DB"):
        value = os.environ.get(variable)
        if value:
            return DatabaseSelection(None, Path(value), f"{variable} environment variable")
    if _is_dev_checkout():
        return DatabaseSelection(
            None, _project_root() / ".emdx" / "dev.db", "dev checkout detected (editable install)"
        )

    from .knowledge_bases import DEFAULT_KB, require_kb, resolve_kb

    selection = require_kb() if require_exists else resolve_kb()
    if selection.name == DEFAULT_KB:
        return DatabaseSelection(DEFAULT_KB, EMDX_CONFIG_DIR / "knowledge.db", selection.reason)
    return DatabaseSelection(selection.name, selection.path, selection.reason)


def get_db_path() -> Path:
    """Get the effective path, creating its parent directory when appropriate."""
    selection = resolve_database()
    if (
        selection.reason == "dev checkout detected (editable install)"
        and not selection.path.exists()
    ):
        print(f"Using dev database at {selection.path}", file=sys.stderr)
    if not os.environ.get("EMDX_TEST_DB"):
        selection.path.parent.mkdir(parents=True, exist_ok=True)
    return selection.path
