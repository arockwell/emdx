"""
Garbage collection for EMDX.
Clean up orphaned data, optimize database, and perform maintenance.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..config.settings import get_db_path
from ..database.connection import DatabaseConnection


class GarbageCollector:
    """Handles garbage collection operations for EMDX."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = Path(db_path) if db_path else get_db_path()
        self._db = DatabaseConnection(self.db_path)
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze database for garbage collection opportunities."""
        results = {
            'orphaned_tags': 0,
            'old_trash': 0,
            'stale_documents': 0,
            'database_size': 0,
            'fragmentation': 0,
            'recommendations': []
        }

        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Check for orphaned tags (tags with no documents)
            cursor.execute("""
                SELECT COUNT(*) FROM tags t
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_tags dt
                    WHERE dt.tag_id = t.id
                )
            """)
            results['orphaned_tags'] = cursor.fetchone()[0]

            # 2. Check for old trash (deleted > 30 days ago)
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM documents
                WHERE is_deleted = 1
                AND deleted_at < ?
            """, (thirty_days_ago,))
            results['old_trash'] = cursor.fetchone()[0]

            # 3. Check for stale documents (not accessed in 180 days)
            six_months_ago = (datetime.now() - timedelta(days=180)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM documents
                WHERE is_deleted = 0
                AND accessed_at < ?
                AND access_count < 5
            """, (six_months_ago,))
            results['stale_documents'] = cursor.fetchone()[0]

            # 4. Check database size and fragmentation
            cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            total_size = cursor.fetchone()[0]

            cursor.execute("SELECT freelist_count * page_size FROM pragma_freelist_count(), pragma_page_size()")
            free_size = cursor.fetchone()[0]

            results['database_size'] = total_size
            results['fragmentation'] = (free_size / total_size * 100) if total_size > 0 else 0

        # Generate recommendations
        if results['orphaned_tags'] > 0:
            results['recommendations'].append(f"Remove {results['orphaned_tags']} orphaned tags")

        if results['old_trash'] > 0:
            results['recommendations'].append(f"Permanently delete {results['old_trash']} old trash items")

        if results['stale_documents'] > 0:
            results['recommendations'].append(f"Archive {results['stale_documents']} stale documents")

        if results['fragmentation'] > 20:
            results['recommendations'].append(f"Vacuum database to reclaim {results['fragmentation']:.1f}% space")

        return results
    
    def clean_orphaned_tags(self) -> int:
        """Remove tags that have no associated documents."""
        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            # Delete orphaned tags
            cursor.execute("""
                DELETE FROM tags
                WHERE id IN (
                    SELECT t.id FROM tags t
                    WHERE NOT EXISTS (
                        SELECT 1 FROM document_tags dt
                        WHERE dt.tag_id = t.id
                    )
                )
            """)

            deleted = cursor.rowcount
            conn.commit()

        return deleted
    
    def clean_old_trash(self, days: int = 30) -> int:
        """Permanently delete documents that have been in trash for X days."""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            # Get the document IDs we're about to delete
            cursor.execute("""
                SELECT id FROM documents
                WHERE is_deleted = 1
                AND deleted_at < ?
            """, (cutoff_date,))
            doc_ids = [row[0] for row in cursor.fetchall()]

            if not doc_ids:
                return 0

            # Create placeholder string for IN clause
            placeholders = ','.join('?' * len(doc_ids))

            # Delete from all tables with FK references to documents
            # 1. document_tags
            cursor.execute(f"""
                DELETE FROM document_tags
                WHERE document_id IN ({placeholders})
            """, doc_ids)

            # 2. workflow_runs (set to NULL instead of delete to preserve workflow history)
            cursor.execute(f"""
                UPDATE workflow_runs
                SET input_doc_id = NULL
                WHERE input_doc_id IN ({placeholders})
            """, doc_ids)

            # 3. tasks (set gameplan_id to NULL to preserve task history)
            cursor.execute(f"""
                UPDATE tasks
                SET gameplan_id = NULL
                WHERE gameplan_id IN ({placeholders})
            """, doc_ids)

            # 4. export_history
            cursor.execute(f"""
                DELETE FROM export_history
                WHERE document_id IN ({placeholders})
            """, doc_ids)

            # 5. executions (set doc_id to NULL to preserve execution history)
            cursor.execute(f"""
                UPDATE executions
                SET doc_id = NULL
                WHERE doc_id IN ({placeholders})
            """, doc_ids)

            # 6. workflow_individual_runs (set output_doc_id to NULL to preserve workflow history)
            cursor.execute(f"""
                UPDATE workflow_individual_runs
                SET output_doc_id = NULL
                WHERE output_doc_id IN ({placeholders})
            """, doc_ids)

            # 7. agent_executions (set input_doc_id to NULL to preserve execution history)
            cursor.execute(f"""
                UPDATE agent_executions
                SET input_doc_id = NULL
                WHERE input_doc_id IN ({placeholders})
            """, doc_ids)

            # 8. workflow_stage_runs (set output_doc_id to NULL to preserve stage history)
            cursor.execute(f"""
                UPDATE workflow_stage_runs
                SET output_doc_id = NULL
                WHERE output_doc_id IN ({placeholders})
            """, doc_ids)

            # Now delete the documents
            cursor.execute(f"""
                DELETE FROM documents
                WHERE id IN ({placeholders})
            """, doc_ids)

            deleted = cursor.rowcount
            conn.commit()

        return deleted
    
    def archive_stale_documents(self, days: int = 180, min_views: int = 5) -> int:
        """Move stale documents to archived status."""
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        with self._db.get_connection() as conn:
            cursor = conn.cursor()

            # Add archived tag to stale documents
            cursor.execute("""
                INSERT OR IGNORE INTO tags (name) VALUES ('📦')
            """)

            cursor.execute("SELECT id FROM tags WHERE name = '📦'")
            archive_tag_id = cursor.fetchone()[0]

            # Tag stale documents
            cursor.execute("""
                INSERT OR IGNORE INTO document_tags (document_id, tag_id)
                SELECT id, ? FROM documents
                WHERE is_deleted = 0
                AND accessed_at < ?
                AND access_count < ?
            """, (archive_tag_id, cutoff_date, min_views))

            archived = cursor.rowcount
            conn.commit()

        return archived
    
    def vacuum_database(self) -> Dict[str, int]:
        """Vacuum the database to reclaim space."""
        # Get size before
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            size_before = cursor.fetchone()[0]

        # Vacuum - needs to be outside a transaction context manager
        # Using direct sqlite3 connection for VACUUM operation
        conn = sqlite3.connect(self.db_path)
        conn.execute("VACUUM")
        conn.close()

        # Get size after
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            size_after = cursor.fetchone()[0]

        return {
            'size_before': size_before,
            'size_after': size_after,
            'space_saved': size_before - size_after
        }


