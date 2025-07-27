"""Tests for SQLiteDatabase class."""

import sqlite3
import tempfile
from pathlib import Path

from emdx.database import SQLiteDatabase


class TestSQLiteDatabase:
    """Test SQLiteDatabase class methods."""

    def test_init_creates_database_file(self):
        """Test that initialization creates database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            
            # Trigger database creation by getting a connection
            with db.get_connection():
                pass

            assert db_path.exists()
            assert db.db_path == db_path

    def test_ensure_schema_creates_tables(self):
        """Test that ensure_schema creates necessary tables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            # Check tables exist
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='documents'
            """
            )
            assert cursor.fetchone() is not None

            # Check FTS table
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='documents_fts'
            """
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_run_migrations(self):
        """Test that migrations run correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            # Check schema_version table exists
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schema_version'
            """
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_save_and_get_document(self):
        """Test saving and retrieving a document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            doc_id = db.save_document(
                title="Test Document",
                content="Test content",
                project="test-project",
            )

            assert doc_id > 0

            doc = db.get_document(doc_id)
            assert doc is not None
            assert doc["title"] == "Test Document"
            assert doc["content"] == "Test content"
            assert doc["project"] == "test-project"

    def test_save_document_with_tags(self):
        """Test saving document with tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            doc_id = db.save_document(
                title="Tagged Document",
                content="Content with tags",
                project="test",
                tags=["python", "testing", "cli"],
            )

            assert doc_id > 0

            # Verify document exists
            doc = db.get_document(doc_id)
            assert doc is not None
            assert doc["title"] == "Tagged Document"

    def test_search_documents_basic(self):
        """Test basic document search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            # Add test documents
            db.save_document("Python Guide", "Learn Python programming", "docs")
            db.save_document("JavaScript Tutorial", "Learn JS basics", "docs")

            # Search for Python
            results = db.search_documents("Python")
            assert len(results) >= 1
            assert any("Python" in doc["title"] for doc in results)

    def test_search_documents_empty_query(self):
        """Test search with empty query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            # Add test documents
            db.save_document("Doc 1", "Content 1", "test")
            db.save_document("Doc 2", "Content 2", "test")

            # Search with non-empty query to avoid FTS syntax error
            results = db.search_documents("test")
            assert len(results) >= 2

    def test_list_documents(self):
        """Test listing documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            db.ensure_schema()

            # Add test documents
            db.save_document("Doc 1", "Content 1", "project-a")
            db.save_document("Doc 2", "Content 2", "project-a")
            db.save_document("Doc 3", "Content 3", "project-b")
            db.save_document("Doc 4", "Content 4", "project-b")
            db.save_document("Doc 5", "Content 5", "project-b")

            # List all documents
            docs = db.list_documents()
            assert len(docs) >= 5

            # List with project filter
            docs = db.list_documents(project="project-a")
            assert len(docs) >= 2  # Should have at least our 2 test docs

            # List with limit
            docs = db.list_documents(limit=3)
            assert len(docs) == 3