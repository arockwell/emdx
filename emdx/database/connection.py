"""
Database connection management for emdx

This module provides connection pooling for SQLite databases.
The pool reuses connections to avoid the overhead of opening/closing
connections for each database operation.
"""

import sqlite3
import threading
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import migrations


# Register datetime adapters globally (only needs to be done once)
sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))


class ConnectionPool:
    """Thread-safe SQLite connection pool.

    Manages a pool of reusable database connections to reduce the overhead
    of repeatedly opening and closing connections.

    Attributes:
        db_path: Path to the SQLite database file
        max_connections: Maximum number of connections in the pool
        timeout: Timeout in seconds when waiting for a connection
    """

    def __init__(
        self,
        db_path: Path,
        max_connections: int = 5,
        timeout: float = 30.0
    ):
        """Initialize the connection pool.

        Args:
            db_path: Path to the SQLite database file
            max_connections: Maximum number of connections to maintain
            timeout: Seconds to wait for a connection before raising an error
        """
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout

        self._pool: deque[sqlite3.Connection] = deque()
        self._in_use: int = 0
        self._lock = threading.Lock()
        self._available = threading.Condition(self._lock)
        self._closed = False

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with proper settings."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            check_same_thread=False  # Allow connection sharing across threads
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _validate_connection(self, conn: sqlite3.Connection) -> bool:
        """Check if a connection is still valid."""
        try:
            conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def acquire(self) -> sqlite3.Connection:
        """Acquire a connection from the pool.

        Returns a connection from the pool if available, creates a new one
        if the pool isn't at capacity, or waits for one to become available.

        Returns:
            A SQLite connection ready for use

        Raises:
            RuntimeError: If the pool is closed
            TimeoutError: If no connection becomes available within timeout
        """
        with self._available:
            if self._closed:
                raise RuntimeError("Connection pool is closed")

            deadline = threading.Event()
            start_time = datetime.now()

            while True:
                # Try to get a connection from the pool
                while self._pool:
                    conn = self._pool.popleft()
                    if self._validate_connection(conn):
                        self._in_use += 1
                        return conn
                    else:
                        # Connection is stale, close it
                        try:
                            conn.close()
                        except sqlite3.Error:
                            pass

                # Create a new connection if under capacity
                if self._in_use < self.max_connections:
                    self._in_use += 1
                    return self._create_connection()

                # Wait for a connection to be returned
                elapsed = (datetime.now() - start_time).total_seconds()
                remaining = self.timeout - elapsed

                if remaining <= 0:
                    raise TimeoutError(
                        f"Could not acquire connection within {self.timeout}s timeout"
                    )

                self._available.wait(timeout=remaining)

                if self._closed:
                    raise RuntimeError("Connection pool is closed")

    def release(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool.

        Args:
            conn: The connection to return to the pool
        """
        with self._available:
            if self._closed:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                return

            self._in_use -= 1

            # Return connection to pool if it's still valid
            if self._validate_connection(conn):
                self._pool.append(conn)
            else:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

            self._available.notify()

    def close(self) -> None:
        """Close all connections in the pool."""
        with self._available:
            self._closed = True

            while self._pool:
                conn = self._pool.popleft()
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

            self._available.notify_all()

    @property
    def size(self) -> int:
        """Current number of connections in the pool (not in use)."""
        with self._lock:
            return len(self._pool)

    @property
    def in_use(self) -> int:
        """Number of connections currently in use."""
        with self._lock:
            return self._in_use

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class DatabaseConnection:
    """SQLite database connection manager for emdx with connection pooling.

    Provides thread-safe access to the database through a connection pool.
    Connections are reused across operations to reduce overhead.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        pool_size: int = 5,
        pool_timeout: float = 30.0
    ):
        """Initialize the database connection manager.

        Args:
            db_path: Path to the database file. Defaults to ~/.config/emdx/knowledge.db
            pool_size: Maximum number of connections in the pool
            pool_timeout: Seconds to wait for a connection from the pool
        """
        if db_path is None:
            # Default location in user config directory
            config_dir = Path.home() / ".config" / "emdx"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "knowledge.db"
        else:
            self.db_path = db_path

        self._pool: Optional[ConnectionPool] = None
        self._pool_size = pool_size
        self._pool_timeout = pool_timeout
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> ConnectionPool:
        """Get or create the connection pool (lazy initialization)."""
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = ConnectionPool(
                        self.db_path,
                        max_connections=self._pool_size,
                        timeout=self._pool_timeout
                    )
        return self._pool

    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool.

        Yields a connection that will be automatically returned to the pool
        when the context manager exits.

        Yields:
            sqlite3.Connection: A database connection
        """
        pool = self._get_pool()
        conn = pool.acquire()
        try:
            yield conn
        finally:
            pool.release(conn)

    def close_pool(self) -> None:
        """Close the connection pool and all its connections.

        After calling this, new connections will create a fresh pool.
        """
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    @property
    def pool_stats(self) -> dict:
        """Get current pool statistics.

        Returns:
            Dictionary with pool_size (available) and in_use counts
        """
        if self._pool is None:
            return {"pool_size": 0, "in_use": 0}
        return {
            "pool_size": self._pool.size,
            "in_use": self._pool.in_use
        }

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
