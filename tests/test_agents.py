"""Comprehensive tests for the EMDX agent system (emdx/agents/*.py).

Tests cover:
- AgentConfig, AgentContext, AgentResult dataclasses
- Agent base class methods
- AgentRegistry CRUD operations
- AgentExecutor with mocked Claude API
- GenericAgent with mocked subprocess
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from emdx.agents.base import Agent, AgentConfig, AgentContext, AgentResult
from emdx.agents.registry import AgentRegistry
from emdx.agents.executor import AgentExecutor
from emdx.agents.generic import GenericAgent


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_agent_config():
    """Create a sample AgentConfig for testing.

    NOTE: save_outputs is False by default to prevent tests from writing
    to the real database. Tests that need to test save behavior should
    explicitly set save_outputs=True and mock save_document.
    """
    return AgentConfig(
        id=1,
        name="test-agent",
        display_name="Test Agent",
        description="A test agent for unit testing",
        category="testing",
        system_prompt="You are a helpful test assistant.",
        user_prompt_template="Process this: {{content}}",
        allowed_tools=["Read", "Write", "Bash"],
        tool_restrictions={"Bash": {"timeout": 60}},
        max_iterations=5,
        timeout_seconds=300,
        requires_confirmation=False,
        max_context_docs=3,
        context_search_query="{{title}}",
        include_doc_content=True,
        output_format="markdown",
        save_outputs=False,  # Disabled to prevent writing to real database in tests
        output_tags=["test", "output"],
        version=1,
        is_active=True,
        is_builtin=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by="test",
        usage_count=10,
        last_used_at=datetime.now(),
        success_count=8,
        failure_count=2
    )


@pytest.fixture
def sample_db_row():
    """Create a sample database row for AgentConfig.from_db_row testing."""
    return {
        'id': 2,
        'name': 'db-agent',
        'display_name': 'DB Agent',
        'description': 'Agent from database',
        'category': 'analysis',
        'system_prompt': 'Analyze the input.',
        'user_prompt_template': 'Analyze: {{query}}',
        'allowed_tools': '["Read", "Grep"]',
        'tool_restrictions': '{"Read": {"max_lines": 1000}}',
        'max_iterations': 15,
        'timeout_seconds': 600,
        'requires_confirmation': 1,
        'max_context_docs': 10,
        'context_search_query': 'related to {{query}}',
        'include_doc_content': 0,
        'output_format': 'json',
        'save_outputs': 1,
        'output_tags': '["analysis", "report"]',
        'version': 2,
        'is_active': 1,
        'is_builtin': 1,
        'created_at': '2024-01-01 10:00:00',
        'updated_at': '2024-01-15 14:30:00',
        'created_by': 'system',
        'usage_count': 50,
        'last_used_at': '2024-01-20 09:00:00',
        'success_count': 45,
        'failure_count': 5
    }


@pytest.fixture
def sample_agent_context():
    """Create a sample AgentContext for testing."""
    return AgentContext(
        execution_id=100,
        working_dir="/tmp/test-agent",
        input_type="document",
        input_doc_id=42,
        input_query=None,
        context_docs=[1, 2, 3],
        parent_execution_id=None,
        variables={"custom_var": "value"},
        log_file="/tmp/test-agent/agent.log"
    )


@pytest.fixture
def mock_db_connection():
    """Create a mock database connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.execute.return_value = mock_cursor
    return mock_conn, mock_cursor


# ============================================================================
# Tests for AgentConfig
# ============================================================================

