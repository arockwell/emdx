"""Database migration system for emdx.

This package contains all database migrations organized by domain:
- core: Documents, tags, executions (migrations 0-6)
- workflow_tables: Workflow orchestration system (migrations 7-8, 11, 14, 16-17, 20-21, 23, 27)
- task_tables: Task management system (migrations 9-10, 34)
- cascade_tables: Cascade/pipeline system (migrations 28-29, 31-32)
- export_tables: Export profiles and Google Docs (migrations 12, 15)
- schema_updates: Schema modifications (migrations 13, 18-19, 22, 26)
- cleanup: Table removals and FK fixes (migrations 24, 30, 35, 37-38)
- misc: Standalone features (migrations 25, 33, 36)

Public API:
- run_migrations(): Run all pending migrations
- MIGRATIONS: List of all migrations in order
- get_schema_version(): Get current schema version
- set_schema_version(): Set schema version
- foreign_keys_disabled(): Context manager for FK-disabled operations
- Individual migration functions (for testing)
"""

from collections.abc import Callable

# Import runner functions
from .runner import (
    foreign_keys_disabled,
    get_schema_version,
    run_migrations,
    set_schema_version,
)

# Import all migration functions from domain modules
from .cascade_tables import (
    migration_028_add_document_stage,
    migration_029_add_document_pr_url,
    migration_031_add_cascade_runs,
    migration_032_extract_cascade_metadata,
)
from .cleanup import (
    migration_024_remove_agent_tables,
    migration_030_cleanup_unused_tables,
    migration_035_remove_workflow_tables,
    migration_037_add_cascade_delete_fks,
    migration_038_add_title_lower_index,
)
from .core import (
    migration_000_create_documents_table,
    migration_001_add_tags,
    migration_002_add_executions,
    migration_003_add_document_relationships,
    migration_004_add_execution_pid,
    migration_005_add_execution_heartbeat,
    migration_006_numeric_execution_ids,
)
from .export_tables import (
    migration_012_add_gdocs,
    migration_015_add_export_profiles,
)
from .misc import (
    migration_025_add_standalone_presets,
    migration_033_add_mail_config,
    migration_036_add_execution_metrics,
)
from .schema_updates import (
    migration_013_make_execution_doc_id_nullable,
    migration_018_add_document_hierarchy,
    migration_019_add_document_sources,
    migration_022_add_document_groups,
    migration_026_add_embeddings,
)
from .task_tables import (
    migration_009_add_tasks,
    migration_010_add_task_executions,
    migration_034_delegate_activity_tracking,
)
from .workflow_tables import (
    migration_007_add_agent_tables,
    migration_008_add_workflow_tables,
    migration_011_add_dynamic_workflow_mode,
    migration_014_fix_individual_runs_fk,
    migration_016_add_input_output_tokens,
    migration_017_add_cost_usd,
    migration_020_add_synthesis_cost,
    migration_021_add_workflow_presets,
    migration_023_deactivate_legacy_workflows,
    migration_027_add_synthesizing_status,
)

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
    (37, "Add ON DELETE CASCADE to foreign keys", migration_037_add_cascade_delete_fks),
    (38, "Add LOWER(title) index for case-insensitive search", migration_038_add_title_lower_index),
]

__all__ = [
    # Runner functions
    "run_migrations",
    "get_schema_version",
    "set_schema_version",
    "foreign_keys_disabled",
    # Migration list
    "MIGRATIONS",
    # Individual migrations (for testing)
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
    "migration_037_add_cascade_delete_fks",
    "migration_038_add_title_lower_index",
]
