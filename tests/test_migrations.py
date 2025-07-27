"""Simple migration tests that work."""

import sqlite3

from emdx.database.migrations import get_schema_version, migration_001_add_tags


class TestSimpleMigrations:
    """Simple tests for migration functionality."""

    def test_schema_version_tracking(self):
        """Test basic schema version tracking."""
        conn = sqlite3.connect(":memory:")

        # New database should have version 0
        version = get_schema_version(conn)
        assert version == 0

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
        from emdx.migrations import MIGRATIONS

        assert len(MIGRATIONS) > 0
        assert all(len(m) == 3 for m in MIGRATIONS)  # version, description, function
        assert all(callable(m[2]) for m in MIGRATIONS)  # functions are callable
