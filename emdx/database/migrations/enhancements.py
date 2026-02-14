"""Enhancement migrations: tokens, hierarchy, presets, embeddings (migrations 016-026).

These migrations add:
- Token and cost tracking
- Document hierarchy and relationships
- Workflow presets and groups
- Semantic search embeddings
"""

import sqlite3


def migration_016_add_input_output_tokens(conn: sqlite3.Connection):
    """Add input_tokens and output_tokens columns to workflow_individual_runs.

    This allows tracking input vs output token usage separately for better
    cost analysis and debugging.
    """
    cursor = conn.cursor()

    # Add input_tokens column
    cursor.execute("""
        ALTER TABLE workflow_individual_runs ADD COLUMN input_tokens INTEGER DEFAULT 0
    """)

    # Add output_tokens column
    cursor.execute("""
        ALTER TABLE workflow_individual_runs ADD COLUMN output_tokens INTEGER DEFAULT 0
    """)

    conn.commit()


def migration_017_add_cost_usd(conn: sqlite3.Connection):
    """Add cost_usd column to workflow_individual_runs.

    Stores the actual cost from Claude API for accurate billing tracking.
    """
    cursor = conn.cursor()

    cursor.execute("""
        ALTER TABLE workflow_individual_runs ADD COLUMN cost_usd REAL DEFAULT 0.0
    """)

    conn.commit()


def migration_018_add_document_hierarchy(conn: sqlite3.Connection):
    """Add relationship and archived_at columns for document hierarchy.

    - relationship: describes how a child relates to parent ('supersedes', 'exploration', 'variant')
    - archived_at: when document was archived (superseded docs auto-archive when parent tagged 'done')
    """
    cursor = conn.cursor()

    # Check existing columns to avoid duplicate column errors
    cursor.execute("PRAGMA table_info(documents)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Add relationship column if not exists
    if "relationship" not in existing_columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN relationship TEXT")

    # Add archived_at column if not exists
    if "archived_at" not in existing_columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN archived_at TIMESTAMP")

    # Add index for efficient archived queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_archived_at ON documents(archived_at)"
    )

    conn.commit()


def migration_019_add_document_sources(conn: sqlite3.Connection):
    """Add document_sources table to track document provenance.

    This table links documents to their originating workflow runs,
    enabling efficient queries without traversing the workflow hierarchy.
    """
    cursor = conn.cursor()

    # Create the bridge table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL UNIQUE,
            workflow_run_id INTEGER,
            workflow_stage_run_id INTEGER,
            workflow_individual_run_id INTEGER,
            source_type TEXT NOT NULL CHECK (source_type IN ('individual_output', 'synthesis', 'stage_output')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL,
            FOREIGN KEY (workflow_stage_run_id) REFERENCES workflow_stage_runs(id) ON DELETE SET NULL,
            FOREIGN KEY (workflow_individual_run_id) REFERENCES workflow_individual_runs(id) ON DELETE SET NULL
        )
    """)

    # Indexes for efficient lookups
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_sources_doc ON document_sources(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_sources_run ON document_sources(workflow_run_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_sources_type ON document_sources(source_type)"
    )

    # Backfill from existing data
    _backfill_document_sources(cursor)

    conn.commit()


def _backfill_document_sources(cursor):
    """Populate document_sources from existing workflow tables."""
    # Backfill from individual runs (most common case)
    cursor.execute("""
        INSERT OR IGNORE INTO document_sources
        (document_id, workflow_run_id, workflow_stage_run_id, workflow_individual_run_id, source_type)
        SELECT
            wir.output_doc_id,
            wsr.workflow_run_id,
            wir.stage_run_id,
            wir.id,
            'individual_output'
        FROM workflow_individual_runs wir
        JOIN workflow_stage_runs wsr ON wir.stage_run_id = wsr.id
        WHERE wir.output_doc_id IS NOT NULL
    """)

    # Backfill synthesis docs from stage runs
    cursor.execute("""
        INSERT OR IGNORE INTO document_sources
        (document_id, workflow_run_id, workflow_stage_run_id, source_type)
        SELECT
            wsr.synthesis_doc_id,
            wsr.workflow_run_id,
            wsr.id,
            'synthesis'
        FROM workflow_stage_runs wsr
        WHERE wsr.synthesis_doc_id IS NOT NULL
    """)

    # Backfill stage output docs (if different from synthesis)
    cursor.execute("""
        INSERT OR IGNORE INTO document_sources
        (document_id, workflow_run_id, workflow_stage_run_id, source_type)
        SELECT
            wsr.output_doc_id,
            wsr.workflow_run_id,
            wsr.id,
            'stage_output'
        FROM workflow_stage_runs wsr
        WHERE wsr.output_doc_id IS NOT NULL
          AND (wsr.synthesis_doc_id IS NULL OR wsr.output_doc_id != wsr.synthesis_doc_id)
    """)


def migration_020_add_synthesis_cost(conn: sqlite3.Connection):
    """Add synthesis_cost_usd to workflow_stage_runs table.

    Tracks the cost of synthesis Claude calls separately from individual runs.
    """
    cursor = conn.cursor()

    # Add synthesis_cost_usd column
    cursor.execute("""
        ALTER TABLE workflow_stage_runs
        ADD COLUMN synthesis_cost_usd REAL DEFAULT 0.0
    """)

    # Also add synthesis token tracking
    cursor.execute("""
        ALTER TABLE workflow_stage_runs
        ADD COLUMN synthesis_input_tokens INTEGER DEFAULT 0
    """)

    cursor.execute("""
        ALTER TABLE workflow_stage_runs
        ADD COLUMN synthesis_output_tokens INTEGER DEFAULT 0
    """)

    conn.commit()


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
