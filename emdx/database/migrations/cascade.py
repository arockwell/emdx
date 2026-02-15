"""Cascade and preset migrations (021-030).

This module contains migrations for cascade pipeline and presets:
- Workflow presets
- Document groups
- Legacy workflow deactivation
- Agent table removal
- Standalone presets
- Embeddings for semantic search
- Synthesizing status
- Document stage and PR URL
- Cleanup of unused tables
"""

import sqlite3

from ._utils import foreign_keys_disabled


def migration_021_add_workflow_presets(conn: sqlite3.Connection):
    """Add workflow_presets table for named variable configurations.

    Presets are named bundles of variables that can be applied to a workflow.
    This allows reusing workflows with different configurations without
    creating duplicate workflow definitions.

    Example:
        Workflow: parallel_analysis
        Presets:
          - "security_audit": {topic: "Security", track_1: "Auth", track_2: "Input validation"}
          - "ux_views": {topic: "UX Analysis", track_1: "Activity View", track_2: "Documents View"}
    """
    cursor = conn.cursor()

    # Create workflow_presets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            variables_json TEXT NOT NULL DEFAULT '{}',
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            UNIQUE(workflow_id, name),
            FOREIGN KEY (workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
        )
    """)

    # Create indexes for efficient queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_workflow_presets_workflow_id
        ON workflow_presets(workflow_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_workflow_presets_name
        ON workflow_presets(workflow_id, name)
    """)

    # Add preset_id to workflow_runs to track which preset was used
    cursor.execute("""
        ALTER TABLE workflow_runs
        ADD COLUMN preset_id INTEGER REFERENCES workflow_presets(id)
    """)

    # Add preset_name for human-readable reference (survives preset deletion)
    cursor.execute("""
        ALTER TABLE workflow_runs
        ADD COLUMN preset_name TEXT
    """)

    conn.commit()


