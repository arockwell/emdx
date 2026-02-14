"""Database migration system for emdx.

This package organizes migrations into logical groups:
- core_schema: Foundational tables (documents, tags, executions) - migrations 000-006
- agents_workflows: Agent and workflow systems - migrations 007-015
- enhancements: Token tracking, hierarchy, presets, embeddings - migrations 016-026
- cascade_cleanup: Cascade pipeline, mail, delegate, cleanup - migrations 027-036

Public API:
- run_migrations(db_path=None): Run all pending migrations
- get_schema_version(conn): Get current schema version
- set_schema_version(conn, version): Set schema version
- MIGRATIONS: List of all migrations for inspection
"""

import sqlite3
from typing import Callable

from ...config.settings import get_db_path

# Import all migration functions from submodules
from .core_schema import (
    migration_000_create_documents_table,
    migration_001_add_tags,
    migration_002_add_executions,
    migration_003_add_document_relationships,
    migration_004_add_execution_pid,
    migration_005_add_execution_heartbeat,
    migration_006_numeric_execution_ids,
)
from .agents_workflows import (
    migration_007_add_agent_tables,
    migration_008_add_workflow_tables,
    migration_009_add_tasks,
    migration_010_add_task_executions,
    migration_011_add_dynamic_workflow_mode,
    migration_012_add_gdocs,
    migration_013_make_execution_doc_id_nullable,
    migration_014_fix_individual_runs_fk,
    migration_015_add_export_profiles,
)
from .enhancements import (
    migration_016_add_input_output_tokens,
    migration_017_add_cost_usd,
    migration_018_add_document_hierarchy,
    migration_019_add_document_sources,
    migration_020_add_synthesis_cost,
    migration_021_add_workflow_presets,
    migration_022_add_document_groups,
    migration_023_deactivate_legacy_workflows,
    migration_024_remove_agent_tables,
    migration_025_add_standalone_presets,
    migration_026_add_embeddings,
)
from .cascade_cleanup import (
    migration_027_add_synthesizing_status,
    migration_028_add_document_stage,
    migration_029_add_document_pr_url,
    migration_030_cleanup_unused_tables,
    migration_031_add_cascade_runs,
    migration_032_extract_cascade_metadata,
    migration_033_add_mail_config,
    migration_034_delegate_activity_tracking,
    migration_035_remove_workflow_tables,
    migration_036_add_execution_metrics,
)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()
    # Return -1 for completely fresh installations (no version recorded yet)
    # This ensures migration 0 will run for new installations
    return result[0] if result[0] is not None else -1


def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set the schema version."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


