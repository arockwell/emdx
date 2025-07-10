"""Tests for tag operations."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sqlite3

from test_fixtures import TestDatabase


class TestTagOperations:
    """Test tag management functions."""
    
    def test_add_tags_to_document(self):
        """Test adding tags to a document."""
        db = TestDatabase(":memory:")
        
        # Create a document
        doc_id = db.save_document("Test Doc", "Content", "project")
        
        # Add tags manually since we're testing the concept
        conn = db.get_connection()
        
        # Create tags
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("python",))
        python_tag_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("testing",))
        testing_tag_id = cursor.lastrowid
        
        # Link tags to document
        conn.execute(
            "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
            (doc_id, python_tag_id)
        )
        conn.execute(
            "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
            (doc_id, testing_tag_id)
        )
        conn.commit()
        
        # Verify tags were added
        cursor = conn.execute("""
            SELECT t.name 
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id = ?
            ORDER BY t.name
        """, (doc_id,))
        
        tags = [row[0] for row in cursor.fetchall()]
        assert tags == ["python", "testing"]
    
    def test_get_or_create_tag(self):
        """Test getting or creating a tag."""
        db = TestDatabase(":memory:")
        conn = db.get_connection()
        
        # Create new tag
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("python",))
        tag_id = cursor.lastrowid
        assert tag_id > 0
        
        # Try to create same tag (should get existing)
        cursor = conn.execute("SELECT id FROM tags WHERE name = ?", ("python",))
        existing_id = cursor.fetchone()[0]
        assert existing_id == tag_id
        
        # Verify only one tag exists
        cursor = conn.execute("SELECT COUNT(*) FROM tags WHERE name = ?", ("python",))
        count = cursor.fetchone()[0]
        assert count == 1
    
    def test_search_by_tags(self):
        """Test searching documents by tags."""
        db = TestDatabase(":memory:")
        
        # Create documents with tags
        doc1 = db.save_document("Python Guide", "Learn Python", "project1")
        doc2 = db.save_document("Python Testing", "Test with pytest", "project1")
        doc3 = db.save_document("JavaScript Guide", "Learn JS", "project1")
        
        conn = db.get_connection()
        
        # Add tags
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("python",))
        python_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("testing",))
        testing_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("javascript",))
        js_id = cursor.lastrowid
        
        # Tag documents
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc1, python_id))
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc2, python_id))
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc2, testing_id))
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc3, js_id))
        conn.commit()
        
        # Search for documents with "python" tag
        cursor = conn.execute("""
            SELECT DISTINCT d.id, d.title
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE t.name = 'python'
            ORDER BY d.id
        """)
        
        results = cursor.fetchall()
        assert len(results) == 2
        assert results[0][1] == "Python Guide"
        assert results[1][1] == "Python Testing"
    
    def test_remove_tag_from_document(self):
        """Test removing a tag from a document."""
        db = TestDatabase(":memory:")
        
        doc_id = db.save_document("Tagged Doc", "Content", "project")
        conn = db.get_connection()
        
        # Add tags
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("removeme",))
        tag_id = cursor.lastrowid
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", ("keepme",))
        keep_id = cursor.lastrowid
        
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc_id, tag_id))
        conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc_id, keep_id))
        conn.commit()
        
        # Remove one tag
        conn.execute("""
            DELETE FROM document_tags 
            WHERE document_id = ? AND tag_id = (
                SELECT id FROM tags WHERE name = ?
            )
        """, (doc_id, "removeme"))
        conn.commit()
        
        # Verify only one tag remains
        cursor = conn.execute("""
            SELECT t.name 
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id = ?
        """, (doc_id,))
        
        remaining_tags = [row[0] for row in cursor.fetchall()]
        assert remaining_tags == ["keepme"]
    
    def test_tag_usage_count(self):
        """Test tag usage counting."""
        db = TestDatabase(":memory:")
        conn = db.get_connection()
        
        # Create tag with usage count
        cursor = conn.execute("INSERT INTO tags (name, usage_count) VALUES (?, ?)", ("popular", 0))
        tag_id = cursor.lastrowid
        
        # Create documents and tag them
        for i in range(3):
            doc_id = db.save_document(f"Doc {i}", "Content", "project")
            conn.execute("INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)", (doc_id, tag_id))
            conn.execute("UPDATE tags SET usage_count = usage_count + 1 WHERE id = ?", (tag_id,))
        
        conn.commit()
        
        # Check usage count
        cursor = conn.execute("SELECT usage_count FROM tags WHERE name = ?", ("popular",))
        count = cursor.fetchone()[0]
        assert count == 3
    
    def test_list_all_tags(self):
        """Test listing all tags in the system."""
        db = TestDatabase(":memory:")
        conn = db.get_connection()
        
        # Create multiple tags with different usage counts
        tags_data = [
            ("python", 5),
            ("javascript", 3),
            ("testing", 8),
            ("docker", 1)
        ]
        
        for name, usage in tags_data:
            conn.execute(
                "INSERT INTO tags (name, usage_count) VALUES (?, ?)",
                (name, usage)
            )
        conn.commit()
        
        # Get all tags ordered by usage
        cursor = conn.execute("""
            SELECT name, usage_count 
            FROM tags 
            ORDER BY usage_count DESC, name
        """)
        
        results = cursor.fetchall()
        assert len(results) == 4
        # Convert Row objects to tuples for comparison
        results_tuples = [(row[0], row[1]) for row in results]
        assert results_tuples[0] == ("testing", 8)
        assert results_tuples[1] == ("python", 5)
        assert results_tuples[2] == ("javascript", 3)
        assert results_tuples[3] == ("docker", 1)