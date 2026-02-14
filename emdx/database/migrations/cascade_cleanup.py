"""Cascade and cleanup migrations (migrations 027-036).

These migrations add:
- Cascade pipeline system (stage, pr_url, cascade_runs)
- Mail configuration
- Delegate activity tracking
- Cleanup of deprecated tables (workflows, etc.)
"""

import sqlite3


def migration_027_add_synthesizing_status(conn: sqlite3.Connection):
    """Add 'synthesizing' status to workflow_stage_runs.

    When a parallel or dynamic workflow enters the synthesis phase
    (combining outputs from multiple runs), this status is used to
    indicate the phase in the UI with a "Synthesizing..." indicator.
    """
    cursor = conn.cursor()

    # Disable foreign key checks during schema change
    cursor.execute("PRAGMA foreign_keys = OFF")

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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)"
    )

    # Re-enable foreign key checks
    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()


def migration_028_add_document_stage(conn: sqlite3.Connection):
    """Add stage column to documents for streaming pipeline processing.

    The stage column enables a status-as-queue pattern where documents
    flow through stages: idea -> prompt -> analyzed -> planned -> done.
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
    journey (idea -> prompt -> analyzed -> planned -> done) to real code changes.
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


def migration_031_add_cascade_runs(conn: sqlite3.Connection):
    """Add cascade_runs table to track end-to-end cascade executions.

    This enables:
    - Tracking a document through its entire cascade journey
    - Grouping related executions in the activity view
    - Supporting --auto mode with stop stage
    - Showing cascade progress as a unit
    """
    cursor = conn.cursor()

    # Create cascade_runs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cascade_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_doc_id INTEGER NOT NULL,
            current_doc_id INTEGER,
            start_stage TEXT NOT NULL,
            stop_stage TEXT NOT NULL DEFAULT 'done',
            current_stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed', 'paused')),
            pr_url TEXT,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            FOREIGN KEY (start_doc_id) REFERENCES documents(id),
            FOREIGN KEY (current_doc_id) REFERENCES documents(id)
        )
    """)

    # Index for finding active runs
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_runs_status
        ON cascade_runs(status)
    """)

    # Index for finding runs by document
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_runs_start_doc
        ON cascade_runs(start_doc_id)
    """)

    # Add cascade_run_id to executions table to link executions to runs
    cursor.execute("""
        ALTER TABLE executions ADD COLUMN cascade_run_id INTEGER
        REFERENCES cascade_runs(id)
    """)

    conn.commit()


def migration_032_extract_cascade_metadata(conn: sqlite3.Connection):
    """Extract cascade metadata (stage, pr_url) to a dedicated table.

    This migration:
    1. Creates document_cascade_metadata table with stage and pr_url columns
    2. Creates partial indexes for efficient stage/pr_url queries
    3. Backfills data from documents table where cascade data exists

    The documents.stage and documents.pr_url columns are kept for backward
    compatibility during the transition period. The new cascade.py module
    reads from the new table while documents.py dual-writes to both.
    """
    cursor = conn.cursor()

    # Create the cascade metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_cascade_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL UNIQUE,
            stage TEXT,
            pr_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Create partial indexes for efficient queries
    # Index on stage for documents currently in cascade (stage IS NOT NULL)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_meta_stage
        ON document_cascade_metadata(stage) WHERE stage IS NOT NULL
    """)

    # Index on pr_url for documents with PRs
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_meta_pr_url
        ON document_cascade_metadata(pr_url) WHERE pr_url IS NOT NULL
    """)

    # Index for efficient lookups by document_id (already UNIQUE but explicit index helps)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_meta_document_id
        ON document_cascade_metadata(document_id)
    """)

    # Backfill existing cascade data from documents table
    cursor.execute("""
        INSERT OR IGNORE INTO document_cascade_metadata (document_id, stage, pr_url)
        SELECT id, stage, pr_url
        FROM documents
        WHERE stage IS NOT NULL OR pr_url IS NOT NULL
    """)

    conn.commit()


def migration_033_add_mail_config(conn: sqlite3.Connection):
    """Add mail configuration and read receipts tables."""
    cursor = conn.cursor()

    # Key-value config table for mail settings (repo, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mail_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Track which issues have been read locally + saved doc IDs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mail_read_receipts (
            issue_number INTEGER PRIMARY KEY,
            repo TEXT NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            saved_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL
        )
    """)

    conn.commit()


