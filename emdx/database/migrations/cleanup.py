"""Cleanup and maintenance migrations.

These migrations remove unused tables, fix foreign keys, and optimize schema:
- Remove agent system tables
- Remove unused tables and dead code
- Remove workflow system tables
- Add ON DELETE CASCADE to foreign keys
- Add optimized indexes
"""

import sqlite3

from .runner import foreign_keys_disabled


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


def migration_035_remove_workflow_tables(conn: sqlite3.Connection):
    """Remove the entire workflow system.

    The workflow system has been replaced by recipes — markdown documents
    tagged with 📋 that Claude reads and follows via `emdx delegate`.

    Tables dropped:
    - workflow_presets
    - workflow_individual_runs
    - workflow_stage_runs
    - workflow_runs
    - workflows
    - document_sources (entirely workflow-coupled)

    FK columns cleaned:
    - task_executions.workflow_run_id → DROP column
    - document_groups.workflow_run_id → DROP column
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_task ON task_executions(task_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_execution ON task_executions(execution_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_type ON task_executions(execution_type)")

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

    conn.commit()


def migration_037_add_cascade_delete_fks(conn: sqlite3.Connection):
    """Add ON DELETE CASCADE to foreign keys missing it.

    This migration fixes 6 foreign keys that were created without CASCADE,
    which can lead to orphan data when parent records are deleted.

    Tables modified:
    - gists: document_id → documents(id) ON DELETE CASCADE
    - gdocs: document_id → documents(id) ON DELETE CASCADE
    - executions: doc_id → documents(id) ON DELETE SET NULL
    - export_history: document_id → documents(id) ON DELETE CASCADE
    - export_history: profile_id → export_profiles(id) ON DELETE CASCADE
    - cascade_runs: start_doc_id → documents(id) ON DELETE CASCADE
    - cascade_runs: current_doc_id → documents(id) ON DELETE SET NULL

    Note: executions.doc_id uses SET NULL because executions are valuable
    historical records even if the associated document is deleted.
    cascade_runs.current_doc_id uses SET NULL because the run may outlive
    intermediate documents.
    """
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = OFF")

    # 1. Recreate gists table with ON DELETE CASCADE
    cursor.execute("DROP TABLE IF EXISTS gists_new")
    cursor.execute("""
        CREATE TABLE gists_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            gist_id TEXT NOT NULL,
            gist_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_public BOOLEAN DEFAULT 0,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("INSERT INTO gists_new SELECT * FROM gists")
    cursor.execute("DROP TABLE gists")
    cursor.execute("ALTER TABLE gists_new RENAME TO gists")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gists_document ON gists(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gists_gist_id ON gists(gist_id)")

    # 2. Recreate gdocs table with ON DELETE CASCADE
    cursor.execute("DROP TABLE IF EXISTS gdocs_new")
    cursor.execute("""
        CREATE TABLE gdocs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            gdoc_id TEXT NOT NULL,
            gdoc_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, gdoc_id),
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("INSERT INTO gdocs_new SELECT * FROM gdocs")
    cursor.execute("DROP TABLE gdocs")
    cursor.execute("ALTER TABLE gdocs_new RENAME TO gdocs")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_document ON gdocs(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_gdoc_id ON gdocs(gdoc_id)")

    # 3. Recreate executions table with ON DELETE SET NULL for doc_id
    # Get current column info to preserve all columns added by later migrations
    cursor.execute("PRAGMA table_info(executions)")
    columns = cursor.fetchall()
    col_names = [col[1] for col in columns]

    cursor.execute("DROP TABLE IF EXISTS executions_new")
    cursor.execute("""
        CREATE TABLE executions_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER,
            doc_title TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            log_file TEXT NOT NULL,
            exit_code INTEGER,
            working_dir TEXT,
            pid INTEGER,
            cascade_run_id INTEGER REFERENCES cascade_runs(id),
            task_id INTEGER REFERENCES tasks(id),
            cost_usd REAL DEFAULT 0.0,
            tokens_used INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE SET NULL
        )
    """)

    # Build the column list for INSERT, only including columns that exist
    exec_cols = ['id', 'doc_id', 'doc_title', 'status', 'started_at', 'completed_at',
                 'log_file', 'exit_code', 'working_dir', 'pid', 'cascade_run_id',
                 'task_id', 'cost_usd', 'tokens_used', 'input_tokens', 'output_tokens']
    existing_cols = [c for c in exec_cols if c in col_names]
    cols_str = ', '.join(existing_cols)
    cursor.execute(f"INSERT INTO executions_new ({cols_str}) SELECT {cols_str} FROM executions")
    cursor.execute("DROP TABLE executions")
    cursor.execute("ALTER TABLE executions_new RENAME TO executions")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_task_id ON executions(task_id)")

    # 4. Recreate export_history table with ON DELETE CASCADE for both FKs
    cursor.execute("DROP TABLE IF EXISTS export_history_new")
    cursor.execute("""
        CREATE TABLE export_history_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            dest_type TEXT NOT NULL,
            dest_url TEXT,
            exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (profile_id) REFERENCES export_profiles(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("INSERT INTO export_history_new SELECT * FROM export_history")
    cursor.execute("DROP TABLE export_history")
    cursor.execute("ALTER TABLE export_history_new RENAME TO export_history")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_document ON export_history(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_profile ON export_history(profile_id)")

    # 5. Recreate cascade_runs table with proper CASCADE/SET NULL
    cursor.execute("DROP TABLE IF EXISTS cascade_runs_new")
    cursor.execute("""
        CREATE TABLE cascade_runs_new (
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
            FOREIGN KEY (start_doc_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (current_doc_id) REFERENCES documents(id) ON DELETE SET NULL
        )
    """)
    cursor.execute("INSERT INTO cascade_runs_new SELECT * FROM cascade_runs")
    cursor.execute("DROP TABLE cascade_runs")
    cursor.execute("ALTER TABLE cascade_runs_new RENAME TO cascade_runs")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cascade_runs_status ON cascade_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cascade_runs_start_doc ON cascade_runs(start_doc_id)")

    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def migration_038_add_title_lower_index(conn: sqlite3.Connection):
    """Add functional index on LOWER(title) for case-insensitive search.

    This index improves performance for case-insensitive title searches,
    which are common in the CLI (emdx find, emdx list, etc.).

    SQLite supports expression indexes since version 3.9.0 (2015).
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_title_lower
        ON documents(LOWER(title))
    """)

    conn.commit()
