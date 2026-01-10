"""Configuration utilities for emdx."""

from pathlib import Path

# Claude model configuration
DEFAULT_CLAUDE_MODEL = "claude-opus-4-5-20251101"


def get_db_path() -> Path:
    """Get the database path."""
    config_dir = Path.home() / ".config" / "emdx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "knowledge.db"