# List of all migrations in order
MIGRATIONS: list[tuple[int, str, Callable]] = [
    (0, "Create documents table", migration_000_create_documents_table),
    (1, "Add tags system", migration_001_add_tags),
    (2, "Add executions tracking", migration_002_add_executions),
    (3, "Add document relationships", migration_003_add_document_relationships),
    (4, "Add execution PID tracking", migration_004_add_execution_pid),
    (5, "Add execution heartbeat tracking", migration_005_add_execution_heartbeat),
    (6, "Convert to numeric execution IDs", migration_006_numeric_execution_ids),
    (7, "Add agent system tables", migration_007_add_agent_tables),
    (8, "Add workflow orchestration tables", migration_008_add_workflow_tables),
    (9, "Add tasks system", migration_009_add_tasks),
    (10, "Add task executions join table", migration_010_add_task_executions),
    (11, "Add dynamic workflow mode", migration_011_add_dynamic_workflow_mode),
    (12, "Add Google Docs exports", migration_012_add_gdocs),
    (13, "Make execution doc_id nullable", migration_013_make_execution_doc_id_nullable),
    (14, "Fix individual_runs FK to executions", migration_014_fix_individual_runs_fk),
    (15, "Add export profiles", migration_015_add_export_profiles),
    (16, "Add input/output tokens to individual runs", migration_016_add_input_output_tokens),
    (17, "Add cost_usd to individual runs", migration_017_add_cost_usd),
    (18, "Add document hierarchy columns", migration_018_add_document_hierarchy),
    (19, "Add document sources bridge table", migration_019_add_document_sources),
    (20, "Add synthesis cost tracking", migration_020_add_synthesis_cost),
    (21, "Add workflow presets", migration_021_add_workflow_presets),
    (22, "Add document groups system", migration_022_add_document_groups),
    (23, "Deactivate legacy builtin workflows", migration_023_deactivate_legacy_workflows),
    (24, "Remove agent system tables", migration_024_remove_agent_tables),
    (25, "Add standalone presets", migration_025_add_standalone_presets),
    (26, "Add embeddings for semantic search", migration_026_add_embeddings),
    (27, "Add synthesizing status to stage runs", migration_027_add_synthesizing_status),
    (28, "Add document stage for cascade", migration_028_add_document_stage),
    (29, "Add document PR URL for cascade", migration_029_add_document_pr_url),
    (30, "Remove unused tables and dead code", migration_030_cleanup_unused_tables),
    (31, "Add cascade runs tracking", migration_031_add_cascade_runs),
    (32, "Extract cascade metadata to dedicated table", migration_032_extract_cascade_metadata),
    (33, "Add mail config and read receipts", migration_033_add_mail_config),
    (34, "Add delegate activity tracking", migration_034_delegate_activity_tracking),
    (35, "Remove workflow system tables", migration_035_remove_workflow_tables),
    (36, "Add execution metrics and task linkage", migration_036_add_execution_metrics),
]


def run_migrations(db_path=None):
    """Run all pending migrations."""
    if db_path is None:
        db_path = get_db_path()
    # Don't return early - we need to run migrations even for new databases
    # The database file will be created when we connect to it

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        current_version = get_schema_version(conn)

        for version, description, migration_func in MIGRATIONS:
            if version > current_version:
                print(f"Running migration {version}: {description}")
                migration_func(conn)
                set_schema_version(conn, version)
                print(f"✅ Migration {version} completed")

    finally:
        conn.close()


# Export public API
__all__ = [
    "run_migrations",
    "get_schema_version",
    "set_schema_version",
    "MIGRATIONS",
    # Individual migrations for test imports
    "migration_000_create_documents_table",
    "migration_001_add_tags",
    "migration_002_add_executions",
    "migration_003_add_document_relationships",
    "migration_004_add_execution_pid",
    "migration_005_add_execution_heartbeat",
    "migration_006_numeric_execution_ids",
    "migration_007_add_agent_tables",
    "migration_008_add_workflow_tables",
    "migration_009_add_tasks",
    "migration_010_add_task_executions",
    "migration_011_add_dynamic_workflow_mode",
    "migration_012_add_gdocs",
    "migration_013_make_execution_doc_id_nullable",
    "migration_014_fix_individual_runs_fk",
    "migration_015_add_export_profiles",
    "migration_016_add_input_output_tokens",
    "migration_017_add_cost_usd",
    "migration_018_add_document_hierarchy",
    "migration_019_add_document_sources",
    "migration_020_add_synthesis_cost",
    "migration_021_add_workflow_presets",
    "migration_022_add_document_groups",
    "migration_023_deactivate_legacy_workflows",
    "migration_024_remove_agent_tables",
    "migration_025_add_standalone_presets",
    "migration_026_add_embeddings",
    "migration_027_add_synthesizing_status",
    "migration_028_add_document_stage",
    "migration_029_add_document_pr_url",
    "migration_030_cleanup_unused_tables",
    "migration_031_add_cascade_runs",
    "migration_032_extract_cascade_metadata",
    "migration_033_add_mail_config",
    "migration_034_delegate_activity_tracking",
    "migration_035_remove_workflow_tables",
    "migration_036_add_execution_metrics",
]
