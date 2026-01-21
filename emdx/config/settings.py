"""Configuration utilities for emdx."""

# Re-export constants for backward compatibility
from .constants import DEFAULT_CLAUDE_MODEL

# Re-export get_db_path from canonical source (supports EMDX_TEST_DB)
from emdx.database.path import get_db_path

__all__ = ["DEFAULT_CLAUDE_MODEL", "get_db_path"]
