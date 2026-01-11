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


def migration_008_add_workflow_tables(conn: sqlite3.Connection):
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_id ON workflow_runs(workflow_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_individual_runs_stage_run_id ON workflow_individual_runs(stage_run_id)")

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


def migration_011_add_dynamic_workflow_mode(conn: sqlite3.Connection):
    """Add 'dynamic' to workflow stage mode CHECK constraint.

    Dynamic mode allows stages to discover items at runtime and process
    them in parallel with isolated worktrees.
    """
    cursor = conn.cursor()

    # Temporarily disable foreign key checks for the table recreation
    cursor.execute("PRAGMA foreign_keys = OFF")

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

    # Re-enable foreign key checks
    cursor.execute("PRAGMA foreign_keys = ON")

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

    # Temporarily disable foreign key checks for the table recreation
    cursor.execute("PRAGMA foreign_keys = OFF")

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

    # Re-enable foreign key checks
    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()


def migration_014_fix_individual_runs_fk(conn: sqlite3.Connection):
    """Fix workflow_individual_runs FK to reference executions instead of agent_executions.

    The workflow executor uses the executions table directly for tracking,
    not agent_executions. This migration fixes the foreign key constraint.
    """
    cursor = conn.cursor()

    # Temporarily disable foreign key checks for the table recreation
    cursor.execute("PRAGMA foreign_keys = OFF")

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

    # Re-enable foreign key checks
    cursor.execute("PRAGMA foreign_keys = ON")

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
]


def run_migrations(db_path=None):
    """Run all pending migrations."""
    if db_path is None:
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
