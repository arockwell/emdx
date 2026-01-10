"""
Document CRUD operations for emdx knowledge base
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Union

from .connection import DatabaseConnection, db_connection

if TYPE_CHECKING:
    from .connection import DatabaseConnection


def _get_db(db: Optional["DatabaseConnection"] = None) -> "DatabaseConnection":
    """Get database connection instance, using global default if not provided."""
    return db if db is not None else db_connection


def save_document(
    title: str,
    content: str,
    project: Optional[str] = None,
    tags: Optional[list[str]] = None,
    parent_id: Optional[int] = None,
    db: Optional["DatabaseConnection"] = None,
) -> int:
    """Save a document to the knowledge base"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO documents (title, content, project, parent_id)
            VALUES (?, ?, ?, ?)
        """,
            (title, content, project, parent_id),
        )

        conn.commit()
        doc_id = cursor.lastrowid
        
        # Add tags if provided
        if tags:
            from emdx.models.tags import add_tags_to_document
            add_tags_to_document(doc_id, tags)
        
        return doc_id


def get_document(
    identifier: Union[str, int],
    db: Optional["DatabaseConnection"] = None,
) -> Optional[dict[str, Any]]:
    """Get a document by ID or title"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)
        
        # Update access tracking
        if identifier_str.isdigit():
            conn.execute(
                """
                UPDATE documents
                SET accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE id = ? AND is_deleted = FALSE
            """,
                (int(identifier_str),),
            )

            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE id = ? AND is_deleted = FALSE
            """,
                (int(identifier_str),),
            )
        else:
            conn.execute(
                """
                UPDATE documents
                SET accessed_at = CURRENT_TIMESTAMP,
                    access_count = access_count + 1
                WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
            """,
                (identifier_str,),
            )

            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
            """,
                (identifier_str,),
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
    project: Optional[str] = None,
    limit: int = 50,
    db: Optional["DatabaseConnection"] = None,
) -> list[dict[str, Any]]:
    """List documents with optional project filter"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
        if project:
            cursor = conn.execute(
                """
                SELECT id, title, project, created_at, access_count
                FROM documents
                WHERE project = ? AND is_deleted = FALSE
                ORDER BY id DESC
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
                ORDER BY id DESC
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


def update_document(
    doc_id: int,
    title: str,
    content: str,
    db: Optional["DatabaseConnection"] = None,
) -> bool:
    """Update a document"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
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


def delete_document(
    identifier: Union[str, int],
    hard_delete: bool = False,
    db: Optional["DatabaseConnection"] = None,
) -> bool:
    """Delete a document by ID or title (soft delete by default)"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)
        
        if hard_delete:
            # Permanent deletion
            if identifier_str.isdigit():
                cursor = conn.execute(
                    """
                    DELETE FROM documents WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier_str),),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM documents WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier_str,),
                )
        else:
            # Soft delete
            if identifier_str.isdigit():
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND is_deleted = FALSE
                """,
                    (int(identifier_str),),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET is_deleted = TRUE, deleted_at = CURRENT_TIMESTAMP
                    WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                """,
                    (identifier_str,),
                )

        conn.commit()
        return cursor.rowcount > 0


def get_recent_documents(
    limit: int = 10,
    db: Optional["DatabaseConnection"] = None,
) -> list[dict[str, Any]]:
    """Get recently accessed documents"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
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


def get_stats(
    project: Optional[str] = None,
    db: Optional["DatabaseConnection"] = None,
) -> dict[str, Any]:
    """Get database statistics"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
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
        stats["table_size"] = f"{db_conn.db_path.stat().st_size / 1024 / 1024:.2f} MB"

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
    days: Optional[int] = None,
    limit: int = 50,
    db: Optional["DatabaseConnection"] = None,
) -> list[dict[str, Any]]:
    """List soft-deleted documents"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
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


def restore_document(
    identifier: Union[str, int],
    db: Optional["DatabaseConnection"] = None,
) -> bool:
    """Restore a soft-deleted document"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
        # Convert to string for consistent handling
        identifier_str = str(identifier)
        if identifier_str.isdigit():
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


def purge_deleted_documents(
    older_than_days: Optional[int] = None,
    db: Optional["DatabaseConnection"] = None,
) -> int:
    """Permanently delete soft-deleted documents"""
    db_conn = _get_db(db)
    with db_conn.get_connection() as conn:
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
