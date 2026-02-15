"""Cascade service facade for the UI layer.

Provides a clean import boundary between UI code and the database layer
for cascade pipeline operations.
"""

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from emdx.database import cascade as cascade_db
from emdx.database.connection import db_connection
from emdx.database.documents import get_document

logger = logging.getLogger(__name__)

# Re-export cascade DB functions used by UI
get_cascade_stats = cascade_db.get_cascade_stats
get_cascade_run_executions = cascade_db.get_cascade_run_executions
list_cascade_runs = cascade_db.list_cascade_runs
list_documents_at_stage = cascade_db.list_documents_at_stage
update_cascade_stage = cascade_db.update_cascade_stage
save_document_to_cascade = cascade_db.save_document_to_cascade
get_document = get_document

def get_recent_pipeline_activity(limit: int = 10) -> list[dict[str, Any]]:
    """Get recent pipeline activity — executions with their input/output docs."""
    PREV_STAGE = {"prompt": "idea", "analyzed": "prompt", "planned": "analyzed", "done": "planned"}

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at,
                   e.completed_at, e.log_file, child.id, child.title,
                   child.stage, input_doc.stage
            FROM executions e
            LEFT JOIN documents child ON child.parent_id = e.doc_id
            LEFT JOIN documents input_doc ON input_doc.id = e.doc_id
            WHERE e.doc_title LIKE 'Cascade:%' OR e.doc_title LIKE 'Pipeline:%'
               OR input_doc.stage IS NOT NULL OR e.cascade_run_id IS NOT NULL
            ORDER BY e.started_at DESC LIMIT ?
            """,
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            output_stage, input_stage = row[9], row[10]
            from_stage = PREV_STAGE.get(output_stage, input_stage or "?") if output_stage else (input_stage or "?")  # noqa: E501
            results.append({
                "exec_id": row[0], "input_id": row[1], "input_title": row[2],
                "status": row[3], "started_at": row[4], "completed_at": row[5],
                "log_file": row[6], "output_id": row[7], "output_title": row[8],
                "output_stage": output_stage, "from_stage": from_stage,
            })
        return results

def get_child_info(parent_id: int) -> dict[str, Any] | None:
    """Get info about the first child document of a parent."""
    with db_connection.get_connection() as conn:
        row = conn.execute(
            "SELECT id, title, stage FROM documents WHERE parent_id = ? LIMIT 1",
            (parent_id,),
        ).fetchone()
        return {"id": row[0], "title": row[1], "stage": row[2]} if row else None

def get_document_pr_url(doc_id: int) -> str | None:
    """Get PR URL for a document."""
    with db_connection.get_connection() as conn:
        row = conn.execute("SELECT pr_url FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return row[0] if row and row[0] else None



def get_orphaned_cascade_executions(
    cutoff_iso: str, limit: int = 50,
) -> list[dict[str, Any]]:
    """Get cascade executions not associated with any cascade run.

    These are legacy executions from before cascade_runs existed, or executions
    where the cascade_run was deleted. Used for backward compatibility in activity view.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at,
                   e.completed_at, d.stage, d.pr_url, e.cascade_run_id
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.doc_id IS NOT NULL
              AND e.started_at > ?
              AND (e.cascade_run_id IS NULL
                   OR e.cascade_run_id NOT IN (SELECT id FROM cascade_runs))
              AND e.id = (
                  SELECT MAX(e2.id) FROM executions e2
                  WHERE e2.doc_id = e.doc_id
              )
            ORDER BY e.started_at DESC
            LIMIT ?
            """,
            (cutoff_iso, limit),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "doc_id": row[1],
            "doc_title": row[2],
            "status": row[3],
            "started_at": row[4],
            "completed_at": row[5],
            "stage": row[6],
            "pr_url": row[7],
            "cascade_run_id": row[8],
        }
        for row in rows
    ]


def monitor_execution_completion(
    exec_id: int,
    doc_id: int,
    doc: dict,
    stage: str,
    log_file: Path,
    next_stage_map: dict,
    on_update: Callable[[str], None],
    save_doc: Callable,
) -> None:
    """Poll a detached execution's log file for completion.

    Runs synchronously — caller should run in a background thread.
    Calls on_update(status_markup) for UI feedback.
    """
    from emdx.models.executions import get_execution, update_execution_status

    poll_interval = 2.0
    max_wait = 1800 if stage == "planned" else 300
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if elapsed > max_wait:
            exec_record = get_execution(exec_id)
            if exec_record and exec_record.pid:
                try:
                    os.kill(exec_record.pid, 9)
                except ProcessLookupError:
                    pass
            update_execution_status(exec_id, "failed", exit_code=-1)
            on_update(f"[red]\u2717 Timeout[/red] after {max_wait}s")
            return

        if log_file.exists():
            try:
                for line in log_file.read_text().splitlines():
                    if line.startswith('{') and '"type":"result"' in line:
                        try:
                            result = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if result.get("is_error"):
                            update_execution_status(exec_id, "failed", exit_code=1)
                            on_update("[red]\u2717 Failed[/red]")
                        else:
                            update_execution_status(exec_id, "completed", exit_code=0)
                            output = result.get("result", "")
                            if output:
                                next_stage = next_stage_map.get(stage, "done")
                                new_id = save_doc(
                                    title=f"{doc.get('title', '')} [{stage}\u2192{next_stage}]",
                                    content=output, project=doc.get("project"), parent_id=doc_id,
                                )
                                update_cascade_stage(new_id, next_stage)
                                update_cascade_stage(doc_id, "done")
                                on_update(f"[green]\u2713 Done![/green] Created #{new_id} at {next_stage}")  # noqa: E501
                            else:
                                on_update("[green]\u2713 Completed[/green]")
                        return
            except Exception as e:
                logger.debug(f"Error reading log file: {e}")

        exec_record = get_execution(exec_id)
        if exec_record and exec_record.is_zombie:
            update_execution_status(exec_id, "failed", exit_code=-1)
            on_update("[red]\u2717 Process died[/red]")
            return

        time.sleep(poll_interval)
