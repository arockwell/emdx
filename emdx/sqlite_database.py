"""
SQLite database connection and operations for emdx
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import migrations


class SQLiteDatabase:
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

            # Create main documents table
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

            # Create FTS5 virtual table for full-text search
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                    title,
                    content,
                    project,
                    content=documents,
                    content_rowid=id,
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
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_accessed ON documents(accessed_at DESC)
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
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gists_document ON gists(document_id)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gists_gist_id ON gists(gist_id)
            """
            )

            conn.commit()

    def save_document(self, title: str, content: str, project: Optional[str] = None) -> int:
        """Save a document to the knowledge base"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (title, content, project)
                VALUES (?, ?, ?)
            """,
                (title, content, project),
            )

            conn.commit()
            return cursor.lastrowid

    def get_document(self, identifier: str) -> Optional[dict[str, Any]]:
        """Get a document by ID or title"""
        with self.get_connection() as conn:
            # Update access tracking
            if identifier.isdigit():
                conn.execute(
                    """
                    UPDATE documents
                    SET accessed_at = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                    WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier),),
                )

                cursor = conn.execute(
                    """
                    SELECT * FROM documents WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier),),
                )
            else:
                conn.execute(
                    """
                    UPDATE documents
                    SET accessed_at = CURRENT_TIMESTAMP,
                        access_count = access_count + 1
                    WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier,),
                )

                cursor = conn.execute(
                    """
                    SELECT * FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier,),
                )

            conn.commit()
            row = cursor.fetchone()

            if row:
                # Convert Row to dict and parse datetime strings
                doc = dict(row)
                for field in ["created_at", "updated_at", "accessed_at"]:
                    if field in doc and isinstance(doc[field], str):
                        doc[field] = datetime.fromisoformat(doc[field])
                return doc
            return None

    def list_documents(
        self, project: Optional[str] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List documents with optional project filter"""
        with self.get_connection() as conn:
            if project:
                cursor = conn.execute(
                    """
                    SELECT id, title, project, created_at, access_count
                    FROM documents
                    WHERE project = ? AND is_deleted = FALSE
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (project, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, title, project, created_at, access_count
                    FROM documents
                    WHERE is_deleted = FALSE
                    ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            # Convert rows and parse datetime strings
            docs = []
            for row in cursor.fetchall():
                doc = dict(row)
                for field in ["created_at", "updated_at", "accessed_at"]:
                    if field in doc and isinstance(doc[field], str):
                        doc[field] = datetime.fromisoformat(doc[field])
                docs.append(doc)
            return docs

    def search_documents(
        self, query: str, project: Optional[str] = None, limit: int = 10, fuzzy: bool = False
    ) -> list[dict[str, Any]]:
        """Search documents using FTS5"""
        with self.get_connection() as conn:
            # For now, fuzzy search just uses regular FTS5
            # Could add rapidfuzz later for title matching

            if project:
                cursor = conn.execute(
                    """
                    SELECT
                        d.id, d.title, d.project, d.created_at,
                        snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                        rank as rank
                    FROM documents d
                    JOIN documents_fts ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ? AND d.project = ? AND d.is_deleted = FALSE
                    ORDER BY rank
                    LIMIT ?
                """,
                    (query, project, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT
                        d.id, d.title, d.project, d.created_at,
                        snippet(documents_fts, 1, '<b>', '</b>', '...', 30) as snippet,
                        rank as rank
                    FROM documents d
                    JOIN documents_fts ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ? AND d.is_deleted = FALSE
                    ORDER BY rank
                    LIMIT ?
                """,
                    (query, limit),
                )

            # Convert rows and parse datetime strings
            docs = []
            for row in cursor.fetchall():
                doc = dict(row)
                for field in ["created_at", "updated_at", "accessed_at"]:
                    if field in doc and isinstance(doc[field], str):
                        doc[field] = datetime.fromisoformat(doc[field])
                docs.append(doc)
            return docs

    def update_document(self, doc_id: int, title: str, content: str) -> bool:
        """Update a document"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE documents
                SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (title, content, doc_id),
            )

            conn.commit()
            return cursor.rowcount > 0

    def delete_document(self, identifier: str, hard_delete: bool = False) -> bool:
        """Delete a document by ID or title (soft delete by default)"""
        with self.get_connection() as conn:
            if hard_delete:
                # Permanent deletion
                if identifier.isdigit():
                    cursor = conn.execute(
                        """
                        DELETE FROM documents WHERE id = ? AND is_deleted = FALSE
                    """,
                        (int(identifier),),
                    )
                else:
                    cursor = conn.execute(
                        """
                        DELETE FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                    """,
                        (identifier,),
                    )
            else:
                # Soft delete
                if identifier.isdigit():
                    cursor = conn.execute(
                        """
                        UPDATE documents
                        SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND is_deleted = FALSE
                    """,
                        (int(identifier),),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE documents
                        SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                        WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                    """,
                        (identifier,),
                    )

            conn.commit()
            return cursor.rowcount > 0

    def get_recent_documents(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recently accessed documents"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, title, project, accessed_at, access_count
                FROM documents
                WHERE is_deleted = FALSE
                ORDER BY accessed_at DESC
                LIMIT ?
            """,
                (limit,),
            )

            # Convert rows and parse datetime strings
            docs = []
            for row in cursor.fetchall():
                doc = dict(row)
                for field in ["created_at", "updated_at", "accessed_at"]:
                    if field in doc and isinstance(doc[field], str):
                        doc[field] = datetime.fromisoformat(doc[field])
                docs.append(doc)
            return docs

    def get_stats(self, project: Optional[str] = None) -> dict[str, Any]:
        """Get database statistics"""
        with self.get_connection() as conn:
            if project:
                # Project-specific stats
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_documents,
                        SUM(access_count) as total_views,
                        AVG(access_count) as avg_views,
                        MAX(created_at) as newest_doc,
                        MAX(accessed_at) as last_accessed
                    FROM documents
                    WHERE project = ? AND is_deleted = FALSE
                """,
                    (project,),
                )
            else:
                # Overall stats
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_documents,
                        COUNT(DISTINCT project) as total_projects,
                        SUM(access_count) as total_views,
                        AVG(access_count) as avg_views,
                        MAX(created_at) as newest_doc,
                        MAX(accessed_at) as last_accessed
                    FROM documents
                    WHERE is_deleted = FALSE
                """
                )

            stats = dict(cursor.fetchone())

            # Get database file size
            stats["table_size"] = f"{self.db_path.stat().st_size / 1024 / 1024:.2f} MB"

            # Get most viewed document
            if project:
                cursor = conn.execute(
                    """
                    SELECT id, title, access_count
                    FROM documents
                    WHERE project = ? AND is_deleted = FALSE
                    ORDER BY access_count DESC
                    LIMIT 1
                """,
                    (project,),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, title, access_count
                    FROM documents
                    WHERE is_deleted = FALSE
                    ORDER BY access_count DESC
                    LIMIT 1
                """
                )

            most_viewed = cursor.fetchone()
            if most_viewed:
                stats["most_viewed"] = dict(most_viewed)

            return stats

    def list_deleted_documents(
        self, days: Optional[int] = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List soft-deleted documents"""
        with self.get_connection() as conn:
            if days:
                cursor = conn.execute(
                    """
                    SELECT id, title, project, deleted_at, access_count
                    FROM documents
                    WHERE is_deleted = TRUE
                    AND deleted_at >= datetime('now', '-' || ? || ' days')
                    ORDER BY deleted_at DESC
                    LIMIT ?
                """,
                    (days, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, title, project, deleted_at, access_count
                    FROM documents
                    WHERE is_deleted = TRUE
                    ORDER BY deleted_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            # Convert rows and parse datetime strings
            docs = []
            for row in cursor.fetchall():
                doc = dict(row)
                for field in ["created_at", "updated_at", "accessed_at", "deleted_at"]:
                    if field in doc and isinstance(doc[field], str):
                        doc[field] = datetime.fromisoformat(doc[field])
                docs.append(doc)
            return docs

    def restore_document(self, identifier: str) -> bool:
        """Restore a soft-deleted document"""
        with self.get_connection() as conn:
            if identifier.isdigit():
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = FALSE, deleted_at = NULL
                    WHERE id = ? AND is_deleted = TRUE
                """,
                    (int(identifier),),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = FALSE, deleted_at = NULL
                    WHERE LOWER(title) = LOWER(?) AND is_deleted = TRUE
                """,
                    (identifier,),
                )

            conn.commit()
            return cursor.rowcount > 0

    def purge_deleted_documents(self, older_than_days: Optional[int] = None) -> int:
        """Permanently delete soft-deleted documents"""
        with self.get_connection() as conn:
            if older_than_days:
                cursor = conn.execute(
                    """
                    DELETE FROM documents
                    WHERE is_deleted = TRUE
                    AND deleted_at <= datetime('now', '-' || ? || ' days')
                """,
                    (older_than_days,),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM documents
                    WHERE is_deleted = TRUE
                """
                )

            conn.commit()
            return cursor.rowcount


# Global database instance
db = SQLiteDatabase()
