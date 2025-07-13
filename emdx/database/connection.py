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
            conn.execute(
                """
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
            """
            )

            # Add soft delete columns to existing databases (migration)
            # Check if columns exist first
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = [col[1] for col in cursor.fetchall()]

            if "deleted_at" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMP")

            if "is_deleted" not in columns:
                conn.execute("ALTER TABLE documents ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE")

            # Create tags table if it doesn't exist
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create document_tags table if it doesn't exist
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE,
                    UNIQUE (document_id, tag_id)
                )
            """
            )

            # Create FTS5 virtual table for full-text search
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title, content, project, content=documents, content_rowid=id,
                    tokenize='porter unicode61'
                )
            """
            )

            # Create triggers to keep FTS in sync
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, content, project)
                    VALUES (new.id, new.title, new.content, new.project);
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    UPDATE documents_fts
                    SET title = new.title, content = new.content, project = new.project
                    WHERE rowid = old.id;
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    DELETE FROM documents_fts WHERE rowid = old.id;
                END
            """
            )

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_accessed ON documents(accessed_at DESC)"
            )

            # Create index after columns exist
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_deleted ON documents(
                    is_deleted, deleted_at
                )
            """
            )

            # Create gists table for tracking document-gist relationships
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    gist_id TEXT NOT NULL,
                    gist_url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_public BOOLEAN DEFAULT 0,
                    FOREIGN KEY (document_id) REFERENCES documents (id)
                )
            """
            )

            # Create indexes for gists table
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gists_document ON gists(document_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gists_gist_id ON gists(gist_id)")

            # Create indexes for tags tables
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_tags_document_id ON document_tags(document_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_document_tags_tag_id ON document_tags(tag_id)"
            )

            conn.commit()


# Global instance for backward compatibility
db_connection = DatabaseConnection()
