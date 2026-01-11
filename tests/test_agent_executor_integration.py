"""Integration tests for AgentExecutor with real database operations.

These tests verify the full agent execution lifecycle using a real SQLite database
(in-memory for speed), testing database operations, agent registration, and
execution tracking with mocked Claude subprocess calls.
"""

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from emdx.agents.base import Agent, AgentConfig, AgentContext, AgentResult
from emdx.agents.executor import AgentExecutor
from emdx.agents.registry import AgentRegistry
from emdx.agents.generic import GenericAgent


# ============================================================================
# Test Database Fixtures
# ============================================================================


class IntegrationTestDatabase:
    """Database helper for integration tests with full schema."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_full_schema()

    def _create_full_schema(self):
        """Create the complete database schema for testing."""
        cursor = self.conn.cursor()

        # Documents table
        cursor.execute("""
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
                is_deleted BOOLEAN DEFAULT FALSE,
                parent_id INTEGER
            )
        """)

        # Executions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executions (
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
                old_id TEXT,
                FOREIGN KEY (doc_id) REFERENCES documents(id)
            )
        """)

        # Agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('research', 'generation', 'analysis', 'maintenance')),
                system_prompt TEXT NOT NULL,
                user_prompt_template TEXT NOT NULL,
                allowed_tools TEXT NOT NULL,
                tool_restrictions TEXT,
                max_iterations INTEGER DEFAULT 10,
                timeout_seconds INTEGER DEFAULT 3600,
                requires_confirmation BOOLEAN DEFAULT FALSE,
                max_context_docs INTEGER DEFAULT 5,
                context_search_query TEXT,
                include_doc_content BOOLEAN DEFAULT TRUE,
                output_format TEXT DEFAULT 'markdown',
                save_outputs BOOLEAN DEFAULT TRUE,
                output_tags TEXT,
                version INTEGER DEFAULT 1,
                is_active BOOLEAN DEFAULT TRUE,
                is_builtin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0
            )
        """)

        # Agent executions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                execution_id INTEGER NOT NULL,
                input_type TEXT NOT NULL CHECK (input_type IN ('document', 'query', 'pipeline')),
                input_doc_id INTEGER,
                input_query TEXT,
                output_doc_ids TEXT,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                total_tokens_used INTEGER,
                execution_time_ms INTEGER,
                iterations_used INTEGER,
                context_doc_ids TEXT,
                tools_used TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents(id),
                FOREIGN KEY (execution_id) REFERENCES executions(id),
                FOREIGN KEY (input_doc_id) REFERENCES documents(id)
            )
        """)

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                usage_count INTEGER DEFAULT 0
            )
        """)

        # Document tags junction table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_tags (
                document_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, tag_id),
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        """)

        self.conn.commit()

    def get_connection(self):
        return self.conn

    def insert_document(self, title: str, content: str, project: str = None) -> int:
        """Insert a test document and return its ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO documents (title, content, project) VALUES (?, ?, ?)",
            (title, content, project)
        )
        self.conn.commit()
        return cursor.lastrowid

    def insert_agent(
        self,
        name: str,
        display_name: str,
        description: str = "Test agent",
        category: str = "analysis",
        system_prompt: str = "You are a test assistant.",
        user_prompt_template: str = "Process: {{content}}",
        allowed_tools: list = None,
        **kwargs
    ) -> int:
        """Insert a test agent and return its ID."""
        if allowed_tools is None:
            allowed_tools = ["Read", "Write"]

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO agents (
                name, display_name, description, category,
                system_prompt, user_prompt_template, allowed_tools,
                is_active, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, 'test')
        """, (
            name, display_name, description, category,
            system_prompt, user_prompt_template, json.dumps(allowed_tools)
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_agent(self, agent_id: int) -> dict:
        """Get an agent by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_agent_execution(self, exec_id: int) -> dict:
        """Get an agent execution by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agent_executions WHERE id = ?", (exec_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_execution(self, exec_id: int) -> dict:
        """Get an execution by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM executions WHERE id = ?", (exec_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self):
        self.conn.close()


@pytest.fixture
def integration_db():
    """Create an integration test database with full schema."""
    db = IntegrationTestDatabase()
    yield db
    db.close()


@pytest.fixture
def mock_db_connection(integration_db):
    """Mock the database connection to use our test database."""
    mock_db = MagicMock()
    mock_db.get_connection.return_value.__enter__ = MagicMock(
        return_value=integration_db.get_connection()
    )
    mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)
    return mock_db


# ============================================================================
# Integration Tests for Agent Executor
# ============================================================================


class TestAgentExecutorDatabaseIntegration:
    """Tests for AgentExecutor with real database operations."""

    def test_create_agent_execution_record(self, integration_db, mock_db_connection):
        """Test that agent execution records are created in the database."""
        # Insert a test agent
        agent_id = integration_db.insert_agent(
            name="test-executor-agent",
            display_name="Test Executor Agent"
        )

        # Insert a mock execution record first (simulating what execute_agent does)
        cursor = integration_db.conn.cursor()
        cursor.execute("""
            INSERT INTO executions (doc_id, doc_title, status, started_at, log_file, working_dir)
            VALUES (0, 'Test Execution', 'running', CURRENT_TIMESTAMP, '/tmp/test.log', '/tmp')
        """)
        integration_db.conn.commit()
        execution_id = cursor.lastrowid

        # Create executor and test _create_agent_execution
        with patch('emdx.agents.executor.db_connection', mock_db_connection):
            executor = AgentExecutor()
            agent_exec_id = executor._create_agent_execution(
                agent_id=agent_id,
                execution_id=execution_id,
                input_type='query',
                input_doc_id=None,
                input_query='test query'
            )

        # Verify the record was created
        agent_exec = integration_db.get_agent_execution(agent_exec_id)
        assert agent_exec is not None
        assert agent_exec['agent_id'] == agent_id
        assert agent_exec['execution_id'] == execution_id
        assert agent_exec['input_type'] == 'query'
        assert agent_exec['input_query'] == 'test query'
        assert agent_exec['status'] == 'pending'

    def test_update_agent_execution_record(self, integration_db, mock_db_connection):
        """Test updating agent execution records."""
        # Create necessary records
        agent_id = integration_db.insert_agent(
            name="test-update-agent",
            display_name="Test Update Agent"
        )

        cursor = integration_db.conn.cursor()
        cursor.execute("""
            INSERT INTO executions (doc_id, doc_title, status, started_at, log_file)
            VALUES (0, 'Test', 'running', CURRENT_TIMESTAMP, '/tmp/test.log')
        """)
        execution_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO agent_executions (agent_id, execution_id, input_type, status)
            VALUES (?, ?, 'query', 'pending')
        """, (agent_id, execution_id))
        agent_exec_id = cursor.lastrowid
        integration_db.conn.commit()

        # Update the execution
        with patch('emdx.agents.executor.db_connection', mock_db_connection):
            executor = AgentExecutor()
            executor._update_agent_execution(agent_exec_id, {
                'status': 'completed',
                'execution_time_ms': 1500,
                'total_tokens_used': 500
            })

        # Verify update
        agent_exec = integration_db.get_agent_execution(agent_exec_id)
        assert agent_exec['status'] == 'completed'
        assert agent_exec['execution_time_ms'] == 1500
        assert agent_exec['total_tokens_used'] == 500

    def test_update_agent_stats_on_success(self, integration_db, mock_db_connection):
        """Test that agent usage stats are updated on successful execution."""
        agent_id = integration_db.insert_agent(
            name="test-stats-agent",
            display_name="Test Stats Agent"
        )

        # Get initial stats
        agent_before = integration_db.get_agent(agent_id)
        assert agent_before['usage_count'] == 0
        assert agent_before['success_count'] == 0

        with patch('emdx.agents.executor.db_connection', mock_db_connection):
            executor = AgentExecutor()
            executor._update_agent_stats(agent_id, success=True)

        # Verify stats updated
        agent_after = integration_db.get_agent(agent_id)
        assert agent_after['usage_count'] == 1
        assert agent_after['success_count'] == 1
        assert agent_after['failure_count'] == 0
        assert agent_after['last_used_at'] is not None

    def test_update_agent_stats_on_failure(self, integration_db, mock_db_connection):
        """Test that agent usage stats are updated on failed execution."""
        agent_id = integration_db.insert_agent(
            name="test-failure-stats-agent",
            display_name="Test Failure Stats Agent"
        )

        with patch('emdx.agents.executor.db_connection', mock_db_connection):
            executor = AgentExecutor()
            executor._update_agent_stats(agent_id, success=False)

        agent_after = integration_db.get_agent(agent_id)
        assert agent_after['usage_count'] == 1
        assert agent_after['success_count'] == 0
        assert agent_after['failure_count'] == 1


