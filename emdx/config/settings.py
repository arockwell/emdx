"""Configuration utilities for emdx."""

from pathlib import Path

# Claude model configuration
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-20250514"


def get_db_path() -> Path:
    """Get the database path."""
    config_dir = Path.home() / ".config" / "emdx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "knowledge.db"
