"""Tests for core database operations."""

import pytest
from datetime import datetime
from pathlib import Path

from emdx.database import SQLiteDatabase


class TestDatabaseOperations:
    """Test core database functionality."""
    
    def test_database_initialization(self, temp_db):
        """Test that database tables are created correctly."""
        with temp_db.get_connection() as conn:
            cursor = conn.cursor()
            
            # First check what tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables found: {tables}")
            
            # Check documents table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='documents'
            """)
            assert cursor.fetchone() is not None
            
            # Check FTS table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='documents_fts'
            """)
            assert cursor.fetchone() is not None
            
            # Check tags table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='tags'
            """)
            assert cursor.fetchone() is not None
    
    def test_save_document(self, temp_db):
        """Test saving a document."""
        doc_id = temp_db.save_document(
            title="Test Document",
            content="This is test content with some keywords.",
            project="test-project"
        )
        
        assert doc_id > 0
        
        # Verify document was saved
        with temp_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, content, project FROM documents WHERE id = ?",
                (doc_id,)
            )
            result = cursor.fetchone()
            
            assert result[0] == "Test Document"
            assert result[1] == "This is test content with some keywords."
            assert result[2] == "test-project"
    
    def test_get_document(self, temp_db):
        """Test retrieving a document by ID."""
        # Save a document first
        doc_id = temp_db.save_document(
            title="Retrieve Test",
            content="Content to retrieve",
            project="test"
        )
        
        # Retrieve it
        doc = temp_db.get_document(doc_id)
        
        assert doc is not None
        assert doc[0] == doc_id
        assert doc[1] == "Retrieve Test"
        assert doc[2] == "Content to retrieve"
        assert doc[3] == "test"
    
    def test_get_nonexistent_document(self, temp_db):
        """Test retrieving a non-existent document."""
        doc = temp_db.get_document(99999)
        assert doc is None
    
    def test_search_documents(self, temp_db, sample_documents):
        """Test full-text search functionality."""
        # Search for "Python"
        results = temp_db.search_documents("Python")
        assert len(results) == 1
        assert "Python Testing Guide" in results[0][1]
        
        # Search for "best practices"
        results = temp_db.search_documents("best practices")
        assert len(results) == 1
        assert "Docker Best Practices" in results[0][1]
        
        # Search for term in multiple documents
        results = temp_db.search_documents("guide")
        assert len(results) == 1  # Only Python Testing Guide
    
    def test_search_with_project_filter(self, temp_db, sample_documents):
        """Test searching within a specific project."""
        # Search in test-project
        results = temp_db.search_documents("", project="test-project")
        assert len(results) == 2  # Two documents in test-project
        
        # Search with query and project filter
        results = temp_db.search_documents("Docker", project="test-project")
        assert len(results) == 1
        assert "Docker Best Practices" in results[0][1]
        
        # Search in different project
        results = temp_db.search_documents("Git", project="another-project")
        assert len(results) == 1
        assert "Git Workflow" in results[0][1]
    
    def test_list_documents(self, temp_db, sample_documents):
        """Test listing all documents."""
        docs = temp_db.list_documents()
        assert len(docs) == 3
        
        # Documents should be ordered by updated_at DESC (newest first)
        titles = [doc[1] for doc in docs]
        assert "Git Workflow" in titles
        assert "Docker Best Practices" in titles
        assert "Python Testing Guide" in titles
    
    def test_list_documents_by_project(self, temp_db, sample_documents):
        """Test listing documents filtered by project."""
        # List test-project documents
        docs = temp_db.list_documents(project="test-project")
        assert len(docs) == 2
        
        # List another-project documents
        docs = temp_db.list_documents(project="another-project")
        assert len(docs) == 1
        assert docs[0][1] == "Git Workflow"
    
    def test_update_document(self, temp_db):
        """Test updating an existing document."""
        # Create document
        doc_id = temp_db.save_document(
            title="Original Title",
            content="Original content",
            project="test"
        )
        
        # Update it
        temp_db.update_document(
            doc_id,
            title="Updated Title",
            content="Updated content"
        )
        
        # Verify update
        doc = temp_db.get_document(doc_id)
        assert doc[1] == "Updated Title"
        assert doc[2] == "Updated content"
    
    def test_delete_document(self, temp_db):
        """Test deleting a document."""
        # Create document
        doc_id = temp_db.save_document(
            title="To Delete",
            content="Will be deleted",
            project="test"
        )
        
        # Verify it exists
        assert temp_db.get_document(doc_id) is not None
        
        # Delete it
        temp_db.delete_document(doc_id)
        
        # Verify it's gone
        assert temp_db.get_document(doc_id) is None
    
    def test_fts_search_special_characters(self, temp_db):
        """Test FTS search with special characters."""
        # Save document with special characters
        doc_id = temp_db.save_document(
            title="C++ Programming",
            content="Learn about C++ and C# programming languages.",
            project="test"
        )
        
        # Search should handle special characters gracefully
        results = temp_db.search_documents("C++")
        assert len(results) == 1
        
        # Search for C# as well
        results = temp_db.search_documents("C#")
        assert len(results) == 1
    
    def test_case_insensitive_search(self, temp_db):
        """Test that search is case-insensitive."""
        doc_id = temp_db.save_document(
            title="Python Guide",
            content="PYTHON is great for TESTING",
            project="test"
        )
        
        # All these should find the document
        for query in ["python", "PYTHON", "Python", "PyThOn"]:
            results = temp_db.search_documents(query)
            assert len(results) == 1
            assert results[0][0] == doc_id
    
    def test_empty_search_returns_all(self, temp_db, sample_documents):
        """Test that empty search query returns all documents."""
        results = temp_db.search_documents("")
        assert len(results) == 3  # All sample documents
    
    def test_database_file_persistence(self, temp_db_file):
        """Test that database persists to file correctly."""
        # Save document
        doc_id = temp_db_file.save_document(
            title="Persistent Doc",
            content="This should persist",
            project="test"
        )
        
        db_path = temp_db_file.db_path
        
        # Create new connection to same file
        db2 = SQLiteDatabase(db_path)
        
        # Should be able to retrieve document
        doc = db2.get_document(doc_id)
        assert doc is not None
        assert doc[1] == "Persistent Doc"