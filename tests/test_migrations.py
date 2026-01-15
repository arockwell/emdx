"""Simple migration tests that work."""

import sqlite3

from emdx.database.migrations import (
    get_schema_version,
    migration_000_create_documents_table,
    migration_001_add_tags,
    migration_022_add_critical_performance_indexes,
)


class TestSimpleMigrations:
    """Simple tests for migration functionality."""

    def test_schema_version_tracking(self):
        """Test basic schema version tracking."""
        conn = sqlite3.connect(":memory:")

        # New database should have version -1 (no migrations applied yet)
        version = get_schema_version(conn)
        assert version == -1

        conn.close()

    def test_tags_migration_creates_tables(self):
        """Test that tags migration creates necessary tables."""
        conn = sqlite3.connect(":memory:")

        # Run the migration
        migration_001_add_tags(conn)

        # Check tables exist
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name IN ('tags', 'document_tags')
        """
        )
        count = cursor.fetchone()[0]
        assert count == 2

        conn.close()

    def test_migrations_list_exists(self):
        """Test that MIGRATIONS list is properly defined."""
        from emdx.database.migrations import MIGRATIONS

        assert len(MIGRATIONS) > 0
        assert all(len(m) == 3 for m in MIGRATIONS)  # version, description, function
        assert all(callable(m[2]) for m in MIGRATIONS)  # functions are callable

    def test_critical_performance_indexes_migration(self):
        """Test that performance indexes migration creates the correct indexes."""
        conn = sqlite3.connect(":memory:")

        # First create the documents table (required for indexes)
        migration_000_create_documents_table(conn)

        # Run the performance indexes migration
        migration_022_add_critical_performance_indexes(conn)

        # Check that the new indexes exist
        cursor = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND name IN (
                'idx_documents_is_deleted_only',
                'idx_documents_is_deleted_project'
            )
            ORDER BY name
        """
        )
        indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_documents_is_deleted_only" in indexes
        assert "idx_documents_is_deleted_project" in indexes
        assert len(indexes) == 2

        conn.close()

    def test_performance_indexes_are_idempotent(self):
        """Test that running the migration twice doesn't cause errors."""
        conn = sqlite3.connect(":memory:")

        # Create base table
        migration_000_create_documents_table(conn)

        # Run migration twice - should not raise
        migration_022_add_critical_performance_indexes(conn)
        migration_022_add_critical_performance_indexes(conn)

        # Verify indexes still exist
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='index' AND name IN (
                'idx_documents_is_deleted_only',
                'idx_documents_is_deleted_project'
            )
        """
        )
        count = cursor.fetchone()[0]
        assert count == 2

        conn.close()
