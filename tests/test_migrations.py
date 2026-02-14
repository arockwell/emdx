"""Simple migration tests that work."""

import sqlite3

import pytest

from emdx.database.migrations import (
    get_schema_version,
    migration_001_add_tags,
    _validate_column_name,
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


class TestColumnNameValidation:
    """Tests for _validate_column_name — prevents SQL injection in dynamic column names."""

    def test_valid_simple_name(self):
        assert _validate_column_name("name") == "name"

    def test_valid_snake_case(self):
        assert _validate_column_name("created_at") == "created_at"

    def test_valid_with_numbers(self):
        assert _validate_column_name("column_1") == "column_1"

    def test_valid_starting_with_underscore(self):
        assert _validate_column_name("_internal") == "_internal"

    def test_valid_uppercase(self):
        assert _validate_column_name("ID") == "ID"

    def test_rejects_sql_injection_semicolon(self):
        with pytest.raises(ValueError):
            _validate_column_name("name; DROP TABLE users--")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            _validate_column_name("column name")

    def test_rejects_hyphens(self):
        with pytest.raises(ValueError):
            _validate_column_name("column-name")

    def test_rejects_starting_with_number(self):
        with pytest.raises(ValueError):
            _validate_column_name("1column")

    def test_rejects_parentheses(self):
        with pytest.raises(ValueError):
            _validate_column_name("name()")

    def test_rejects_quotes(self):
        with pytest.raises(ValueError):
            _validate_column_name("name'")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            _validate_column_name("")
