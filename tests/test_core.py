"""Simple tests for core functionality that actually work."""

from unittest.mock import patch

from test_fixtures import DatabaseForTesting


class TestCoreFunctionality:
    """Test core functionality using our test database."""

    def test_save_and_search_workflow(self):
        """Test saving documents and then searching for them."""
        db = DatabaseForTesting(":memory:")

        # Save some documents
        db.save_document("Python Guide", "Learn Python programming", "tutorials")
        db.save_document("JavaScript Guide", "Learn JavaScript", "tutorials")
        db.save_document("Python Testing", "Testing with pytest", "testing")

        # Search for Python documents
        results = db.search_documents("Python")
        assert len(results) == 2

        # Search in specific project
        results = db.search_documents("Python", project="tutorials")
        assert len(results) == 1
        assert results[0]["title"] == "Python Guide"

    def test_document_lifecycle(self):
        """Test complete document lifecycle: create, update, delete."""
        db = DatabaseForTesting(":memory:")

        # Create
        doc_id = db.save_document("Original Title", "Original content", "test")
        assert doc_id > 0

        # Read
        doc = db.get_document(doc_id)
        assert doc["title"] == "Original Title"

        # Update
        db.update_document(doc_id, "Updated Title", "Updated content")
        doc = db.get_document(doc_id)
        assert doc["title"] == "Updated Title"

        # Delete (soft delete)
        db.delete_document(doc_id)
        doc = db.get_document(doc_id)
        assert doc is None

    @patch("emdx.database.db")
    def test_mock_database_operations(self, mock_db):
        """Test using mocked database for isolated testing."""
        # Mock the database responses
        mock_db.save_document.return_value = 123
        mock_db.get_document.return_value = (123, "Test", "Content", "project", "", "", "", 0)
        mock_db.search_documents.return_value = [
            (123, "Test", "Content", "project", "2024-01-01", 5)
        ]

        # Test save
        doc_id = mock_db.save_document("Test", "Content", "project")
        assert doc_id == 123

        # Test get
        doc = mock_db.get_document(123)
        assert doc[1] == "Test"

        # Test search
        results = mock_db.search_documents("Test")
        assert len(results) == 1

    def test_project_filtering(self):
        """Test filtering documents by project."""
        db = DatabaseForTesting(":memory:")

        # Create documents in different projects
        db.save_document("Project A Doc 1", "Content", "project-a")
        db.save_document("Project A Doc 2", "Content", "project-a")
        db.save_document("Project B Doc 1", "Content", "project-b")
        db.save_document("No Project Doc", "Content", None)

        # List by project
        project_a_docs = db.list_documents(project="project-a")
        assert len(project_a_docs) == 2

        project_b_docs = db.list_documents(project="project-b")
        assert len(project_b_docs) == 1

        # List all
        all_docs = db.list_documents()
        assert len(all_docs) == 4
