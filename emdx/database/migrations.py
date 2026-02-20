"""Database migration system for emdx."""
# ruff: noqa: E501
# SQL schema definitions contain long lines for readability; breaking them
# would make the migration scripts harder to understand and maintain.

import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

from ..config.settings import get_db_path


@contextmanager
def foreign_keys_disabled(conn: sqlite3.Connection) -> Generator[None, None, None]:
    """Context manager to temporarily disable foreign key constraints.

    Used during migrations that need to recreate tables, which requires
    foreign keys to be disabled to avoid constraint violations during
    the table swap.

    Usage:
        with foreign_keys_disabled(conn):
            # recreate table operations here
            pass
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")
    try:
        yield
    finally:
        cursor.execute("PRAGMA foreign_keys = ON")


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


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the schema version."""
    cursor = conn.cursor()
    cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def migration_000_create_documents_table(conn: sqlite3.Connection) -> None:
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


def migration_001_add_tags(conn: sqlite3.Connection) -> None:
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


def migration_002_add_executions(conn: sqlite3.Connection) -> None:
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


def migration_003_add_document_relationships(conn: sqlite3.Connection) -> None:
    """Add parent_id column to track document generation relationships."""
    cursor = conn.cursor()

    # Add parent_id column to documents table
    cursor.execute("ALTER TABLE documents ADD COLUMN parent_id INTEGER")

    # Add foreign key constraint (SQLite doesn't support adding FK constraints later)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_parent_id ON documents(parent_id)")

    conn.commit()


def migration_004_add_execution_pid(conn: sqlite3.Connection) -> None:
    """Add process ID tracking to executions table."""
    cursor = conn.cursor()

    # Add pid column to executions table
    cursor.execute("ALTER TABLE executions ADD COLUMN pid INTEGER")

    conn.commit()


def migration_005_add_execution_heartbeat(conn: sqlite3.Connection) -> None:
    """Add heartbeat tracking to executions table."""
    cursor = conn.cursor()

    # Add last_heartbeat column to executions table
    cursor.execute("ALTER TABLE executions ADD COLUMN last_heartbeat TIMESTAMP")

    # Create index for efficient heartbeat queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_heartbeat ON executions(status, last_heartbeat)"
    )

    conn.commit()


def migration_006_numeric_execution_ids(conn: sqlite3.Connection) -> None:
    """Convert executions table to use numeric IDs."""
    cursor = conn.cursor()

    # Check if we need to migrate (if id column is still TEXT)
    cursor.execute("PRAGMA table_info(executions)")
    columns = cursor.fetchall()
    id_col = next((col for col in columns if col[1] == "id"), None)

    if id_col and id_col[2] == "TEXT":
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_executions_heartbeat ON executions(status, last_heartbeat)"
        )

    conn.commit()


