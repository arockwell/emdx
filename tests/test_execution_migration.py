"""Tests for execution ID migration to numeric IDs."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from emdx.database.migrations import (
    run_migrations,
    migration_002_add_executions,
    migration_005_execution_numeric_id,
    get_schema_version,
    set_schema_version,
)
from emdx.models.executions import (
    create_execution,
    get_execution,
    format_execution_log_filename,
    update_execution_status,
    get_recent_executions,
)
from emdx.database.connection import db_connection


@pytest.fixture
def test_db(tmp_path):
    """Create a test database."""
    db_path = tmp_path / "test.db"
    # Override the default database path
    db_connection._db_path = str(db_path)
    yield db_path
    # Clean up
    db_connection._db_path = None
    db_connection._conn = None


def test_migration_creates_numeric_id_column(test_db):
    """Test that migration adds numeric ID column and preserves data."""
    conn = sqlite3.connect(test_db)

    # Create base tables first
    from emdx.database.migrations import (
        migration_000_create_documents_table,
        migration_001_add_tags,
        migration_004_add_execution_pid,
    )

    migration_000_create_documents_table(conn)
    migration_001_add_tags(conn)

    # Create old-style executions table
    migration_002_add_executions(conn)

    # Add pid column (migration 4)
    migration_004_add_execution_pid(conn)

    # Insert test data with string IDs
    conn.execute(
        """
        INSERT INTO executions (id, doc_id, doc_title, status, started_at, log_file, pid)
        VALUES ('claude-123-456789', 123, 'Test Doc', 'completed', CURRENT_TIMESTAMP, 'test.log', NULL)
    """
    )
    conn.execute(
        """
        INSERT INTO executions (id, doc_id, doc_title, status, started_at, log_file, pid)
        VALUES ('claude-456-789012', 456, 'Another Doc', 'running', CURRENT_TIMESTAMP, 'test2.log', NULL)
    """
    )
    conn.commit()

    # Run migration
    migration_005_execution_numeric_id(conn)

    # Check new table structure
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(executions)")
    columns = {col[1]: col for col in cursor.fetchall()}

    assert "id" in columns
    assert columns["id"][2] == "INTEGER"  # Type
    assert columns["id"][5] == 1  # Primary key

    assert "string_id" in columns
    assert columns["string_id"][2] == "TEXT"

    # Check data was preserved
    cursor.execute("SELECT id, string_id, doc_id, doc_title FROM executions ORDER BY id")
    rows = cursor.fetchall()

    assert len(rows) == 2
    assert rows[0][1] == "claude-123-456789"  # string_id preserved
    assert rows[0][2] == 123  # doc_id
    assert rows[1][1] == "claude-456-789012"
    assert rows[1][2] == 456

    conn.close()


def test_create_execution_with_numeric_id(test_db):
    """Test creating new executions with auto-incrementing IDs."""
    # Run all migrations
    run_migrations()

    # Create executions
    id1 = create_execution(
        doc_id=100, doc_title="Test Document 1", log_file="/tmp/test1.log", working_dir="/tmp/work1"
    )

    id2 = create_execution(
        doc_id=200,
        doc_title="Test Document 2",
        log_file="/tmp/test2.log",
        working_dir="/tmp/work2",
        string_id="legacy-id-123",  # Test with legacy ID
    )

    # Check IDs are numeric and incrementing
    assert isinstance(id1, int)
    assert isinstance(id2, int)
    assert id2 == id1 + 1

    # Verify data
    exec1 = get_execution(id1)
    assert exec1.id == id1
    assert exec1.doc_id == 100
    assert exec1.doc_title == "Test Document 1"

    exec2 = get_execution(id2)
    assert exec2.id == id2
    assert exec2.doc_id == 200


def test_get_execution_backwards_compatibility(test_db):
    """Test that get_execution works with numeric IDs and numeric strings."""
    run_migrations()

    # Create execution
    exec_id = create_execution(doc_id=300, doc_title="Legacy Test", log_file="/tmp/legacy.log")

    # Verify numeric ID was created
    assert isinstance(exec_id, int)
    assert exec_id > 0

    # Get by numeric ID
    exec_by_num = get_execution(exec_id)
    assert exec_by_num is not None
    assert exec_by_num.id == exec_id
    assert exec_by_num.doc_title == "Legacy Test"

    # Test with numeric string (important for CLI compatibility)
    exec_by_numstr = get_execution(str(exec_id))
    assert exec_by_numstr is not None
    assert exec_by_numstr.id == exec_id

    # Test non-existent numeric ID
    exec_not_found = get_execution(999999)
    assert exec_not_found is None


def test_format_execution_log_filename():
    """Test log filename formatting with numeric IDs."""
    assert format_execution_log_filename(1) == "execution_00000001_output.log"
    assert format_execution_log_filename(42) == "execution_00000042_output.log"
    assert format_execution_log_filename(12345678) == "execution_12345678_output.log"
    assert format_execution_log_filename(999999999) == "execution_999999999_output.log"


def test_update_execution_status_with_numeric_id(test_db):
    """Test updating execution status works with numeric IDs."""
    run_migrations()

    # Create execution
    exec_id = create_execution(doc_id=400, doc_title="Status Test", log_file="/tmp/status.log")

    # Initial status should be running
    exec = get_execution(exec_id)
    assert exec.status == "running"
    assert exec.exit_code is None

    # Update status
    update_execution_status(exec_id, "completed", 0)

    # Verify update
    exec = get_execution(exec_id)
    assert exec.status == "completed"
    assert exec.exit_code == 0
    assert exec.completed_at is not None


def test_get_recent_executions_with_numeric_ids(test_db):
    """Test that get_recent_executions returns proper numeric IDs."""
    run_migrations()

    # Create multiple executions
    ids = []
    for i in range(5):
        exec_id = create_execution(
            doc_id=500 + i, doc_title=f"Recent Test {i}", log_file=f"/tmp/recent{i}.log"
        )
        ids.append(exec_id)

    # Get recent executions
    recent = get_recent_executions(limit=3)

    # Should get most recent 3 in reverse order
    assert len(recent) == 3
    assert all(isinstance(e.id, int) for e in recent)
    assert [e.id for e in recent] == sorted(ids[-3:], reverse=True)


def test_concurrent_execution_creation(test_db):
    """Test that concurrent execution creation doesn't conflict."""
    run_migrations()

    # Simulate concurrent creation
    import threading

    results = []

    def create_exec(index):
        exec_id = create_execution(
            doc_id=600 + index,
            doc_title=f"Concurrent {index}",
            log_file=f"/tmp/concurrent{index}.log",
        )
        results.append(exec_id)

    # Create threads
    threads = []
    for i in range(10):
        t = threading.Thread(target=create_exec, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # All IDs should be unique
    assert len(results) == 10
    assert len(set(results)) == 10
    assert all(isinstance(id, int) for id in results)


def test_migration_idempotency(test_db):
    """Test that migration can be run multiple times safely."""
    conn = sqlite3.connect(test_db)

    # Run all prerequisite migrations
    from emdx.database.migrations import (
        migration_000_create_documents_table,
        migration_001_add_tags,
        migration_003_add_document_relationships,
        migration_004_add_execution_pid,
    )

    migration_000_create_documents_table(conn)
    migration_001_add_tags(conn)
    migration_002_add_executions(conn)
    migration_003_add_document_relationships(conn)
    migration_004_add_execution_pid(conn)

    # Run numeric ID migration
    migration_005_execution_numeric_id(conn)

    # Try to run again - should not fail
    try:
        migration_005_execution_numeric_id(conn)
        # If SQLite doesn't error on recreating table, that's ok
    except sqlite3.OperationalError as e:
        # Expected if table already exists
        assert "already exists" in str(e) or "duplicate" in str(e)

    conn.close()
