"""Task system migrations.

These migrations establish the task management system:
- Tasks table
- Task dependencies
- Task log
- Task executions join table
- Delegate activity tracking
"""

import sqlite3


def migration_009_add_tasks(conn: sqlite3.Connection):
    """Add tasks tables for task management system."""
    cursor = conn.cursor()

    # Create tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 3,
            gameplan_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
            project TEXT,
            current_step TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # Create task dependencies table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_deps (
            task_id INTEGER NOT NULL,
            depends_on INTEGER NOT NULL,
            PRIMARY KEY (task_id, depends_on),
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
            FOREIGN KEY (depends_on) REFERENCES tasks(id) ON DELETE CASCADE
        )
    """)

    # Create task log table (append-only work log)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_gameplan ON tasks(gameplan_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_log_task ON task_log(task_id)")

    conn.commit()


def migration_010_add_task_executions(conn: sqlite3.Connection):
    """Add task_executions table - the join between tasks and workflows.

    This table connects the task system to the workflow system, tracking
    how each task was executed (via workflow, direct Claude call, or manually).
    """
    cursor = conn.cursor()

    # Create task_executions table - the join table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,

            -- Links to execution method (only one should be set based on type)
            workflow_run_id INTEGER REFERENCES workflow_runs(id) ON DELETE SET NULL,
            execution_id INTEGER REFERENCES executions(id) ON DELETE SET NULL,

            -- Execution type determines which link is used
            execution_type TEXT NOT NULL CHECK (execution_type IN ('workflow', 'direct', 'manual')),

            -- Status tracking
            status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),

            -- Timing
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,

            -- Notes/context
            notes TEXT
        )
    """)

    # Create indexes for efficient queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_task ON task_executions(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_workflow_run ON task_executions(workflow_run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_execution ON task_executions(execution_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_status ON task_executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_executions_type ON task_executions(execution_type)")

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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_parent_task_id ON tasks(parent_task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_output_doc_id ON tasks(output_doc_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_execution_id ON tasks(execution_id)")

    conn.commit()