def migration_034_delegate_activity_tracking(conn: sqlite3.Connection):
    """Add delegate activity tracking columns to tasks table."""
    cursor = conn.cursor()

    existing = {row[1] for row in cursor.execute("PRAGMA table_info(tasks)").fetchall()}

    new_columns = [
        ("prompt", "TEXT"),
        ("type", "TEXT DEFAULT 'single'"),
        ("execution_id", "INTEGER REFERENCES executions(id)"),
        ("output_doc_id", "INTEGER REFERENCES documents(id)"),
        ("source_doc_id", "INTEGER REFERENCES documents(id)"),
        ("parent_task_id", "INTEGER REFERENCES tasks(id)"),
        ("seq", "INTEGER"),
        ("retry_of", "INTEGER REFERENCES tasks(id)"),
        ("error", "TEXT"),
        ("tags", "TEXT"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_output_doc_id ON tasks(output_doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_execution_id ON tasks(execution_id)")

    conn.commit()


def migration_035_remove_workflow_tables(conn: sqlite3.Connection):
    """Remove the entire workflow system.

    The workflow system has been replaced by recipes - markdown documents
    tagged with recipe that Claude reads and follows via `emdx delegate`.

    Tables dropped:
    - workflow_presets
    - workflow_individual_runs
    - workflow_stage_runs
    - workflow_runs
    - workflows
    - document_sources (entirely workflow-coupled)

    FK columns cleaned:
    - task_executions.workflow_run_id -> DROP column
    - document_groups.workflow_run_id -> DROP column
    """
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = OFF")

    # 1. Drop workflow tables (in FK dependency order)
    cursor.execute("DROP TABLE IF EXISTS workflow_presets")
    cursor.execute("DROP TABLE IF EXISTS workflow_individual_runs")
    cursor.execute("DROP TABLE IF EXISTS workflow_stage_runs")
    cursor.execute("DROP TABLE IF EXISTS workflow_runs")
    cursor.execute("DROP TABLE IF EXISTS workflows")
    cursor.execute("DROP TABLE IF EXISTS document_sources")

    # 2. Recreate task_executions without workflow_run_id column
    cursor.execute("DROP TABLE IF EXISTS task_executions_new")
    cursor.execute("""
        CREATE TABLE task_executions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            execution_id INTEGER REFERENCES executions(id) ON DELETE SET NULL,
            execution_type TEXT NOT NULL CHECK (execution_type IN ('workflow', 'direct', 'manual')),
            status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            notes TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO task_executions_new (id, task_id, execution_id, execution_type, status, started_at, completed_at, notes)
        SELECT id, task_id, execution_id, execution_type, status, started_at, completed_at, notes
        FROM task_executions
    """)
    cursor.execute("DROP TABLE task_executions")
    cursor.execute("ALTER TABLE task_executions_new RENAME TO task_executions")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_task ON task_executions(task_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_execution ON task_executions(execution_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_type ON task_executions(execution_type)"
    )

    # 3. Recreate document_groups without workflow_run_id column
    cursor.execute("DROP TABLE IF EXISTS document_groups_new")
    cursor.execute("""
        CREATE TABLE document_groups_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            parent_group_id INTEGER,
            group_type TEXT DEFAULT 'batch' CHECK (group_type IN ('batch', 'initiative', 'round', 'session', 'custom')),
            project TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            doc_count INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            total_cost_usd REAL DEFAULT 0.0,
            FOREIGN KEY (parent_group_id) REFERENCES document_groups_new(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        INSERT INTO document_groups_new (id, name, description, parent_group_id, group_type, project,
            created_at, created_by, updated_at, is_active, doc_count, total_tokens, total_cost_usd)
        SELECT id, name, description, parent_group_id, group_type, project,
            created_at, created_by, updated_at, is_active, doc_count, total_tokens, total_cost_usd
        FROM document_groups
    """)
    cursor.execute("DROP TABLE document_groups")
    cursor.execute("ALTER TABLE document_groups_new RENAME TO document_groups")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_name ON document_groups(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_parent ON document_groups(parent_group_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_project ON document_groups(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_type ON document_groups(group_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_active ON document_groups(is_active)")

    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def migration_036_add_execution_metrics(conn: sqlite3.Connection):
    """Add metrics and task linkage to executions table.

    Fixes delegate->activity browser data flow:
    - task_id: links execution back to creating task
    - cost_usd, tokens_used, input_tokens, output_tokens: persist metrics
    """
    cursor = conn.cursor()

    existing = {row[1] for row in cursor.execute("PRAGMA table_info(executions)").fetchall()}

    new_columns = [
        ("task_id", "INTEGER REFERENCES tasks(id)"),
        ("cost_usd", "REAL DEFAULT 0.0"),
        ("tokens_used", "INTEGER DEFAULT 0"),
        ("input_tokens", "INTEGER DEFAULT 0"),
        ("output_tokens", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE executions ADD COLUMN {col_name} {col_def}")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_task_id ON executions(task_id)")

    conn.commit()
