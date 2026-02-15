"""
Database connection management for emdx
"""

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from ..config.constants import EMDX_CONFIG_DIR
from . import migrations


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable.

    When running tests, set EMDX_TEST_DB to a temp file path to prevent
    tests from polluting the real database.
    """
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"


class DatabaseConnection:
    """SQLite database connection manager for emdx"""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            self.db_path = get_db_path()
        else:
            self.db_path = db_path

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
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

    def ensure_schema(self) -> None:
        """Ensure the database schema is up to date.

        All schema creation is handled by the migrations system.
        This method simply runs any pending migrations.
        """
        migrations.run_migrations(self.db_path)


# Global instance for backward compatibility
db_connection = DatabaseConnection()
