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
from typing import Union

from ..models.document import Document
from ..models.search import SearchHit
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
)


class SQLiteDatabase:
    """Thin wrapper delegating all operations to the global database functions.

    All operations go through the canonical functions in database/documents.py
    and database/search.py, which use the global db_connection singleton.
    Test isolation is handled by the conftest fixture that redirects the
    singleton to a temporary database — no separate "isolated mode" needed.
    """

    @staticmethod
    def _conn() -> DatabaseConnection:
        """Get the current global DatabaseConnection.

        Uses dynamic lookup so that test fixtures can swap the singleton.
        """
        from . import connection

        return connection.db_connection

    @property
    def db_path(self) -> Path:
        """Get database path."""
        return self._conn().db_path

    def get_connection(self) -> AbstractContextManager[sqlite3.Connection]:
        """Get database connection."""
        return self._conn().get_connection()

    def ensure_schema(self) -> None:
        """Ensure database schema."""
        return self._conn().ensure_schema()

    # ── Document operations ──────────────────────────────────────────────

    def save_document(
        self,
        title: str,
        content: str,
        project: str | None = None,
        tags: list[str] | None = None,
        parent_id: int | None = None,
    ) -> int:
        """Save a document to the database."""
        return save_document(title, content, project, tags, parent_id)

    def get_document(self, identifier: Union[str, int]) -> Document | None:
        """Get a document by ID or title."""
        return get_document(identifier)

    def list_documents(self, project: str | None = None, limit: int = 50) -> list[Document]:
        """List documents with optional filters."""
        return list_documents(project, limit)

    def update_document(self, doc_id: int, title: str, content: str) -> bool:
        """Update a document."""
        return update_document(doc_id, title, content)

    def delete_document(self, identifier: Union[str, int], hard_delete: bool = False) -> bool:
        """Delete a document (soft delete by default)."""
        return delete_document(identifier, hard_delete)

    def get_recent_documents(self, limit: int = 10) -> list[Document]:
        """Get recently accessed documents."""
        return get_recent_documents(limit)

    def get_stats(self, project: str | None = None) -> DatabaseStats:
        """Get database statistics."""
        return get_stats(project)

    def list_deleted_documents(
        self,
        days: int | None = None,
        limit: int = 50,
    ) -> list[Document]:
        """List soft-deleted documents."""
        return list_deleted_documents(days, limit)

    def restore_document(self, identifier: Union[str, int]) -> bool:
        """Restore a soft-deleted document."""
        return restore_document(identifier)

    def purge_deleted_documents(self, older_than_days: int | None = None) -> int:
        """Permanently delete soft-deleted documents."""
        return purge_deleted_documents(older_than_days)

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
    ) -> list[SearchHit]:
        """Search documents using FTS."""
        return search_documents(
            query,
            project,
            limit,
            fuzzy,
            created_after,
            created_before,
            modified_after,
            modified_before,
        )


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
    "DatabaseStats",
    "DatabaseConnection",
    "Document",
    "SearchHit",
]