class TestAgentRegistryDatabaseIntegration:
    """Integration tests for AgentRegistry with real database."""

    def test_get_agent_from_database(self, integration_db, mock_db_connection):
        """Test loading an agent from the database."""
        agent_id = integration_db.insert_agent(
            name="db-loaded-agent",
            display_name="DB Loaded Agent",
            description="Agent loaded from database",
            system_prompt="You are a test agent.",
            user_prompt_template="Process: {{input}}"
        )

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            agent = registry.get_agent(agent_id)

        assert agent is not None
        assert agent.config.id == agent_id
        assert agent.config.name == "db-loaded-agent"
        assert agent.config.display_name == "DB Loaded Agent"
        assert isinstance(agent, GenericAgent)

    def test_get_agent_by_name_from_database(self, integration_db, mock_db_connection):
        """Test loading an agent by name from the database."""
        integration_db.insert_agent(
            name="named-agent",
            display_name="Named Agent",
            description="Agent found by name"
        )

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            agent = registry.get_agent_by_name("named-agent")

        assert agent is not None
        assert agent.config.name == "named-agent"

    def test_get_nonexistent_agent(self, integration_db, mock_db_connection):
        """Test that getting a nonexistent agent returns None."""
        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            agent = registry.get_agent(99999)

        assert agent is None

    def test_list_agents_from_database(self, integration_db, mock_db_connection):
        """Test listing all agents from the database."""
        integration_db.insert_agent(name="agent-1", display_name="Agent 1", category="analysis")
        integration_db.insert_agent(name="agent-2", display_name="Agent 2", category="generation")
        integration_db.insert_agent(name="agent-3", display_name="Agent 3", category="analysis")

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            agents = registry.list_agents()

        assert len(agents) == 3
        names = [a['name'] for a in agents]
        assert "agent-1" in names
        assert "agent-2" in names
        assert "agent-3" in names

    def test_list_agents_by_category(self, integration_db, mock_db_connection):
        """Test listing agents filtered by category."""
        integration_db.insert_agent(name="analysis-1", display_name="Analysis 1", category="analysis")
        integration_db.insert_agent(name="analysis-2", display_name="Analysis 2", category="analysis")
        integration_db.insert_agent(name="generation-1", display_name="Generation 1", category="generation")

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            analysis_agents = registry.list_agents(category="analysis")

        assert len(analysis_agents) == 2
        for agent in analysis_agents:
            assert agent['category'] == "analysis"

    def test_create_agent_in_database(self, integration_db, mock_db_connection):
        """Test creating a new agent in the database."""
        config = {
            'name': 'new-test-agent',
            'display_name': 'New Test Agent',
            'description': 'A newly created test agent',
            'category': 'maintenance',
            'system_prompt': 'You are a new agent.',
            'user_prompt_template': 'Do: {{task}}',
            'allowed_tools': ['Read', 'Write', 'Bash'],
            'output_tags': ['test', 'new'],
            'created_by': 'test-user'
        }

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            agent_id = registry.create_agent(config)

        assert agent_id is not None
        created_agent = integration_db.get_agent(agent_id)
        assert created_agent['name'] == 'new-test-agent'
        assert created_agent['display_name'] == 'New Test Agent'
        assert json.loads(created_agent['allowed_tools']) == ['Read', 'Write', 'Bash']

    def test_update_agent_in_database(self, integration_db, mock_db_connection):
        """Test updating an agent in the database."""
        agent_id = integration_db.insert_agent(
            name="update-test-agent",
            display_name="Original Name"
        )

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            result = registry.update_agent(agent_id, {
                'display_name': 'Updated Name',
                'description': 'Updated description'
            })

        assert result is True
        updated_agent = integration_db.get_agent(agent_id)
        assert updated_agent['display_name'] == 'Updated Name'
        assert updated_agent['description'] == 'Updated description'

    def test_soft_delete_agent(self, integration_db, mock_db_connection):
        """Test soft deleting an agent."""
        agent_id = integration_db.insert_agent(
            name="delete-test-agent",
            display_name="Delete Test"
        )

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            result = registry.delete_agent(agent_id)

        assert result is True
        deleted_agent = integration_db.get_agent(agent_id)
        assert deleted_agent['is_active'] == 0  # Soft deleted

    def test_hard_delete_agent(self, integration_db, mock_db_connection):
        """Test hard deleting an agent."""
        agent_id = integration_db.insert_agent(
            name="hard-delete-agent",
            display_name="Hard Delete Test"
        )

        with patch('emdx.agents.registry.db_connection', mock_db_connection):
            registry = AgentRegistry()
            result = registry.delete_agent(agent_id, hard_delete=True)

        assert result is True
        deleted_agent = integration_db.get_agent(agent_id)
        assert deleted_agent is None  # Actually deleted


