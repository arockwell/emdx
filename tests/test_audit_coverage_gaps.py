"""Tests for data-mutating hot spots flagged by the 2026-07-18 audit (#1063).

Covers:
- Transitive dependency-cycle detection in tasks (_would_cycle via add_dependency)
- find_supersede_candidate matching behavior
- Data-transforming migrations: migration_042 (emoji tag conversion)
  and migration_037 (cascade-FK table rebuild preserves rows)
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture(autouse=True)
def clean_tables(isolate_test_database):
    """Clean the tables these tests mutate, before and after each test."""
    from emdx.database.connection import db_connection

    def _clean() -> None:
        with db_connection.get_connection() as conn:
            conn.execute("DELETE FROM task_deps")
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM gists")
            conn.execute("DELETE FROM documents")
            conn.commit()

    _clean()
    yield
    _clean()


# =========================================================================
# Transitive dependency cycles (models/tasks.py::_would_cycle)
# =========================================================================


class TestTransitiveDependencyCycles:
    """add_dependency must reject cycles of any length, not just direct ones."""

    @staticmethod
    def _make_tasks(n: int) -> list[int]:
        from emdx.models.tasks import create_task

        return [create_task(title=f"cycle-test-{i}") for i in range(n)]

    def test_direct_cycle_rejected(self):
        from emdx.models.tasks import add_dependency

        a, b = self._make_tasks(2)
        assert add_dependency(a, b) is True
        assert add_dependency(b, a) is False

    def test_self_dependency_rejected(self):
        from emdx.models.tasks import add_dependency

        (a,) = self._make_tasks(1)
        assert add_dependency(a, a) is False

    def test_transitive_cycle_rejected(self):
        """A→B→C established; adding C→A must be rejected (A→B→C→A)."""
        from emdx.models.tasks import add_dependency

        a, b, c = self._make_tasks(3)
        assert add_dependency(a, b) is True
        assert add_dependency(b, c) is True
        assert add_dependency(c, a) is False

    def test_long_transitive_cycle_rejected(self):
        """Five-hop chain; closing the loop anywhere must be rejected."""
        from emdx.models.tasks import add_dependency

        ids = self._make_tasks(5)
        for upstream, downstream in zip(ids, ids[1:], strict=False):
            assert add_dependency(upstream, downstream) is True
        assert add_dependency(ids[-1], ids[0]) is False
        assert add_dependency(ids[3], ids[1]) is False

    def test_valid_diamond_allowed(self):
        """Diamond (A→B, A→C, B→D, C→D) is a DAG and must be allowed."""
        from emdx.models.tasks import add_dependency

        a, b, c, d = self._make_tasks(4)
        assert add_dependency(a, b) is True
        assert add_dependency(a, c) is True
        assert add_dependency(b, d) is True
        assert add_dependency(c, d) is True


# =========================================================================
# find_supersede_candidate (database/documents.py)
# =========================================================================


class TestFindSupersedeCandidate:
    def test_exact_title_same_project_matches(self):
        from emdx.database.documents import find_supersede_candidate, save_document

        doc_id = save_document("Auth Gameplan", "old content", project="emdx")
        candidate = find_supersede_candidate("Auth Gameplan", project="emdx")
        assert candidate is not None
        assert candidate.id == doc_id

    def test_dissimilar_title_not_matched(self):
        from emdx.database.documents import find_supersede_candidate, save_document

        save_document("Auth Gameplan", "content", project="emdx")
        candidate = find_supersede_candidate(
            "Completely Unrelated Grocery List", project="emdx"
        )
        assert candidate is None

    def test_cross_project_not_matched(self):
        from emdx.database.documents import find_supersede_candidate, save_document

        save_document("Auth Gameplan", "content", project="other-project")
        candidate = find_supersede_candidate("Auth Gameplan", project="emdx")
        assert candidate is None

    def test_most_recent_candidate_wins(self):
        from emdx.database.connection import db_connection
        from emdx.database.documents import find_supersede_candidate, save_document

        older = save_document("Auth Gameplan", "v1", project="emdx")
        newer = save_document("Auth Gameplan", "v2", project="emdx")
        # Both saves land in the same second; make recency unambiguous
        with db_connection.get_connection() as conn:
            conn.execute(
                "UPDATE documents SET created_at = datetime('now', '-1 day') WHERE id = ?",
                (older,),
            )
            conn.commit()
        candidate = find_supersede_candidate("Auth Gameplan", project="emdx")
        assert candidate is not None
        assert candidate.id == newer

    def test_child_documents_not_matched(self):
        """Docs with a parent are already linked; they must not be candidates."""
        from emdx.database.documents import (
            find_supersede_candidate,
            save_document,
        )

        parent = save_document("Auth Gameplan", "parent", project="emdx")
        child = save_document(
            "Auth Gameplan", "child", project="emdx", parent_id=parent
        )
        candidate = find_supersede_candidate("Auth Gameplan", project="emdx")
        assert candidate is not None
        assert candidate.id != child


# =========================================================================
# Data-transforming migrations
# =========================================================================


class TestMigration042EmojiTagConversion:
    """migration_042 must convert/merge emoji tags without losing associations."""

    def _run(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.database.migrations import migration_042_convert_emoji_tags_to_text

        with db_connection.get_connection() as conn:
            migration_042_convert_emoji_tags_to_text(conn)

    def test_emoji_renamed_when_no_text_equivalent(self):
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document

        doc_id = save_document("Doc", "content")
        with db_connection.get_connection() as conn:
            cur = conn.execute("INSERT INTO tags (name) VALUES ('🎯')")
            emoji_id = cur.lastrowid
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, emoji_id),
            )
            conn.commit()

        self._run()

        with db_connection.get_connection() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM tags").fetchall()}
            assert "🎯" not in names
            assert "gameplan" in names
            # The document keeps its (renamed) tag
            row = conn.execute(
                "SELECT t.name FROM tags t "
                "JOIN document_tags dt ON dt.tag_id = t.id "
                "WHERE dt.document_id = ?",
                (doc_id,),
            ).fetchone()
            assert row[0] == "gameplan"

    def test_emoji_merged_into_existing_text_tag(self):
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document

        doc_a = save_document("Doc A", "content")
        doc_b = save_document("Doc B", "content")
        with db_connection.get_connection() as conn:
            text_id = conn.execute("INSERT INTO tags (name) VALUES ('gameplan')").lastrowid
            emoji_id = conn.execute("INSERT INTO tags (name) VALUES ('🎯')").lastrowid
            # doc_a has BOTH forms (merge must dedupe); doc_b only emoji
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_a, text_id),
            )
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_a, emoji_id),
            )
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_b, emoji_id),
            )
            conn.commit()

        self._run()

        with db_connection.get_connection() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM tags").fetchall()}
            assert "🎯" not in names
            rows = conn.execute(
                "SELECT dt.document_id FROM document_tags dt "
                "JOIN tags t ON t.id = dt.tag_id WHERE t.name = 'gameplan' "
                "ORDER BY dt.document_id",
                (),
            ).fetchall()
            assert [r[0] for r in rows] == sorted([doc_a, doc_b])
            # usage_count recomputed to distinct documents
            count = conn.execute(
                "SELECT usage_count FROM tags WHERE name = 'gameplan'"
            ).fetchone()[0]
            assert count == 2

    def test_idempotent_on_clean_db(self):
        # No emoji tags present: running the migration must be a no-op
        self._run()
        self._run()


class TestMigration037CascadeRebuild:
    """migration_037 rebuilds tables to add CASCADE FKs — rows must survive.

    Run against a scratch DB with the pre-037 table shapes (the migration ran
    historically against that schema; the live schema has since evolved).
    """

    @staticmethod
    def _build_pre_037_db(path) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT, content TEXT);
            CREATE TABLE tasks (id INTEGER PRIMARY KEY);
            CREATE TABLE export_profiles (id INTEGER PRIMARY KEY);
            -- Pre-037 shapes: same column order as the rebuilt tables, no CASCADE
            CREATE TABLE gists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                gist_id TEXT NOT NULL,
                gist_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_public BOOLEAN DEFAULT 0,
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            CREATE TABLE gdocs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                gdoc_id TEXT NOT NULL,
                gdoc_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(document_id, gdoc_id),
                FOREIGN KEY (document_id) REFERENCES documents(id)
            );
            CREATE TABLE executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER,
                doc_title TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                log_file TEXT NOT NULL,
                exit_code INTEGER,
                working_dir TEXT,
                pid INTEGER,
                cascade_run_id INTEGER,
                task_id INTEGER,
                cost_usd REAL DEFAULT 0.0,
                tokens_used INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                FOREIGN KEY (doc_id) REFERENCES documents(id)
            );
            CREATE TABLE export_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                profile_id INTEGER NOT NULL,
                dest_type TEXT NOT NULL,
                dest_url TEXT,
                exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id),
                FOREIGN KEY (profile_id) REFERENCES export_profiles(id)
            );
            CREATE TABLE cascade_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_doc_id INTEGER NOT NULL,
                current_doc_id INTEGER,
                start_stage TEXT NOT NULL,
                stop_stage TEXT NOT NULL DEFAULT 'done',
                current_stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                pr_url TEXT,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (start_doc_id) REFERENCES documents(id)
            );
            """
        )
        conn.commit()
        return conn

    def test_rows_survive_rebuild_and_cascade_applies(self, tmp_path):
        from emdx.database.migrations import migration_037_add_cascade_delete_fks

        conn = self._build_pre_037_db(tmp_path / "pre037.db")
        try:
            conn.execute("INSERT INTO documents (id, title, content) VALUES (1, 'Doc', 'c')")
            conn.execute(
                "INSERT INTO gists (document_id, gist_id, gist_url) "
                "VALUES (1, 'abc123', 'https://gist.github.com/abc123')"
            )
            conn.execute(
                "INSERT INTO executions (doc_id, doc_title, status, started_at, log_file) "
                "VALUES (1, 'Doc', 'completed', '2026-01-01', '/tmp/log')"
            )
            conn.execute(
                "INSERT INTO cascade_runs (start_doc_id, start_stage, current_stage) "
                "VALUES (1, 'plan', 'plan')"
            )
            conn.commit()

            migration_037_add_cascade_delete_fks(conn)

            # All rows preserved through the rebuild
            assert conn.execute("SELECT COUNT(*) FROM gists").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM cascade_runs").fetchone()[0] == 1
            row = conn.execute(
                "SELECT document_id FROM gists WHERE gist_id = 'abc123'"
            ).fetchone()
            assert row == (1,)

            # CASCADE/SET NULL semantics now apply
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM documents WHERE id = 1")
            conn.commit()
            assert conn.execute("SELECT COUNT(*) FROM gists").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM cascade_runs").fetchone()[0] == 0
            # executions row survives with doc_id nulled (ON DELETE SET NULL)
            assert conn.execute("SELECT doc_id FROM executions").fetchone() == (None,)
        finally:
            conn.close()
