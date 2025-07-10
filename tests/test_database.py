"""Database tests for EMDX."""

import pytest
from test_fixtures import TestDatabase


class TestDatabaseOperations:
    """Test database operations."""
    
    def test_save_and_retrieve_document(self):
        """Test saving and retrieving a document."""
        db = TestDatabase(":memory:")
        
        doc_id = db.save_document(
            title="Test Document",
            content="This is test content",
            project="test-project"
        )
        
        assert doc_id > 0
        
        doc = db.get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Test Document"
        assert doc["content"] == "This is test content"
        assert doc["project"] == "test-project"
    
    def test_search_documents(self):
        """Test searching documents."""
        db = TestDatabase(":memory:")
        
        db.save_document("Python Guide", "Learn Python programming", "project1")
        db.save_document("JavaScript Guide", "Learn JavaScript", "project1") 
        db.save_document("Python Testing", "Testing with pytest", "project2")
        
        results = db.search_documents("Python")
        assert len(results) == 2
        
        results = db.search_documents("Python", project="project1")
        assert len(results) == 1
        assert results[0]["title"] == "Python Guide"
    
    def test_update_document(self):
        """Test updating a document."""
        db = TestDatabase(":memory:")
        
        doc_id = db.save_document("Original", "Original content", "test")
        
        db.update_document(doc_id, "Updated", "Updated content")
        
        doc = db.get_document(doc_id)
        assert doc["title"] == "Updated"
        assert doc["content"] == "Updated content"
    
    def test_delete_document(self):
        """Test deleting a document."""
        db = TestDatabase(":memory:")
        
        doc_id = db.save_document("To Delete", "Will be deleted", "test")
        
        db.delete_document(doc_id)
        
        doc = db.get_document(doc_id)
        assert doc is None
    
    def test_list_documents(self):
        """Test listing documents."""
        db = TestDatabase(":memory:")
        
        db.save_document("Doc 1", "Content 1", "project1")
        db.save_document("Doc 2", "Content 2", "project1")
        db.save_document("Doc 3", "Content 3", "project2")
        
        docs = db.list_documents()
        assert len(docs) == 3
        
        docs = db.list_documents(project="project1")
        assert len(docs) == 2
