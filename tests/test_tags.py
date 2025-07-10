"""Tests for tag management functionality."""

import pytest
from unittest.mock import Mock, patch
import sqlite3

from emdx.tags import (
    get_or_create_tag,
    add_tags_to_document,
    remove_tags_from_document,
    get_document_tags,
    list_all_tags,
    get_tag_suggestions,
    search_by_tags
)


class TestTagOperations:
    """Test tag operations with database."""
    
    def test_get_or_create_tag_new(self, temp_db):
        """Test creating a new tag."""
        with temp_db.get_connection() as conn:
            tag_id = get_or_create_tag(conn, "Python")
            assert tag_id > 0
            
            # Verify tag was created
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
            result = cursor.fetchone()
            assert result[0] == "python"  # Should be lowercase
    
    def test_get_or_create_tag_existing(self, temp_db):
        """Test getting an existing tag."""
        with temp_db.get_connection() as conn:
            # Create tag first
            tag_id1 = get_or_create_tag(conn, "Python")
            
            # Get same tag again (different case)
            tag_id2 = get_or_create_tag(conn, "PYTHON")
            
            assert tag_id1 == tag_id2  # Should return same ID
    
    def test_add_tags_to_document(self, temp_db):
        """Test adding multiple tags to a document."""
        # First create a document
        doc_id = temp_db.save_document(
            title="Test Document",
            content="Test content",
            project="test"
        )
        
        # Mock the db module to use our temp_db
        with patch('emdx.tags.db', temp_db):
            added = add_tags_to_document(doc_id, ["Python", "Testing", "pytest"])
            assert len(added) == 3
            assert "python" in added
            assert "testing" in added
            assert "pytest" in added
    
    def test_add_duplicate_tags(self, temp_db):
        """Test adding duplicate tags to a document."""
        doc_id = temp_db.save_document(
            title="Test Document",
            content="Test content",
            project="test"
        )
        
        with patch('emdx.tags.db', temp_db):
            # Add tags first time
            added1 = add_tags_to_document(doc_id, ["Python", "Testing"])
            assert len(added1) == 2
            
            # Try to add same tags again
            added2 = add_tags_to_document(doc_id, ["Python", "Testing", "New"])
            assert len(added2) == 1  # Only "New" should be added
            assert "new" in added2
    
    def test_get_document_tags(self, temp_db, sample_documents):
        """Test retrieving tags for a document."""
        with patch('emdx.tags.db', temp_db):
            # Get tags for first document
            tags = get_document_tags(sample_documents[0])
            
            assert len(tags) == 3
            assert "python" in tags
            assert "testing" in tags
            assert "pytest" in tags
    
    def test_list_all_tags(self, temp_db, sample_documents):
        """Test getting all tags in the system."""
        with patch('emdx.tags.db', temp_db):
            all_tags = list_all_tags()
            tag_names = [tag['name'] for tag in all_tags]
            
            # Should have all unique tags from sample documents
            expected_tags = {"python", "testing", "pytest", "docker", 
                           "devops", "git", "version-control"}
            assert set(tag_names) == expected_tags
    
    def test_remove_tags_from_document(self, temp_db, sample_documents):
        """Test removing tags from a document."""
        with patch('emdx.tags.db', temp_db):
            doc_id = sample_documents[0]  # First document
            
            # Remove one tag
            removed = remove_tags_from_document(doc_id, ["python"])
            assert len(removed) == 1
            assert "python" in removed
            
            # Verify tag was removed
            remaining_tags = get_document_tags(doc_id)
            assert "python" not in remaining_tags
            assert "testing" in remaining_tags  # Other tags remain
    
    def test_tag_suggestions(self, temp_db, sample_documents):
        """Test getting tag suggestions based on partial input."""
        with patch('emdx.tags.db', temp_db):
            # Test with partial match
            suggestions = get_tag_suggestions("py")
            
            assert "python" in suggestions
            assert "pytest" in suggestions
            
            # Test with exact match
            suggestions = get_tag_suggestions("docker")
            assert "docker" in suggestions
    
    def test_search_by_tags(self, temp_db, sample_documents):
        """Test searching documents by tags."""
        with patch('emdx.tags.db', temp_db):
            # Search by single tag
            results = search_by_tags(["python"])
            assert len(results) == 1
            assert results[0]['title'] == "Python Testing Guide"
            
            # Search by multiple tags (OR operation by default)
            results = search_by_tags(["python", "docker"], mode='any')
            assert len(results) == 2
            
            # Search by non-existent tag
            results = search_by_tags(["nonexistent"])
            assert len(results) == 0
    
    def test_empty_tag_handling(self, temp_db):
        """Test handling of empty or whitespace tags."""
        doc_id = temp_db.save_document(
            title="Test Document",
            content="Test content",
            project="test"
        )
        
        with patch('emdx.tags.db', temp_db):
            # Try to add empty tags
            added = add_tags_to_document(doc_id, ["", "  ", "valid-tag"])
            assert len(added) == 1
            assert "valid-tag" in added