def migration_007_add_agent_tables(conn: sqlite3.Connection) -> None:
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON agent_executions(agent_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_status ON agent_executions(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_executions_started_at ON agent_executions(started_at)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents(is_active)")

    # Insert default system agents
    cursor.execute("""
        INSERT OR IGNORE INTO agents (
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


def migration_008_add_workflow_tables(conn: sqlite3.Connection) -> None:
    """Add tables for workflow orchestration system.

    Workflows allow composing multiple agent runs with different execution modes:
    - single: Run once
    - parallel: Run N times simultaneously, synthesize results
    - iterative: Run N times sequentially, each building on previous
    - adversarial: Advocate -> Critic -> Synthesizer pattern
    """
    cursor = conn.cursor()

    # Create workflows table - defines reusable workflow templates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            definition_json TEXT NOT NULL,
            category TEXT DEFAULT 'custom' CHECK (category IN ('analysis', 'planning', 'implementation', 'review', 'custom')),
            is_builtin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            usage_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0
        )
    """)

    # Create workflow_runs table - tracks each execution of a workflow
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            gameplan_id INTEGER,
            task_id INTEGER,
            parent_run_id INTEGER,
            input_doc_id INTEGER,
            input_variables TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
            current_stage TEXT,
            current_stage_run INTEGER DEFAULT 0,
            context_json TEXT DEFAULT '{}',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            output_doc_ids TEXT,
            error_message TEXT,
            total_tokens_used INTEGER DEFAULT 0,
            total_execution_time_ms INTEGER DEFAULT 0,
            FOREIGN KEY (workflow_id) REFERENCES workflows(id),
            FOREIGN KEY (input_doc_id) REFERENCES documents(id),
            FOREIGN KEY (parent_run_id) REFERENCES workflow_runs(id)
        )
    """)

    # Create workflow_stage_runs table - tracks each stage execution
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_stage_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_run_id INTEGER NOT NULL,
            stage_name TEXT NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('single', 'parallel', 'iterative', 'adversarial')),
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

    # Create workflow_individual_runs table - tracks each individual run within a stage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_individual_runs (
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
            FOREIGN KEY (agent_execution_id) REFERENCES agent_executions(id),
            FOREIGN KEY (output_doc_id) REFERENCES documents(id)
        )
    """)

    # Create iteration_strategies table - predefined prompt sequences for iterative mode
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS iteration_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            prompts_json TEXT NOT NULL,
            recommended_runs INTEGER DEFAULT 5,
            category TEXT DEFAULT 'general',
            is_builtin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflows_category ON workflows(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflows_is_active ON workflows(is_active)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_stage_run_id ON workflow_individual_runs(stage_run_id)"
    )

    # Insert builtin iteration strategies
    cursor.execute("""
        INSERT OR IGNORE INTO iteration_strategies (name, display_name, description, prompts_json, recommended_runs, category, is_builtin)
        VALUES
        ('analysis_deepening', 'Analysis Deepening', 'Progressive analysis that digs deeper with each iteration',
         '["Analyze {{input}} thoroughly.", "What did {{prev}} miss?", "Synthesize {{all_prev}}.", "Steel-man weakest points.", "Final synthesis."]',
         5, 'analysis', TRUE),
        ('plan_refinement', 'Plan Refinement', 'Iterative planning that identifies and addresses risks',
         '["Create initial plan for {{input}}.", "Review risks in {{prev}}.", "Revise plan.", "Identify failure modes.", "Final plan."]',
         5, 'planning', TRUE),
        ('adversarial_review', 'Adversarial Review', 'Advocate-Critic-Synthesizer pattern',
         '["ADVOCATE: Argue FOR {{input}}.", "CRITIC: Argue AGAINST {{prev}}.", "SYNTHESIS: Balance views."]',
         3, 'review', TRUE)
    """)

    # Insert builtin workflow templates
    cursor.execute("""
        INSERT OR IGNORE INTO workflows (name, display_name, description, definition_json, category, is_builtin, created_by)
        VALUES
        ('deep_analysis', 'Deep Analysis', 'Parallel coverage + iterative deepening',
         '{"stages": [{"name": "initial_scan", "mode": "parallel", "runs": 3}, {"name": "deep_dive", "mode": "iterative", "runs": 5, "iteration_strategy": "analysis_deepening"}]}',
         'analysis', TRUE, 'system'),
        ('robust_planning', 'Robust Planning', 'Iterative refinement + adversarial review',
         '{"stages": [{"name": "initial_plan", "mode": "iterative", "runs": 3, "iteration_strategy": "plan_refinement"}, {"name": "challenge", "mode": "adversarial", "runs": 3}]}',
         'planning', TRUE, 'system'),
        ('quick_analysis', 'Quick Analysis', 'Fast parallel analysis with synthesis',
         '{"stages": [{"name": "analyze", "mode": "parallel", "runs": 3}]}',
         'analysis', TRUE, 'system')
    """)

    conn.commit()


def migration_009_add_tasks(conn: sqlite3.Connection) -> None:
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


def migration_010_add_task_executions(conn: sqlite3.Connection) -> None:
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_task ON task_executions(task_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_workflow_run ON task_executions(workflow_run_id)"
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

    conn.commit()


def migration_011_add_dynamic_workflow_mode(conn: sqlite3.Connection) -> None:
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)"
        )

    conn.commit()


def migration_012_add_gdocs(conn: sqlite3.Connection) -> None:
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


def migration_013_make_execution_doc_id_nullable(conn: sqlite3.Connection) -> None:
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_executions_started_at ON executions(started_at)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_executions_doc_id ON executions(doc_id)")

    conn.commit()


