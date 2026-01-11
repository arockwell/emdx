"""Database operations for workflow orchestration system."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from emdx.database.connection import db_connection


# =============================================================================
# Workflow CRUD operations
# =============================================================================

def create_workflow(
    name: str,
    display_name: str,
    definition_json: str,
    description: Optional[str] = None,
    category: str = 'custom',
    created_by: Optional[str] = None,
) -> int:
    """Create a new workflow definition."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflows (name, display_name, description, definition_json, category, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, display_name, description, definition_json, category, created_by),
        )
        conn.commit()
        return cursor.lastrowid


def get_workflow(workflow_id: int) -> Optional[Dict[str, Any]]:
    """Get a workflow by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflows WHERE id = ? AND is_active = TRUE",
            (workflow_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_workflow_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a workflow by name."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflows WHERE name = ? AND is_active = TRUE",
            (name,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_workflows(
    category: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List workflows with optional filtering."""
    with db_connection.get_connection() as conn:
        query = "SELECT * FROM workflows WHERE 1=1"
        params = []

        if not include_inactive:
            query += " AND is_active = TRUE"

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY usage_count DESC, name ASC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_workflow(
    workflow_id: int,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    definition_json: Optional[str] = None,
    category: Optional[str] = None,
) -> bool:
    """Update a workflow definition."""
    with db_connection.get_connection() as conn:
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params = []

        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if definition_json is not None:
            updates.append("definition_json = ?")
            params.append(definition_json)
        if category is not None:
            updates.append("category = ?")
            params.append(category)

        params.append(workflow_id)
        cursor = conn.execute(
            f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_workflow(workflow_id: int, hard_delete: bool = False) -> bool:
    """Delete a workflow (soft delete by default)."""
    with db_connection.get_connection() as conn:
        if hard_delete:
            cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        else:
            cursor = conn.execute(
                "UPDATE workflows SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (workflow_id,),
            )
        conn.commit()
        return cursor.rowcount > 0


def increment_workflow_usage(workflow_id: int, success: bool = True) -> None:
    """Increment usage count and optionally success/failure count."""
    with db_connection.get_connection() as conn:
        if success:
            conn.execute(
                """
                UPDATE workflows
                SET usage_count = usage_count + 1,
                    success_count = success_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (workflow_id,),
            )
        else:
            conn.execute(
                """
                UPDATE workflows
                SET usage_count = usage_count + 1,
                    failure_count = failure_count + 1,
                    last_used_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (workflow_id,),
            )
        conn.commit()


# =============================================================================
# Workflow Run operations
# =============================================================================

def create_workflow_run(
    workflow_id: int,
    input_doc_id: Optional[int] = None,
    input_variables: Optional[Dict[str, Any]] = None,
    gameplan_id: Optional[int] = None,
    task_id: Optional[int] = None,
    parent_run_id: Optional[int] = None,
) -> int:
    """Create a new workflow run."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs
            (workflow_id, input_doc_id, input_variables, gameplan_id, task_id, parent_run_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                workflow_id,
                input_doc_id,
                json.dumps(input_variables) if input_variables else None,
                gameplan_id,
                task_id,
                parent_run_id,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_workflow_run(run_id: int) -> Optional[Dict[str, Any]]:
    """Get a workflow run by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_workflow_runs(
    workflow_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List workflow runs with optional filtering."""
    with db_connection.get_connection() as conn:
        query = "SELECT * FROM workflow_runs WHERE 1=1"
        params = []

        if workflow_id:
            query += " AND workflow_id = ?"
            params.append(workflow_id)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_workflow_run(
    run_id: int,
    status: Optional[str] = None,
    current_stage: Optional[str] = None,
    current_stage_run: Optional[int] = None,
    context_json: Optional[str] = None,
    output_doc_ids: Optional[List[int]] = None,
    error_message: Optional[str] = None,
    total_tokens_used: Optional[int] = None,
    total_execution_time_ms: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> bool:
    """Update a workflow run."""
    with db_connection.get_connection() as conn:
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if current_stage is not None:
            updates.append("current_stage = ?")
            params.append(current_stage)
        if current_stage_run is not None:
            updates.append("current_stage_run = ?")
            params.append(current_stage_run)
        if context_json is not None:
            updates.append("context_json = ?")
            params.append(context_json)
        if output_doc_ids is not None:
            updates.append("output_doc_ids = ?")
            params.append(json.dumps(output_doc_ids))
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if total_tokens_used is not None:
            updates.append("total_tokens_used = ?")
            params.append(total_tokens_used)
        if total_execution_time_ms is not None:
            updates.append("total_execution_time_ms = ?")
            params.append(total_execution_time_ms)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at.isoformat() if isinstance(started_at, datetime) else started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at)

        if not updates:
            return False

        params.append(run_id)
        cursor = conn.execute(
            f"UPDATE workflow_runs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def cleanup_zombie_workflow_runs(max_age_hours: float = 2.0) -> int:
    """Mark stale 'running' workflow runs as failed.

    This cleans up zombie runs from processes that died without updating status.
    Call this on application startup.

    Args:
        max_age_hours: Workflows running longer than this are considered zombies

    Returns:
        Number of workflow runs marked as failed
    """
    with db_connection.get_connection() as conn:
        # Find and update zombie runs
        cursor = conn.execute(
            """
            UPDATE workflow_runs
            SET status = 'failed',
                error_message = 'Marked as failed: process appears to have died without cleanup',
                completed_at = datetime('now')
            WHERE status = 'running'
            AND started_at < datetime('now', ? || ' hours')
            """,
            (f"-{max_age_hours}",),
        )
        conn.commit()

        # Also clean up associated stage runs and individual runs
        conn.execute(
            """
            UPDATE workflow_stage_runs
            SET status = 'failed'
            WHERE status IN ('pending', 'running')
            AND workflow_run_id IN (
                SELECT id FROM workflow_runs
                WHERE status = 'failed'
                AND error_message LIKE 'Marked as failed: process appears%'
            )
            """
        )
        conn.execute(
            """
            UPDATE workflow_individual_runs
            SET status = 'failed'
            WHERE status IN ('pending', 'running')
            AND stage_run_id IN (
                SELECT id FROM workflow_stage_runs
                WHERE status = 'failed'
                AND workflow_run_id IN (
                    SELECT id FROM workflow_runs
                    WHERE status = 'failed'
                    AND error_message LIKE 'Marked as failed: process appears%'
                )
            )
            """
        )
        conn.commit()

        return cursor.rowcount


# =============================================================================
# Workflow Stage Run operations
# =============================================================================

def create_stage_run(
    workflow_run_id: int,
    stage_name: str,
    mode: str,
    target_runs: int,
) -> int:
    """Create a new stage run."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_stage_runs
            (workflow_run_id, stage_name, mode, target_runs, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (workflow_run_id, stage_name, mode, target_runs),
        )
        conn.commit()
        return cursor.lastrowid


def get_stage_run(stage_run_id: int) -> Optional[Dict[str, Any]]:
    """Get a stage run by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM workflow_stage_runs WHERE id = ?", (stage_run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_stage_runs(workflow_run_id: int) -> List[Dict[str, Any]]:
    """List all stage runs for a workflow run."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_stage_runs WHERE workflow_run_id = ? ORDER BY id",
            (workflow_run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_stage_run(
    stage_run_id: int,
    status: Optional[str] = None,
    runs_completed: Optional[int] = None,
    target_runs: Optional[int] = None,
    output_doc_id: Optional[int] = None,
    synthesis_doc_id: Optional[int] = None,
    error_message: Optional[str] = None,
    tokens_used: Optional[int] = None,
    execution_time_ms: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> bool:
    """Update a stage run."""
    with db_connection.get_connection() as conn:
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if runs_completed is not None:
            updates.append("runs_completed = ?")
            params.append(runs_completed)
        if target_runs is not None:
            updates.append("target_runs = ?")
            params.append(target_runs)
        if output_doc_id is not None:
            updates.append("output_doc_id = ?")
            params.append(output_doc_id)
        if synthesis_doc_id is not None:
            updates.append("synthesis_doc_id = ?")
            params.append(synthesis_doc_id)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if tokens_used is not None:
            updates.append("tokens_used = ?")
            params.append(tokens_used)
        if execution_time_ms is not None:
            updates.append("execution_time_ms = ?")
            params.append(execution_time_ms)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at.isoformat() if isinstance(started_at, datetime) else started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at)

        if not updates:
            return False

        params.append(stage_run_id)
        cursor = conn.execute(
            f"UPDATE workflow_stage_runs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Workflow Individual Run operations
# =============================================================================

def create_individual_run(
    stage_run_id: int,
    run_number: int,
    prompt_used: Optional[str] = None,
    input_context: Optional[str] = None,
) -> int:
    """Create a new individual run within a stage."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO workflow_individual_runs
            (stage_run_id, run_number, prompt_used, input_context, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (stage_run_id, run_number, prompt_used, input_context),
        )
        conn.commit()
        return cursor.lastrowid


def get_individual_run(individual_run_id: int) -> Optional[Dict[str, Any]]:
    """Get an individual run by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_individual_runs WHERE id = ?",
            (individual_run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_individual_runs(stage_run_id: int) -> List[Dict[str, Any]]:
    """List all individual runs for a stage run."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM workflow_individual_runs WHERE stage_run_id = ? ORDER BY run_number",
            (stage_run_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def count_individual_runs(stage_run_id: int) -> Dict[str, int]:
    """Count individual runs by status for a stage run.

    Returns:
        Dict with 'total', 'completed', 'running', 'failed', 'pending' counts
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """SELECT status, COUNT(*) as count
               FROM workflow_individual_runs
               WHERE stage_run_id = ?
               GROUP BY status""",
            (stage_run_id,),
        )
        counts = {'total': 0, 'completed': 0, 'running': 0, 'failed': 0, 'pending': 0}
        for row in cursor.fetchall():
            status = row['status'] or 'pending'
            counts[status] = row['count']
            counts['total'] += row['count']
        return counts


def update_individual_run(
    individual_run_id: int,
    status: Optional[str] = None,
    agent_execution_id: Optional[int] = None,
    output_doc_id: Optional[int] = None,
    error_message: Optional[str] = None,
    tokens_used: Optional[int] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    execution_time_ms: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> bool:
    """Update an individual run."""
    with db_connection.get_connection() as conn:
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if agent_execution_id is not None:
            updates.append("agent_execution_id = ?")
            params.append(agent_execution_id)
        if output_doc_id is not None:
            updates.append("output_doc_id = ?")
            params.append(output_doc_id)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if tokens_used is not None:
            updates.append("tokens_used = ?")
            params.append(tokens_used)
        if input_tokens is not None:
            updates.append("input_tokens = ?")
            params.append(input_tokens)
        if output_tokens is not None:
            updates.append("output_tokens = ?")
            params.append(output_tokens)
        if cost_usd is not None:
            updates.append("cost_usd = ?")
            params.append(cost_usd)
        if execution_time_ms is not None:
            updates.append("execution_time_ms = ?")
            params.append(execution_time_ms)
        if started_at is not None:
            updates.append("started_at = ?")
            params.append(started_at.isoformat() if isinstance(started_at, datetime) else started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at)

        if not updates:
            return False

        params.append(individual_run_id)
        cursor = conn.execute(
            f"UPDATE workflow_individual_runs SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


# =============================================================================
# Iteration Strategy operations
# =============================================================================

def get_iteration_strategy(strategy_id: int) -> Optional[Dict[str, Any]]:
    """Get an iteration strategy by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM iteration_strategies WHERE id = ?",
            (strategy_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_iteration_strategy_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get an iteration strategy by name."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM iteration_strategies WHERE name = ?",
            (name,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_iteration_strategies(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """List iteration strategies with optional category filter."""
    with db_connection.get_connection() as conn:
        if category:
            cursor = conn.execute(
                "SELECT * FROM iteration_strategies WHERE category = ? ORDER BY name",
                (category,),
            )
        else:
            cursor = conn.execute("SELECT * FROM iteration_strategies ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]


def create_iteration_strategy(
    name: str,
    display_name: str,
    prompts: List[str],
    description: Optional[str] = None,
    recommended_runs: int = 5,
    category: str = 'general',
) -> int:
    """Create a new iteration strategy."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO iteration_strategies
            (name, display_name, description, prompts_json, recommended_runs, category)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, display_name, description, json.dumps(prompts), recommended_runs, category),
        )
        conn.commit()
        return cursor.lastrowid


def get_active_execution_for_run(workflow_run_id: int) -> Optional[Dict[str, Any]]:
    """Get the currently running execution (log file) for a workflow run.

    Returns the execution record with log_file path if there's an active individual run.
    """
    with db_connection.get_connection() as conn:
        # Find any running individual run for this workflow
        cursor = conn.execute(
            """
            SELECT ir.*, sr.stage_name
            FROM workflow_individual_runs ir
            JOIN workflow_stage_runs sr ON ir.stage_run_id = sr.id
            WHERE sr.workflow_run_id = ?
            AND ir.status = 'running'
            ORDER BY ir.id DESC
            LIMIT 1
            """,
            (workflow_run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        result = dict(row)

        # Try to find execution by agent_execution_id first
        if result.get('agent_execution_id'):
            exec_cursor = conn.execute(
                "SELECT log_file, status as exec_status FROM executions WHERE id = ?",
                (result['agent_execution_id'],),
            )
            exec_row = exec_cursor.fetchone()
            if exec_row:
                result['log_file'] = exec_row['log_file']
                result['exec_status'] = exec_row['exec_status']
                return result

        # Fallback: find execution by title pattern "Workflow Agent Run #{individual_run_id}"
        individual_run_id = result['id']
        exec_cursor = conn.execute(
            """
            SELECT log_file, status as exec_status FROM executions
            WHERE doc_title LIKE ?
            AND status = 'running'
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"Workflow Agent Run #{individual_run_id}%",),
        )
        exec_row = exec_cursor.fetchone()
        if exec_row:
            result['log_file'] = exec_row['log_file']
            result['exec_status'] = exec_row['exec_status']
        else:
            result['log_file'] = None
            result['exec_status'] = None

        return result


def get_agent_execution(execution_id: int) -> Optional[Dict[str, Any]]:
    """Get an execution record by ID.

    Returns the execution record with log_file path.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM executions WHERE id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_latest_execution_for_run(workflow_run_id: int) -> Optional[Dict[str, Any]]:
    """Get the most recent execution (with log file) for a workflow run.

    Returns the execution record for the most recently started individual run,
    regardless of status. Useful for showing what just ran.
    """
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT ir.*, sr.stage_name, e.log_file, e.status as exec_status
            FROM workflow_individual_runs ir
            JOIN workflow_stage_runs sr ON ir.stage_run_id = sr.id
            LEFT JOIN executions e ON ir.agent_execution_id = e.id
            WHERE sr.workflow_run_id = ?
            AND e.log_file IS NOT NULL
            ORDER BY ir.started_at DESC, ir.id DESC
            LIMIT 1
            """,
            (workflow_run_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
