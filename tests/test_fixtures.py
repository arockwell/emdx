"""Test database setup."""

import sqlite3


class DatabaseForTesting:
    """Test database wrapper that handles in-memory databases correctly."""

    def __init__(self, db_path=":memory:"):
        self.db_path = db_path
        if db_path == ":memory:":
            self.conn = sqlite3.connect(":memory:")
            self.conn.row_factory = sqlite3.Row
            self._create_schema()
        else:
            self.conn = None
            self._create_schema()

    def get_connection(self):
        """Get a database connection."""
        if self.db_path == ":memory:":
            return self.conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _create_schema(self):
        """Create the database schema."""
        conn = self.get_connection()

        # Create documents table
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
                is_deleted BOOLEAN DEFAULT FALSE,
                doc_type TEXT NOT NULL DEFAULT 'user'
            )
        """
        )

        # Create tags table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create document_tags junction table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_tags (
                document_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, tag_id),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """
        )

        # Create document_links table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_doc_id INTEGER NOT NULL,
                target_doc_id INTEGER NOT NULL,
                similarity_score REAL NOT NULL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                method TEXT NOT NULL DEFAULT 'auto',
                FOREIGN KEY (source_doc_id)
                    REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (target_doc_id)
                    REFERENCES documents(id) ON DELETE CASCADE,
                UNIQUE(source_doc_id, target_doc_id)
            )
            """
        )

        conn.commit()

        if self.db_path != ":memory:":
            conn.close()

    def save_document(self, title, content, project=None):
        """Save a document to the database."""
        conn = self.get_connection()
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content, project)
            VALUES (?, ?, ?)
        """,
            (title, content, project),
        )

        doc_id = cursor.lastrowid

        if self.db_path != ":memory:":
            conn.commit()
            conn.close()
        else:
            conn.commit()

        return doc_id

    def get_document(self, doc_id):
        """Get a document by ID."""
        conn = self.get_connection()
        cursor = conn.execute(
            """
            SELECT id, title, content, project
            FROM documents
            WHERE id = ? AND (is_deleted = 0 OR is_deleted IS NULL)
        """,
            (doc_id,),
        )

        result = cursor.fetchone()

        if self.db_path != ":memory:":
            conn.close()

        return result

    def search_documents(self, query, project=None):
        """Simple search implementation."""
        conn = self.get_connection()

        if project:
            cursor = conn.execute(
                """
                SELECT id, title, content, project
                FROM documents
                WHERE (is_deleted = 0 OR is_deleted IS NULL)
                AND project = ?
                AND (title LIKE ? OR content LIKE ?)
                ORDER BY created_at DESC
            """,
                (project, f"%{query}%", f"%{query}%"),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, content, project
                FROM documents
                WHERE (is_deleted = 0 OR is_deleted IS NULL)
                AND (title LIKE ? OR content LIKE ?)
                ORDER BY created_at DESC
            """,
                (f"%{query}%", f"%{query}%"),
            )

        results = cursor.fetchall()

        if self.db_path != ":memory:":
            conn.close()

        return results

    def list_documents(self, project=None):
        """List all documents."""
        conn = self.get_connection()

        if project:
            cursor = conn.execute(
                """
                SELECT id, title, content, project
                FROM documents
                WHERE (is_deleted = 0 OR is_deleted IS NULL)
                AND project = ?
                ORDER BY created_at DESC
            """,
                (project,),
            )
        else:
            cursor = conn.execute(
                """
                SELECT id, title, content, project
                FROM documents
                WHERE (is_deleted = 0 OR is_deleted IS NULL)
                ORDER BY created_at DESC
            """
            )

        results = cursor.fetchall()

        if self.db_path != ":memory:":
            conn.close()

        return results

    def update_document(self, doc_id, title, content):
        """Update a document."""
        conn = self.get_connection()
        conn.execute(
            """
            UPDATE documents
            SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (title, content, doc_id),
        )

        if self.db_path != ":memory:":
            conn.commit()
            conn.close()
        else:
            conn.commit()

    def delete_document(self, doc_id):
        """Delete a document."""
        conn = self.get_connection()
        conn.execute(
            """
            UPDATE documents
            SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (doc_id,),
        )

        if self.db_path != ":memory:":
            conn.commit()
            conn.close()
        else:
            conn.commit()

    def close(self):
        """Close the in-memory connection if applicable."""
        if self.conn:
            self.conn.close()