class TestAgentExecutorFullFlow:
    """Integration tests for the full agent execution flow."""

    @pytest.mark.asyncio
    async def test_execute_agent_input_validation(self, integration_db, mock_db_connection):
        """Test that input validation works correctly in execute_agent."""
        agent_id = integration_db.insert_agent(
            name="validation-agent",
            display_name="Validation Test Agent"
        )

        with patch('emdx.agents.executor.agent_registry') as mock_registry:
            mock_agent = MagicMock()
            mock_agent.config = AgentConfig(
                id=agent_id,
                name="validation-agent",
                display_name="Validation Test Agent",
                description="Test",
                category="analysis",
                system_prompt="Test",
                user_prompt_template="{{content}}",
                allowed_tools=["Read"],
                max_context_docs=0
            )
            mock_registry.get_agent.return_value = mock_agent

            executor = AgentExecutor()

            # Test document input without doc_id
            with pytest.raises(ValueError, match="Document ID required"):
                await executor.execute_agent(
                    agent_id=agent_id,
                    input_type='document'
                )

            # Test query input without query string
            with pytest.raises(ValueError, match="Query required"):
                await executor.execute_agent(
                    agent_id=agent_id,
                    input_type='query'
                )

            # Test invalid input type
            with pytest.raises(ValueError, match="Invalid input type"):
                await executor.execute_agent(
                    agent_id=agent_id,
                    input_type='invalid_type',
                    input_query='test'
                )

    def test_build_agent_prompt_with_document_content(self, integration_db, mock_db_connection):
        """Test building prompts with actual document content."""
        doc_id = integration_db.insert_document(
            title="Test Document",
            content="This is the document content for testing."
        )

        config = AgentConfig(
            id=1,
            name="doc-prompt-agent",
            display_name="Doc Prompt Agent",
            description="Test",
            category="analysis",
            system_prompt="Analyze documents.",
            user_prompt_template="Analyze this content: {{content}}",
            allowed_tools=["Read"]
        )
        agent = GenericAgent(config)

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="document",
            input_doc_id=doc_id
        )

        # Mock get_document to return our test document
        class MockDoc:
            content = "This is the document content for testing."

        with patch('emdx.models.documents.get_document', return_value=MockDoc()):
            executor = AgentExecutor()
            prompt = executor._build_agent_prompt(agent, context)

        assert "This is the document content for testing." in prompt

    def test_build_agent_prompt_with_query(self):
        """Test building prompts with query input."""
        config = AgentConfig(
            id=1,
            name="query-prompt-agent",
            display_name="Query Prompt Agent",
            description="Test",
            category="analysis",
            system_prompt="Answer questions.",
            user_prompt_template="Answer this question: {{query}}",
            allowed_tools=["Read"]
        )
        agent = GenericAgent(config)

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="What is the meaning of life?"
        )

        executor = AgentExecutor()
        prompt = executor._build_agent_prompt(agent, context)

        assert "What is the meaning of life?" in prompt

    def test_build_agent_prompt_with_variables(self):
        """Test building prompts with custom variables."""
        config = AgentConfig(
            id=1,
            name="var-prompt-agent",
            display_name="Variable Prompt Agent",
            description="Test",
            category="analysis",
            system_prompt="Process data.",
            user_prompt_template="Process {{data}} in {{mode}} mode with {{level}} detail",
            allowed_tools=["Read"]
        )
        agent = GenericAgent(config)

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test",
            variables={'data': 'input_data', 'mode': 'fast', 'level': 'high'}
        )

        executor = AgentExecutor()
        prompt = executor._build_agent_prompt(agent, context)

        assert "input_data" in prompt
        assert "fast" in prompt
        assert "high" in prompt


