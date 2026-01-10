"""
Database connection management for emdx
"""

import sqlite3
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from emdx.config.settings import get_db_path
from . import migrations

# Register datetime adapters at module level (once)
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))


class DatabaseConnection:
    """SQLite database connection manager for emdx with simple connection pooling.

    This class provides a thread-safe connection pool for SQLite connections.
    Connections are reused when possible to reduce connection overhead.

    Attributes:
        db_path: Path to the SQLite database file.
        max_pool_size: Maximum number of connections to keep in the pool.
    """

    def __init__(self, db_path: Optional[Path] = None, max_pool_size: int = 5):
        """Initialize the database connection manager.

        Args:
            db_path: Optional path to the database file.
                If None, uses get_db_path() which respects EMDX_DATABASE_URL
                environment variable.
            max_pool_size: Maximum number of connections to keep in the pool.
        """
        self.db_path = db_path if db_path is not None else get_db_path()
        self.max_pool_size = max_pool_size
        self._pool: deque = deque()
        self._lock = threading.Lock()

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with proper settings."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False,  # Allow connection reuse across threads
        )
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager.

        Uses connection pooling for efficiency. Connections are returned to the
        pool after use unless the pool is full.
        """
        conn = None
        with self._lock:
            if self._pool:
                conn = self._pool.pop()

        if conn is None:
            conn = self._create_connection()

        try:
            yield conn
        finally:
            # Return to pool if space available, otherwise close
            with self._lock:
                if len(self._pool) < self.max_pool_size:
                    self._pool.append(conn)
                else:
                    conn.close()

    def close_all(self) -> None:
        """Close all connections in the pool.

        Call this during application shutdown for clean resource cleanup.
        """
        with self._lock:
            while self._pool:
                conn = self._pool.pop()
                try:
                    conn.close()
                except Exception:
                    pass  # Ignore errors during cleanup

    def ensure_schema(self):
        """Ensure the tables and FTS5 virtual table exist"""
        # Run any pending migrations first
        migrations.run_migrations(self.db_path)

        with self.get_connection() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # The schema is now primarily handled by migrations, but we keep these
            # CREATE TABLE IF NOT EXISTS statements as a safety net for edge cases
            # and backwards compatibility

            # Note: migration_000 creates the documents table and related schema
            # Note: migration_001 creates the tags tables

            # Legacy code for backwards compatibility - these should be no-ops
            # if migrations have run successfully
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    deleted_at TIMESTAMP,
                    is_deleted BOOLEAN DEFAULT FALSE
                )
            """
            )

            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, content, project, content=documents, content_rowid=id,
                    tokenize='porter unicode61'
                )
            """
            )

            # Create triggers to keep FTS in sync
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, content, project)
                    VALUES (new.id, new.title, new.content, new.project);
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    UPDATE documents_fts
                    SET title = new.title, content = new.content, project = new.project
                    WHERE rowid = old.id;
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            """
            )

            conn.commit()


# Global instance for backward compatibility
db_connection = DatabaseConnection()
