"""Test fixture utilities for database testing."""

import sqlite3
from pathlib import Path
from typing import Union

from emdx.sqlite_database import SQLiteDatabase


def create_test_schema(db: SQLiteDatabase):
    """Create the database schema for testing without migrations."""
    with db.get_connection() as conn:
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Create documents table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                project TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                deleted_at TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Create FTS5 virtual table
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title,
                content,
                project,
                content=documents,
                content_rowid=id
            )
        """)
        
        # Create triggers for FTS
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, content, project)
                VALUES (new.id, new.title, new.content, new.project);
            END
        """)
        
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        """)
        
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                UPDATE documents_fts 
                SET title = new.title, content = new.content, project = new.project
                WHERE rowid = new.id;
            END
        """)
        
        # Create tags table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create document_tags junction table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS document_tags (
                document_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, tag_id),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)
        
        # Create indices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_usage ON tags(usage_count)")
        
        conn.commit()


def create_test_database(db_path: Union[str, Path] = ":memory:") -> SQLiteDatabase:
    """Create a test database with schema."""
    if isinstance(db_path, str) and db_path == ":memory:":
        db = SQLiteDatabase(Path(":memory:"))
    else:
        db = SQLiteDatabase(Path(db_path))
    
    create_test_schema(db)
    return db