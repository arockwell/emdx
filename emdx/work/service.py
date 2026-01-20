"""
Service layer for the Unified Work System.

Handles all database operations and business logic for work items.
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from ..database import db
from ..utils.git import get_git_project
from .models import WorkItem, WorkDep, Cascade, WorkTransition

logger = logging.getLogger(__name__)

# Default cache TTL for cascades (60 seconds)
_DEFAULT_CASCADE_CACHE_TTL = 60.0


def generate_work_id(title: str, timestamp: Optional[datetime] = None) -> str:
    """Generate a short hash ID for a work item."""
    timestamp = timestamp or datetime.now()
    seed = f"{title}:{timestamp.isoformat()}"
    hash_hex = hashlib.sha256(seed.encode()).hexdigest()[:6]
    return f"emdx-{hash_hex}"


class WorkService:
    """Service for managing work items."""

    def __init__(self):
        """Initialize the work service with cascade caching."""
        self._cascade_cache: Dict[str, Cascade] = {}
        self._cascade_cache_time: float = 0.0
        self._cascade_cache_ttl: float = _DEFAULT_CASCADE_CACHE_TTL

    def _invalidate_cascade_cache(self) -> None:
        """Invalidate the cascade cache (call after cascade modifications)."""
        self._cascade_cache.clear()
        self._cascade_cache_time = 0.0

    def _is_cascade_cache_valid(self) -> bool:
        """Check if the cascade cache is still valid."""
        return (time.time() - self._cascade_cache_time) < self._cascade_cache_ttl

    # ==========================================================================
    # CASCADE OPERATIONS
    # ==========================================================================

    def get_cascade(self, name: str) -> Optional[Cascade]:
        """Get a cascade definition by name (with caching).

        Cascades are cached to reduce database queries and object allocations
        when checking blocker status in get() and list() methods.
        """
        # Check cache validity
        if not self._is_cascade_cache_valid():
            self._cascade_cache.clear()
            self._cascade_cache_time = time.time()

        # Return from cache if available
        if name in self._cascade_cache:
            return self._cascade_cache[name]

        # Load from database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, stages, processors, description, created_at FROM cascades WHERE name = ?",
                (name,)
            )
            row = cursor.fetchone()
            cascade = Cascade.from_row(row) if row else None

        # Store in cache (even None results to avoid repeated DB queries)
        if cascade is not None:
            self._cascade_cache[name] = cascade

        return cascade

    def list_cascades(self) -> List[Cascade]:
        """List all cascade definitions."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, stages, processors, description, created_at FROM cascades ORDER BY name"
            )
            return [Cascade.from_row(row) for row in cursor.fetchall()]

    def create_cascade(
        self,
        name: str,
        stages: List[str],
        processors: Optional[Dict[str, str]] = None,
        description: Optional[str] = None,
    ) -> Cascade:
        """Create a new cascade definition."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO cascades (name, stages, processors, description)
                VALUES (?, ?, ?, ?)
                """,
                (name, json.dumps(stages), json.dumps(processors or {}), description)
            )
            conn.commit()

        # Invalidate cascade cache after modification
        self._invalidate_cascade_cache()

        return Cascade(
            name=name,
            stages=stages,
            processors=processors or {},
            description=description,
        )

    # ==========================================================================
    # WORK ITEM OPERATIONS
    # ==========================================================================

    def add(
        self,
        title: str,
        cascade: str = "default",
        stage: Optional[str] = None,
        content: Optional[str] = None,
        priority: int = 3,
        type_: str = "task",
        parent_id: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        project: Optional[str] = None,
    ) -> WorkItem:
        """Add a new work item."""
        # Get cascade definition to validate and determine initial stage
        cascade_def = self.get_cascade(cascade)
        if not cascade_def:
            raise ValueError(f"Unknown cascade: {cascade}")

        # Default to first stage if not specified
        if stage is None:
            stage = cascade_def.stages[0]
        elif stage not in cascade_def.stages:
            raise ValueError(f"Invalid stage '{stage}' for cascade '{cascade}'")

        # Generate ID and determine project
        work_id = generate_work_id(title)
        project = project or get_git_project()

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Insert work item
            cursor.execute(
                """
                INSERT INTO work_items (
                    id, title, content, cascade, stage, priority, type, parent_id, project
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (work_id, title, content, cascade, stage, priority, type_, parent_id, project)
            )

            # Add initial transition
            cursor.execute(
                """
                INSERT INTO work_transitions (work_id, from_stage, to_stage, transitioned_by)
                VALUES (?, NULL, ?, 'created')
                """,
                (work_id, stage)
            )

            # Add dependencies if specified
            if depends_on:
                for dep_id in depends_on:
                    cursor.execute(
                        """
                        INSERT INTO work_deps (work_id, depends_on, dep_type)
                        VALUES (?, ?, 'blocks')
                        """,
                        (work_id, dep_id)
                    )

            conn.commit()

        return self.get(work_id)

    def get(self, work_id: str) -> Optional[WorkItem]:
        """Get a work item by ID."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, content, cascade, stage, priority, type,
                       parent_id, project, pr_number, output_doc_id,
                       created_at, updated_at, started_at, completed_at,
                       claimed_by, claimed_at
                FROM work_items WHERE id = ?
                """,
                (work_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            item = WorkItem.from_row(row)

            # Check if blocked
            cursor.execute(
                """
                SELECT wd.depends_on, wi.stage, wi.title
                FROM work_deps wd
                JOIN work_items wi ON wd.depends_on = wi.id
                WHERE wd.work_id = ? AND wd.dep_type = 'blocks'
                """,
                (work_id,)
            )
            for dep_id, dep_stage, dep_title in cursor.fetchall():
                # Check if blocker is in a terminal state
                blocker_cascade = self.get_cascade(
                    self._get_work_cascade(cursor, dep_id)
                )
                if blocker_cascade and not blocker_cascade.is_terminal_stage(dep_stage):
                    item.is_blocked = True
                    item.blocked_by.append(dep_id)

            return item

    def _get_work_cascade(self, cursor, work_id: str) -> str:
        """Helper to get cascade name for a work item."""
        cursor.execute("SELECT cascade FROM work_items WHERE id = ?", (work_id,))
        row = cursor.fetchone()
        return row[0] if row else "default"

    def list(
        self,
        cascade: Optional[str] = None,
        stage: Optional[str] = None,
        include_done: bool = False,
        project: Optional[str] = None,
        limit: int = 100,
    ) -> List[WorkItem]:
        """List work items with optional filters."""
        conditions = []
        params = []

        if cascade:
            conditions.append("cascade = ?")
            params.append(cascade)

        if stage:
            conditions.append("stage = ?")
            params.append(stage)

        if not include_done:
            # Exclude common terminal stages
            conditions.append("stage NOT IN ('done', 'merged', 'conclusion', 'deployed', 'completed')")

        if project:
            conditions.append("project = ?")
            params.append(project)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, title, content, cascade, stage, priority, type,
                       parent_id, project, pr_number, output_doc_id,
                       created_at, updated_at, started_at, completed_at,
                       claimed_by, claimed_at
                FROM work_items
                WHERE {where_clause}
                ORDER BY priority ASC, created_at ASC
                LIMIT ?
                """,
                (*params, limit)
            )
            items = [WorkItem.from_row(row) for row in cursor.fetchall()]

            # Check blocked status for each item
            for item in items:
                cursor.execute(
                    """
                    SELECT wd.depends_on, wi.stage
                    FROM work_deps wd
                    JOIN work_items wi ON wd.depends_on = wi.id
                    WHERE wd.work_id = ? AND wd.dep_type = 'blocks'
                    """,
                    (item.id,)
                )
                for dep_id, dep_stage in cursor.fetchall():
                    blocker_cascade = self.get_cascade(item.cascade)
                    if blocker_cascade and not blocker_cascade.is_terminal_stage(dep_stage):
                        item.is_blocked = True
                        item.blocked_by.append(dep_id)

            return items

    def ready(
        self,
        cascade: Optional[str] = None,
        stage: Optional[str] = None,
        limit: int = 50,
    ) -> List[WorkItem]:
        """Get work items that are ready (unblocked, not claimed, not done)."""
        conditions = ["1=1"]
        params = []

        if cascade:
            conditions.append("w.cascade = ?")
            params.append(cascade)

        if stage:
            conditions.append("w.stage = ?")
            params.append(stage)

        # Exclude terminal stages
        conditions.append("w.stage NOT IN ('done', 'merged', 'conclusion', 'deployed', 'completed')")

        # Not claimed
        conditions.append("w.claimed_by IS NULL")

        where_clause = " AND ".join(conditions)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT w.id, w.title, w.content, w.cascade, w.stage, w.priority, w.type,
                       w.parent_id, w.project, w.pr_number, w.output_doc_id,
                       w.created_at, w.updated_at, w.started_at, w.completed_at,
                       w.claimed_by, w.claimed_at
                FROM work_items w
                WHERE {where_clause}
                AND NOT EXISTS (
                    SELECT 1 FROM work_deps wd
                    JOIN work_items blocker ON wd.depends_on = blocker.id
                    WHERE wd.work_id = w.id
                    AND wd.dep_type = 'blocks'
                    AND blocker.stage NOT IN ('done', 'merged', 'conclusion', 'deployed', 'completed')
                )
                ORDER BY w.priority ASC, w.created_at ASC
                LIMIT ?
                """,
                (*params, limit)
            )
            return [WorkItem.from_row(row) for row in cursor.fetchall()]

    def advance(
        self,
        work_id: str,
        transitioned_by: str = "manual",
        new_content: Optional[str] = None,
    ) -> WorkItem:
        """Advance a work item to the next stage in its cascade."""
        item = self.get(work_id)
        if not item:
            raise ValueError(f"Work item not found: {work_id}")

        cascade = self.get_cascade(item.cascade)
        if not cascade:
            raise ValueError(f"Cascade not found: {item.cascade}")

        next_stage = cascade.get_next_stage(item.stage)
        if not next_stage:
            raise ValueError(f"Work item {work_id} is already at final stage '{item.stage}'")

        return self.set_stage(work_id, next_stage, transitioned_by, new_content)

    def set_stage(
        self,
        work_id: str,
        new_stage: str,
        transitioned_by: str = "manual",
        new_content: Optional[str] = None,
    ) -> WorkItem:
        """Set a work item to a specific stage."""
        item = self.get(work_id)
        if not item:
            raise ValueError(f"Work item not found: {work_id}")

        cascade = self.get_cascade(item.cascade)
        if not cascade:
            raise ValueError(f"Cascade not found: {item.cascade}")

        if new_stage not in cascade.stages:
            raise ValueError(f"Invalid stage '{new_stage}' for cascade '{item.cascade}'")

        old_stage = item.stage
        now = datetime.now().isoformat()

        with db.get_connection() as conn:
            cursor = conn.cursor()

            # Update work item
            update_fields = ["stage = ?", "updated_at = ?"]
            update_params = [new_stage, now]

            if new_content is not None:
                update_fields.append("content = ?")
                update_params.append(new_content)

            # Track started_at for implementing stage
            if new_stage in ("implementing", "draft", "fixing"):
                update_fields.append("started_at = ?")
                update_params.append(now)

            # Track completed_at for terminal stages
            if cascade.is_terminal_stage(new_stage):
                update_fields.append("completed_at = ?")
                update_params.append(now)
                # Clear claim when done
                update_fields.append("claimed_by = NULL")
                update_fields.append("claimed_at = NULL")

            update_params.append(work_id)
            cursor.execute(
                f"UPDATE work_items SET {', '.join(update_fields)} WHERE id = ?",
                update_params
            )

            # Record transition
            cursor.execute(
                """
                INSERT INTO work_transitions (work_id, from_stage, to_stage, transitioned_by, content_snapshot)
                VALUES (?, ?, ?, ?, ?)
                """,
                (work_id, old_stage, new_stage, transitioned_by, new_content)
            )

            conn.commit()

        return self.get(work_id)

    def claim(self, work_id: str, claimed_by: str) -> WorkItem:
        """Claim a work item for processing."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # Check if already claimed
            cursor.execute(
                "SELECT claimed_by FROM work_items WHERE id = ?",
                (work_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Work item not found: {work_id}")
            if row[0] and row[0] != claimed_by:
                raise ValueError(f"Work item {work_id} already claimed by {row[0]}")

            cursor.execute(
                """
                UPDATE work_items
                SET claimed_by = ?, claimed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (claimed_by, now, now, work_id)
            )
            conn.commit()

        return self.get(work_id)

    def release(self, work_id: str) -> WorkItem:
        """Release a claimed work item."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE work_items
                SET claimed_by = NULL, claimed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), work_id)
            )
            conn.commit()

        return self.get(work_id)

    def done(
        self,
        work_id: str,
        pr_number: Optional[int] = None,
        output_doc_id: Optional[int] = None,
    ) -> WorkItem:
        """Mark a work item as done."""
        item = self.get(work_id)
        if not item:
            raise ValueError(f"Work item not found: {work_id}")

        cascade = self.get_cascade(item.cascade)
        if not cascade:
            raise ValueError(f"Cascade not found: {item.cascade}")

        # Get terminal stage for this cascade
        terminal_stage = cascade.stages[-1] if cascade.stages else "done"

        with db.get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute(
                """
                UPDATE work_items
                SET stage = ?, completed_at = ?, updated_at = ?,
                    pr_number = COALESCE(?, pr_number),
                    output_doc_id = COALESCE(?, output_doc_id),
                    claimed_by = NULL, claimed_at = NULL
                WHERE id = ?
                """,
                (terminal_stage, now, now, pr_number, output_doc_id, work_id)
            )

            # Record transition
            cursor.execute(
                """
                INSERT INTO work_transitions (work_id, from_stage, to_stage, transitioned_by)
                VALUES (?, ?, ?, 'done')
                """,
                (work_id, item.stage, terminal_stage)
            )

            conn.commit()

        return self.get(work_id)

    def update(
        self,
        work_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        priority: Optional[int] = None,
        type_: Optional[str] = None,
    ) -> WorkItem:
        """Update work item fields."""
        updates = []
        params = []

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if content is not None:
            updates.append("content = ?")
            params.append(content)
        if priority is not None:
            updates.append("priority = ?")
            params.append(priority)
        if type_ is not None:
            updates.append("type = ?")
            params.append(type_)

        if not updates:
            return self.get(work_id)

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(work_id)

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE work_items SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        return self.get(work_id)

    def delete(self, work_id: str) -> bool:
        """Delete a work item and its dependencies."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM work_items WHERE id = ?", (work_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    # ==========================================================================
    # DEPENDENCY OPERATIONS
    # ==========================================================================

    def add_dependency(
        self,
        work_id: str,
        depends_on: str,
        dep_type: str = "blocks",
    ) -> WorkDep:
        """Add a dependency between work items."""
        if dep_type not in ("blocks", "related", "discovered-from"):
            raise ValueError(f"Invalid dependency type: {dep_type}")

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO work_deps (work_id, depends_on, dep_type)
                VALUES (?, ?, ?)
                """,
                (work_id, depends_on, dep_type)
            )
            conn.commit()

        return WorkDep(work_id=work_id, depends_on=depends_on, dep_type=dep_type)

    def remove_dependency(self, work_id: str, depends_on: str) -> bool:
        """Remove a dependency."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM work_deps WHERE work_id = ? AND depends_on = ?",
                (work_id, depends_on)
            )
            removed = cursor.rowcount > 0
            conn.commit()
            return removed

    def get_dependencies(self, work_id: str) -> List[Tuple[WorkDep, WorkItem]]:
        """Get all dependencies for a work item with their work items."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT wd.work_id, wd.depends_on, wd.dep_type, wd.created_at,
                       wi.id, wi.title, wi.content, wi.cascade, wi.stage, wi.priority, wi.type,
                       wi.parent_id, wi.project, wi.pr_number, wi.output_doc_id,
                       wi.created_at, wi.updated_at, wi.started_at, wi.completed_at,
                       wi.claimed_by, wi.claimed_at
                FROM work_deps wd
                JOIN work_items wi ON wd.depends_on = wi.id
                WHERE wd.work_id = ?
                """,
                (work_id,)
            )
            results = []
            for row in cursor.fetchall():
                dep = WorkDep.from_row(row[:4])
                item = WorkItem.from_row(row[4:])
                results.append((dep, item))
            return results

    def get_dependents(self, work_id: str) -> List[Tuple[WorkDep, WorkItem]]:
        """Get all work items that depend on this one."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT wd.work_id, wd.depends_on, wd.dep_type, wd.created_at,
                       wi.id, wi.title, wi.content, wi.cascade, wi.stage, wi.priority, wi.type,
                       wi.parent_id, wi.project, wi.pr_number, wi.output_doc_id,
                       wi.created_at, wi.updated_at, wi.started_at, wi.completed_at,
                       wi.claimed_by, wi.claimed_at
                FROM work_deps wd
                JOIN work_items wi ON wd.work_id = wi.id
                WHERE wd.depends_on = ?
                """,
                (work_id,)
            )
            results = []
            for row in cursor.fetchall():
                dep = WorkDep.from_row(row[:4])
                item = WorkItem.from_row(row[4:])
                results.append((dep, item))
            return results

    # ==========================================================================
    # STATISTICS & QUERIES
    # ==========================================================================

    def get_stage_counts(self, cascade: Optional[str] = None) -> Dict[str, Dict[str, int]]:
        """Get counts of work items by cascade and stage."""
        with db.get_connection() as conn:
            cursor = conn.cursor()

            if cascade:
                cursor.execute(
                    """
                    SELECT cascade, stage, COUNT(*) as count
                    FROM work_items
                    WHERE cascade = ?
                    GROUP BY cascade, stage
                    """,
                    (cascade,)
                )
            else:
                cursor.execute(
                    """
                    SELECT cascade, stage, COUNT(*) as count
                    FROM work_items
                    GROUP BY cascade, stage
                    """
                )

            results: Dict[str, Dict[str, int]] = {}
            for cascade_name, stage, count in cursor.fetchall():
                if cascade_name not in results:
                    results[cascade_name] = {}
                results[cascade_name][stage] = count

            return results

    def get_transitions(self, work_id: str) -> List[WorkTransition]:
        """Get transition history for a work item."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, work_id, from_stage, to_stage, transitioned_by, content_snapshot, created_at
                FROM work_transitions
                WHERE work_id = ?
                ORDER BY created_at ASC
                """,
                (work_id,)
            )
            return [WorkTransition.from_row(row) for row in cursor.fetchall()]

    def get_recent_transitions(self, limit: int = 20) -> List[WorkTransition]:
        """Get recent transitions across all work items."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, work_id, from_stage, to_stage, transitioned_by, content_snapshot, created_at
                FROM work_transitions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            return [WorkTransition.from_row(row) for row in cursor.fetchall()]
