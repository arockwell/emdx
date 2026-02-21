"""
EMDX Database Package

Organized database operations split into focused modules:
- connection: Database connection management
- documents: Document CRUD operations
- search: Full-text search operations
- migrations: Database schema migrations
This package maintains backward compatibility with the original sqlite_database.py API.
"""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Union, cast

from .connection import DatabaseConnection, db_connection
from .documents import (
    delete_document,
    get_document,
    get_recent_documents,
    get_stats,
    list_deleted_documents,
    list_documents,
    purge_deleted_documents,
    restore_document,
    save_document,
    update_document,
)
from .search import search_documents
from .types import (
    DatabaseStats,
    DeletedDocumentItem,
    DocumentListItem,
    DocumentRow,
    RecentDocumentItem,
    SearchResult,
)


class SQLiteDatabase:
    """Backward-compatible wrapper providing both global and isolated database access.

    Two modes of operation:

    1. **Global mode** (no db_path): Delegates all operations to the canonical
       functions in database/documents.py and database/search.py, which use the
       global db_connection singleton. This avoids duplicating SQL.

    2. **Isolated mode** (custom db_path): Uses its own DatabaseConnection with
       self-contained SQL for complete test isolation. Tests create instances
       with temporary paths that MUST NOT touch the global database.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._connection: DatabaseConnection | None
        if db_path is not None:
            # Custom path: create own connection (for test isolation)
            self._connection = DatabaseConnection(db_path)
            self._uses_global_connection = False
        else:
            # No path: use global db_connection (allows test fixture override)
            self._connection = None  # Will use db_connection dynamically
            self._uses_global_connection = True
        self._uses_custom_path = db_path is not None

    def _get_connection_instance(self) -> DatabaseConnection:
        """Get the appropriate DatabaseConnection instance."""
        if self._uses_global_connection:
            from . import connection
            return connection.db_connection
        assert self._connection is not None
        return self._connection

    @property
    def db_path(self) -> Path:
        """Get database path."""
        return self._get_connection_instance().db_path

    def get_connection(self) -> AbstractContextManager[sqlite3.Connection]:
        """Get database connection."""
        return self._get_connection_instance().get_connection()

    def ensure_schema(self) -> None:
        """Ensure database schema."""
        return self._get_connection_instance().ensure_schema()

    # ── Document operations ──────────────────────────────────────────────
    #
    # Global mode: delegate to database/documents.py (single source of truth).
    # Isolated mode: self-contained SQL against the instance's own database.

    def save_document(
        self,
        title: str,
        content: str,
        project: str | None = None,
        tags: list[str] | None = None,
        parent_id: int | None = None,
    ) -> int:
        """Save a document to the database."""
        if not self._uses_custom_path:
            return save_document(title, content, project, tags, parent_id)

        # Isolated mode — self-contained SQL for test databases
        assert self._connection is not None
        with self._connection.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO documents (title, content, project, parent_id) VALUES (?, ?, ?, ?)",
                (title, content, project, parent_id),
            )
            conn.commit()
            doc_id: int = cursor.lastrowid  # type: ignore[assignment]

            if tags:
                for tag_name in tags:
                    tag_name = tag_name.lower().strip()
                    cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    result = cursor.fetchone()
                    if result:
                        tag_id = result[0]
                    else:
                        cursor = conn.execute(
                            "INSERT INTO tags (name, usage_count) VALUES (?, 0)", (tag_name,),
                        )
                        tag_id = cursor.lastrowid
                    conn.execute(
                        "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                        (doc_id, tag_id),
                    )
                conn.commit()

            return doc_id

    def get_document(self, identifier: Union[str, int]) -> DocumentRow | None:
        """Get a document by ID or title."""
        if not self._uses_custom_path:
            return get_document(identifier)

        # Isolated mode
        assert self._connection is not None
        with self._connection.get_connection() as conn:
            identifier_str = str(identifier)
            if identifier_str.isdigit():
                conn.execute(
                    "UPDATE documents SET accessed_at = CURRENT_TIMESTAMP, "
                    "access_count = access_count + 1 WHERE id = ? AND is_deleted = FALSE",
                    (int(identifier_str),),
                )
                cursor = conn.execute(
                    "SELECT * FROM documents WHERE id = ? AND is_deleted = FALSE",
                    (int(identifier_str),),
                )
            else:
                conn.execute(
                    "UPDATE documents SET accessed_at = CURRENT_TIMESTAMP, "
                    "access_count = access_count + 1 WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE",  # noqa: E501
                    (identifier_str,),
                )
                cursor = conn.execute(
                    "SELECT * FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE",
                    (identifier_str,),
                )
            conn.commit()
            row = cursor.fetchone()
            return cast(DocumentRow, dict(row)) if row else None

    def list_documents(self, project: str | None = None, limit: int = 50) -> list[DocumentListItem]:
        """List documents with optional filters."""
        if not self._uses_custom_path:
            return list_documents(project, limit)

        # Isolated mode
        assert self._connection is not None
        with self._connection.get_connection() as conn:
            conditions = ["is_deleted = FALSE", "archived_at IS NULL"]
            params: list[Any] = []
            if project:
                conditions.append("project = ?")
                params.append(project)
            where_clause = " AND ".join(conditions)
            params.append(limit)
            cursor = conn.execute(
                f"SELECT id, title, project, created_at, access_count "
                f"FROM documents WHERE {where_clause} ORDER BY id DESC LIMIT ?",
                params,
            )
            return [cast(DocumentListItem, dict(row)) for row in cursor.fetchall()]

    def update_document(self, doc_id: int, title: str, content: str) -> bool:
        """Update a document."""
        if not self._uses_custom_path:
            return update_document(doc_id, title, content)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE documents SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",  # noqa: E501
                (title, content, doc_id),
            )
            conn.commit()
            return bool(cursor.rowcount > 0)

    def delete_document(self, identifier: Union[str, int], hard_delete: bool = False) -> bool:
        """Delete a document (soft delete by default)."""
        if not self._uses_custom_path:
            return delete_document(identifier, hard_delete)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            identifier_str = str(identifier)
            if hard_delete:
                if identifier_str.isdigit():
                    cursor = conn.execute(
                        "DELETE FROM documents WHERE id = ? AND is_deleted = FALSE",
                        (int(identifier_str),),
                    )
                else:
                    cursor = conn.execute(
                        "DELETE FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE",  # noqa: E501
                        (identifier_str,),
                    )
            else:
                if identifier_str.isdigit():
                    cursor = conn.execute(
                        "UPDATE documents SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                        "WHERE id = ? AND is_deleted = FALSE",
                        (int(identifier_str),),
                    )
                else:
                    cursor = conn.execute(
                        "UPDATE documents SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP "
                        "WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE",
                        (identifier_str,),
                    )
            conn.commit()
            return bool(cursor.rowcount > 0)

    def get_recent_documents(self, limit: int = 10) -> list[RecentDocumentItem]:
        """Get recently accessed documents."""
        if not self._uses_custom_path:
            return get_recent_documents(limit)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, project, accessed_at, access_count "
                "FROM documents WHERE is_deleted = FALSE ORDER BY accessed_at DESC LIMIT ?",
                (limit,),
            )
            return [cast(RecentDocumentItem, dict(row)) for row in cursor.fetchall()]

    def get_stats(self, project: str | None = None) -> DatabaseStats:
        """Get database statistics."""
        if not self._uses_custom_path:
            return get_stats(project)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            if project:
                cursor = conn.execute(
                    "SELECT COUNT(*) as total_documents, SUM(access_count) as total_views, "
                    "AVG(access_count) as avg_views FROM documents "
                    "WHERE project = ? AND is_deleted = FALSE",
                    (project,),
                )
            else:
                cursor = conn.execute(
                    "SELECT COUNT(*) as total_documents, COUNT(DISTINCT project) as total_projects, "  # noqa: E501
                    "SUM(access_count) as total_views, AVG(access_count) as avg_views "
                    "FROM documents WHERE is_deleted = FALSE"
                )
            return cast(DatabaseStats, dict(cursor.fetchone()))

    def list_deleted_documents(
        self, days: int | None = None, limit: int = 50,
    ) -> list[DeletedDocumentItem]:
        """List soft-deleted documents."""
        if not self._uses_custom_path:
            return list_deleted_documents(days, limit)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            if days:
                cursor = conn.execute(
                    "SELECT id, title, project, deleted_at, access_count FROM documents "
                    "WHERE is_deleted = TRUE AND deleted_at >= datetime('now', '-' || ? || ' days') "  # noqa: E501
                    "ORDER BY deleted_at DESC LIMIT ?",
                    (days, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, title, project, deleted_at, access_count FROM documents "
                    "WHERE is_deleted = TRUE ORDER BY deleted_at DESC LIMIT ?",
                    (limit,),
                )
            return [cast(DeletedDocumentItem, dict(row)) for row in cursor.fetchall()]

    def restore_document(self, identifier: Union[str, int]) -> bool:
        """Restore a soft-deleted document."""
        if not self._uses_custom_path:
            return restore_document(identifier)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            identifier_str = str(identifier)
            if identifier_str.isdigit():
                cursor = conn.execute(
                    "UPDATE documents SET is_deleted = FALSE, deleted_at = NULL "
                    "WHERE id = ? AND is_deleted = TRUE",
                    (int(identifier_str),),
                )
            else:
                cursor = conn.execute(
                    "UPDATE documents SET is_deleted = FALSE, deleted_at = NULL "
                    "WHERE LOWER(title) = LOWER(?) AND is_deleted = TRUE",
                    (identifier_str,),
                )
            conn.commit()
            return bool(cursor.rowcount > 0)

    def purge_deleted_documents(self, older_than_days: int | None = None) -> int:
        """Permanently delete soft-deleted documents."""
        if not self._uses_custom_path:
            return purge_deleted_documents(older_than_days)

        assert self._connection is not None
        with self._connection.get_connection() as conn:
            if older_than_days:
                cursor = conn.execute(
                    "DELETE FROM documents WHERE is_deleted = TRUE "
                    "AND deleted_at <= datetime('now', '-' || ? || ' days')",
                    (older_than_days,),
                )
            else:
                cursor = conn.execute("DELETE FROM documents WHERE is_deleted = TRUE")
            conn.commit()
            return int(cursor.rowcount)

    def search_documents(
        self,
        query: str,
        project: str | None = None,
        limit: int = 10,
        fuzzy: bool = False,
        created_after: str | None = None,
        created_before: str | None = None,
        modified_after: str | None = None,
        modified_before: str | None = None,
    ) -> list[SearchResult]:
        """Search documents using FTS."""
        if not self._uses_custom_path:
            return search_documents(query, project, limit, fuzzy,
                                    created_after, created_before,
                                    modified_after, modified_before)

        # Isolated mode — self-contained FTS search for test databases
        assert self._connection is not None
        with self._connection.get_connection() as conn:
            if query == "*":
                conditions = ["d.is_deleted = FALSE"]
                params: list[Any] = []
                if project:
                    conditions.append("d.project = ?")
                    params.append(project)
                where_clause = " AND ".join(conditions)
                params.append(limit)
                cursor = conn.execute(
                    f"SELECT d.id, d.title, d.content, d.project, d.created_at, "
                    f"d.updated_at, d.access_count, NULL as snippet "
                    f"FROM documents d WHERE {where_clause} ORDER BY d.id DESC LIMIT ?",
                    params,
                )
                return [cast(SearchResult, dict(row)) for row in cursor.fetchall()]

            conditions = ["d.is_deleted = FALSE"]
            params = []
            if project:
                conditions.append("d.project = ?")
                params.append(project)
            where_clause = " AND ".join(conditions)

            from .search import escape_fts5_query
            safe_query = escape_fts5_query(query)

            cursor = conn.execute(
                f"SELECT d.id, d.title, d.content, d.project, d.created_at, "
                f"d.updated_at, d.access_count, "
                f"snippet(documents_fts, 1, '<mark>', '</mark>', '...', 32) as snippet "
                f"FROM documents d JOIN documents_fts fts ON d.id = fts.rowid "
                f"WHERE fts.documents_fts MATCH ? AND {where_clause} ORDER BY rank LIMIT ?",
                [safe_query] + params + [limit],
            )
            return [cast(SearchResult, dict(row)) for row in cursor.fetchall()]


# Create global instance for backward compatibility
db = SQLiteDatabase()

# Export the individual functions for direct use
__all__ = [
    "db",
    "SQLiteDatabase",
    "db_connection",
    "save_document",
    "get_document",
    "list_documents",
    "update_document",
    "delete_document",
    "get_recent_documents",
    "get_stats",
    "list_deleted_documents",
    "restore_document",
    "purge_deleted_documents",
    "search_documents",
]
