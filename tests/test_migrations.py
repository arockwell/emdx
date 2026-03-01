"""Tests for the migration system."""

import sqlite3

from emdx.database.migrations import (
    MIGRATIONS,
    get_applied_migrations,
    get_schema_version,
    migration_001_add_tags,
    migration_054_set_based_migration_tracking,
    record_migration,
    run_migrations,
)


class TestSimpleMigrations:
    """Simple tests for migration functionality."""

    def test_get_applied_migrations_empty(self):
        """Fresh database returns empty set."""
        conn = sqlite3.connect(":memory:")
        applied = get_applied_migrations(conn)
        assert applied == set()
        conn.close()

    def test_get_schema_version_legacy(self):
        """Legacy get_schema_version still works for backward compat."""
        conn = sqlite3.connect(":memory:")
        version = get_schema_version(conn)
        assert version == -1
        conn.close()

    def test_tags_migration_creates_tables(self):
        """Test that tags migration creates necessary tables."""
        conn = sqlite3.connect(":memory:")
        migration_001_add_tags(conn)

        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name IN ('tags', 'document_tags')
        """
        )
        count = cursor.fetchone()[0]
        assert count == 2
        conn.close()

    def test_migrations_list_has_string_ids(self):
        """MIGRATIONS list uses string IDs and callable functions."""
        assert len(MIGRATIONS) > 0
        assert all(len(m) == 3 for m in MIGRATIONS)
        assert all(isinstance(m[0], str) for m in MIGRATIONS)
        assert all(callable(m[2]) for m in MIGRATIONS)

    def test_record_and_get_migrations_legacy(self):
        """record_migration falls back to schema_version before transition."""
        conn = sqlite3.connect(":memory:")

        # Before transition, should use schema_version table
        record_migration(conn, "0")
        record_migration(conn, "1")

        applied = get_applied_migrations(conn)
        assert "0" in applied
        assert "1" in applied
        conn.close()

    def test_record_and_get_migrations_new(self):
        """record_migration uses schema_migrations after transition."""
        conn = sqlite3.connect(":memory:")

        # Create schema_version with some legacy entries
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.commit()

        # Run the transition migration
        migration_054_set_based_migration_tracking(conn)

        # Now schema_migrations should exist with copied entries
        applied = get_applied_migrations(conn)
        assert "0" in applied
        assert "1" in applied

        # New records should go to schema_migrations
        record_migration(conn, "20260301_120000")
        applied = get_applied_migrations(conn)
        assert "20260301_120000" in applied
        conn.close()

    def test_run_migrations_fresh_db(self, tmp_path):
        """run_migrations on a fresh DB applies all migrations."""
        db_path = tmp_path / "test.db"
        run_migrations(db_path)

        conn = sqlite3.connect(db_path)
        applied = get_applied_migrations(conn)
        expected = {m[0] for m in MIGRATIONS}
        assert applied == expected
        conn.close()

    def test_run_migrations_idempotent(self, tmp_path):
        """Running migrations twice doesn't re-apply anything."""
        db_path = tmp_path / "test.db"
        run_migrations(db_path)
        # Second run should be a no-op (no output)
        run_migrations(db_path)

        conn = sqlite3.connect(db_path)
        applied = get_applied_migrations(conn)
        expected = {m[0] for m in MIGRATIONS}
        assert applied == expected
        conn.close()
