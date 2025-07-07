"""
SQLite database connection and operations for emdx
"""

import sqlite3
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json

class SQLiteDatabase:
    """SQLite database connection manager for emdx"""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            # Default location in user config directory
            config_dir = Path.home() / '.config' / 'emdx'
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / 'knowledge.db'
        else:
            self.db_path = db_path
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
        finally:
            conn.close()
    
    def ensure_schema(self):
        """Ensure the tables and FTS5 virtual table exist"""
        with self.get_connection() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Create main documents table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                )
            """)
            
            # Create FTS5 virtual table for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title,
                    content,
                    project,
                    content=documents,
                    content_rowid=id,
                    tokenize='porter unicode61'
                )
            """)
            
            # Create triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, content, project) 
                    VALUES (new.id, new.title, new.content, new.project);
                END
            """)
            
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    UPDATE documents_fts 
                    SET title = new.title, content = new.content, project = new.project
                    WHERE rowid = old.id;
                END
            """)
            
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            """)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_accessed ON documents(accessed_at DESC)
            """)
            
            conn.commit()
    
    def save_document(self, title: str, content: str, project: Optional[str] = None) -> int:
        """Save a document to the knowledge base"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                INSERT INTO documents (title, content, project)
                VALUES (?, ?, ?)
            """, (title, content, project))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_document(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID or title"""
        with self.get_connection() as conn:
            # Update access tracking
            if identifier.isdigit():
                conn.execute("""
                    UPDATE documents 
                    SET accessed_at = CURRENT_TIMESTAMP, 
                        access_count = access_count + 1
                    WHERE id = ?
                """, (int(identifier),))
                
                cursor = conn.execute("""
                    SELECT * FROM documents WHERE id = ?
                """, (int(identifier),))
            else:
                conn.execute("""
                    UPDATE documents 
                    SET accessed_at = CURRENT_TIMESTAMP, 
                        access_count = access_count + 1
                    WHERE LOWER(title) = LOWER(?)
                """, (identifier,))
                
                cursor = conn.execute("""
                    SELECT * FROM documents WHERE LOWER(title) = LOWER(?)
                """, (identifier,))
            
            conn.commit()
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    def list_documents(self, project: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List documents with optional project filter"""
        with self.get_connection() as conn:
            if project:
                cursor = conn.execute("""
                    SELECT id, title, project, created_at, access_count
                    FROM documents
                    WHERE project = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (project, limit))
            else:
                cursor = conn.execute("""
                    SELECT id, title, project, created_at, access_count
                    FROM documents
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def search_documents(self, query: str, project: Optional[str] = None, 
                        limit: int = 10, fuzzy: bool = False) -> List[Dict[str, Any]]:
        """Search documents using FTS5"""
        with self.get_connection() as conn:
            # For now, fuzzy search just uses regular FTS5
            # Could add rapidfuzz later for title matching
            
            if project:
                cursor = conn.execute("""
                    SELECT 
                        d.id, d.title, d.project, d.created_at,
                        snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                        rank as rank
                    FROM documents d
                    JOIN documents_fts ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ? AND d.project = ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, project, limit))
            else:
                cursor = conn.execute("""
                    SELECT 
                        d.id, d.title, d.project, d.created_at,
                        snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                        rank as rank
                    FROM documents d
                    JOIN documents_fts ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (query, limit))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def update_document(self, doc_id: int, title: str, content: str) -> bool:
        """Update a document"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                UPDATE documents
                SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (title, content, doc_id))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_document(self, identifier: str) -> bool:
        """Delete a document by ID or title"""
        with self.get_connection() as conn:
            if identifier.isdigit():
                cursor = conn.execute("""
                    DELETE FROM documents WHERE id = ?
                """, (int(identifier),))
            else:
                cursor = conn.execute("""
                    DELETE FROM documents WHERE LOWER(title) = LOWER(?)
                """, (identifier,))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def get_recent_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently accessed documents"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, title, project, accessed_at, access_count
                FROM documents
                ORDER BY accessed_at DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self, project: Optional[str] = None) -> Dict[str, Any]:
        """Get database statistics"""
        with self.get_connection() as conn:
            if project:
                # Project-specific stats
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_documents,
                        SUM(access_count) as total_views,
                        AVG(access_count) as avg_views,
                        MAX(created_at) as newest_doc,
                        MAX(accessed_at) as last_accessed
                    FROM documents
                    WHERE project = ?
                """, (project,))
            else:
                # Overall stats
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_documents,
                        COUNT(DISTINCT project) as total_projects,
                        SUM(access_count) as total_views,
                        AVG(access_count) as avg_views,
                        MAX(created_at) as newest_doc,
                        MAX(accessed_at) as last_accessed
                    FROM documents
                """)
            
            stats = dict(cursor.fetchone())
            
            # Get database file size
            stats['table_size'] = f"{self.db_path.stat().st_size / 1024 / 1024:.2f} MB"
            
            # Get most viewed document
            if project:
                cursor = conn.execute("""
                    SELECT id, title, access_count
                    FROM documents
                    WHERE project = ?
                    ORDER BY access_count DESC
                    LIMIT 1
                """, (project,))
            else:
                cursor = conn.execute("""
                    SELECT id, title, access_count
                    FROM documents
                    ORDER BY access_count DESC
                    LIMIT 1
                """)
            
            most_viewed = cursor.fetchone()
            if most_viewed:
                stats['most_viewed'] = dict(most_viewed)
            
            return stats


# Global database instance
db = SQLiteDatabase()