def migration_014_fix_individual_runs_fk(conn: sqlite3.Connection) -> None:
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
        cursor.execute(
            "ALTER TABLE workflow_individual_runs_new RENAME TO workflow_individual_runs"
        )

        # Recreate indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_stage_run_id ON workflow_individual_runs(stage_run_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_status ON workflow_individual_runs(status)"
        )

    conn.commit()


def migration_015_add_export_profiles(conn: sqlite3.Connection) -> None:
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_profiles_project ON export_profiles(project)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_profiles_is_active ON export_profiles(is_active)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_history_document ON export_history(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_history_profile ON export_history(profile_id)"
    )

    # Insert built-in profiles
    builtin_profiles = [
        {
            "name": "blog-post",
            "display_name": "Blog Post",
            "description": "Export as blog post with YAML frontmatter",
            "format": "markdown",
            "add_frontmatter": True,
            "frontmatter_fields": '["title", "date", "tags"]',
            "strip_tags": '["🚧", "🚨", "🐛"]',
            "dest_type": "file",
            "dest_path": "~/blog/drafts/{{title}}.md",
            "is_builtin": True,
        },
        {
            "name": "gdoc-meeting",
            "display_name": "Google Doc (Meeting)",
            "description": "Export meeting notes to Google Docs",
            "format": "gdoc",
            "header_template": "# Meeting Notes: {{title}}\n\nDate: {{date}}\n",
            "dest_type": "gdoc",
            "gdoc_folder": "EMDX Meetings",
            "is_builtin": True,
        },
        {
            "name": "github-issue",
            "display_name": "GitHub Issue",
            "description": "Format for GitHub issue creation",
            "format": "markdown",
            "tag_to_label": '{"🐛": "bug", "✨": "enhancement", "🔧": "refactor"}',
            "strip_tags": '["🚧", "🚨"]',
            "dest_type": "clipboard",
            "is_builtin": True,
        },
        {
            "name": "share-external",
            "display_name": "Share External",
            "description": "Clean version for external sharing",
            "format": "markdown",
            "strip_tags": '["🚧", "🚨", "🐛", "🎯", "🔍"]',
            "dest_type": "clipboard",
            "is_builtin": True,
        },
        {
            "name": "quick-gist",
            "display_name": "Quick Gist",
            "description": "Create secret GitHub gist",
            "format": "gist",
            "dest_type": "gist",
            "gist_public": False,
            "post_actions": '["copy_url", "open_browser"]',
            "is_builtin": True,
        },
    ]

    for profile in builtin_profiles:
        cursor.execute(
            """
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
        """,
            {
                "name": profile.get("name"),
                "display_name": profile.get("display_name"),
                "description": profile.get("description"),
                "format": profile.get("format", "markdown"),
                "add_frontmatter": profile.get("add_frontmatter", False),
                "frontmatter_fields": profile.get("frontmatter_fields"),
                "strip_tags": profile.get("strip_tags"),
                "header_template": profile.get("header_template"),
                "footer_template": profile.get("footer_template"),
                "tag_to_label": profile.get("tag_to_label"),
                "dest_type": profile.get("dest_type", "clipboard"),
                "dest_path": profile.get("dest_path"),
                "gdoc_folder": profile.get("gdoc_folder"),
                "gist_public": profile.get("gist_public", False),
                "post_actions": profile.get("post_actions"),
                "is_builtin": profile.get("is_builtin", False),
            },
        )

    conn.commit()


def migration_016_add_input_output_tokens(conn: sqlite3.Connection) -> None:
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


def migration_017_add_cost_usd(conn: sqlite3.Connection) -> None:
    """Add cost_usd column to workflow_individual_runs.

    Stores the actual cost from Claude API for accurate billing tracking.
    """
    cursor = conn.cursor()

    cursor.execute("""
        ALTER TABLE workflow_individual_runs ADD COLUMN cost_usd REAL DEFAULT 0.0
    """)

    conn.commit()


def migration_018_add_document_hierarchy(conn: sqlite3.Connection) -> None:
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_archived_at ON documents(archived_at)")

    conn.commit()


def migration_019_add_document_sources(conn: sqlite3.Connection) -> None:
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


