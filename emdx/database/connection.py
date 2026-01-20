"""
Database connection management for emdx
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import migrations
from .path import get_db_path


class DatabaseConnection:
    """SQLite database connection manager for emdx"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = get_db_path()
        else:
            self.db_path = db_path

    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager"""
        conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row  # Enable column access by name

        # Enable foreign key constraints for this connection
        conn.execute("PRAGMA foreign_keys = ON")

        # Register datetime adapter
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
        sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))

        try:
            yield conn
        finally:
            conn.close()

    def ensure_schema(self):
        """Ensure the database schema is up to date.

        All schema creation is handled by the migrations system.
        This method simply runs any pending migrations.
        """
        migrations.run_migrations(self.db_path)


# Global instance for backward compatibility
db_connection = DatabaseConnection()
