"""Database operations for presets."""

from datetime import datetime
from typing import List, Optional

from ..database.connection import db_connection
from .models import Preset


def create_preset(
    name: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    discover_command: Optional[str] = None,
    task_template: Optional[str] = None,
    synthesize: bool = False,
    max_jobs: Optional[int] = None,
) -> Preset:
    """Create a new preset."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO run_presets
            (name, display_name, description, discover_command,
             task_template, synthesize, max_jobs)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, display_name or name, description, discover_command,
             task_template, synthesize, max_jobs),
        )
        conn.commit()
        preset_id = cursor.lastrowid

        return get_preset_by_id(preset_id)


def get_preset(name: str) -> Optional[Preset]:
    """Get preset by name."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM run_presets WHERE name = ? AND is_active = TRUE",
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return Preset.from_row(dict(row))
        return None


def get_preset_by_id(preset_id: int) -> Optional[Preset]:
    """Get preset by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM run_presets WHERE id = ?",
            (preset_id,),
        )
        row = cursor.fetchone()
        if row:
            return Preset.from_row(dict(row))
        return None


def list_presets(include_inactive: bool = False) -> List[Preset]:
    """List all presets."""
    with db_connection.get_connection() as conn:
        if include_inactive:
            cursor = conn.execute(
                "SELECT * FROM run_presets ORDER BY usage_count DESC, name"
            )
        else:
            cursor = conn.execute(
                """SELECT * FROM run_presets
                   WHERE is_active = TRUE
                   ORDER BY usage_count DESC, name"""
            )
        return [Preset.from_row(dict(row)) for row in cursor.fetchall()]


def update_preset(
    name: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    discover_command: Optional[str] = None,
    task_template: Optional[str] = None,
    synthesize: Optional[bool] = None,
    max_jobs: Optional[int] = None,
) -> Optional[Preset]:
    """Update a preset."""
    updates = []
    params = []

    if display_name is not None:
        updates.append("display_name = ?")
        params.append(display_name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if discover_command is not None:
        updates.append("discover_command = ?")
        params.append(discover_command)
    if task_template is not None:
        updates.append("task_template = ?")
        params.append(task_template)
    if synthesize is not None:
        updates.append("synthesize = ?")
        params.append(synthesize)
    if max_jobs is not None:
        updates.append("max_jobs = ?")
        params.append(max_jobs)

    if not updates:
        return get_preset(name)

    updates.append("updated_at = ?")
    params.append(datetime.now())
    params.append(name)

    with db_connection.get_connection() as conn:
        conn.execute(
            f"UPDATE run_presets SET {', '.join(updates)} WHERE name = ?",
            params,
        )
        conn.commit()
        return get_preset(name)


def delete_preset(name: str) -> bool:
    """Soft-delete a preset."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "UPDATE run_presets SET is_active = FALSE WHERE name = ?",
            (name,),
        )
        conn.commit()
        return cursor.rowcount > 0


def increment_usage(name: str) -> None:
    """Increment usage count for a preset."""
    with db_connection.get_connection() as conn:
        conn.execute(
            """UPDATE run_presets
               SET usage_count = usage_count + 1, last_used_at = ?
               WHERE name = ?""",
            (datetime.now(), name),
        )
        conn.commit()