class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_agent_config_creation(self, sample_agent_config):
        """Test creating an AgentConfig with all fields."""
        config = sample_agent_config

        assert config.id == 1
        assert config.name == "test-agent"
        assert config.display_name == "Test Agent"
        assert config.category == "testing"
        assert config.allowed_tools == ["Read", "Write", "Bash"]
        assert config.max_iterations == 5
        assert config.is_active is True
        assert config.is_builtin is False

    def test_agent_config_defaults(self):
        """Test AgentConfig default values."""
        config = AgentConfig(
            id=1,
            name="minimal",
            display_name="Minimal Agent",
            description="Minimal",
            category="test",
            system_prompt="Test",
            user_prompt_template="{{content}}",
            allowed_tools=[]
        )

        assert config.tool_restrictions is None
        assert config.max_iterations == 10
        assert config.timeout_seconds == 3600
        assert config.requires_confirmation is False
        assert config.max_context_docs == 5
        assert config.output_format == 'markdown'
        assert config.save_outputs is True
        assert config.version == 1
        assert config.is_active is True
        assert config.is_builtin is False
        assert config.usage_count == 0
        assert config.success_count == 0
        assert config.failure_count == 0

    def test_agent_config_from_db_row(self, sample_db_row):
        """Test creating AgentConfig from database row."""
        config = AgentConfig.from_db_row(sample_db_row)

        assert config.id == 2
        assert config.name == 'db-agent'
        assert config.display_name == 'DB Agent'
        assert config.category == 'analysis'
        assert config.allowed_tools == ['Read', 'Grep']
        assert config.tool_restrictions == {'Read': {'max_lines': 1000}}
        assert config.max_iterations == 15
        assert config.requires_confirmation is True
        assert config.include_doc_content is False
        assert config.output_tags == ['analysis', 'report']
        assert config.is_builtin is True
        assert config.usage_count == 50
        assert config.success_count == 45
        assert config.failure_count == 5

    def test_agent_config_from_db_row_with_nulls(self):
        """Test from_db_row handles null JSON fields."""
        row = {
            'id': 3,
            'name': 'null-agent',
            'display_name': 'Null Agent',
            'description': 'Agent with nulls',
            'category': 'test',
            'system_prompt': 'Test',
            'user_prompt_template': '{{input}}',
            'allowed_tools': None,  # Null
            'tool_restrictions': None,
            'output_tags': None
        }

        config = AgentConfig.from_db_row(row)

        assert config.allowed_tools == []
        assert config.tool_restrictions is None
        assert config.output_tags is None


# ============================================================================
# Tests for AgentContext
# ============================================================================

class TestAgentContext:
    """Tests for AgentContext dataclass."""

    def test_agent_context_creation(self, sample_agent_context):
        """Test creating an AgentContext with all fields."""
        context = sample_agent_context

        assert context.execution_id == 100
        assert context.working_dir == "/tmp/test-agent"
        assert context.input_type == "document"
        assert context.input_doc_id == 42
        assert context.input_query is None
        assert context.context_docs == [1, 2, 3]
        assert context.variables == {"custom_var": "value"}

    def test_agent_context_defaults(self):
        """Test AgentContext default values."""
        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query"
        )

        assert context.input_doc_id is None
        assert context.input_query is None
        assert context.context_docs == []
        assert context.parent_execution_id is None
        assert context.variables == {}
        assert context.log_file is None

    def test_agent_context_query_type(self):
        """Test AgentContext with query input type."""
        context = AgentContext(
            execution_id=2,
            working_dir="/tmp/query",
            input_type="query",
            input_query="What is the meaning of life?"
        )

        assert context.input_type == "query"
        assert context.input_query == "What is the meaning of life?"
        assert context.input_doc_id is None


# ============================================================================
# Tests for AgentResult
# ============================================================================

class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_agent_result_completed(self):
        """Test creating a completed AgentResult."""
        result = AgentResult(
            status='completed',
            output_doc_ids=[10, 11],
            execution_time_ms=1500,
            total_tokens_used=500,
            iterations_used=3,
            tools_used=['Read', 'Write'],
            metadata={'key': 'value'}
        )

        assert result.status == 'completed'
        assert result.output_doc_ids == [10, 11]
        assert result.error_message is None
        assert result.execution_time_ms == 1500
        assert result.total_tokens_used == 500
        assert result.iterations_used == 3
        assert result.tools_used == ['Read', 'Write']

    def test_agent_result_failed(self):
        """Test creating a failed AgentResult."""
        result = AgentResult(
            status='failed',
            error_message='Connection timeout',
            execution_time_ms=30000
        )

        assert result.status == 'failed'
        assert result.error_message == 'Connection timeout'
        assert result.output_doc_ids == []
        assert result.tools_used == []

    def test_agent_result_defaults(self):
        """Test AgentResult default values."""
        result = AgentResult(status='completed')

        assert result.output_doc_ids == []
        assert result.error_message is None
        assert result.execution_time_ms == 0
        assert result.total_tokens_used == 0
        assert result.iterations_used == 0
        assert result.tools_used == []
        assert result.metadata == {}


