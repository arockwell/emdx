"""Database operations for custom discoveries.

Custom discoveries allow users to register their own discovery patterns
that can be used just like built-in discoveries.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ..database.connection import db_connection


@dataclass
class CustomDiscovery:
    """A user-defined discovery command.

    Stored in the database for persistence across sessions.
    """

    id: int
    name: str
    command: str
    description: Optional[str]
    category: str
    requires: Optional[List[str]]
    example_output: Optional[str]
    created_at: datetime
    updated_at: datetime
    usage_count: int
    last_used_at: Optional[datetime]
    is_active: bool

    @classmethod
    def from_row(cls, row: dict) -> "CustomDiscovery":
        """Create CustomDiscovery from database row."""
        requires = None
        if row.get("requires"):
            try:
                requires = json.loads(row["requires"])
            except (json.JSONDecodeError, TypeError):
                requires = []

        return cls(
            id=row["id"],
            name=row["name"],
            command=row["command"],
            description=row.get("description"),
            category=row.get("category", "custom"),
            requires=requires,
            example_output=row.get("example_output"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            usage_count=row.get("usage_count", 0),
            last_used_at=row.get("last_used_at"),
            is_active=bool(row.get("is_active", True)),
        )


def ensure_table():
    """Ensure the custom_discoveries table exists.

    This is called lazily when first accessing custom discoveries.
    The table is created via migration 028, but this provides a fallback.
    """
    with db_connection.get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_discoveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                command TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'custom',
                requires TEXT,
                example_output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_discoveries_name ON custom_discoveries(name)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_discoveries_active ON custom_discoveries(is_active)"
        )
        conn.commit()


def create_discovery(
    name: str,
    command: str,
    description: Optional[str] = None,
    category: str = "custom",
    requires: Optional[List[str]] = None,
    example_output: Optional[str] = None,
) -> CustomDiscovery:
    """Create a new custom discovery.

    Args:
        name: Unique name for the discovery (used with @ prefix)
        command: Shell command that outputs items (one per line)
        description: Human-readable description
        category: Category for organization (default: custom)
        requires: List of required CLI tools
        example_output: Example output for help text

    Returns:
        The created CustomDiscovery

    Raises:
        ValueError: If a discovery with this name already exists
    """
    ensure_table()

    requires_json = json.dumps(requires) if requires else None

    with db_connection.get_connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO custom_discoveries
                (name, command, description, category, requires, example_output)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, command, description, category, requires_json, example_output),
            )
            conn.commit()
            discovery_id = cursor.lastrowid
            return get_discovery_by_id(discovery_id)
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Discovery '@{name}' already exists")
            raise


def get_discovery(name: str) -> Optional[CustomDiscovery]:
    """Get a custom discovery by name.

    Args:
        name: Discovery name (without @ prefix)

    Returns:
        CustomDiscovery if found, None otherwise
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM custom_discoveries WHERE name = ? AND is_active = TRUE",
            (name,),
        )
        row = cursor.fetchone()
        if row:
            return CustomDiscovery.from_row(dict(row))
        return None


def get_discovery_by_id(discovery_id: int) -> Optional[CustomDiscovery]:
    """Get a custom discovery by ID.

    Args:
        discovery_id: Discovery ID

    Returns:
        CustomDiscovery if found, None otherwise
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM custom_discoveries WHERE id = ?",
            (discovery_id,),
        )
        row = cursor.fetchone()
        if row:
            return CustomDiscovery.from_row(dict(row))
        return None


def list_discoveries(include_inactive: bool = False) -> List[CustomDiscovery]:
    """List all custom discoveries.

    Args:
        include_inactive: Include soft-deleted discoveries

    Returns:
        List of CustomDiscovery objects
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        if include_inactive:
            cursor = conn.execute(
                "SELECT * FROM custom_discoveries ORDER BY usage_count DESC, name"
            )
        else:
            cursor = conn.execute(
                """SELECT * FROM custom_discoveries
                   WHERE is_active = TRUE
                   ORDER BY usage_count DESC, name"""
            )
        return [CustomDiscovery.from_row(dict(row)) for row in cursor.fetchall()]


def update_discovery(
    name: str,
    command: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    requires: Optional[List[str]] = None,
    example_output: Optional[str] = None,
) -> Optional[CustomDiscovery]:
    """Update a custom discovery.

    Args:
        name: Discovery name to update
        command: New shell command
        description: New description
        category: New category
        requires: New list of required tools
        example_output: New example output

    Returns:
        Updated CustomDiscovery, or None if not found
    """
    ensure_table()

    updates = []
    params = []

    if command is not None:
        updates.append("command = ?")
        params.append(command)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if category is not None:
        updates.append("category = ?")
        params.append(category)
    if requires is not None:
        updates.append("requires = ?")
        params.append(json.dumps(requires))
    if example_output is not None:
        updates.append("example_output = ?")
        params.append(example_output)

    if not updates:
        return get_discovery(name)

    updates.append("updated_at = ?")
    params.append(datetime.now())
    params.append(name)

    with db_connection.get_connection() as conn:
        conn.execute(
            f"UPDATE custom_discoveries SET {', '.join(updates)} WHERE name = ?",
            params,
        )
        conn.commit()
        return get_discovery(name)


def delete_discovery(name: str) -> bool:
    """Soft-delete a custom discovery.

    Args:
        name: Discovery name to delete

    Returns:
        True if discovery was deleted, False if not found
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "UPDATE custom_discoveries SET is_active = FALSE, updated_at = ? WHERE name = ?",
            (datetime.now(), name),
        )
        conn.commit()
        return cursor.rowcount > 0


def hard_delete_discovery(name: str) -> bool:
    """Permanently delete a custom discovery.

    Args:
        name: Discovery name to delete

    Returns:
        True if discovery was deleted, False if not found
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM custom_discoveries WHERE name = ?",
            (name,),
        )
        conn.commit()
        return cursor.rowcount > 0


def increment_usage(name: str) -> None:
    """Increment usage count for a discovery.

    Called each time a discovery is used.

    Args:
        name: Discovery name
    """
    ensure_table()

    with db_connection.get_connection() as conn:
        conn.execute(
            """UPDATE custom_discoveries
               SET usage_count = usage_count + 1, last_used_at = ?
               WHERE name = ?""",
            (datetime.now(), name),
        )
        conn.commit()
