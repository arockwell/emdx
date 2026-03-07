"""Tests for SQLiteDatabase wrapper and core database operations.

These tests use the conftest isolate_test_database fixture (autouse)
which redirects the global db_connection to a temporary test database.
"""

from emdx.database import SQLiteDatabase, db, get_document, save_document, search_documents


class TestSQLiteDatabase:
    """Test SQLiteDatabase wrapper delegates to global functions correctly."""

    def test_global_instance_exists(self):
        """The module-level db instance should exist."""
        assert isinstance(db, SQLiteDatabase)

    def test_db_path_is_set(self):
        """db_path should return a valid path."""
        assert db.db_path is not None
        assert db.db_path.suffix == ".db"

    def test_save_and_get_document(self):
        """Test saving and retrieving a document via the wrapper."""
        doc_id = db.save_document(
            title="Test Document",
            content="Test content",
            project="test-project",
        )
        assert doc_id > 0

        doc = db.get_document(doc_id)
        assert doc is not None
        assert doc.title == "Test Document"
        assert doc.content == "Test content"
        assert doc.project == "test-project"

    def test_save_document_with_tags(self):
        """Test saving document with tags."""
        doc_id = db.save_document(
            title="Tagged Document",
            content="Content with tags",
            project="test",
            tags=["python", "testing", "cli"],
        )
        assert doc_id > 0

        doc = db.get_document(doc_id)
        assert doc is not None
        assert doc.title == "Tagged Document"

    def test_search_documents_basic(self):
        """Test basic document search."""
        db.save_document("Python Guide", "Learn Python programming", "docs")
        db.save_document("JavaScript Tutorial", "Learn JS basics", "docs")

        results = db.search_documents("Python")
        assert len(results) >= 1
        assert any("Python" in hit.title for hit in results)

    def test_list_documents(self):
        """Test listing documents."""
        db.save_document("Doc 1", "Content 1", "project-a")
        db.save_document("Doc 2", "Content 2", "project-a")
        db.save_document("Doc 3", "Content 3", "project-b")

        docs = db.list_documents()
        assert len(docs) >= 3

        docs = db.list_documents(project="project-a")
        assert len(docs) >= 2

        docs = db.list_documents(limit=2)
        assert len(docs) == 2

    def test_wrapper_delegates_to_global_functions(self):
        """Verify the wrapper produces the same results as direct function calls."""
        doc_id = save_document("Direct Save", "Direct content", "test")
        assert doc_id > 0

        # Both paths should return the same document
        via_wrapper = db.get_document(doc_id)
        via_function = get_document(doc_id)
        assert via_wrapper is not None
        assert via_function is not None
        assert via_wrapper.id == via_function.id
        assert via_wrapper.title == via_function.title

    def test_search_via_wrapper_and_function(self):
        """Search results should be consistent between wrapper and direct calls."""
        db.save_document("Wrapper Search Test", "unique_search_token_xyz", "test")

        via_wrapper = db.search_documents("unique_search_token_xyz")
        via_function = search_documents("unique_search_token_xyz")
        assert len(via_wrapper) == len(via_function)
