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
    # Return -1 for completely fresh installations (no version recorded yet)
    # This ensures migration 0 will run for new installations
    return result[0] if result[0] is not None else -1


def set_schema_version(conn: sqlite3.Connection, version: int):
    """Set the schema version."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def migration_000_create_documents_table(conn: sqlite3.Connection):
    """Create the initial documents table and related schema."""
    cursor = conn.cursor()
    
    # Create documents table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            deleted_at TIMESTAMP,
            is_deleted BOOLEAN DEFAULT FALSE
        )
        """
    )
    
    # Create FTS5 virtual table for full-text search
    cursor.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
            title, content, project, content=documents, content_rowid=id,
            tokenize='porter unicode61'
        )
        """
    )
    
    # Create triggers to keep FTS in sync
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
            INSERT INTO documents_fts(rowid, title, content, project)
            VALUES (new.id, new.title, new.content, new.project);
        END
        """
    )
    
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
            UPDATE documents_fts
            SET title = new.title, content = new.content, project = new.project
            WHERE rowid = old.id;
        END
        """
    )
    
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
            DELETE FROM documents_fts WHERE rowid = old.id;
        END
        """
    )
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_documents_accessed ON documents(accessed_at DESC)"
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_documents_deleted ON documents(
            is_deleted, deleted_at
        )
        """
    )
    
    # Create gists table for tracking document-gist relationships
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            gist_id TEXT NOT NULL,
            gist_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_public BOOLEAN DEFAULT 0,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
        """
    )
    
    # Create indexes for gists table
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gists_document ON gists(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gists_gist_id ON gists(gist_id)")
    
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


def migration_005_add_execution_heartbeat(conn: sqlite3.Connection):
    """Add heartbeat tracking to executions table."""
    cursor = conn.cursor()
    
    # Add last_heartbeat column to executions table
    cursor.execute("ALTER TABLE executions ADD COLUMN last_heartbeat TIMESTAMP")
    
    # Create index for efficient heartbeat queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_heartbeat ON executions(status, last_heartbeat)")
    
    conn.commit()


def migration_006_numeric_execution_ids(conn: sqlite3.Connection):
    """Convert executions table to use numeric IDs."""
    cursor = conn.cursor()
    
    # Check if we need to migrate (if id column is still TEXT)
    cursor.execute("PRAGMA table_info(executions)")
    columns = cursor.fetchall()
    id_col = next((col for col in columns if col[1] == 'id'), None)
    
    if id_col and id_col[2] == 'TEXT':
        # Create new table with numeric ID
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                doc_title TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                log_file TEXT NOT NULL,
                exit_code INTEGER,
                working_dir TEXT,
                pid INTEGER,
                last_heartbeat TIMESTAMP,
                old_id TEXT,  -- Keep old ID for reference
                FOREIGN KEY (doc_id) REFERENCES documents(id)
            )
        """)
        
        # Copy data from old table
        cursor.execute("""
            INSERT INTO executions_new 
            (doc_id, doc_title, status, started_at, completed_at, log_file, 
             exit_code, working_dir, pid, last_heartbeat, old_id)
            SELECT doc_id, doc_title, status, started_at, completed_at, log_file,
                   exit_code, working_dir, pid, NULL, id
            FROM executions
        """)
        
        # Drop old table and rename new one
        cursor.execute("DROP TABLE executions")
        cursor.execute("ALTER TABLE executions_new RENAME TO executions")
        
        # Recreate indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_heartbeat ON executions(status, last_heartbeat)")
    
    conn.commit()


def migration_007_add_agent_tables(conn: sqlite3.Connection):
    """Add tables for agent system."""
    cursor = conn.cursor()
    
    # Create agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('research', 'generation', 'analysis', 'maintenance')),
            
            -- Prompt configuration
            system_prompt TEXT NOT NULL,
            user_prompt_template TEXT NOT NULL,
            
            -- Tool configuration
            allowed_tools TEXT NOT NULL,  -- JSON array of tool names
            tool_restrictions TEXT,       -- JSON object with per-tool restrictions
            
            -- Execution configuration
            max_iterations INTEGER DEFAULT 10,
            timeout_seconds INTEGER DEFAULT 3600,
            requires_confirmation BOOLEAN DEFAULT FALSE,
            
            -- Context configuration
            max_context_docs INTEGER DEFAULT 5,
            context_search_query TEXT,
            include_doc_content BOOLEAN DEFAULT TRUE,
            
            -- Output configuration
            output_format TEXT DEFAULT 'markdown',
            save_outputs BOOLEAN DEFAULT TRUE,
            output_tags TEXT,  -- JSON array of tags
            
            -- Metadata
            version INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            is_builtin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            
            -- Usage tracking
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0
        )
    """)
    
    # Create agent executions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            execution_id INTEGER NOT NULL,
            
            -- Input/Output tracking
            input_type TEXT NOT NULL CHECK (input_type IN ('document', 'query', 'pipeline')),
            input_doc_id INTEGER,
            input_query TEXT,
            output_doc_ids TEXT,  -- JSON array of created doc IDs
            
            -- Execution details
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            
            -- Performance metrics
            total_tokens_used INTEGER,
            execution_time_ms INTEGER,
            iterations_used INTEGER,
            
            -- Context tracking
            context_doc_ids TEXT,  -- JSON array of doc IDs used as context
            tools_used TEXT,       -- JSON array of tools actually used
            
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (execution_id) REFERENCES executions(id),
            FOREIGN KEY (input_doc_id) REFERENCES documents(id)
        )
    """)
    
    # Create agent pipelines table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_pipelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            
            -- Pipeline configuration
            agents TEXT NOT NULL,  -- JSON array of {agent_id, config}
            execution_mode TEXT DEFAULT 'sequential' CHECK (execution_mode IN ('sequential', 'parallel', 'conditional')),
            stop_on_error BOOLEAN DEFAULT TRUE,
            
            -- Metadata
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            
            -- Usage tracking
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP
        )
    """)
    
    # Create agent templates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            agent_config TEXT NOT NULL,  -- Full agent configuration as JSON
            
            -- Sharing metadata
            is_public BOOLEAN DEFAULT FALSE,
            author TEXT NOT NULL,
            tags TEXT,  -- JSON array for categorization
            
            -- Usage tracking
            install_count INTEGER DEFAULT 0,
            rating_sum INTEGER DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON agent_executions(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_executions_status ON agent_executions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_executions_started_at ON agent_executions(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents(is_active)")
    
    # Insert default system agents
    cursor.execute("""
        INSERT INTO agents (
            name, display_name, description, category,
            system_prompt, user_prompt_template,
            allowed_tools, is_builtin, created_by
        ) VALUES 
        (
            'doc-generator',
            'Documentation Generator',
            'Generates comprehensive documentation from code analysis',
            'generation',
            'You are a documentation expert. Your role is to analyze code and generate clear, comprehensive documentation that helps developers understand and use the codebase effectively.',
            'Analyze {{target}} and generate {{doc_type}} documentation. Focus on clarity, completeness, and practical examples.',
            '["Glob", "Grep", "Read", "Write", "Task"]',
            TRUE,
            'system'
        ),
        (
            'code-reviewer',
            'Code Reviewer',
            'Reviews code changes and provides feedback',
            'analysis',
            'You are an expert code reviewer focusing on code quality, security, performance, and best practices. Provide constructive feedback that helps developers improve their code.',
            'Review the following code changes:\n\n{{diff}}\n\nFocus on: {{focus_areas}}',
            '["Read", "Grep", "Glob"]',
            TRUE,
            'system'
        )
    """)
    
    conn.commit()


# List of all migrations in order
MIGRATIONS: list[tuple[int, str, Callable]] = [
    (0, "Create documents table", migration_000_create_documents_table),
    (1, "Add tags system", migration_001_add_tags),
    (2, "Add executions tracking", migration_002_add_executions),
    (3, "Add document relationships", migration_003_add_document_relationships),
    (4, "Add execution PID tracking", migration_004_add_execution_pid),
    (5, "Add execution heartbeat tracking", migration_005_add_execution_heartbeat),
    (6, "Convert to numeric execution IDs", migration_006_numeric_execution_ids),
    (7, "Add agent system tables", migration_007_add_agent_tables),
]


def run_migrations():
    """Run all pending migrations."""
    db_path = get_db_path()
    # Don't return early - we need to run migrations even for new databases
    # The database file will be created when we connect to it
    
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
