"""Extended database tests that work."""

import pytest
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path

from test_fixtures import TestDatabase


class TestDatabaseExtended:
    """Extended database functionality tests."""
    
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
    
