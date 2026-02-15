"""Database migration runner and version tracking."""

import sqlite3
from collections.abc import Callable
from contextlib import contextmanager

from ...config.settings import get_db_path


@contextmanager
def foreign_keys_disabled(conn: sqlite3.Connection):
    """Context manager to temporarily disable foreign key constraints.

    Used during migrations that need to recreate tables, which requires
    foreign keys to be disabled to avoid constraint violations during
    the table swap.

    Usage:
        with foreign_keys_disabled(conn):
            # recreate table operations here
            pass
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    try:
        yield
    finally:
        cursor.execute("PRAGMA foreign_keys = ON")


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()
    # Return -1 for completely fresh installations (no version recorded yet)
    # This ensures migration 0 will run for new installations
    return result[0] if result[0] is not None else -1


def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set the schema version."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def run_migrations(db_path=None, migrations: list[tuple[int, str, Callable]] = None):
    """Run all pending migrations.

    Args:
        db_path: Path to the database file. If None, uses the default path.
        migrations: List of migrations to run. If None, uses the default MIGRATIONS list.
    """
    if db_path is None:
        db_path = get_db_path()
    # Don't return early - we need to run migrations even for new databases
    # The database file will be created when we connect to it

    # Import here to avoid circular imports
    if migrations is None:
        from . import MIGRATIONS
        migrations = MIGRATIONS

    conn = sqlite3.connect(db_path)
    # Enable foreign keys for this connection (migrations use foreign_keys_disabled()
    # context manager when they need to temporarily disable them for table recreation)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        current_version = get_schema_version(conn)

        for version, description, migration_func in migrations:
            if version > current_version:
                print(f"Running migration {version}: {description}")
                migration_func(conn)
                set_schema_version(conn, version)
                print(f"✅ Migration {version} completed")

    finally:
        conn.close()
