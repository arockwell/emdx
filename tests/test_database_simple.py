"""Simple database tests that actually work."""

import pytest
from test_fixtures_simple import TestDatabase


class TestSimpleDatabase:
    """Test basic database operations with our simple test database."""
    
    def test_save_and_retrieve_document(self):
        """Test saving and retrieving a document."""
        db = TestDatabase(":memory:")
        
        # Save a document
        doc_id = db.save_document(
            title="Test Document",
            content="This is test content",
            project="test-project"
        )
        
        assert doc_id > 0
        
        # Retrieve it
        doc = db.get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Test Document"
        assert doc["content"] == "This is test content"
        assert doc["project"] == "test-project"
    
    def test_search_documents(self):
        """Test searching documents."""
        db = TestDatabase(":memory:")
        
        # Add test documents
        db.save_document("Python Guide", "Learn Python programming", "project1")
        db.save_document("JavaScript Guide", "Learn JavaScript", "project1") 
        db.save_document("Python Testing", "Testing with pytest", "project2")
        
        # Search for Python
        results = db.search_documents("Python")
        assert len(results) == 2
        
        # Search in specific project
        results = db.search_documents("Python", project="project1")
        assert len(results) == 1
        assert results[0]["title"] == "Python Guide"
    
    def test_update_document(self):
        """Test updating a document."""
        db = TestDatabase(":memory:")
        
        # Create a document
        doc_id = db.save_document("Original", "Original content", "test")
        
        # Update it
        db.update_document(doc_id, "Updated", "Updated content")
        
        # Verify update
        doc = db.get_document(doc_id)
        assert doc["title"] == "Updated"
        assert doc["content"] == "Updated content"
    
    def test_delete_document(self):
        """Test deleting a document."""
        db = TestDatabase(":memory:")
        
        # Create a document
        doc_id = db.save_document("To Delete", "Will be deleted", "test")
        
        # Delete it
        db.delete_document(doc_id)
        
        # Should not be found
        doc = db.get_document(doc_id)
        assert doc is None
    
    def test_list_documents(self):
        """Test listing documents."""
        db = TestDatabase(":memory:")
        
        # Add documents
        db.save_document("Doc 1", "Content 1", "project1")
        db.save_document("Doc 2", "Content 2", "project1")
        db.save_document("Doc 3", "Content 3", "project2")
        
        # List all
        docs = db.list_documents()
        assert len(docs) == 3
        
        # List by project
        docs = db.list_documents(project="project1")
        assert len(docs) == 2