# ============================================================================
# Tests for Agent Base Class
# ============================================================================

class ConcreteAgent(Agent):
    """Concrete implementation of Agent for testing."""

    async def execute(self, context: AgentContext) -> AgentResult:
        return AgentResult(status='completed')


class TestAgentBaseClass:
    """Tests for Agent base class methods."""

    def test_validate_tools_all_allowed(self, sample_agent_config):
        """Test validate_tools when all requested tools are allowed."""
        agent = ConcreteAgent(sample_agent_config)

        requested = ['Read', 'Write']
        validated = agent.validate_tools(requested)

        assert validated == ['Read', 'Write']

    def test_validate_tools_partial_allowed(self, sample_agent_config):
        """Test validate_tools filters out disallowed tools."""
        agent = ConcreteAgent(sample_agent_config)

        requested = ['Read', 'Dangerous', 'Write', 'Unknown']
        validated = agent.validate_tools(requested)

        assert validated == ['Read', 'Write']

    def test_validate_tools_none_allowed(self, sample_agent_config):
        """Test validate_tools when no requested tools are allowed."""
        agent = ConcreteAgent(sample_agent_config)

        requested = ['Dangerous', 'Unknown', 'NotAllowed']
        validated = agent.validate_tools(requested)

        assert validated == []

    def test_format_prompt_simple(self, sample_agent_config):
        """Test format_prompt with simple substitution."""
        agent = ConcreteAgent(sample_agent_config)

        result = agent.format_prompt(content="Hello World")

        assert result == "Process this: Hello World"

    def test_format_prompt_multiple_variables(self):
        """Test format_prompt with multiple variables."""
        config = AgentConfig(
            id=1,
            name="test",
            display_name="Test",
            description="Test",
            category="test",
            system_prompt="Test",
            user_prompt_template="Title: {{title}}, Author: {{author}}, Date: {{date}}",
            allowed_tools=[]
        )
        agent = ConcreteAgent(config)

        result = agent.format_prompt(title="My Doc", author="John", date="2024-01-01")

        assert result == "Title: My Doc, Author: John, Date: 2024-01-01"

    def test_format_prompt_missing_variable(self, sample_agent_config):
        """Test format_prompt leaves unreplaced variables as-is."""
        agent = ConcreteAgent(sample_agent_config)

        result = agent.format_prompt()  # No content provided

        assert "{{content}}" in result

    def test_apply_tool_restrictions_with_restrictions(self, sample_agent_config):
        """Test apply_tool_restrictions returns matching restrictions."""
        agent = ConcreteAgent(sample_agent_config)

        restrictions = agent.apply_tool_restrictions(['Bash', 'Read'])

        assert restrictions == {'Bash': {'timeout': 60}}

    def test_apply_tool_restrictions_no_match(self, sample_agent_config):
        """Test apply_tool_restrictions when no tools match."""
        agent = ConcreteAgent(sample_agent_config)

        restrictions = agent.apply_tool_restrictions(['Read', 'Write'])

        assert restrictions == {}

    def test_apply_tool_restrictions_none(self):
        """Test apply_tool_restrictions when no restrictions configured."""
        config = AgentConfig(
            id=1,
            name="test",
            display_name="Test",
            description="Test",
            category="test",
            system_prompt="Test",
            user_prompt_template="{{input}}",
            allowed_tools=['Bash'],
            tool_restrictions=None
        )
        agent = ConcreteAgent(config)

        restrictions = agent.apply_tool_restrictions(['Bash'])

        assert restrictions == {}


# ============================================================================
# Tests for AgentRegistry
# ============================================================================

