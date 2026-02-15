"""Miscellaneous migrations.

These migrations add various standalone features:
- Standalone presets for emdx run
- Mail config and read receipts
- Execution metrics and task linkage
"""

import sqlite3


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


def migration_036_add_execution_metrics(conn: sqlite3.Connection):
    """Add metrics and task linkage to executions table.

    Fixes delegate→activity browser data flow:
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
