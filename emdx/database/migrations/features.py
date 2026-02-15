"""Feature addition migrations (011-020).

This module contains migrations that add new features:
- Dynamic workflow mode
- Google Docs exports
- Export profiles
- Token and cost tracking
- Document hierarchy and sources
"""

import sqlite3

from ._utils import foreign_keys_disabled


def migration_011_add_dynamic_workflow_mode(conn: sqlite3.Connection):
    """Add 'dynamic' to workflow stage mode CHECK constraint.

    Dynamic mode allows stages to discover items at runtime and process
    them in parallel with isolated worktrees.
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
        # SQLite doesn't support ALTER TABLE to modify constraints, so we need to
        # recreate the table with the new constraint
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_stage_runs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_run_id INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('single', 'parallel', 'iterative', 'adversarial', 'dynamic')),
                target_runs INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                runs_completed INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                output_doc_id INTEGER,
                synthesis_doc_id INTEGER,
                error_message TEXT,
                tokens_used INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id),
                FOREIGN KEY (output_doc_id) REFERENCES documents(id),
                FOREIGN KEY (synthesis_doc_id) REFERENCES documents(id)
            )
        """)

        # Copy data from old table
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


def migration_012_add_gdocs(conn: sqlite3.Connection):
    """Add gdocs table for tracking Google Docs exports."""
    cursor = conn.cursor()

    # Create gdocs table for tracking document-gdoc relationships
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gdocs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            gdoc_id TEXT NOT NULL,
            gdoc_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, gdoc_id),
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    """)

    # Create indexes for gdocs table
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_document ON gdocs(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_gdoc_id ON gdocs(gdoc_id)")

    conn.commit()


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


def migration_014_fix_individual_runs_fk(conn: sqlite3.Connection):
    """Fix workflow_individual_runs FK to reference executions instead of agent_executions.

    The workflow executor uses the executions table directly for tracking,
    not agent_executions. This migration fixes the foreign key constraint.
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
        # Recreate table with corrected FK
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_individual_runs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage_run_id INTEGER NOT NULL,
                run_number INTEGER NOT NULL,
                agent_execution_id INTEGER,
                prompt_used TEXT,
                input_context TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                output_doc_id INTEGER,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                tokens_used INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                FOREIGN KEY (stage_run_id) REFERENCES workflow_stage_runs(id),
                FOREIGN KEY (agent_execution_id) REFERENCES executions(id),
                FOREIGN KEY (output_doc_id) REFERENCES documents(id)
            )
        """)

        # Copy data from old table
        cursor.execute("""
            INSERT INTO workflow_individual_runs_new
            SELECT * FROM workflow_individual_runs
        """)

        # Drop old table and rename new one
        cursor.execute("DROP TABLE workflow_individual_runs")
        cursor.execute("ALTER TABLE workflow_individual_runs_new RENAME TO workflow_individual_runs")

        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_stage_run_id ON workflow_individual_runs(stage_run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_status ON workflow_individual_runs(status)")

    conn.commit()


def migration_015_add_export_profiles(conn: sqlite3.Connection):
    """Add export profiles and export history tables.

    Export profiles provide reusable, configurable export configurations
    for transforming and exporting EMDX documents to various formats and
    destinations (clipboard, file, Google Docs, GitHub Gist).
    """
    cursor = conn.cursor()

    # Create export_profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            format TEXT NOT NULL DEFAULT 'markdown',
            strip_tags TEXT,  -- JSON array of emoji tags to strip
            add_frontmatter BOOLEAN DEFAULT FALSE,
            frontmatter_fields TEXT,  -- JSON array: ['title', 'date', 'tags']
            header_template TEXT,
            footer_template TEXT,
            tag_to_label TEXT,  -- JSON object: {'🔧': 'refactor', '🐛': 'bug'}
            dest_type TEXT NOT NULL DEFAULT 'clipboard',
            dest_path TEXT,
            gdoc_folder TEXT,
            gist_public BOOLEAN DEFAULT FALSE,
            post_actions TEXT,  -- JSON array: ['copy_url', 'open_browser']
            project TEXT,  -- NULL = global profile
            is_active BOOLEAN DEFAULT TRUE,
            is_builtin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP
        )
    """)

    # Create export_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            dest_type TEXT NOT NULL,
            dest_url TEXT,
            exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (profile_id) REFERENCES export_profiles(id)
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_name ON export_profiles(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_project ON export_profiles(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_is_active ON export_profiles(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_document ON export_history(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_profile ON export_history(profile_id)")

    # Insert built-in profiles
    builtin_profiles = [
        {
            'name': 'blog-post',
            'display_name': 'Blog Post',
            'description': 'Export as blog post with YAML frontmatter',
            'format': 'markdown',
            'add_frontmatter': True,
            'frontmatter_fields': '["title", "date", "tags"]',
            'strip_tags': '["🚧", "🚨", "🐛"]',
            'dest_type': 'file',
            'dest_path': '~/blog/drafts/{{title}}.md',
            'is_builtin': True,
        },
        {
            'name': 'gdoc-meeting',
            'display_name': 'Google Doc (Meeting)',
            'description': 'Export meeting notes to Google Docs',
            'format': 'gdoc',
            'header_template': '# Meeting Notes: {{title}}\n\nDate: {{date}}\n',
            'dest_type': 'gdoc',
            'gdoc_folder': 'EMDX Meetings',
            'is_builtin': True,
        },
        {
            'name': 'github-issue',
            'display_name': 'GitHub Issue',
            'description': 'Format for GitHub issue creation',
            'format': 'markdown',
            'tag_to_label': '{"🐛": "bug", "✨": "enhancement", "🔧": "refactor"}',
            'strip_tags': '["🚧", "🚨"]',
            'dest_type': 'clipboard',
            'is_builtin': True,
        },
        {
            'name': 'share-external',
            'display_name': 'Share External',
            'description': 'Clean version for external sharing',
            'format': 'markdown',
            'strip_tags': '["🚧", "🚨", "🐛", "🎯", "🔍"]',
            'dest_type': 'clipboard',
            'is_builtin': True,
        },
        {
            'name': 'quick-gist',
            'display_name': 'Quick Gist',
            'description': 'Create secret GitHub gist',
            'format': 'gist',
            'dest_type': 'gist',
            'gist_public': False,
            'post_actions': '["copy_url", "open_browser"]',
            'is_builtin': True,
        },
    ]

    for profile in builtin_profiles:
        cursor.execute("""
            INSERT OR IGNORE INTO export_profiles (
                name, display_name, description, format,
                add_frontmatter, frontmatter_fields, strip_tags,
                header_template, footer_template, tag_to_label,
                dest_type, dest_path, gdoc_folder, gist_public,
                post_actions, is_builtin
            ) VALUES (
                :name, :display_name, :description, :format,
                :add_frontmatter, :frontmatter_fields, :strip_tags,
                :header_template, :footer_template, :tag_to_label,
                :dest_type, :dest_path, :gdoc_folder, :gist_public,
                :post_actions, :is_builtin
            )
        """, {
            'name': profile.get('name'),
            'display_name': profile.get('display_name'),
            'description': profile.get('description'),
            'format': profile.get('format', 'markdown'),
            'add_frontmatter': profile.get('add_frontmatter', False),
            'frontmatter_fields': profile.get('frontmatter_fields'),
            'strip_tags': profile.get('strip_tags'),
            'header_template': profile.get('header_template'),
            'footer_template': profile.get('footer_template'),
            'tag_to_label': profile.get('tag_to_label'),
            'dest_type': profile.get('dest_type', 'clipboard'),
            'dest_path': profile.get('dest_path'),
            'gdoc_folder': profile.get('gdoc_folder'),
            'gist_public': profile.get('gist_public', False),
            'post_actions': profile.get('post_actions'),
            'is_builtin': profile.get('is_builtin', False),
        })

    conn.commit()


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


# Export all migrations from this module
FEATURES_MIGRATIONS = [
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
]