def _backfill_document_sources(cursor: sqlite3.Cursor) -> None:
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


def migration_020_add_synthesis_cost(conn: sqlite3.Connection) -> None:
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


def migration_021_add_workflow_presets(conn: sqlite3.Connection) -> None:
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


def migration_022_add_document_groups(conn: sqlite3.Connection) -> None:
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


def migration_023_deactivate_legacy_workflows(conn: sqlite3.Connection) -> None:
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
        "deep_analysis",
        "robust_planning",
        "quick_analysis",
        "tech_debt_analysis",
        "code_fix",
        "tech_debt_discovery",
        "architecture_review",
        "fix_and_pr",
        "comprehensive_tech_debt",
        "parallel_task_fix",
        "feature_exploration",
        "feature_exploration_v2",
        "feature_exploration_dynamic",
        "feature_development",
        "feature_development_v2",
        "full_feature_development",
        "implement_tracks_c_d",
        "weird_feature_exploration",
        "tech_debt_parallel_fix",
        "merge_main_all_branches",
        "ux_views_analysis",
    ]

    # Soft-delete by setting is_active = FALSE
    placeholders = ",".join("?" * len(legacy_workflows))
    cursor.execute(
        f"""
        UPDATE workflows
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE name IN ({placeholders})
        """,
        legacy_workflows,
    )

    conn.commit()


def migration_024_remove_agent_tables(conn: sqlite3.Connection) -> None:
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


def migration_025_add_standalone_presets(conn: sqlite3.Connection) -> None:
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


def migration_026_add_embeddings(conn: sqlite3.Connection) -> None:
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


def migration_027_add_synthesizing_status(conn: sqlite3.Connection) -> None:
    """Add 'synthesizing' status to workflow_stage_runs.

    When a parallel or dynamic workflow enters the synthesis phase
    (combining outputs from multiple runs), this status is used to
    indicate the phase in the UI with a "🔮 Synthesizing..." indicator.
    """
    cursor = conn.cursor()

    with foreign_keys_disabled(conn):
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

    conn.commit()


def migration_028_add_document_stage(conn: sqlite3.Connection) -> None:
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


def migration_029_add_document_pr_url(conn: sqlite3.Connection) -> None:
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


def migration_030_cleanup_unused_tables(conn: sqlite3.Connection) -> None:
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


def migration_031_add_cascade_runs(conn: sqlite3.Connection) -> None:
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


def migration_032_extract_cascade_metadata(conn: sqlite3.Connection) -> None:
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


def migration_033_add_mail_config(conn: sqlite3.Connection) -> None:
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


def migration_034_delegate_activity_tracking(conn: sqlite3.Connection) -> None:
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


def migration_035_remove_workflow_tables(conn: sqlite3.Connection) -> None:
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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dg_parent ON document_groups(parent_group_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_project ON document_groups(project)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_type ON document_groups(group_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dg_active ON document_groups(is_active)")

    conn.commit()


def migration_036_add_execution_metrics(conn: sqlite3.Connection) -> None:
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


def migration_037_add_cascade_delete_fks(conn: sqlite3.Connection) -> None:
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
    exec_cols = [
        "id",
        "doc_id",
        "doc_title",
        "status",
        "started_at",
        "completed_at",
        "log_file",
        "exit_code",
        "working_dir",
        "pid",
        "cascade_run_id",
        "task_id",
        "cost_usd",
        "tokens_used",
        "input_tokens",
        "output_tokens",
    ]
    existing_cols = [c for c in exec_cols if c in col_names]
    cols_str = ", ".join(existing_cols)
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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_history_document ON export_history(document_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_export_history_profile ON export_history(profile_id)"
    )

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
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cascade_runs_start_doc ON cascade_runs(start_doc_id)"
    )

    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def migration_038_add_title_lower_index(conn: sqlite3.Connection) -> None:
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


def migration_039_add_categories_and_epic_fields(conn: sqlite3.Connection) -> None:
    """Add categories table and epic fields to tasks.

    Categories are permanent buckets with a short key (SEC, DEBT) that own
    the numbering namespace. Epics are regular tasks with type='epic' that
    group work within a category.
    """
    cursor = conn.cursor()

    # Create categories table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add epic columns to tasks
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(tasks)").fetchall()}

    if "epic_key" not in existing:
        cursor.execute("ALTER TABLE tasks ADD COLUMN epic_key TEXT REFERENCES categories(key)")
    if "epic_seq" not in existing:
        cursor.execute("ALTER TABLE tasks ADD COLUMN epic_seq INTEGER")

    # Unique index: only one task per (epic_key, epic_seq) combination
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_epic_seq
        ON tasks(epic_key, epic_seq)
        WHERE epic_key IS NOT NULL AND epic_seq IS NOT NULL
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_epic_key ON tasks(epic_key)")

    conn.commit()


def migration_040_add_chunk_embeddings(conn: sqlite3.Connection) -> None:
    """Add chunk embeddings table for chunk-level semantic search.

    Chunks are sections of documents split by markdown headings. Each chunk
    gets its own embedding, enabling more precise semantic search that returns
    the relevant paragraph, not the entire 5000-word document.
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunk_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            heading_path TEXT NOT NULL,
            text TEXT NOT NULL,
            model_name TEXT NOT NULL,
            embedding BLOB NOT NULL,
            dimension INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
            UNIQUE(document_id, chunk_index, model_name)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_document
        ON chunk_embeddings(document_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_model
        ON chunk_embeddings(model_name)
    """)

    conn.commit()


