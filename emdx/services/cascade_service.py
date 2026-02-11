"""Cascade service facade for the UI layer.

Provides a clean import boundary between UI code and the database layer
for cascade pipeline operations. Also houses query functions previously
embedded as raw SQL in UI code.
"""

from typing import Any, Dict, List

from emdx.database import cascade as cascade_db
from emdx.database.connection import db_connection
from emdx.database.documents import get_document

# Re-export cascade DB functions used by UI
get_cascade_stats = cascade_db.get_cascade_stats
get_cascade_run_executions = cascade_db.get_cascade_run_executions
list_cascade_runs = cascade_db.list_cascade_runs
list_documents_at_stage = cascade_db.list_documents_at_stage
update_cascade_stage = cascade_db.update_cascade_stage
save_document_to_cascade = cascade_db.save_document_to_cascade

# Re-export document fetch (used alongside cascade ops)
get_document = get_document

__all__ = [
    "get_cascade_run_executions",
    "get_cascade_stats",
    "get_document",
    "get_recent_cascade_activity",
    "get_recent_cascade_runs",
    "get_recent_pipeline_activity",
    "list_cascade_runs",
    "list_documents_at_stage",
    "save_document_to_cascade",
    "update_cascade_stage",
]


def get_recent_cascade_activity(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent cascade activity from executions and document changes.

    Moved from emdx/ui/cascade_browser.py to eliminate raw SQL in UI.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                e.id,
                e.doc_id,
                e.doc_title,
                e.status,
                e.started_at,
                e.completed_at,
                d.stage,
                d.parent_id,
                e.cascade_run_id
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.doc_title LIKE 'Cascade:%' OR e.doc_title LIKE 'Pipeline:%' OR d.stage IS NOT NULL OR e.cascade_run_id IS NOT NULL
            ORDER BY e.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        return [
            {
                "exec_id": row[0],
                "doc_id": row[1],
                "doc_title": row[2],
                "status": row[3],
                "started_at": row[4],
                "completed_at": row[5],
                "stage": row[6],
                "parent_id": row[7],
                "cascade_run_id": row[8],
            }
            for row in rows
        ]


def get_recent_pipeline_activity(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent pipeline activity - executions with their input/output docs.

    Moved from emdx/ui/cascade_browser.py to eliminate raw SQL in UI.
    """
    PREV_STAGE = {
        "prompt": "idea",
        "analyzed": "prompt",
        "planned": "analyzed",
        "done": "planned",
    }

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                e.id as exec_id,
                e.doc_id as input_id,
                e.doc_title as input_title,
                e.status,
                e.started_at,
                e.completed_at,
                e.log_file,
                child.id as output_id,
                child.title as output_title,
                child.stage as output_stage,
                input_doc.stage as input_stage
            FROM executions e
            LEFT JOIN documents child ON child.parent_id = e.doc_id
            LEFT JOIN documents input_doc ON input_doc.id = e.doc_id
            WHERE e.doc_title LIKE 'Cascade:%'
               OR e.doc_title LIKE 'Pipeline:%'
               OR input_doc.stage IS NOT NULL
               OR e.cascade_run_id IS NOT NULL
            ORDER BY e.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            output_stage = row[9]
            input_stage = row[10]
            if output_stage:
                from_stage = PREV_STAGE.get(output_stage, input_stage or "?")
            else:
                from_stage = input_stage or "?"

            results.append({
                "exec_id": row[0],
                "input_id": row[1],
                "input_title": row[2],
                "status": row[3],
                "started_at": row[4],
                "completed_at": row[5],
                "log_file": row[6],
                "output_id": row[7],
                "output_title": row[8],
                "output_stage": output_stage,
                "from_stage": from_stage,
            })
        return results


def get_recent_cascade_runs(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent cascade runs with their status and progress.

    Moved from emdx/ui/cascade_browser.py to eliminate raw SQL in UI.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                cr.id,
                cr.start_doc_id,
                cr.current_doc_id,
                cr.start_stage,
                cr.stop_stage,
                cr.current_stage,
                cr.status,
                cr.pr_url,
                cr.started_at,
                cr.completed_at,
                cr.error_message,
                d.title as start_doc_title
            FROM cascade_runs cr
            LEFT JOIN documents d ON cr.start_doc_id = d.id
            ORDER BY cr.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        return [
            {
                "run_id": row[0],
                "start_doc_id": row[1],
                "current_doc_id": row[2],
                "start_stage": row[3],
                "stop_stage": row[4],
                "current_stage": row[5],
                "status": row[6],
                "pr_url": row[7],
                "started_at": row[8],
                "completed_at": row[9],
                "error_message": row[10],
                "start_doc_title": row[11],
            }
            for row in rows
        ]
