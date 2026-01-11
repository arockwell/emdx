"""Configuration utilities for emdx."""

import os
from pathlib import Path
from typing import Optional


class EmdxConfig:
    """Centralized configuration for emdx"""
    
    def __init__(self, db_path: Optional[Path] = None, db_url: Optional[str] = None):
        self._db_path = db_path
        self._db_url = db_url
        
    @property
    def db_path(self) -> Path:
        """Get the database path."""
        if self._db_path:
            return self._db_path
        
        # Check for environment variable
        env_path = os.environ.get("EMDX_DB_PATH")
        if env_path:
            return Path(env_path)
            
        # Default location
        config_dir = Path.home() / ".config" / "emdx"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "knowledge.db"
    
    @property
    def db_url(self) -> Optional[str]:
        """Get the database URL (for future database backends)."""
        if self._db_url:
            return self._db_url
        return os.environ.get("EMDX_DATABASE_URL")


# Global configuration instance - will be set by the application
_config: Optional[EmdxConfig] = None


def get_config() -> EmdxConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = EmdxConfig()
    return _config


def set_config(config: EmdxConfig) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config

# Re-export constants for backward compatibility
from .constants import DEFAULT_CLAUDE_MODEL


def get_db_path() -> Path:
    """Get the database path - backwards compatibility function."""
    return get_config().db_path