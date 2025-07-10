"""Database tests for EMDX."""

import pytest
import tempfile
from pathlib import Path
import sqlite3
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
    
    def test_database_with_file_persistence(self):
        """Test database with file persistence."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
            
        try:
            # Create and save
            db1 = TestDatabase(str(db_path))
            doc_id = db1.save_document("Persistent Doc", "Content", "test")
            
            # Open again and verify
            db2 = TestDatabase(str(db_path))
            doc = db2.get_document(doc_id)
            assert doc['title'] == "Persistent Doc"
            
        finally:
            db_path.unlink(missing_ok=True)
    
    def test_search_case_insensitive(self):
        """Test case-insensitive search."""
        db = TestDatabase(":memory:")
        
        db.save_document("Python Guide", "Learn PYTHON programming", "test")
        db.save_document("python basics", "Python for beginners", "test")
        
        # Search with different cases
        for query in ["python", "PYTHON", "Python", "PyThOn"]:
            results = db.search_documents(query)
            assert len(results) == 2
    
    def test_empty_database_operations(self):
        """Test operations on empty database."""
        db = TestDatabase(":memory:")
        
        # List empty database
        docs = db.list_documents()
        assert len(docs) == 0
        
        # Search empty database
        results = db.search_documents("anything")
        assert len(results) == 0
        
        # Get non-existent document
        doc = db.get_document(1)
        assert doc is None
    
    def test_database_operations_edge_cases(self):
        """Test edge cases in database operations."""
        db = TestDatabase(":memory:")
        
        # Test empty search
        results = db.search_documents("")
        assert results == db.list_documents()
        
        # Test search with no results
        results = db.search_documents("nonexistent123456")
        assert len(results) == 0
        
        # Test get non-existent document
        doc = db.get_document(99999)
        assert doc is None
    
    def test_project_name_handling(self):
        """Test different project name scenarios."""
        db = TestDatabase(":memory:")
        
        # Save with no project
        doc_id = db.save_document("No Project", "Content", None)
        doc = db.get_document(doc_id)
        assert doc['project'] is None
        
        # Save with empty string project
        doc_id = db.save_document("Empty Project", "Content", "")
        doc = db.get_document(doc_id)
        assert doc['project'] == ""
        
        # Save with spaces in project name
        doc_id = db.save_document("Spaced Project", "Content", "my project name")
        doc = db.get_document(doc_id)
        assert doc['project'] == "my project name"
    
    def test_content_edge_cases(self):
        """Test edge cases with content."""
        db = TestDatabase(":memory:")
        
        # Very long content
        long_content = "x" * 10000
        doc_id = db.save_document("Long Doc", long_content, "test")
        doc = db.get_document(doc_id)
        assert len(doc['content']) == 10000
        
        # Content with special characters
        special_content = "Content with 'quotes' and \"double quotes\" and \n newlines"
        doc_id = db.save_document("Special Doc", special_content, "test")
        doc = db.get_document(doc_id)
        assert doc['content'] == special_content
        
        # Empty content
        doc_id = db.save_document("Empty Content", "", "test")
        doc = db.get_document(doc_id)
        assert doc['content'] == ""
    
    def test_multiple_document_operations(self):
        """Test operations on multiple documents."""
        db = TestDatabase(":memory:")
        
        # Create 10 documents
        doc_ids = []
        for i in range(10):
            doc_id = db.save_document(f"Doc {i}", f"Content {i}", f"project{i % 3}")
            doc_ids.append(doc_id)
        
        # List all should return 10
        all_docs = db.list_documents()
        assert len(all_docs) == 10
        
        # Delete half
        for i in range(5):
            db.delete_document(doc_ids[i])
        
        # Should have 5 left
        remaining = db.list_documents()
        assert len(remaining) == 5
        
        # Update all remaining
        for doc in remaining:
            db.update_document(doc['id'], f"Updated {doc['title']}", "Updated content")
        
        # Verify updates
        for doc in db.list_documents():
            assert doc['title'].startswith("Updated")
    
    def test_search_with_special_characters(self):
        """Test searching with special characters."""
        db = TestDatabase(":memory:")
        
        # Save documents with special characters
        db.save_document("C++ Programming", "Learn C++ basics", "test")
        db.save_document("C# Development", "C# for beginners", "test")
        db.save_document("Regular Text", "Normal content", "test")
        
        # Search for C++ (special characters)
        results = db.search_documents("C++")
        assert len(results) == 1
        assert results[0]['title'] == "C++ Programming"
        
        # Search for partial match
        results = db.search_documents("C#")
        assert len(results) == 1
        assert results[0]['title'] == "C# Development"
    
    def test_concurrent_access_simulation(self):
        """Test simulated concurrent access patterns."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
            
        try:
            # First connection saves a document
            db1 = TestDatabase(db_path)
            doc_id = db1.save_document("Concurrent Test", "Content", "test")
            
            # Second connection reads it
            db2 = TestDatabase(db_path)
            doc = db2.get_document(doc_id)
            assert doc['title'] == "Concurrent Test"
            
            # First connection updates
            db1.update_document(doc_id, "Updated Concurrent", "New content")
            
            # Second connection sees update
            doc = db2.get_document(doc_id)
            assert doc['title'] == "Updated Concurrent"
            
        finally:
            Path(db_path).unlink(missing_ok=True)
