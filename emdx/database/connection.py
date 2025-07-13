"""
Database connection management for emdx
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import migrations


class DatabaseConnection:
    """SQLite database connection manager for emdx"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            # Default location in user config directory
            config_dir = Path.home() / ".config" / "emdx"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "knowledge.db"
        else:
            self.db_path = db_path

    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager"""
        conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row  # Enable column access by name

        # Register datetime adapter
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
        sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))

        try:
            yield conn
        finally:
            conn.close()

    def ensure_schema(self):
        """Ensure the tables and FTS5 virtual table exist"""
        # Run any pending migrations first
        migrations.run_migrations()

        with self.get_connection() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")

            # Create documents table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    project TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP,
                    deleted_at TIMESTAMP NULL
                )
            """)

            # Create document_tags table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    tag TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    UNIQUE (document_id, tag)
                )
            """)

            # Create FTS5 virtual table for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, content, project, content=documents, content_rowid=id,
                    tokenize='porter unicode61'
                )
            """)

            # Create triggers to keep FTS table synchronized
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents
                BEGIN
                    INSERT INTO documents_fts(rowid, title, content, project) 
                    VALUES (new.id, new.title, new.content, new.project);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_fts_delete AFTER DELETE ON documents
                BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS documents_fts_update AFTER UPDATE ON documents
                BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                    INSERT INTO documents_fts(rowid, title, content, project) 
                    VALUES (new.id, new.title, new.content, new.project);
                END
            """)

            # Create indexes for better performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents(updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_deleted_at ON documents(deleted_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_document_tags_document_id ON document_tags(document_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag)")

            conn.commit()


# Global instance for backward compatibility
db_connection = DatabaseConnection()