class TestAgentRegistry:
    """Tests for AgentRegistry."""

    def test_registry_singleton(self):
        """Test that AgentRegistry is a singleton."""
        registry1 = AgentRegistry()
        registry2 = AgentRegistry()

        assert registry1 is registry2

    def test_register_valid_agent(self):
        """Test registering a valid agent class."""
        registry = AgentRegistry()

        class CustomAgent(Agent):
            async def execute(self, context):
                return AgentResult(status='completed')

        registry.register('custom', CustomAgent)

        assert 'custom' in registry._agents
        assert registry._agents['custom'] is CustomAgent

    def test_register_invalid_agent(self):
        """Test registering a non-Agent class raises error."""
        registry = AgentRegistry()

        class NotAnAgent:
            pass

        with pytest.raises(ValueError, match="must be a subclass of Agent"):
            registry.register('invalid', NotAnAgent)

    @patch('emdx.agents.registry.db_connection')
    def test_get_agent_found(self, mock_db, sample_db_row):
        """Test getting an agent by ID when it exists."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = sample_db_row
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        agent = registry.get_agent(2)

        assert agent is not None
        assert agent.config.id == 2
        assert agent.config.name == 'db-agent'

    @patch('emdx.agents.registry.db_connection')
    def test_get_agent_not_found(self, mock_db):
        """Test getting an agent that doesn't exist."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        agent = registry.get_agent(999)

        assert agent is None

    @patch('emdx.agents.registry.db_connection')
    def test_get_agent_by_name(self, mock_db, sample_db_row):
        """Test getting an agent by name."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = sample_db_row
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        agent = registry.get_agent_by_name('db-agent')

        assert agent is not None
        assert agent.config.name == 'db-agent'

    @patch('emdx.agents.registry.db_connection')
    def test_list_agents(self, mock_db, sample_db_row):
        """Test listing all agents."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [sample_db_row]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        agents = registry.list_agents()

        assert len(agents) == 1
        assert agents[0]['name'] == 'db-agent'
        assert agents[0]['allowed_tools'] == ['Read', 'Grep']

    @patch('emdx.agents.registry.db_connection')
    def test_list_agents_by_category(self, mock_db, sample_db_row):
        """Test listing agents filtered by category."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [sample_db_row]
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        agents = registry.list_agents(category='analysis')

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert 'category = ?' in call_args[0][0]
        assert 'analysis' in call_args[0][1]

    @patch('emdx.agents.registry.db_connection')
    def test_create_agent(self, mock_db):
        """Test creating a new agent."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 10
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        config = {
            'name': 'new-agent',
            'display_name': 'New Agent',
            'description': 'A new agent',
            'category': 'testing',
            'system_prompt': 'You are a test agent.',
            'user_prompt_template': '{{input}}',
            'allowed_tools': ['Read', 'Write'],
            'output_tags': ['test'],
            'created_by': 'test-user'
        }

        agent_id = registry.create_agent(config)

        assert agent_id == 10
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('emdx.agents.registry.db_connection')
    def test_update_agent(self, mock_db):
        """Test updating an existing agent."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        updates = {
            'display_name': 'Updated Name',
            'description': 'Updated description',
            'allowed_tools': ['Read', 'Write', 'Bash']
        }

        result = registry.update_agent(5, updates)

        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('emdx.agents.registry.db_connection')
    def test_update_agent_empty_updates(self, mock_db):
        """Test updating with no changes returns True."""
        registry = AgentRegistry()

        result = registry.update_agent(5, {})

        assert result is True

    @patch('emdx.agents.registry.db_connection')
    def test_delete_agent_soft(self, mock_db):
        """Test soft deleting an agent."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = registry.delete_agent(5)

        assert result is True
        call_args = mock_cursor.execute.call_args
        assert 'is_active = FALSE' in call_args[0][0]

    @patch('emdx.agents.registry.db_connection')
    def test_delete_agent_hard(self, mock_db):
        """Test hard deleting an agent."""
        registry = AgentRegistry()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        result = registry.delete_agent(5, hard_delete=True)

        assert result is True
        call_args = mock_cursor.execute.call_args
        assert 'DELETE FROM agents' in call_args[0][0]


# ============================================================================
# Tests for AgentExecutor
# ============================================================================

