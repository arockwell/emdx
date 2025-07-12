"""Tests for SQLiteDatabase class."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sqlite3

from emdx.sqlite_database import SQLiteDatabase


class TestSQLiteDatabase:
    """Test SQLiteDatabase class methods."""

    def test_init_creates_database_file(self):
        """Test that initialization creates database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            assert db_path.exists()
            assert db.db_path == db_path

    def test_ensure_schema_creates_tables(self):
        """Test that ensure_schema creates necessary tables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

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

    def test_save_document_basic(self):
        """Test saving a basic document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            doc_id = db.save_document(
                title="Test Document", content="Test content", project="test-project"
            )

            assert doc_id > 0

            # Verify document was saved
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

            doc_id = db.save_document(
                title="Tagged Document",
                content="Content with tags",
                project="test",
                tags=["python", "testing", "cli"],
            )

            assert doc_id > 0

            # Check tags were saved
            conn = sqlite3.connect(db_path)
            cursor = conn.execute(
                """
                SELECT t.name 
                FROM tags t
                JOIN document_tags dt ON t.id = dt.tag_id
                WHERE dt.document_id = ?
                ORDER BY t.name
            """,
                (doc_id,),
            )
            tags = [row[0] for row in cursor.fetchall()]
            conn.close()

            assert tags == ["cli", "python", "testing"]

    def test_get_document_not_found(self):
        """Test getting non-existent document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            doc = db.get_document(99999)
            assert doc is None

    def test_update_document(self):
        """Test updating a document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Save initial document
            doc_id = db.save_document("Original", "Original content", "test")

            # Update it
            db.update_document(doc_id, "Updated Title", "Updated content")

            # Verify update
            doc = db.get_document(doc_id)
            assert doc["title"] == "Updated Title"
            assert doc["content"] == "Updated content"

    def test_delete_document(self):
        """Test deleting a document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Save and delete
            doc_id = db.save_document("To Delete", "Content", "test")
            db.delete_document(doc_id)

            # Verify deletion
            doc = db.get_document(doc_id)
            assert doc is None

    def test_search_documents_basic(self):
        """Test basic document search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add test documents
            db.save_document("Python Guide", "Learn Python programming", "docs")
            db.save_document("JavaScript Guide", "Learn JavaScript", "docs")
            db.save_document("Python Testing", "Testing with pytest", "test")

            # Search for Python
            results = db.search_documents("Python")
            assert len(results) == 2

            # Search with project filter
            results = db.search_documents("Python", project="docs")
            assert len(results) == 1
            assert results[0]["title"] == "Python Guide"

    def test_search_documents_empty_query(self):
        """Test search with empty query returns all documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add documents
            db.save_document("Doc 1", "Content 1", "test")
            db.save_document("Doc 2", "Content 2", "test")

            # Empty search
            results = db.search_documents("")
            assert len(results) == 2

    def test_list_documents(self):
        """Test listing documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add documents
            for i in range(5):
                db.save_document(f"Doc {i}", f"Content {i}", "test")

            # List all
            docs = db.list_documents()
            assert len(docs) == 5

            # List with limit
            docs = db.list_documents(limit=3)
            assert len(docs) == 3

    def test_get_recently_accessed(self):
        """Test getting recently accessed documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add documents
            doc_ids = []
            for i in range(3):
                doc_id = db.save_document(f"Doc {i}", f"Content {i}", "test")
                doc_ids.append(doc_id)

            # Access in specific order
            for doc_id in reversed(doc_ids):
                db.get_document(doc_id)  # This should update last_accessed

            # Get recently accessed
            recent = db.get_recently_accessed(limit=2)
            assert len(recent) <= 2

    def test_get_stats(self):
        """Test getting database statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add test data
            db.save_document("Doc 1", "Content 1", "project-a")
            db.save_document("Doc 2", "Content 2", "project-a")
            db.save_document("Doc 3", "Content 3", "project-b")

            stats = db.get_stats()

            assert stats["total_documents"] == 3
            assert stats["total_projects"] == 2
            assert "total_size" in stats
            assert "most_viewed" in stats
            assert "project_stats" in stats

    def test_get_projects(self):
        """Test getting project list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add documents with projects
            db.save_document("Doc 1", "Content", "project-a")
            db.save_document("Doc 2", "Content", "project-a")
            db.save_document("Doc 3", "Content", "project-b")
            db.save_document("Doc 4", "Content", None)

            projects = db.get_projects()

            assert len(projects) == 3
            project_names = [p["project"] for p in projects]
            assert "project-a" in project_names
            assert "project-b" in project_names
            assert None in project_names

    def test_export_to_json(self):
        """Test exporting database to JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)

            # Add test documents
            db.save_document("Export Test", "Content to export", "test")

            export_path = Path(tmpdir) / "export.json"
            db.export_to_json(export_path)

            assert export_path.exists()

            # Verify JSON content
            import json

            with open(export_path) as f:
                data = json.load(f)

            assert "documents" in data
            assert len(data["documents"]) == 1
            assert data["documents"][0]["title"] == "Export Test"

    def test_import_from_json(self):
        """Test importing from JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test JSON
            import json

            json_path = Path(tmpdir) / "import.json"
            test_data = {
                "documents": [
                    {
                        "title": "Imported Doc",
                        "content": "Imported content",
                        "project": "imported",
                        "tags": ["tag1", "tag2"],
                    }
                ]
            }
            with open(json_path, "w") as f:
                json.dump(test_data, f)

            # Import into database
            db_path = Path(tmpdir) / "test.db"
            db = SQLiteDatabase(db_path)
            result = db.import_from_json(json_path)

            assert result["imported"] == 1
            assert result["failed"] == 0

            # Verify import
            docs = db.list_documents()
            assert len(docs) == 1
            assert docs[0]["title"] == "Imported Doc"
