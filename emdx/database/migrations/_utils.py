"""Shared utilities for database migrations."""

import sqlite3
from contextlib import contextmanager


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
