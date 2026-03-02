"""Tests for the migration system."""

import sqlite3

from emdx.database.migrations import (
    MIGRATIONS,
    _ensure_schema_migrations,
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

    def test_record_migration_timestamp_without_schema_migrations(self):
        """record_migration with a timestamp ID creates schema_migrations on demand.

        This is the FIX-33 regression scenario: a DB that only has schema_version
        (no schema_migrations) tries to record a timestamp-format migration ID.
        The legacy path called int("20260301_140000") which raises ValueError.
        The fix should create schema_migrations on demand instead.
        """
        conn = sqlite3.connect(":memory:")

        # Simulate a legacy DB: schema_version exists with numeric versions,
        # but schema_migrations does NOT exist (migration 54 was never run).
        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for v in range(54):  # Versions 0-53 recorded in legacy table
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        conn.commit()

        # This should NOT raise ValueError — it must create schema_migrations on demand
        record_migration(conn, "20260301_140000")

        # schema_migrations should now exist and contain the timestamp ID
        applied = get_applied_migrations(conn)
        assert "20260301_140000" in applied

        # Legacy versions should also be present (copied from schema_version)
        assert "0" in applied
        assert "53" in applied

        conn.close()

    def test_record_migration_timestamp_idempotent_without_schema_migrations(self):
        """Recording the same timestamp ID twice on a legacy DB is idempotent."""
        conn = sqlite3.connect(":memory:")

        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Record same timestamp ID twice — should not raise or duplicate
        record_migration(conn, "20260301_140000")
        record_migration(conn, "20260301_140000")

        applied = get_applied_migrations(conn)
        assert "20260301_140000" in applied
        conn.close()

    def test_ensure_schema_migrations_copies_legacy_versions(self):
        """_ensure_schema_migrations copies existing schema_version rows."""
        conn = sqlite3.connect(":memory:")

        conn.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO schema_version (version) VALUES (10)")
        conn.execute("INSERT INTO schema_version (version) VALUES (20)")
        conn.commit()

        _ensure_schema_migrations(conn)

        applied = get_applied_migrations(conn)
        assert "10" in applied
        assert "20" in applied
        conn.close()

    def test_ensure_schema_migrations_idempotent(self):
        """Calling _ensure_schema_migrations twice is safe."""
        conn = sqlite3.connect(":memory:")
        _ensure_schema_migrations(conn)
        _ensure_schema_migrations(conn)  # should not raise
        conn.close()

    def test_timestamp_migrations_recorded_after_full_run(self, tmp_path):
        """All timestamp-format migrations are durably recorded after run_migrations."""
        db_path = tmp_path / "test.db"
        run_migrations(db_path)

        conn = sqlite3.connect(db_path)
        applied = get_applied_migrations(conn)

        # Verify all timestamp-format migrations are recorded
        timestamp_migrations = [m[0] for m in MIGRATIONS if "_" in m[0]]
        for version in timestamp_migrations:
            assert version in applied, f"Timestamp migration {version} not recorded"

        conn.close()