def migration_041_add_execution_output_text(conn: sqlite3.Connection) -> None:
    """Add output_text column to executions for persisting answer text.

    When an execution completes (e.g. TUI Ask), the answer text is stored here
    so the activity screen can display it without parsing log files.
    """
    cursor = conn.cursor()
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(executions)").fetchall()}
    if "output_text" not in existing:
        cursor.execute("ALTER TABLE executions ADD COLUMN output_text TEXT")
    conn.commit()


def migration_042_convert_emoji_tags_to_text(conn: sqlite3.Connection) -> None:
    """Convert emoji tags to their canonical text equivalents.

    This migration removes the emoji alias system. All emoji tags in the
    tags table are converted to their text form (e.g., 🎯 → gameplan).
    If both the emoji and text tag exist, document_tags associations are
    moved from the emoji tag to the text tag, then the emoji tag is deleted.
    """
    cursor = conn.cursor()

    # Hardcoded reverse map: emoji → canonical text name
    emoji_to_text: dict[str, str] = {
        "🎯": "gameplan",
        "🔍": "analysis",
        "📝": "notes",
        "📚": "docs",
        "🏗️": "architecture",
        "🚀": "active",
        "✅": "done",
        "🚧": "blocked",
        "🎉": "success",
        "❌": "failed",
        "⚡": "partial",
        "🔧": "refactor",
        "🧪": "test",
        "🐛": "bug",
        "✨": "feature",
        "💎": "quality",
        "🚨": "urgent",
        "🐌": "low",
        "📊": "project",
        "📋": "recipe",
        "🟢": "active",  # anomaly — merge into active
    }

    for emoji, text_name in emoji_to_text.items():
        # Check if the emoji tag exists
        cursor.execute("SELECT id FROM tags WHERE name = ?", (emoji,))
        emoji_row = cursor.fetchone()
        if not emoji_row:
            continue
        emoji_tag_id = emoji_row[0]

        # Check if the text equivalent already exists
        cursor.execute("SELECT id FROM tags WHERE name = ?", (text_name,))
        text_row = cursor.fetchone()

        if text_row:
            # Text tag exists — move associations from emoji to text tag
            text_tag_id = text_row[0]

            # Move document_tags: update emoji→text, ignore duplicates
            cursor.execute(
                "UPDATE OR IGNORE document_tags SET tag_id = ? WHERE tag_id = ?",
                (text_tag_id, emoji_tag_id),
            )
            # Delete any remaining emoji associations (duplicates that were ignored)
            cursor.execute(
                "DELETE FROM document_tags WHERE tag_id = ?",
                (emoji_tag_id,),
            )
            # Delete the emoji tag
            cursor.execute("DELETE FROM tags WHERE id = ?", (emoji_tag_id,))

            # Update usage count on the text tag
            cursor.execute(
                """
                UPDATE tags SET usage_count = (
                    SELECT COUNT(DISTINCT document_id)
                    FROM document_tags WHERE tag_id = ?
                ) WHERE id = ?
                """,
                (text_tag_id, text_tag_id),
            )
        else:
            # No text equivalent — just rename the emoji tag
            cursor.execute(
                "UPDATE tags SET name = ? WHERE id = ?",
                (text_name, emoji_tag_id),
            )

    conn.commit()


