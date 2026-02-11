"""Document operations for emdx.

Re-exports from emdx.database.documents — the canonical implementation.
This module exists for backward compatibility; prefer importing directly
from emdx.database.documents for new code.
"""

# Re-export all document operations from the canonical sources
from emdx.database.documents import (
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
from emdx.database.search import search_documents

__all__ = [
    "delete_document",
    "get_document",
    "get_recent_documents",
    "get_stats",
    "list_deleted_documents",
    "list_documents",
    "purge_deleted_documents",
    "restore_document",
    "save_document",
    "search_documents",
    "update_document",
]