class TestGenericAgentIntegration:
    """Integration tests for GenericAgent execution."""

    def test_build_full_prompt_structure(self):
        """Test that GenericAgent builds properly structured prompts."""
        config = AgentConfig(
            id=1,
            name="full-prompt-agent",
            display_name="Full Prompt Agent",
            description="Agent for testing full prompt structure",
            category="analysis",
            system_prompt="You are an expert analyst.",
            user_prompt_template="Analyze: {{content}}",
            allowed_tools=["Read", "Write", "Bash"],
            output_format="markdown"
        )
        agent = GenericAgent(config)

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp/test",
            input_type="query",
            input_query="test content"
        )

        prompt = agent._build_full_prompt(context)

        # Verify prompt sections
        assert "# System Instructions" in prompt
        assert "You are an expert analyst." in prompt
        assert "# Allowed Tools" in prompt
        assert "Read, Write, Bash" in prompt
        assert "# Output Format" in prompt
        assert "markdown" in prompt

    def test_extract_tools_used_from_output(self):
        """Test extracting used tools from execution output."""
        config = AgentConfig(
            id=1,
            name="tool-extract-agent",
            display_name="Tool Extract Agent",
            description="Test",
            category="analysis",
            system_prompt="Test",
            user_prompt_template="{{content}}",
            allowed_tools=["Read", "Write", "Grep"]
        )
        agent = GenericAgent(config)

        output = """
        Using tool: Read
        File contents here...
        Using tool: Grep
        Search results...
        Tool: Write
        Writing output...
        Using tool: Read
        More content...
        """

        tools = agent._extract_tools_used(output)

        assert 'Read' in tools
        assert 'Grep' in tools
        assert 'Write' in tools
        # Should deduplicate
        assert len([t for t in tools if t == 'Read']) == 1

    @pytest.mark.asyncio
    async def test_generic_agent_execute_with_mocked_subprocess(self):
        """Test GenericAgent.execute with mocked Claude subprocess."""
        config = AgentConfig(
            id=1,
            name="subprocess-test-agent",
            display_name="Subprocess Test Agent",
            description="Test agent for subprocess execution",
            category="analysis",
            system_prompt="You are a test agent.",
            user_prompt_template="Process: {{content}}",
            allowed_tools=["Read"],
            save_outputs=False  # Don't try to save output
        )
        agent = GenericAgent(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            context = AgentContext(
                execution_id=1,
                working_dir=tmpdir,
                input_type="query",
                input_query="test input",
                log_file=str(Path(tmpdir) / "test.log")
            )

            # Mock subprocess
            mock_process = MagicMock()
            mock_process.returncode = 0

            def readline_gen():
                yield '{"type": "text", "text": "Processing complete"}\n'
                yield ''

            gen = readline_gen()
            mock_process.stdout.readline.side_effect = lambda: next(gen, '')
            mock_process.poll.side_effect = [None, 0]

            import emdx.agents.generic as generic_module
            original_subprocess = generic_module.subprocess

            try:
                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.return_value = mock_process

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess

        assert result.status == 'completed'
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_generic_agent_handles_subprocess_failure(self):
        """Test GenericAgent handles subprocess failures gracefully."""
        config = AgentConfig(
            id=1,
            name="failure-test-agent",
            display_name="Failure Test Agent",
            description="Test",
            category="analysis",
            system_prompt="Test",
            user_prompt_template="{{content}}",
            allowed_tools=["Read"],
            save_outputs=False
        )
        agent = GenericAgent(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            context = AgentContext(
                execution_id=1,
                working_dir=tmpdir,
                input_type="query",
                input_query="test",
                log_file=str(Path(tmpdir) / "test.log")
            )

            import emdx.agents.generic as generic_module
            original_subprocess = generic_module.subprocess

            try:
                mock_process = MagicMock()
                mock_process.returncode = 1

                def readline_gen():
                    yield 'Error: Command failed\n'
                    yield ''

                gen = readline_gen()
                mock_process.stdout.readline.side_effect = lambda: next(gen, '')
                mock_process.poll.side_effect = [None, 1]

                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.return_value = mock_process

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess

        assert result.status == 'failed'
        assert result.metadata.get('exit_code') == 1


class TestAgentConfigIntegration:
    """Integration tests for AgentConfig parsing and serialization."""

    def test_agent_config_from_db_row_full(self, integration_db):
        """Test creating AgentConfig from a complete database row."""
        cursor = integration_db.conn.cursor()
        cursor.execute("""
            INSERT INTO agents (
                name, display_name, description, category,
                system_prompt, user_prompt_template, allowed_tools,
                tool_restrictions, max_iterations, timeout_seconds,
                requires_confirmation, max_context_docs, context_search_query,
                include_doc_content, output_format, save_outputs, output_tags,
                version, is_active, is_builtin, created_by,
                usage_count, success_count, failure_count
            ) VALUES (
                'full-config-agent', 'Full Config Agent', 'Complete agent configuration',
                'analysis', 'System prompt here', 'User prompt: {{input}}',
                '["Read", "Write", "Bash"]', '{"Bash": {"timeout": 60}}',
                15, 1800, TRUE, 10, 'related to {{query}}',
                FALSE, 'json', TRUE, '["analysis", "test"]',
                2, TRUE, FALSE, 'test-user',
                100, 95, 5
            )
        """)
        integration_db.conn.commit()

        cursor.execute("SELECT * FROM agents WHERE name = 'full-config-agent'")
        row = cursor.fetchone()
        row_dict = dict(row)

        config = AgentConfig.from_db_row(row_dict)

        assert config.name == 'full-config-agent'
        assert config.display_name == 'Full Config Agent'
        assert config.allowed_tools == ['Read', 'Write', 'Bash']
        assert config.tool_restrictions == {'Bash': {'timeout': 60}}
        assert config.max_iterations == 15
        assert config.timeout_seconds == 1800
        assert config.requires_confirmation is True
        assert config.max_context_docs == 10
        assert config.include_doc_content is False
        assert config.output_format == 'json'
        assert config.output_tags == ['analysis', 'test']
        assert config.usage_count == 100
        assert config.success_count == 95
        assert config.failure_count == 5

    def test_agent_config_handles_null_json_fields(self, integration_db):
        """Test that AgentConfig handles null optional JSON fields gracefully."""
        cursor = integration_db.conn.cursor()
        # allowed_tools is NOT NULL in schema, but tool_restrictions and output_tags can be NULL
        cursor.execute("""
            INSERT INTO agents (
                name, display_name, description, category,
                system_prompt, user_prompt_template, allowed_tools,
                tool_restrictions, output_tags
            ) VALUES (
                'null-json-agent', 'Null JSON Agent', 'Agent with null optional JSON fields',
                'analysis', 'System', 'User: {{input}}',
                '[]', NULL, NULL
            )
        """)
        integration_db.conn.commit()

        cursor.execute("SELECT * FROM agents WHERE name = 'null-json-agent'")
        row = cursor.fetchone()
        row_dict = dict(row)

        config = AgentConfig.from_db_row(row_dict)

        assert config.allowed_tools == []
        assert config.tool_restrictions is None
        assert config.output_tags is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