def migration_043_add_document_links(conn: sqlite3.Connection) -> None:
    """Add document_links table for bidirectional knowledge graph links.

    Stores semantic similarity links between documents, both auto-detected
    (via embedding similarity on save) and manually created.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS document_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_doc_id INTEGER NOT NULL,
            target_doc_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            method TEXT NOT NULL DEFAULT 'auto',
            FOREIGN KEY (source_doc_id)
                REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY (target_doc_id)
                REFERENCES documents(id) ON DELETE CASCADE,
            UNIQUE(source_doc_id, target_doc_id)
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_links_source "
        "ON document_links(source_doc_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_doc_links_target "
        "ON document_links(target_doc_id)"
    )

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
    (8, "Add workflow orchestration tables", migration_008_add_workflow_tables),
    (9, "Add tasks system", migration_009_add_tasks),
    (10, "Add task executions join table", migration_010_add_task_executions),
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
    (21, "Add workflow presets", migration_021_add_workflow_presets),
    (22, "Add document groups system", migration_022_add_document_groups),
    (23, "Deactivate legacy builtin workflows", migration_023_deactivate_legacy_workflows),
    (24, "Remove agent system tables", migration_024_remove_agent_tables),
    (25, "Add standalone presets", migration_025_add_standalone_presets),
    (26, "Add embeddings for semantic search", migration_026_add_embeddings),
    (27, "Add synthesizing status to stage runs", migration_027_add_synthesizing_status),
    (28, "Add document stage for cascade", migration_028_add_document_stage),
    (29, "Add document PR URL for cascade", migration_029_add_document_pr_url),
    (30, "Remove unused tables and dead code", migration_030_cleanup_unused_tables),
    (31, "Add cascade runs tracking", migration_031_add_cascade_runs),
    (32, "Extract cascade metadata to dedicated table", migration_032_extract_cascade_metadata),
    (33, "Add mail config and read receipts", migration_033_add_mail_config),
    (34, "Add delegate activity tracking", migration_034_delegate_activity_tracking),
    (35, "Remove workflow system tables", migration_035_remove_workflow_tables),
    (36, "Add execution metrics and task linkage", migration_036_add_execution_metrics),
    (37, "Add ON DELETE CASCADE to foreign keys", migration_037_add_cascade_delete_fks),
    (38, "Add LOWER(title) index for case-insensitive search", migration_038_add_title_lower_index),
    (39, "Add categories and epic fields to tasks", migration_039_add_categories_and_epic_fields),
    (40, "Add chunk embeddings for semantic search", migration_040_add_chunk_embeddings),
    (41, "Add output_text to executions", migration_041_add_execution_output_text),
    (42, "Convert emoji tags to text", migration_042_convert_emoji_tags_to_text),
    (43, "Add document links table", migration_043_add_document_links),
]


def run_migrations(db_path: str | Path | None = None) -> None:
    """Run all pending migrations."""
    if db_path is None:
        db_path = get_db_path()
    # Don't return early - we need to run migrations even for new databases
    # The database file will be created when we connect to it

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        # Enable foreign keys for this connection (migrations use foreign_keys_disabled()
        # context manager when they need to temporarily disable them for table recreation)
        conn.execute("PRAGMA foreign_keys = ON")

        current_version = get_schema_version(conn)

        for version, description, migration_func in MIGRATIONS:
            if version > current_version:
                print(f"Running migration {version}: {description}")
                try:
                    migration_func(conn)
                except Exception as e:
                    # Rollback any uncommitted changes from the failed migration
                    conn.rollback()
                    raise RuntimeError(f"Migration {version} ({description}) failed: {e}") from e
                set_schema_version(conn, version)
                print(f"✅ Migration {version} completed")

    finally:
        if conn is not None:
            conn.close()
