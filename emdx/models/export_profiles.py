"""Export profile model operations for emdx.

This module provides CRUD operations for export profiles, which are
reusable configurations for transforming and exporting documents.
"""

import json
from datetime import datetime
from typing import Any, Optional

from emdx.database import db_connection


def create_profile(
    name: str,
    display_name: str,
    description: Optional[str] = None,
    format: str = "markdown",
    strip_tags: Optional[list[str]] = None,
    add_frontmatter: bool = False,
    frontmatter_fields: Optional[list[str]] = None,
    header_template: Optional[str] = None,
    footer_template: Optional[str] = None,
    tag_to_label: Optional[dict[str, str]] = None,
    dest_type: str = "clipboard",
    dest_path: Optional[str] = None,
    gdoc_folder: Optional[str] = None,
    gist_public: bool = False,
    post_actions: Optional[list[str]] = None,
    project: Optional[str] = None,
) -> int:
    """Create a new export profile.

    Args:
        name: Unique profile identifier (e.g., 'blog-post')
        display_name: Human-readable name
        description: Profile description
        format: Output format (markdown, gdoc, gist, etc.)
        strip_tags: List of emoji tags to strip from content
        add_frontmatter: Whether to add YAML frontmatter
        frontmatter_fields: List of fields to include in frontmatter
        header_template: Template to prepend to content
        footer_template: Template to append to content
        tag_to_label: Mapping of emoji tags to text labels
        dest_type: Destination type (clipboard, file, gdoc, gist)
        dest_path: File path for file destination
        gdoc_folder: Google Drive folder for gdoc destination
        gist_public: Whether to create public gists
        post_actions: List of post-export actions
        project: Project scope (None = global)

    Returns:
        The ID of the created profile
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO export_profiles (
                name, display_name, description, format,
                strip_tags, add_frontmatter, frontmatter_fields,
                header_template, footer_template, tag_to_label,
                dest_type, dest_path, gdoc_folder, gist_public,
                post_actions, project
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                name,
                display_name,
                description,
                format,
                json.dumps(strip_tags) if strip_tags else None,
                add_frontmatter,
                json.dumps(frontmatter_fields) if frontmatter_fields else None,
                header_template,
                footer_template,
                json.dumps(tag_to_label) if tag_to_label else None,
                dest_type,
                dest_path,
                gdoc_folder,
                gist_public,
                json.dumps(post_actions) if post_actions else None,
                project,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_profile(name_or_id: str | int) -> Optional[dict[str, Any]]:
    """Get an export profile by name or ID.

    Args:
        name_or_id: Profile name (string) or ID (integer)

    Returns:
        Profile dictionary or None if not found
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        if isinstance(name_or_id, int) or (
            isinstance(name_or_id, str) and name_or_id.isdigit()
        ):
            profile_id = int(name_or_id)
            cursor.execute(
                "SELECT * FROM export_profiles WHERE id = ? AND is_active = TRUE",
                (profile_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM export_profiles WHERE name = ? AND is_active = TRUE",
                (name_or_id,),
            )

        row = cursor.fetchone()
        if row:
            return _row_to_profile(row)
        return None


def list_profiles(
    project: Optional[str] = None,
    include_builtin: bool = True,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List all export profiles.

    Args:
        project: Filter by project (None = global profiles only)
        include_builtin: Include built-in profiles
        include_inactive: Include inactive profiles

    Returns:
        List of profile dictionaries
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        conditions = []
        params = []

        if not include_inactive:
            conditions.append("is_active = TRUE")

        if project is not None:
            # Include global profiles and project-specific profiles
            conditions.append("(project IS NULL OR project = ?)")
            params.append(project)
        else:
            # Only global profiles
            conditions.append("project IS NULL")

        if not include_builtin:
            conditions.append("is_builtin = FALSE")

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"""
            SELECT * FROM export_profiles
            WHERE {where_clause}
            ORDER BY use_count DESC, display_name ASC
        """

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [_row_to_profile(row) for row in rows]


def update_profile(name_or_id: str | int, **kwargs) -> bool:
    """Update an export profile.

    Args:
        name_or_id: Profile name or ID
        **kwargs: Fields to update

    Returns:
        True if profile was updated, False otherwise
    """
    profile = get_profile(name_or_id)
    if not profile:
        return False

    # Prevent updating built-in profiles' core configuration
    if profile.get("is_builtin"):
        # Only allow updating use_count and last_used_at for built-in profiles
        allowed_fields = {"use_count", "last_used_at", "is_active"}
        if not set(kwargs.keys()).issubset(allowed_fields):
            raise ValueError("Cannot modify built-in profile configuration")

    # JSON-encode list/dict fields
    for field in ["strip_tags", "frontmatter_fields", "post_actions"]:
        if field in kwargs and kwargs[field] is not None:
            kwargs[field] = json.dumps(kwargs[field])

    if "tag_to_label" in kwargs and kwargs["tag_to_label"] is not None:
        kwargs["tag_to_label"] = json.dumps(kwargs["tag_to_label"])

    # Build update query
    set_clauses = [f"{key} = ?" for key in kwargs.keys()]
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE export_profiles
            SET {', '.join(set_clauses)}
            WHERE id = ?
        """,
            (*kwargs.values(), profile["id"]),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_profile(name_or_id: str | int, hard_delete: bool = False) -> bool:
    """Delete an export profile.

    Args:
        name_or_id: Profile name or ID
        hard_delete: If True, permanently delete; otherwise soft delete

    Returns:
        True if profile was deleted, False otherwise
    """
    profile = get_profile(name_or_id)
    if not profile:
        return False

    # Prevent deleting built-in profiles
    if profile.get("is_builtin"):
        raise ValueError("Cannot delete built-in profiles")

    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        if hard_delete:
            cursor.execute("DELETE FROM export_profiles WHERE id = ?", (profile["id"],))
        else:
            cursor.execute(
                """
                UPDATE export_profiles
                SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (profile["id"],),
            )

        conn.commit()
        return cursor.rowcount > 0


def increment_use_count(profile_id: int) -> None:
    """Increment the use count for a profile.

    Args:
        profile_id: Profile ID
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE export_profiles
            SET use_count = use_count + 1,
                last_used_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (profile_id,),
        )
        conn.commit()


def record_export(
    document_id: int,
    profile_id: int,
    dest_type: str,
    dest_url: Optional[str] = None,
) -> int:
    """Record an export in the history.

    Args:
        document_id: Document ID that was exported
        profile_id: Profile ID that was used
        dest_type: Destination type
        dest_url: URL or path where exported

    Returns:
        The ID of the export history record
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO export_history (document_id, profile_id, dest_type, dest_url)
            VALUES (?, ?, ?, ?)
        """,
            (document_id, profile_id, dest_type, dest_url),
        )
        conn.commit()

        # Also increment use count
        increment_use_count(profile_id)

        return cursor.lastrowid


def get_export_history(
    document_id: Optional[int] = None,
    profile_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get export history.

    Args:
        document_id: Filter by document ID
        profile_id: Filter by profile ID
        limit: Maximum number of records to return

    Returns:
        List of export history records
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()

        conditions = []
        params = []

        if document_id is not None:
            conditions.append("eh.document_id = ?")
            params.append(document_id)

        if profile_id is not None:
            conditions.append("eh.profile_id = ?")
            params.append(profile_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        cursor.execute(
            f"""
            SELECT eh.*, ep.name as profile_name, ep.display_name as profile_display_name,
                   d.title as document_title
            FROM export_history eh
            JOIN export_profiles ep ON eh.profile_id = ep.id
            JOIN documents d ON eh.document_id = d.id
            WHERE {where_clause}
            ORDER BY eh.exported_at DESC
            LIMIT ?
        """,
            params,
        )

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def _row_to_profile(row) -> dict[str, Any]:
    """Convert a database row to a profile dictionary.

    Parses JSON fields and converts types appropriately.
    """
    profile = dict(row)

    # Parse JSON fields
    for field in ["strip_tags", "frontmatter_fields", "post_actions"]:
        if profile.get(field):
            try:
                profile[field] = json.loads(profile[field])
            except (json.JSONDecodeError, TypeError):
                profile[field] = None

    if profile.get("tag_to_label"):
        try:
            profile["tag_to_label"] = json.loads(profile["tag_to_label"])
        except (json.JSONDecodeError, TypeError):
            profile["tag_to_label"] = None

    # Convert boolean fields
    for field in ["add_frontmatter", "gist_public", "is_active", "is_builtin"]:
        if field in profile:
            profile[field] = bool(profile[field])

    return profile
