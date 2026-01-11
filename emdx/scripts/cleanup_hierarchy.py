#!/usr/bin/env python3
"""One-time cleanup script to archive garbage docs and establish hierarchy.

This script performs the following cleanup operations:
1. Archives "Workflow Agent Output" documents (intermediate workflow outputs)
2. Archives "Synthesis (error)" documents (failed synthesis attempts)
3. Archives "Test Agent:" documents (test agent runs)
4. Links workflow individual outputs to their synthesis documents
5. Links exact-title duplicates (older becomes child of newer with 'supersedes' relationship)

Usage:
    # Run directly
    poetry run python emdx/scripts/cleanup_hierarchy.py

    # Or via CLI command
    poetry run emdx maintain cleanup-hierarchy
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics from cleanup operation."""

    workflow_output_archived: int = 0
    synthesis_error_archived: int = 0
    test_agent_archived: int = 0
    duplicates_linked: int = 0
    workflow_docs_linked: int = 0
    errors: List[str] = field(default_factory=list)

    def total_archived(self) -> int:
        """Return total documents archived."""
        return (
            self.workflow_output_archived
            + self.synthesis_error_archived
            + self.test_agent_archived
        )

    def total_linked(self) -> int:
        """Return total documents linked."""
        return self.duplicates_linked + self.workflow_docs_linked

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "workflow_output_archived": self.workflow_output_archived,
            "synthesis_error_archived": self.synthesis_error_archived,
            "test_agent_archived": self.test_agent_archived,
            "duplicates_linked": self.duplicates_linked,
            "workflow_docs_linked": self.workflow_docs_linked,
            "total_archived": self.total_archived(),
            "total_linked": self.total_linked(),
            "errors": self.errors,
        }


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable."""
    import os

    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    return Path.home() / ".config" / "emdx" / "knowledge.db"


def cleanup(
    db_path: Optional[Path] = None,
    dry_run: bool = False,
) -> CleanupStats:
    """Run cleanup operations to archive garbage docs and establish hierarchy.

    Args:
        db_path: Path to database file. If None, uses default location.
        dry_run: If True, don't actually make changes, just report what would be done.

    Returns:
        CleanupStats with counts of affected documents.
    """
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return CleanupStats(errors=[f"Database not found: {db_path}"])

    stats = CleanupStats()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Archive "Workflow Agent Output" docs
        stats.workflow_output_archived = _archive_by_title_pattern(
            cur, "Workflow Agent Output%", dry_run
        )

        # 2. Archive "Synthesis (error)" docs
        stats.synthesis_error_archived = _archive_by_title_pattern(
            cur, "Synthesis (error)%", dry_run
        )

        # 3. Archive "Test Agent:" docs
        stats.test_agent_archived = _archive_by_title_pattern(
            cur, "Test Agent:%", dry_run
        )

        # 4. Link workflow individual outputs to their synthesis docs
        stats.workflow_docs_linked = _link_workflow_outputs_to_syntheses(cur, dry_run)

        # 5. Link exact-title duplicates (older becomes child of newer)
        stats.duplicates_linked = _link_duplicate_titles(cur, dry_run)

        if not dry_run:
            conn.commit()

        conn.close()

    except sqlite3.Error as e:
        logger.error(f"Database error during cleanup: {e}")
        stats.errors.append(f"Database error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during cleanup: {e}")
        stats.errors.append(f"Unexpected error: {e}")

    return stats


def _archive_by_title_pattern(
    cur: sqlite3.Cursor,
    pattern: str,
    dry_run: bool,
) -> int:
    """Archive documents matching a title pattern.

    Args:
        cur: Database cursor
        pattern: SQL LIKE pattern to match against title
        dry_run: If True, only count matching docs

    Returns:
        Number of documents archived (or that would be archived)
    """
    if dry_run:
        cur.execute(
            """
            SELECT COUNT(*) as count
            FROM documents
            WHERE title LIKE ?
            AND archived_at IS NULL
            AND is_deleted = FALSE
            """,
            (pattern,),
        )
        result = cur.fetchone()
        return result["count"] if result else 0

    cur.execute(
        """
        UPDATE documents
        SET archived_at = CURRENT_TIMESTAMP
        WHERE title LIKE ?
        AND archived_at IS NULL
        AND is_deleted = FALSE
        """,
        (pattern,),
    )
    return cur.rowcount


def _link_workflow_outputs_to_syntheses(
    cur: sqlite3.Cursor,
    dry_run: bool,
) -> int:
    """Link workflow individual outputs to their synthesis documents.

    Uses workflow_stage_runs.synthesis_doc_id and workflow_individual_runs.output_doc_id
    to establish parent-child relationships.

    Args:
        cur: Database cursor
        dry_run: If True, only count potential links

    Returns:
        Number of documents linked
    """
    # Check if the tables exist (they may not if workflow feature isn't used)
    cur.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='workflow_stage_runs'
        """
    )
    if not cur.fetchone():
        logger.info("workflow_stage_runs table not found, skipping workflow linking")
        return 0

    cur.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='workflow_individual_runs'
        """
    )
    if not cur.fetchone():
        logger.info("workflow_individual_runs table not found, skipping workflow linking")
        return 0

    # Find pairs of synthesis_doc_id and output_doc_id
    cur.execute(
        """
        SELECT wsr.synthesis_doc_id, wir.output_doc_id
        FROM workflow_stage_runs wsr
        JOIN workflow_individual_runs wir ON wir.stage_run_id = wsr.id
        WHERE wsr.synthesis_doc_id IS NOT NULL
        AND wir.output_doc_id IS NOT NULL
        """
    )

    rows = cur.fetchall()
    if not rows:
        return 0

    linked = 0
    for row in rows:
        synthesis_id = row["synthesis_doc_id"]
        output_id = row["output_doc_id"]

        if dry_run:
            # Check if this would be a valid link (doc exists and has no parent)
            cur.execute(
                """
                SELECT id FROM documents
                WHERE id = ? AND parent_id IS NULL AND is_deleted = FALSE
                """,
                (output_id,),
            )
            if cur.fetchone():
                linked += 1
        else:
            cur.execute(
                """
                UPDATE documents
                SET parent_id = ?, relationship = 'exploration'
                WHERE id = ? AND parent_id IS NULL AND is_deleted = FALSE
                """,
                (synthesis_id, output_id),
            )
            if cur.rowcount > 0:
                linked += 1

    return linked


def _link_duplicate_titles(
    cur: sqlite3.Cursor,
    dry_run: bool,
) -> int:
    """Link documents with duplicate normalized titles.

    For documents with the same normalized title within the same project,
    older documents become children of newer documents with a 'supersedes'
    relationship.

    Note: Certain generic titles are excluded from linking to prevent
    unrelated documents from being chained together (e.g., "Synthesis",
    "Workflow Output", etc.)

    Args:
        cur: Database cursor
        dry_run: If True, only count potential links

    Returns:
        Number of documents linked
    """
    # Import here to avoid circular imports
    from emdx.utils.title_normalization import normalize_title

    # Normalized titles that are too generic to link
    # These would incorrectly chain unrelated documents
    EXCLUDED_NORMALIZED_TITLES = {
        "synthesis",
        "synthesis error",
        "workflow output",
        "workflow agent output",
        "test document",
        "test",
        "untitled",
        "note",
        "notes",
    }

    # Get all non-deleted, non-archived documents without a parent
    cur.execute(
        """
        SELECT id, title, project, created_at
        FROM documents
        WHERE is_deleted = FALSE
        AND parent_id IS NULL
        ORDER BY created_at DESC
        """
    )

    docs = cur.fetchall()

    # Group by normalized title + project
    # seen_titles maps (normalized_title, project) -> newest doc id
    seen_titles: Dict[Tuple[str, Optional[str]], int] = {}
    links_to_create: List[Tuple[int, int]] = []  # (child_id, parent_id)

    for doc in docs:
        norm_title = normalize_title(doc["title"])
        if not norm_title:
            continue

        # Skip generic titles that shouldn't be linked
        if norm_title.lower() in EXCLUDED_NORMALIZED_TITLES:
            continue

        key = (norm_title, doc["project"])

        if key in seen_titles:
            # This doc is older (we're iterating DESC by created_at),
            # so it should become a child of the newer one
            newer_id = seen_titles[key]
            links_to_create.append((doc["id"], newer_id))
        else:
            # This is the newest doc with this title+project
            seen_titles[key] = doc["id"]

    if dry_run:
        return len(links_to_create)

    linked = 0
    for child_id, parent_id in links_to_create:
        cur.execute(
            """
            UPDATE documents
            SET parent_id = ?, relationship = 'supersedes'
            WHERE id = ? AND parent_id IS NULL AND is_deleted = FALSE
            """,
            (parent_id, child_id),
        )
        if cur.rowcount > 0:
            linked += 1

    return linked


def main():
    """Run cleanup as a standalone script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Archive garbage documents and establish document hierarchy"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Path to database file (default: ~/.config/emdx/knowledge.db)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.dry_run:
        print("DRY RUN - No changes will be made\n")

    print("Running cleanup migration...")
    stats = cleanup(db_path=args.db_path, dry_run=args.dry_run)

    action = "Would archive" if args.dry_run else "Archived"
    link_action = "Would link" if args.dry_run else "Linked"

    print(f"{action} {stats.workflow_output_archived} Workflow Agent Output docs")
    print(f"{action} {stats.synthesis_error_archived} Synthesis (error) docs")
    print(f"{action} {stats.test_agent_archived} Test Agent docs")
    print(f"{link_action} {stats.workflow_docs_linked} workflow outputs to syntheses")
    print(f"{link_action} {stats.duplicates_linked} duplicate title docs")

    if stats.errors:
        print("\nErrors encountered:")
        for error in stats.errors:
            print(f"  - {error}")
        return 1

    if args.dry_run:
        print("\nRun without --dry-run to apply changes")
    else:
        print("\nCleanup complete!")

    return 0


if __name__ == "__main__":
    exit(main())
