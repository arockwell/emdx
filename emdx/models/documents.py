"""Document operations for emdx."""

from typing import Any, Optional

from emdx.config.constants import DEFAULT_BROWSE_LIMIT, DEFAULT_LIST_LIMIT
from emdx.database import db


def save_document(title: str, content: str, project: Optional[str] = None, tags: Optional[list[str]] = None, parent_id: Optional[int] = None) -> int:
    """Save a document to the knowledge base"""
    return db.save_document(title, content, project, tags, parent_id)


def get_document(identifier: str) -> Optional[dict[str, Any]]:
    """Get a document by ID or title"""
    return db.get_document(identifier)


def list_documents(project: Optional[str] = None, limit: int = DEFAULT_BROWSE_LIMIT, include_archived: bool = False) -> list[dict[str, Any]]:
    """List documents with optional project filter"""
    return db.list_documents(project, limit, include_archived=include_archived)


def search_documents(
    query: str,
    project: Optional[str] = None,
    limit: int = DEFAULT_LIST_LIMIT, 
    fuzzy: bool = False,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None
) -> list[dict[str, Any]]:
    """Search documents using FTS5 with optional date filters"""
    return db.search_documents(query, project, limit, fuzzy, 
                             created_after, created_before, 
                             modified_after, modified_before)


def update_document(doc_id: int, title: str, content: str) -> bool:
    """Update a document"""
    return db.update_document(doc_id, title, content)


def delete_document(identifier: str, hard_delete: bool = False) -> bool:
    """Delete a document by ID or title (soft delete by default)"""
    return db.delete_document(identifier, hard_delete)


def get_recent_documents(limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
    """Get recently accessed documents"""
    return db.get_recent_documents(limit)


def get_stats(project: Optional[str] = None) -> dict[str, Any]:
    """Get database statistics"""
    return db.get_stats(project)


def list_deleted_documents(days: Optional[int] = None, limit: int = DEFAULT_BROWSE_LIMIT) -> list[dict[str, Any]]:
    """List soft-deleted documents"""
    return db.list_deleted_documents(days, limit)


def restore_document(identifier: str) -> bool:
    """Restore a soft-deleted document"""
    return db.restore_document(identifier)


def purge_deleted_documents(older_than_days: Optional[int] = None) -> int:
    """Permanently delete soft-deleted documents"""
    return db.purge_deleted_documents(older_than_days)
