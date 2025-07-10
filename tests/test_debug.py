"""Debug test fixture issues."""

import pytest
from test_fixtures import create_test_database


def test_fixture_creates_tables():
    """Test that our fixture creates tables correctly."""
    db = create_test_database(":memory:")
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables created: {tables}")
        
        assert "documents" in tables
        assert "tags" in tables
        assert "document_tags" in tables
        
        # Test we can insert
        cursor.execute("""
            INSERT INTO documents (title, content, project)
            VALUES ('Test', 'Content', 'Project')
        """)
        doc_id = cursor.lastrowid
        assert doc_id > 0