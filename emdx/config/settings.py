"""Configuration utilities for emdx."""

import os
from pathlib import Path
from typing import Optional

# Claude model configuration
DEFAULT_CLAUDE_MODEL = "claude-opus-4-5-20251101"

# Module-level variable for runtime database path override
_db_path_override: Optional[Path] = None


def set_db_path(path: Optional[Path]) -> None:
    """Set the database path override.

    This allows the main app callback to pass the --db-url option
    to the database connection layer.

    Args:
        path: The database path to use, or None to use defaults.
    """
    global _db_path_override
    _db_path_override = path


def get_db_path() -> Path:
    """Get the database path.

    Priority order:
    1. Runtime override (set via set_db_path)
    2. EMDX_DATABASE_URL environment variable
    3. Default path: ~/.config/emdx/knowledge.db

    Returns:
        Path to the database file.
    """
    # Priority 1: Runtime override
    if _db_path_override is not None:
        parent = _db_path_override.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        return _db_path_override

    # Priority 2: Environment variable
    env_path = os.environ.get("EMDX_DATABASE_URL")
    if env_path:
        path = Path(env_path)
        parent = path.parent
        if parent and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        return path

    # Priority 3: Default location
    config_dir = Path.home() / ".config" / "emdx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "knowledge.db"