class TestAgentExecutor:
    """Tests for AgentExecutor."""

    @pytest.mark.asyncio
    @patch('emdx.agents.executor.agent_registry')
    async def test_execute_agent_not_found(self, mock_registry):
        """Test executing a non-existent agent raises error."""
        executor = AgentExecutor()
        mock_registry.get_agent.return_value = None

        with pytest.raises(ValueError, match="Agent 999 not found"):
            await executor.execute_agent(
                agent_id=999,
                input_type='query',
                input_query='test query'
            )

    @pytest.mark.asyncio
    @patch('emdx.agents.executor.agent_registry')
    async def test_execute_agent_invalid_input_type(self, mock_registry, sample_agent_config):
        """Test executing with invalid input type raises error."""
        executor = AgentExecutor()
        mock_agent = ConcreteAgent(sample_agent_config)
        mock_registry.get_agent.return_value = mock_agent

        with pytest.raises(ValueError, match="Invalid input type"):
            await executor.execute_agent(
                agent_id=1,
                input_type='invalid',
                input_query='test'
            )

    @pytest.mark.asyncio
    @patch('emdx.agents.executor.agent_registry')
    async def test_execute_agent_document_without_id(self, mock_registry, sample_agent_config):
        """Test executing document type without doc_id raises error."""
        executor = AgentExecutor()
        mock_agent = ConcreteAgent(sample_agent_config)
        mock_registry.get_agent.return_value = mock_agent

        with pytest.raises(ValueError, match="Document ID required"):
            await executor.execute_agent(
                agent_id=1,
                input_type='document'
            )

    @pytest.mark.asyncio
    @patch('emdx.agents.executor.agent_registry')
    async def test_execute_agent_query_without_query(self, mock_registry, sample_agent_config):
        """Test executing query type without query string raises error."""
        executor = AgentExecutor()
        mock_agent = ConcreteAgent(sample_agent_config)
        mock_registry.get_agent.return_value = mock_agent

        with pytest.raises(ValueError, match="Query required"):
            await executor.execute_agent(
                agent_id=1,
                input_type='query'
            )

    def test_build_agent_prompt_with_query(self):
        """Test building prompt for query input type."""
        executor = AgentExecutor()
        # Use a config with {{query}} in the template
        config = AgentConfig(
            id=1,
            name="query-agent",
            display_name="Query Agent",
            description="Agent for query input",
            category="testing",
            system_prompt="Test",
            user_prompt_template="Answer this question: {{query}}",
            allowed_tools=["Read"]
        )
        agent = ConcreteAgent(config)
        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="What is Python?"
        )

        prompt = executor._build_agent_prompt(agent, context)

        assert "What is Python?" in prompt

    @patch('emdx.models.documents.get_document')
    def test_build_agent_prompt_with_document(self, mock_get_doc, sample_agent_config):
        """Test building prompt for document input type."""
        executor = AgentExecutor()
        agent = ConcreteAgent(sample_agent_config)

        # Create a proper mock object with content attribute
        class MockDoc:
            content = "Document content here"
        mock_get_doc.return_value = MockDoc()

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="document",
            input_doc_id=42
        )

        prompt = executor._build_agent_prompt(agent, context)

        assert "Document content here" in prompt

    @patch('emdx.agents.executor.db_connection')
    def test_create_agent_execution(self, mock_db):
        """Test creating agent execution record."""
        executor = AgentExecutor()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 50
        mock_conn.cursor.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        execution_id = executor._create_agent_execution(
            agent_id=1,
            execution_id=100,
            input_type='query',
            input_doc_id=None,
            input_query='test'
        )

        assert execution_id == 50
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('emdx.agents.executor.db_connection')
    def test_update_agent_execution(self, mock_db):
        """Test updating agent execution record."""
        executor = AgentExecutor()

        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        executor._update_agent_execution(50, {
            'status': 'completed',
            'execution_time_ms': 1500
        })

        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch('emdx.agents.executor.db_connection')
    def test_update_agent_execution_empty(self, mock_db):
        """Test updating with empty updates does nothing."""
        executor = AgentExecutor()

        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        executor._update_agent_execution(50, {})

        mock_conn.execute.assert_not_called()

    @patch('emdx.agents.executor.db_connection')
    def test_update_agent_stats_success(self, mock_db):
        """Test updating agent stats on success."""
        executor = AgentExecutor()

        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        executor._update_agent_stats(1, success=True)

        call_args = mock_conn.execute.call_args
        assert 'success_count = success_count + 1' in call_args[0][0]

    @patch('emdx.agents.executor.db_connection')
    def test_update_agent_stats_failure(self, mock_db):
        """Test updating agent stats on failure."""
        executor = AgentExecutor()

        mock_conn = MagicMock()
        mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

        executor._update_agent_stats(1, success=False)

        call_args = mock_conn.execute.call_args
        assert 'failure_count = failure_count + 1' in call_args[0][0]


