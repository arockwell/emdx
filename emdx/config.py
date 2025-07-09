"""Configuration utilities for emdx."""

from pathlib import Path

def get_db_path() -> Path:
    """Get the database path."""
    config_dir = Path.home() / '.config' / 'emdx'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / 'knowledge.db'