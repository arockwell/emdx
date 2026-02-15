"""Database migration system for emdx.

This package contains the migration system split into logical groups:
- initial.py: Core schema (migrations 000-010)
- features.py: Feature additions (migrations 011-020)
- cascade.py: Cascade and presets (migrations 021-030)
- recent.py: Recent additions (migrations 031-038)

The public API remains identical to the original migrations.py module.
"""

import sqlite3
from typing import Callable

from ...config.settings import get_db_path

# Re-export the foreign_keys_disabled context manager
from ._utils import foreign_keys_disabled

# Import migration lists from each module
from .initial import (
    INITIAL_MIGRATIONS,
    migration_000_create_documents_table,
    migration_001_add_tags,
    migration_002_add_executions,
    migration_003_add_document_relationships,
    migration_004_add_execution_pid,
    migration_005_add_execution_heartbeat,
    migration_006_numeric_execution_ids,
    migration_007_add_agent_tables,
    migration_008_add_workflow_tables,
    migration_009_add_tasks,
    migration_010_add_task_executions,
)
from .features import (
    FEATURES_MIGRATIONS,
    migration_011_add_dynamic_workflow_mode,
    migration_012_add_gdocs,
    migration_013_make_execution_doc_id_nullable,
    migration_014_fix_individual_runs_fk,
    migration_015_add_export_profiles,
    migration_016_add_input_output_tokens,
    migration_017_add_cost_usd,
    migration_018_add_document_hierarchy,
    migration_019_add_document_sources,
    migration_020_add_synthesis_cost,
)
from .cascade import (
    CASCADE_MIGRATIONS,
    migration_021_add_workflow_presets,
    migration_022_add_document_groups,
    migration_023_deactivate_legacy_workflows,
    migration_024_remove_agent_tables,
    migration_025_add_standalone_presets,
    migration_026_add_embeddings,
    migration_027_add_synthesizing_status,
    migration_028_add_document_stage,
    migration_029_add_document_pr_url,
    migration_030_cleanup_unused_tables,
)
from .recent import (
    RECENT_MIGRATIONS,
    migration_031_add_cascade_runs,
    migration_032_extract_cascade_metadata,
    migration_033_add_mail_config,
    migration_034_delegate_activity_tracking,
    migration_035_remove_workflow_tables,
    migration_036_add_execution_metrics,
    migration_037_add_cascade_delete_fks,
    migration_038_add_title_lower_index,
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


# List of all migrations in order - combined from all modules
MIGRATIONS: list[tuple[int, str, Callable]] = (
    INITIAL_MIGRATIONS + FEATURES_MIGRATIONS + CASCADE_MIGRATIONS + RECENT_MIGRATIONS
)


def run_migrations(db_path=None):
    """Run all pending migrations."""
    if db_path is None:
        db_path = get_db_path()
    # Don't return early - we need to run migrations even for new databases
    # The database file will be created when we connect to it

    conn = sqlite3.connect(db_path)
    # Enable foreign keys for this connection (migrations use foreign_keys_disabled()
    # context manager when they need to temporarily disable them for table recreation)
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


# Re-export all public symbols for backward compatibility
__all__ = [
    # Core functions
    "foreign_keys_disabled",
    "get_schema_version",
    "set_schema_version",
    "run_migrations",
    "MIGRATIONS",
    # Initial migrations (000-010)
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
    # Features migrations (011-020)
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
    # Cascade migrations (021-030)
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
    # Recent migrations (031-038)
    "migration_031_add_cascade_runs",
    "migration_032_extract_cascade_metadata",
    "migration_033_add_mail_config",
    "migration_034_delegate_activity_tracking",
    "migration_035_remove_workflow_tables",
    "migration_036_add_execution_metrics",
    "migration_037_add_cascade_delete_fks",
    "migration_038_add_title_lower_index",
]
