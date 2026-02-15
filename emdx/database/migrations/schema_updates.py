"""Schema update migrations.

These migrations modify existing tables with additional columns and features:
- Make execution doc_id nullable
- Document hierarchy columns
- Document sources bridge table
- Document groups system
- Embeddings for semantic search
"""

import sqlite3

from .runner import foreign_keys_disabled


def migration_013_make_execution_doc_id_nullable(conn: sqlite3.Connection):
    """Make doc_id nullable in executions table for workflow agent runs.

    Workflow agent executions don't always have an associated document,
    so doc_id should be nullable instead of NOT NULL.
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
        # SQLite doesn't support ALTER TABLE to modify constraints, so we need to
        # recreate the table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions_new (
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
                FOREIGN KEY (doc_id) REFERENCES documents(id)
            )
        """)

        # Copy data from old table
        cursor.execute("""
            INSERT INTO executions_new (id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid)
            SELECT id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid
            FROM executions
        """)

        # Drop old table and rename new one
        cursor.execute("DROP TABLE executions")
        cursor.execute("ALTER TABLE executions_new RENAME TO executions")

        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")

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
