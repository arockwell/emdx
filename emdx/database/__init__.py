"""
EMDX Database Package

Organized database operations split into focused modules:
- connection: Database connection management
- documents: Document CRUD operations
- search: Full-text search operations
- migrations: Database schema migrations

This package maintains backward compatibility with the original sqlite_database.py API.
"""

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


class SQLiteDatabase:
    """Backward-compatible wrapper for the original SQLiteDatabase class"""

    def __init__(self, db_path=None):
        self._connection = DatabaseConnection(db_path)

    def get_connection(self):
        """Get database connection - delegates to connection module"""
        return self._connection.get_connection()

    def ensure_schema(self):
        """Ensure database schema - delegates to connection module"""
        return self._connection.ensure_schema()

    # Document operations - delegate to documents module
    def save_document(self, title, content, project=None):
        return save_document(title, content, project)

    def get_document(self, identifier):
        return get_document(identifier)

    def list_documents(self, project=None, limit=50):
        return list_documents(project, limit)

    def update_document(self, doc_id, title, content):
        return update_document(doc_id, title, content)

    def delete_document(self, identifier, hard_delete=False):
        return delete_document(identifier, hard_delete)

    def get_recent_documents(self, limit=10):
        return get_recent_documents(limit)

    def get_stats(self, project=None):
        return get_stats(project)

    def list_deleted_documents(self, days=None, limit=50):
        return list_deleted_documents(days, limit)

    def restore_document(self, identifier):
        return restore_document(identifier)

    def purge_deleted_documents(self, older_than_days=None):
        return purge_deleted_documents(older_than_days)

    # Search operations - delegate to search module
    def search_documents(self, query, project=None, limit=10, fuzzy=False):
        return search_documents(query, project, limit, fuzzy)


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