# ============================================================================
# Tests for GenericAgent
# ============================================================================

class TestGenericAgent:
    """Tests for GenericAgent with mocked subprocess/Claude API."""

    def test_build_full_prompt_includes_system(self, sample_agent_config):
        """Test _build_full_prompt includes system prompt."""
        agent = GenericAgent(sample_agent_config)
        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test"
        )

        prompt = agent._build_full_prompt(context)

        assert "# System Instructions" in prompt
        assert sample_agent_config.system_prompt in prompt

    def test_build_full_prompt_includes_tools(self, sample_agent_config):
        """Test _build_full_prompt includes allowed tools."""
        agent = GenericAgent(sample_agent_config)
        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test"
        )

        prompt = agent._build_full_prompt(context)

        assert "# Allowed Tools" in prompt
        assert "Read, Write, Bash" in prompt

    @patch('emdx.agents.generic.get_document')
    def test_build_full_prompt_includes_context_docs(self, mock_get_doc, sample_agent_config):
        """Test _build_full_prompt includes context documents."""
        sample_agent_config.include_doc_content = True
        agent = GenericAgent(sample_agent_config)

        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.title = "Test Doc"
        mock_doc.content = "Test content"
        mock_get_doc.return_value = mock_doc

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test",
            context_docs=[1]
        )

        prompt = agent._build_full_prompt(context)

        assert "# Context Documents" in prompt
        assert "Test Doc" in prompt
        assert "Test content" in prompt

    def test_build_full_prompt_includes_output_format(self, sample_agent_config):
        """Test _build_full_prompt includes output format."""
        agent = GenericAgent(sample_agent_config)
        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test"
        )

        prompt = agent._build_full_prompt(context)

        assert "# Output Format" in prompt
        assert "markdown" in prompt

    def test_extract_tools_used_from_output(self, sample_agent_config):
        """Test extracting tools used from Claude output."""
        agent = GenericAgent(sample_agent_config)

        output = """
        Using tool: Read
        Some content here
        Tool: Write
        More content
        Using tool: Read
        """

        tools = agent._extract_tools_used(output)

        assert 'Read' in tools
        assert 'Write' in tools
        # Should deduplicate
        assert tools.count('Read') == 1

    def test_extract_tools_used_empty_output(self, sample_agent_config):
        """Test extracting tools from empty output."""
        agent = GenericAgent(sample_agent_config)

        tools = agent._extract_tools_used("")

        assert tools == []

    @pytest.mark.asyncio
    async def test_execute_success(self, sample_agent_config):
        """Test successful agent execution with mocked subprocess."""
        agent = GenericAgent(sample_agent_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            context = AgentContext(
                execution_id=1,
                working_dir=tmpdir,
                input_type="query",
                input_query="test",
                log_file=str(Path(tmpdir) / "test.log")
            )

            mock_process = MagicMock()
            mock_process.returncode = 0

            # Create an iterator that returns lines then signals done
            def readline_generator():
                yield '{"type": "text", "text": "Hello"}\n'
                yield '{"type": "text", "text": "World"}\n'
                yield ''

            gen = readline_generator()
            mock_process.stdout.readline.side_effect = lambda: next(gen, '')
            mock_process.poll.side_effect = [None, None, 0]

            # Patch at the module where it's imported
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
        assert result.execution_time_ms >= 0  # Can be 0 with mocked subprocess

    @pytest.mark.asyncio
    async def test_execute_failure(self, sample_agent_config):
        """Test failed agent execution with mocked subprocess."""
        agent = GenericAgent(sample_agent_config)

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

                def readline_generator():
                    yield 'Error: Something went wrong\n'
                    yield ''

                gen = readline_generator()
                mock_process.stdout.readline.side_effect = lambda: next(gen, '')
                mock_process.poll.side_effect = [None, 1]

                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.return_value = mock_process

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess

        assert result.status == 'failed'
        assert result.error_message is not None
        assert result.metadata['exit_code'] == 1

    @pytest.mark.asyncio
    async def test_execute_command_not_found(self, sample_agent_config):
        """Test agent execution when claude command not found."""
        agent = GenericAgent(sample_agent_config)

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
                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.side_effect = FileNotFoundError("No such file")

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess

        assert result.status == 'failed'
        assert 'not found' in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execute_saves_output(self, sample_agent_config):
        """Test that execution saves output as document."""
        sample_agent_config.save_outputs = True
        agent = GenericAgent(sample_agent_config)

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
            original_save_document = generic_module.save_document

            try:
                mock_process = MagicMock()
                mock_process.returncode = 0

                def readline_generator():
                    yield 'Generated output content\n'
                    yield ''

                gen = readline_generator()
                mock_process.stdout.readline.side_effect = lambda: next(gen, '')
                mock_process.poll.side_effect = [None, 0]

                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.return_value = mock_process

                mock_save = MagicMock(return_value=100)
                generic_module.save_document = mock_save

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess
                generic_module.save_document = original_save_document

        assert result.status == 'completed'
        mock_save.assert_called_once()
        assert 100 in result.output_doc_ids

    @pytest.mark.asyncio
    async def test_execute_no_save_when_disabled(self, sample_agent_config):
        """Test that output is not saved when save_outputs is False."""
        sample_agent_config.save_outputs = False
        agent = GenericAgent(sample_agent_config)

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
            original_save_document = generic_module.save_document

            try:
                mock_process = MagicMock()
                mock_process.returncode = 0

                def readline_generator():
                    yield 'output\n'
                    yield ''

                gen = readline_generator()
                mock_process.stdout.readline.side_effect = lambda: next(gen, '')
                mock_process.poll.side_effect = [None, 0]

                generic_module.subprocess = MagicMock()
                generic_module.subprocess.Popen.return_value = mock_process

                mock_save = MagicMock(return_value=100)
                generic_module.save_document = mock_save

                result = await agent.execute(context)
            finally:
                generic_module.subprocess = original_subprocess
                generic_module.save_document = original_save_document

        mock_save.assert_not_called()
        assert result.output_doc_ids == []


# ============================================================================
# Integration-style tests (still mocked but testing component interactions)
# ============================================================================

class TestAgentSystemIntegration:
    """Integration-style tests for the agent system."""

    def test_agent_config_round_trip(self, sample_db_row):
        """Test creating AgentConfig from db row and using it."""
        config = AgentConfig.from_db_row(sample_db_row)
        agent = GenericAgent(config)

        # Verify we can use the agent
        validated = agent.validate_tools(['Read', 'Grep', 'Unknown'])
        assert validated == ['Read', 'Grep']

        prompt = agent.format_prompt(query="test query")
        assert "test query" in prompt

    def test_agent_result_metadata_preservation(self):
        """Test that AgentResult preserves all metadata."""
        metadata = {
            'custom_field': 'value',
            'nested': {'key': 'nested_value'},
            'list': [1, 2, 3]
        }

        result = AgentResult(
            status='completed',
            metadata=metadata
        )

        assert result.metadata == metadata
        assert result.metadata['nested']['key'] == 'nested_value'
        assert result.metadata['list'] == [1, 2, 3]

    def test_context_variable_inheritance(self, sample_agent_config):
        """Test that context variables are properly passed to prompt."""
        sample_agent_config.user_prompt_template = "Process {{content}} with {{mode}} and {{level}}"
        agent = GenericAgent(sample_agent_config)

        context = AgentContext(
            execution_id=1,
            working_dir="/tmp",
            input_type="query",
            input_query="test",
            variables={'mode': 'fast', 'level': 'high'}
        )

        prompt = agent._build_full_prompt(context)

        assert 'fast' in prompt
        assert 'high' in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
