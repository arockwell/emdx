"""Workflow system migrations.

These migrations establish and evolve the workflow orchestration system:
- Agent system (later removed)
- Workflows, stages, individual runs
- Iteration strategies
- Dynamic workflow mode
- Presets and improvements
"""

import sqlite3

from .runner import foreign_keys_disabled


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


def migration_021_add_workflow_presets(conn: sqlite3.Connection):
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


def migration_023_deactivate_legacy_workflows(conn: sqlite3.Connection):
    """Deactivate legacy builtin workflows that are superseded by dynamic task-driven workflows.

    These workflows were created before the dynamic workflow system (task_parallel, parallel_fix,
    parallel_analysis, dynamic_items) which use --task flags for flexible execution. The legacy
    workflows had hardcoded prompts and are no longer needed for new work.

    Workflows are soft-deleted (is_active=FALSE) rather than hard-deleted to preserve
    historical workflow_runs that reference them.
    """
    cursor = conn.cursor()

    # Legacy workflow names to deactivate
    legacy_workflows = [
        'deep_analysis',
        'robust_planning',
        'quick_analysis',
        'tech_debt_analysis',
        'code_fix',
        'tech_debt_discovery',
        'architecture_review',
        'fix_and_pr',
        'comprehensive_tech_debt',
        'parallel_task_fix',
        'feature_exploration',
        'feature_exploration_v2',
        'feature_exploration_dynamic',
        'feature_development',
        'feature_development_v2',
        'full_feature_development',
        'implement_tracks_c_d',
        'weird_feature_exploration',
        'tech_debt_parallel_fix',
        'merge_main_all_branches',
        'ux_views_analysis',
    ]

    # Soft-delete by setting is_active = FALSE
    placeholders = ','.join('?' * len(legacy_workflows))
    cursor.execute(
        f"""
        UPDATE workflows
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE name IN ({placeholders})
        """,
        legacy_workflows,
    )

    conn.commit()


def migration_027_add_synthesizing_status(conn: sqlite3.Connection):
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_workflow_run_id ON workflow_stage_runs(workflow_run_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_stage_runs_status ON workflow_stage_runs(status)")

    conn.commit()
