"""Database migration system for emdx."""

import sqlite3
from typing import Callable

from ..config.settings import get_db_path


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()
    return result[0] if result[0] is not None else 0


def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set the schema version."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def migration_001_add_tags(conn: sqlite3.Connection):
    """Add tags tables for tag system support."""
    cursor = conn.cursor()

    # Create tags table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0
        )
    """
    )

    # Create document_tags junction table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS document_tags (
            document_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (document_id, tag_id),
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """
    )

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_document_tags_tag_id ON document_tags(tag_id)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_document_tags_document_id ON document_tags(document_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")

    conn.commit()


def migration_002_add_executions(conn: sqlite3.Connection):
    """Add executions table for tracking Claude executions."""
    cursor = conn.cursor()

    # Create executions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            doc_id INTEGER NOT NULL,
            doc_title TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
            started_at TIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            log_file TEXT NOT NULL,
            exit_code INTEGER,
            working_dir TEXT,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    """
    )

    # Create indexes for efficient queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")

    conn.commit()


def migration_003_add_document_relationships(conn: sqlite3.Connection):
    """Add parent_id column to track document generation relationships."""
    cursor = conn.cursor()

    # Add parent_id column to documents table
    cursor.execute("ALTER TABLE documents ADD COLUMN parent_id INTEGER")
    
    # Add foreign key constraint (SQLite doesn't support adding FK constraints later)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_parent_id ON documents(parent_id)")

    conn.commit()


def migration_004_add_execution_pid(conn: sqlite3.Connection):
    """Add process ID tracking to executions table."""
    cursor = conn.cursor()
    
    # Add pid column to executions table
    cursor.execute("ALTER TABLE executions ADD COLUMN pid INTEGER")
    
    conn.commit()


# List of all migrations in order
MIGRATIONS: list[tuple[int, str, Callable]] = [
    (1, "Add tags system", migration_001_add_tags),
    (2, "Add executions tracking", migration_002_add_executions),
    (3, "Add document relationships", migration_003_add_document_relationships),
    (4, "Add execution PID tracking", migration_004_add_execution_pid),
]


def run_migrations():
    """Run all pending migrations."""
    db_path = get_db_path()
    if not db_path.exists():
        return  # Database will be created with latest schema

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        current_version = get_schema_version(conn)

        for version, description, migration_func in MIGRATIONS:
            if version > current_version:
                print(f"Running migration {version}: {description}")
                migration_func(conn)
                set_schema_version(conn, version)
                print(f"✅ Migration {version} completed")

    finally:
        conn.close()
