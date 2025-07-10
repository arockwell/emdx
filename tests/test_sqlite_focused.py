"""Focused tests for SQLiteDatabase that actually work."""

import pytest
from emdx.sqlite_database import SQLiteDatabase


def test_basic_document_lifecycle(sqlite_db):
    """Test the basic document lifecycle."""
    # Create
    doc_id = sqlite_db.save_document("Test Doc", "Test content", "test-project")
    assert doc_id > 0
    
    # Read
    doc = sqlite_db.get_document(str(doc_id))
    assert doc is not None
    assert doc['title'] == "Test Doc"
    assert doc['content'] == "Test content"
    
    # Update
    success = sqlite_db.update_document(doc_id, "Updated Doc", "Updated content")
    assert success
    
    doc = sqlite_db.get_document(str(doc_id))
    assert doc['title'] == "Updated Doc"
    
    # Delete (soft)
    success = sqlite_db.delete_document(str(doc_id))
    assert success
    
    # Should not find soft-deleted document
    doc = sqlite_db.get_document(str(doc_id))
    assert doc is None


def test_search_functionality(sqlite_db):
    """Test search functionality."""
    # Add test documents
    sqlite_db.save_document("Python Guide", "Learn Python programming", "docs")
    sqlite_db.save_document("JavaScript Guide", "Learn JavaScript", "docs")
    sqlite_db.save_document("Python Testing", "Testing with pytest", "test")
    
    # Search for Python
    results = sqlite_db.search_documents("Python")
    assert len(results) == 2
    
    # Search with project filter
    results = sqlite_db.search_documents("Python", project="docs")
    assert len(results) == 1


def test_list_and_stats(sqlite_db):
    """Test listing and statistics."""
    # Add some documents
    for i in range(3):
        sqlite_db.save_document(f"Doc {i}", f"Content {i}", "test")
    
    # List documents
    docs = sqlite_db.list_documents()
    assert len(docs) == 3
    
    # Get stats
    stats = sqlite_db.get_stats()
    assert stats['total_documents'] == 3
    assert stats['total_projects'] == 1