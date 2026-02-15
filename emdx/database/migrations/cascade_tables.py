"""Cascade system migrations.

These migrations establish the cascade/pipeline system:
- Document stage for pipeline processing
- PR URL tracking
- Cascade runs tracking
- Cascade metadata extraction
"""

import sqlite3


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