def migration_022_add_document_groups(conn: sqlite3.Connection):
    """Add document grouping system for organizing related documents.

    This enables hierarchical organization of documents into batches, rounds,
    and initiatives - independent of how they were created (workflow, sub-agent,
    manual save).
    """
    cursor = conn.cursor()

    # Create document_groups table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            parent_group_id INTEGER,
            group_type TEXT DEFAULT 'batch' CHECK (group_type IN ('batch', 'initiative', 'round', 'session', 'custom')),
            project TEXT,
            workflow_run_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            doc_count INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            total_cost_usd REAL DEFAULT 0.0,

            FOREIGN KEY (parent_group_id) REFERENCES document_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL
        )
    """)

    # Create document_group_members table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member' CHECK (role IN ('primary', 'exploration', 'synthesis', 'variant', 'member')),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            added_by TEXT,

            UNIQUE (group_id, document_id),
            FOREIGN KEY (group_id) REFERENCES document_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Create indexes for document_groups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_name ON document_groups(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_parent ON document_groups(parent_group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_project ON document_groups(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_workflow ON document_groups(workflow_run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_type ON document_groups(group_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_active ON document_groups(is_active)")

    # Create indexes for document_group_members
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dgm_group ON document_group_members(group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dgm_doc ON document_group_members(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dgm_role ON document_group_members(role)")

    conn.commit()


def migration_023_deactivate_legacy_workflows(conn: sqlite3.Connection):
    """Deactivate legacy builtin workflows that are superseded by dynamic task-driven workflows.

    These workflows were created before the dynamic workflow system (task_parallel, parallel_fix,
    parallel_analysis, dynamic_items) which use --task flags for flexible execution. The legacy
    workflows had hardcoded prompts and are no longer needed for new work.

    Workflows are soft-deleted (is_active=FALSE) rather than hard-deleted to preserve
    historical workflow_runs that reference them.

    Legacy workflows being deactivated:
    - deep_analysis, robust_planning, quick_analysis (IDs 1-3) - original builtins
    - tech_debt_analysis, code_fix, tech_debt_discovery (IDs 4-6) - early tech debt
    - architecture_review, fix_and_pr (IDs 7-8) - early patterns
    - comprehensive_tech_debt, parallel_task_fix (IDs 10-11) - superseded by parallel_fix
    - feature_exploration_v2, feature_exploration_dynamic (IDs 14-15) - superseded by task_parallel
    - Various feature dev workflows (IDs 17-23) - one-off or superseded

    Workflows kept active:
    - #24 parallel_analysis - Reusable analysis with --task
    - #29 dynamic_items - Dynamic item processing
    - #30 parallel_fix - Reusable fix workflow with worktree isolation
    - #31 task_parallel - Core task-driven parallel execution
    """
    cursor = conn.cursor()

    # Legacy workflow names to deactivate
    # Note: Names must match exactly what's in the database
    legacy_workflows = [
        'deep_analysis',
        'robust_planning',
        'quick_analysis',
        'tech_debt_analysis',
        'code_fix',
        'tech_debt_discovery',
        'architecture_review',
        'fix_and_pr',
        'comprehensive_tech_debt',
        'parallel_task_fix',
        'feature_exploration',
        'feature_exploration_v2',
        'feature_exploration_dynamic',
        'feature_development',
        'feature_development_v2',
        'full_feature_development',
        'implement_tracks_c_d',
        'weird_feature_exploration',
        'tech_debt_parallel_fix',
        'merge_main_all_branches',
        'ux_views_analysis',
    ]

    # Soft-delete by setting is_active = FALSE
    placeholders = ','.join('?' * len(legacy_workflows))
    cursor.execute(
        f"""
        UPDATE workflows
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE name IN ({placeholders})
        """,
        legacy_workflows,
    )

    conn.commit()


def migration_024_remove_agent_tables(conn: sqlite3.Connection):
    """Remove the agent system tables.

    The agent system has been deprecated in favor of the workflow system,
    which provides all agent capabilities plus advanced orchestration patterns
    (parallel execution, synthesis, worktree isolation, presets, etc.).

    Tables being removed:
    - agent_executions: Agent execution history
    - agents: Agent definitions and configurations

    This is a destructive migration - agent data will be lost. However, the
    agent system was never actively used in production.
    """
    cursor = conn.cursor()

    # Drop agent_executions first (references agents table)
    cursor.execute("DROP TABLE IF EXISTS agent_executions")

    # Drop agents table
    cursor.execute("DROP TABLE IF EXISTS agents")

    # Also drop any related indexes (SQLite drops them with table, but be explicit)
    cursor.execute("DROP INDEX IF EXISTS idx_agents_category")
    cursor.execute("DROP INDEX IF EXISTS idx_agents_is_active")
    cursor.execute("DROP INDEX IF EXISTS idx_agent_exec_agent")
    cursor.execute("DROP INDEX IF EXISTS idx_agent_exec_status")

    conn.commit()


def migration_025_add_standalone_presets(conn: sqlite3.Connection):
    """Add standalone presets table for quick run configurations.

    Unlike workflow_presets which are tied to specific workflows,
    these presets are standalone configurations for the `emdx run` command.
    They store discovery commands, templates, and execution options.
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT,
            description TEXT,
            discover_command TEXT,
            task_template TEXT,
            synthesize BOOLEAN DEFAULT FALSE,
            max_jobs INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_run_presets_name
        ON run_presets(name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_run_presets_active
        ON run_presets(is_active)
    """)

    conn.commit()


def migration_026_add_embeddings(conn: sqlite3.Connection):
    """Add document embeddings table for semantic search.

    Stores vector embeddings computed by sentence-transformers for
    semantic similarity search and RAG (retrieval-augmented generation).
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            model_name TEXT NOT NULL,
            embedding BLOB NOT NULL,
            dimension INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            UNIQUE(document_id, model_name)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_document
        ON document_embeddings(document_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_model
        ON document_embeddings(model_name)
    """)

    conn.commit()


def migration_027_add_synthesizing_status(conn: sqlite3.Connection):
    """Add 'synthesizing' status to workflow_stage_runs.

    When a parallel or dynamic workflow enters the synthesis phase
    (combining outputs from multiple runs), this status is used to
    indicate the phase in the UI with a "🔮 Synthesizing..." indicator.
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
        # Drop any leftover _new table from previous failed run
        cursor.execute("DROP TABLE IF EXISTS workflow_stage_runs_new")

        # Create new table with updated status constraint including 'synthesizing'
        cursor.execute("""
            CREATE TABLE workflow_stage_runs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_run_id INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('single', 'parallel', 'iterative', 'adversarial', 'dynamic')),
                target_runs INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'synthesizing', 'completed', 'failed', 'cancelled')),
                runs_completed INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                output_doc_id INTEGER,
                synthesis_doc_id INTEGER,
                error_message TEXT,
                tokens_used INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                synthesis_cost_usd REAL DEFAULT 0.0,
                synthesis_input_tokens INTEGER DEFAULT 0,
                synthesis_output_tokens INTEGER DEFAULT 0,
                FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id),
                FOREIGN KEY (output_doc_id) REFERENCES documents(id),
                FOREIGN KEY (synthesis_doc_id) REFERENCES documents(id)
            )
        """)

        # Copy existing data
        cursor.execute("""
            INSERT INTO workflow_stage_runs_new
            SELECT * FROM workflow_stage_runs
        """)

        # Drop old table and rename new one
        cursor.execute("DROP TABLE workflow_stage_runs")
        cursor.execute("ALTER TABLE workflow_stage_runs_new RENAME TO workflow_stage_runs")

        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)")

    conn.commit()


def migration_028_add_document_stage(conn: sqlite3.Connection):
    """Add stage column to documents for streaming pipeline processing.

    The stage column enables a status-as-queue pattern where documents
    flow through stages: idea → prompt → analyzed → planned → done.
    Each stage is watched by a patrol that processes items and advances them.
    """
    cursor = conn.cursor()

    # Add stage column with default 'idea' for new pipeline items
    # NULL means the document is not part of the pipeline
    cursor.execute("""
        ALTER TABLE documents ADD COLUMN stage TEXT DEFAULT NULL
    """)

    # Index for efficient stage-based queries (the core of the patrol system)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_stage
        ON documents(stage) WHERE stage IS NOT NULL
    """)

    conn.commit()


def migration_029_add_document_pr_url(conn: sqlite3.Connection):
    """Add pr_url column to documents for tracking pipeline outputs.

    When a pipeline document reaches 'done' through actual implementation,
    this column stores the PR URL that was created. This links the pipeline
    journey (idea → prompt → analyzed → planned → done) to real code changes.
    """
    cursor = conn.cursor()

    # Add pr_url column - NULL for most docs, set when implementation creates a PR
    cursor.execute("""
        ALTER TABLE documents ADD COLUMN pr_url TEXT DEFAULT NULL
    """)

    # Index for finding docs with PRs
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_pr_url
        ON documents(pr_url) WHERE pr_url IS NOT NULL
    """)

    conn.commit()


def migration_030_cleanup_unused_tables(conn: sqlite3.Connection):
    """Remove unused tables and features identified in cruft audit.

    Removes:
    - agent_pipelines (orphaned, 0 rows)
    - agent_templates (orphaned, 0 rows)
    - iteration_strategies (0 usage)
    - run_presets (superseded by emdx each)

    Also deactivates dynamic_items workflow (0 recent uses).
    """
    cursor = conn.cursor()

    # Drop orphaned agent tables
    cursor.execute("DROP TABLE IF EXISTS agent_pipelines")
    cursor.execute("DROP TABLE IF EXISTS agent_templates")

    # Drop iteration strategies (never used)
    cursor.execute("DROP TABLE IF EXISTS iteration_strategies")

    # Drop run_presets (superseded by emdx each)
    cursor.execute("DROP TABLE IF EXISTS run_presets")

    # Deactivate unused workflows
    cursor.execute("""
        UPDATE workflows
        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
        WHERE name = 'dynamic_items' AND usage_count = 0
    """)

    conn.commit()


# Export all migrations from this module
CASCADE_MIGRATIONS = [
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
]
