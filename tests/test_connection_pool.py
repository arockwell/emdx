"""Tests for database connection pooling."""

import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from emdx.database.connection import ConnectionPool, DatabaseConnection


class TestConnectionPool:
    """Tests for the ConnectionPool class."""

    def test_pool_creation(self):
        """Test that pool can be created with valid parameters."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=3)
            assert pool.max_connections == 3
            assert pool.size == 0
            assert pool.in_use == 0
            pool.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_acquire_and_release(self):
        """Test basic acquire and release of connections."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=3)

            # Acquire a connection
            conn = pool.acquire()
            assert pool.in_use == 1
            assert pool.size == 0

            # Verify it's a valid connection
            conn.execute("SELECT 1")

            # Release back to pool
            pool.release(conn)
            assert pool.in_use == 0
            assert pool.size == 1

            pool.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_connection_reuse(self):
        """Test that connections are reused from the pool."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=3)

            # Acquire and release
            conn1 = pool.acquire()
            conn1_id = id(conn1)
            pool.release(conn1)

            # Acquire again - should get the same connection
            conn2 = pool.acquire()
            assert id(conn2) == conn1_id

            pool.release(conn2)
            pool.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_max_connections_limit(self):
        """Test that pool respects max_connections limit."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=2, timeout=0.1)

            # Acquire max connections
            conn1 = pool.acquire()
            conn2 = pool.acquire()
            assert pool.in_use == 2

            # Third acquire should timeout
            with pytest.raises(TimeoutError):
                pool.acquire()

            pool.release(conn1)
            pool.release(conn2)
            pool.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_concurrent_access(self):
        """Test thread-safe concurrent access to the pool."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=5)

            # Create a table
            conn = pool.acquire()
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            conn.commit()
            pool.release(conn)

            results = []
            errors = []

            def worker(thread_id):
                try:
                    conn = pool.acquire()
                    conn.execute(
                        "INSERT INTO test (value) VALUES (?)",
                        (f"thread_{thread_id}",)
                    )
                    conn.commit()
                    time.sleep(0.01)  # Simulate some work
                    pool.release(conn)
                    return thread_id
                except Exception as e:
                    errors.append((thread_id, e))
                    return None

            # Run 20 concurrent operations with 5 connections
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(worker, i) for i in range(20)]
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        results.append(result)

            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 20

            # Verify all inserts were successful
            conn = pool.acquire()
            cursor = conn.execute("SELECT COUNT(*) FROM test")
            count = cursor.fetchone()[0]
            assert count == 20
            pool.release(conn)

            pool.close()
        finally:
            db_path.unlink(missing_ok=True)

    def test_pool_close(self):
        """Test that closing the pool releases all connections."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            pool = ConnectionPool(db_path, max_connections=3)

            # Acquire and release some connections
            conn1 = pool.acquire()
            conn2 = pool.acquire()
            pool.release(conn1)
            pool.release(conn2)

            assert pool.size == 2

            # Close the pool
            pool.close()

            # Acquiring after close should raise
            with pytest.raises(RuntimeError, match="pool is closed"):
                pool.acquire()

        finally:
            db_path.unlink(missing_ok=True)

    def test_context_manager(self):
        """Test pool as context manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            with ConnectionPool(db_path, max_connections=3) as pool:
                conn = pool.acquire()
                conn.execute("SELECT 1")
                pool.release(conn)

            # Pool should be closed after context exit
            with pytest.raises(RuntimeError, match="pool is closed"):
                pool.acquire()

        finally:
            db_path.unlink(missing_ok=True)


class TestDatabaseConnectionPooling:
    """Tests for DatabaseConnection with pooling."""

    def test_connection_reuse_through_manager(self):
        """Test that DatabaseConnection reuses pool connections."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            db = DatabaseConnection(db_path, pool_size=3)

            # First connection
            with db.get_connection() as conn1:
                conn1.execute(
                    "CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"
                )
                conn1.commit()
                conn1_id = id(conn1)

            # Second connection should reuse from pool
            with db.get_connection() as conn2:
                assert id(conn2) == conn1_id

            db.close_pool()
        finally:
            db_path.unlink(missing_ok=True)

    def test_pool_stats(self):
        """Test pool statistics."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            db = DatabaseConnection(db_path, pool_size=3)

            # Before any use
            stats = db.pool_stats
            assert stats == {"pool_size": 0, "in_use": 0}

            # During connection use
            with db.get_connection() as conn:
                stats = db.pool_stats
                assert stats["in_use"] == 1

            # After release
            stats = db.pool_stats
            assert stats["pool_size"] == 1
            assert stats["in_use"] == 0

            db.close_pool()
        finally:
            db_path.unlink(missing_ok=True)

    def test_close_pool(self):
        """Test that close_pool properly cleans up."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            db = DatabaseConnection(db_path, pool_size=3)

            # Use some connections
            with db.get_connection() as conn:
                conn.execute(
                    "CREATE TABLE test (id INTEGER PRIMARY KEY)"
                )
                conn.commit()

            # Close the pool
            db.close_pool()

            # Should be able to get a fresh connection (creates new pool)
            with db.get_connection() as conn:
                conn.execute("SELECT * FROM test")

            db.close_pool()
        finally:
            db_path.unlink(missing_ok=True)

    def test_concurrent_database_operations(self):
        """Test concurrent operations through DatabaseConnection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            db = DatabaseConnection(db_path, pool_size=5)

            # Create table
            with db.get_connection() as conn:
                conn.execute(
                    "CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)"
                )
                conn.commit()

            errors = []

            def worker(thread_id):
                try:
                    with db.get_connection() as conn:
                        conn.execute(
                            "INSERT INTO test (value) VALUES (?)",
                            (f"thread_{thread_id}",)
                        )
                        conn.commit()
                        time.sleep(0.01)
                    return True
                except Exception as e:
                    errors.append((thread_id, e))
                    return False

            # Run concurrent operations
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(worker, i) for i in range(20)]
                results = [f.result() for f in as_completed(futures)]

            assert all(results), f"Some operations failed: {errors}"

            # Verify all inserts
            with db.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM test")
                count = cursor.fetchone()[0]
                assert count == 20

            db.close_pool()
        finally:
            db_path.unlink(missing_ok=True)
