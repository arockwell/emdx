"""
Database Initializer - Centralized database schema management.

This module provides a singleton-pattern initializer that ensures the database
schema is created only once per process, eliminating the repeated db.ensure_schema()
calls scattered across commands.

Usage:
    from emdx.applications import ensure_db

    @app.command()
    def my_command():
        ensure_db()  # Call once at command entry point
        # ... rest of command logic
"""

import threading
from pathlib import Path
from typing import Optional

from ..database import db


class DatabaseInitializer:
    """
    Singleton-pattern database initializer.

    Ensures database schema is created exactly once per process,
    regardless of how many commands call ensure_db().

    Thread-safe implementation for concurrent access.
    """

    _instance: Optional["DatabaseInitializer"] = None
    _lock = threading.Lock()
    _initialized = False
    _schema_lock = threading.Lock()

    def __new__(cls) -> "DatabaseInitializer":
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def ensure_ready(self) -> bool:
        """
        Ensure database schema is ready for use.

        Returns:
            True if schema was just initialized, False if already initialized.
        """
        if self._initialized:
            return False

        with self._schema_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return False

            db.ensure_schema()
            self._initialized = True
            return True

    @classmethod
    def reset(cls) -> None:
        """
        Reset initialization state. Used primarily for testing.
        """
        with cls._lock:
            cls._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if database has been initialized."""
        return self._initialized


# Module-level convenience function
def ensure_db() -> bool:
    """
    Ensure database is ready for use.

    This is the primary entry point for database initialization.
    Call this once at the start of any command that needs database access.

    Returns:
        True if schema was just initialized, False if already initialized.

    Example:
        @app.command()
        def save(...):
            ensure_db()
            # ... command implementation
    """
    return DatabaseInitializer().ensure_ready()
