"""Simple tests that don't require database setup."""

import pytest
from pathlib import Path
import sqlite3
import tempfile

from emdx.sqlite_database import SQLiteDatabase


def test_basic_database_connection():
    """Test that we can create a basic database connection."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db = SQLiteDatabase(Path(f.name))
        
        # Manually create schema without migrations
        with db.get_connection() as conn:
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO test (id) VALUES (1)")
            conn.commit()
            
            cursor = conn.execute("SELECT * FROM test")
            result = cursor.fetchone()
            assert result[0] == 1


def test_in_memory_database():
    """Test in-memory database creation."""
    # Create an in-memory database with manual schema
    conn = sqlite3.connect(":memory:")
    
    # Create a simple table
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO test (id, name) VALUES (1, 'test')")
    
    cursor = conn.execute("SELECT * FROM test")
    result = cursor.fetchone()
    assert result[0] == 1
    assert result[1] == 'test'
    
    conn.close()


def test_manual_schema_creation():
    """Test creating schema manually without migrations."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        db = SQLiteDatabase(Path(f.name))
        
        with db.get_connection() as conn:
            # Create documents table manually
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert a document
            cursor = conn.execute("""
                INSERT INTO documents (title, content, project)
                VALUES (?, ?, ?)
            """, ("Test", "Content", "Project"))
            
            doc_id = cursor.lastrowid
            assert doc_id > 0
            
            # Retrieve it
            cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
            result = cursor.fetchone()
            assert result is not None