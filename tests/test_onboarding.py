"""Tests for first-run onboarding seeding."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_test_db(db_path: Path) -> sqlite3.Connection:
    """Create a minimal test database with schema_flags, documents, tasks, and categories."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_flags (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT,
            parent_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE,
            doc_type TEXT NOT NULL DEFAULT 'user'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_tags (
            document_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (document_id, tag_id),
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 3,
            gameplan_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
            project TEXT,
            current_step TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            type TEXT DEFAULT 'single',
            source_doc_id INTEGER REFERENCES documents(id),
            output_doc_id INTEGER REFERENCES documents(id),
            parent_task_id INTEGER REFERENCES tasks(id),
            epic_key TEXT REFERENCES categories(key),
            epic_seq INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_deps (
            task_id INTEGER NOT NULL,
            depends_on INTEGER NOT NULL,
            PRIMARY KEY (task_id, depends_on),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


class _MockDb:
    """Minimal mock for emdx.database.db that wraps a real SQLite connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_connection(self) -> _ConnCtx:
        return _ConnCtx(self._conn)


class _ConnCtx:
    """Context manager that returns a shared connection."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, *args: object) -> None:
        pass


@pytest.fixture()
def onboarding_db(tmp_path: Path) -> sqlite3.Connection:
    """Create a fresh isolated database for onboarding tests."""
    db_path = tmp_path / "onboarding_test.db"
    return _make_test_db(db_path)


class TestMaybeSeedOnboarding:
    """Tests for maybe_seed_onboarding()."""

    def test_fresh_db_seeds_docs_and_tasks(self, onboarding_db: sqlite3.Connection) -> None:
        """Fresh DB with no documents seeds welcome docs and tutorial tasks."""
        mock_db = _MockDb(onboarding_db)

        with (
            patch("emdx.onboarding.db", mock_db),
            patch("emdx.database.documents.db_connection", mock_db),
            patch("emdx.models.tasks.db", mock_db),
            patch("emdx.models.categories.db", mock_db),
        ):
            from emdx.onboarding import maybe_seed_onboarding

            maybe_seed_onboarding()

        # Should have created 2 tutorial documents
        cursor = onboarding_db.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE")
        doc_count = cursor.fetchone()[0]
        assert doc_count == 2, f"Expected 2 docs, got {doc_count}"

        # Should have welcome doc and shortcuts doc
        cursor = onboarding_db.execute(
            "SELECT title FROM documents WHERE is_deleted = FALSE ORDER BY id"
        )
        titles = [row[0] for row in cursor.fetchall()]
        assert "Welcome to emdx" in titles
        assert "Keyboard Shortcuts" in titles

        # Should have created the epic + 5 tasks = 6 task rows
        cursor = onboarding_db.execute("SELECT COUNT(*) FROM tasks")
        task_count = cursor.fetchone()[0]
        assert task_count == 6, f"Expected 6 tasks (1 epic + 5), got {task_count}"

        # Should have set the seeded flag
        cursor = onboarding_db.execute(
            "SELECT value FROM schema_flags WHERE key = 'onboarding_seeded'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "1"

    def test_idempotent_second_call_is_noop(self, onboarding_db: sqlite3.Connection) -> None:
        """Second call is a no-op when the seeded flag is already set."""
        mock_db = _MockDb(onboarding_db)

        with (
            patch("emdx.onboarding.db", mock_db),
            patch("emdx.database.documents.db_connection", mock_db),
            patch("emdx.models.tasks.db", mock_db),
            patch("emdx.models.categories.db", mock_db),
        ):
            from emdx.onboarding import maybe_seed_onboarding

            maybe_seed_onboarding()  # first call — seeds
            maybe_seed_onboarding()  # second call — should be no-op

        cursor = onboarding_db.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE")
        doc_count = cursor.fetchone()[0]
        assert doc_count == 2, f"Expected 2 docs after two calls, got {doc_count}"

        cursor = onboarding_db.execute("SELECT COUNT(*) FROM tasks")
        task_count = cursor.fetchone()[0]
        assert task_count == 6, f"Expected 6 tasks after two calls, got {task_count}"

    def test_existing_user_skip(self, onboarding_db: sqlite3.Connection) -> None:
        """DB with existing documents skips seeding and sets the flag."""
        # Pre-populate with a user document
        onboarding_db.execute(
            "INSERT INTO documents (title, content) VALUES (?, ?)",
            ("My existing doc", "Some content"),
        )
        onboarding_db.commit()

        mock_db = _MockDb(onboarding_db)

        with (
            patch("emdx.onboarding.db", mock_db),
            patch("emdx.database.documents.db_connection", mock_db),
            patch("emdx.models.tasks.db", mock_db),
            patch("emdx.models.categories.db", mock_db),
        ):
            from emdx.onboarding import maybe_seed_onboarding

            maybe_seed_onboarding()

        # Should NOT have added tutorial documents
        cursor = onboarding_db.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE")
        doc_count = cursor.fetchone()[0]
        assert doc_count == 1, f"Expected only the pre-existing doc, got {doc_count}"

        # Should NOT have added tasks
        cursor = onboarding_db.execute("SELECT COUNT(*) FROM tasks")
        task_count = cursor.fetchone()[0]
        assert task_count == 0, f"Expected 0 tasks, got {task_count}"

        # Should still have set the seeded flag
        cursor = onboarding_db.execute(
            "SELECT value FROM schema_flags WHERE key = 'onboarding_seeded'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "1"

    def test_no_schema_flags_table_returns_early(self, tmp_path: Path) -> None:
        """When schema_flags table doesn't exist, returns without error."""
        db_path = tmp_path / "no_flags.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                title TEXT,
                content TEXT,
                is_deleted BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()

        mock_db = _MockDb(conn)

        with patch("emdx.onboarding.db", mock_db):
            from emdx.onboarding import maybe_seed_onboarding

            # Should not raise — gracefully returns
            maybe_seed_onboarding()

        # No documents should have been added
        cursor = conn.execute("SELECT COUNT(*) FROM documents")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_logging_on_missing_schema_flags(self, tmp_path: Path) -> None:
        """Bare except block logs a debug message."""
        db_path = tmp_path / "no_flags_log.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                title TEXT,
                content TEXT,
                is_deleted BOOLEAN DEFAULT FALSE
            )
        """)
        conn.commit()

        mock_db = _MockDb(conn)

        with (
            patch("emdx.onboarding.db", mock_db),
            patch("emdx.onboarding.logger") as mock_logger,
        ):
            from emdx.onboarding import maybe_seed_onboarding

            maybe_seed_onboarding()

        mock_logger.debug.assert_called_once_with(
            "schema_flags table not yet available, skipping onboarding check"
        )
        conn.close()
