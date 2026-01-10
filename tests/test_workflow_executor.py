"""Integration tests for the workflow executor.

Tests the WorkflowExecutor class which orchestrates multi-stage agent runs
with different execution modes (single, parallel, iterative, adversarial, dynamic).
"""

import asyncio
import pytest
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from emdx.workflows.base import (
    ExecutionMode,
    StageConfig,
    WorkflowConfig,
    WorkflowRun,
)
from emdx.workflows.executor import WorkflowExecutor
from emdx.workflows.strategies import StageResult
from emdx.workflows.strategies.base import ExecutionStrategy
from emdx.workflows.strategies.single import SingleExecutionStrategy
from emdx.workflows.strategies.dynamic import DynamicExecutionStrategy


class MockDocumentService:
    """Mock document service for testing."""

    def __init__(self):
        self._docs: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self._docs.get(doc_id)

    def save_document(
        self,
        title: str,
        content: str,
        tags: Optional[list] = None,
    ) -> int:
        doc_id = self._next_id
        self._next_id += 1
        self._docs[doc_id] = {
            'id': doc_id,
            'title': title,
            'content': content,
            'tags': tags or [],
        }
        return doc_id

    def add_document(self, doc_id: int, title: str, content: str) -> None:
        """Add a document with a specific ID for test setup."""
        self._docs[doc_id] = {
            'id': doc_id,
            'title': title,
            'content': content,
        }


class MockExecutionService:
    """Mock execution service for testing."""

    def __init__(self):
        self._next_id = 1

    def create_execution(
        self,
        doc_id: int,
        doc_title: str,
        log_file: str,
        working_dir: Optional[str] = None,
    ) -> int:
        exec_id = self._next_id
        self._next_id += 1
        return exec_id

    def update_execution_status(
        self,
        exec_id: int,
        status: str,
        exit_code: Optional[int] = None,
    ) -> None:
        pass


class MockClaudeService:
    """Mock Claude service for testing."""

    def __init__(self, return_code: int = 0):
        self.return_code = return_code
        self.call_count = 0

    def execute_with_claude(
        self,
        task: str,
        execution_id: int,
        log_file: Path,
        allowed_tools: list,
        verbose: bool = False,
        working_dir: Optional[str] = None,
        doc_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        self.call_count += 1
        # Create a mock log file with output doc ID
        log_file.write_text(f"Created document #100")
        return self.return_code


class WorkflowTestDatabase:
    """In-memory database for workflow testing."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create minimal schema for workflow testing."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                definition_json TEXT,
                category TEXT DEFAULT 'custom',
                is_builtin BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                current_stage TEXT,
                current_stage_run INTEGER DEFAULT 0,
                input_doc_id INTEGER,
                input_variables TEXT,
                context_json TEXT,
                gameplan_id INTEGER,
                task_id INTEGER,
                parent_run_id INTEGER,
                output_doc_ids TEXT,
                error_message TEXT,
                total_tokens_used INTEGER DEFAULT 0,
                total_execution_time_ms INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            );

            CREATE TABLE IF NOT EXISTS workflow_stage_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_run_id INTEGER NOT NULL,
                stage_name TEXT NOT NULL,
                mode TEXT NOT NULL,
                target_runs INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                runs_completed INTEGER DEFAULT 0,
                output_doc_id INTEGER,
                synthesis_doc_id INTEGER,
                error_message TEXT,
                tokens_used INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id)
            );

            CREATE TABLE IF NOT EXISTS workflow_individual_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage_run_id INTEGER NOT NULL,
                run_number INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                agent_execution_id INTEGER,
                prompt_used TEXT,
                input_context TEXT,
                output_doc_id INTEGER,
                error_message TEXT,
                tokens_used INTEGER DEFAULT 0,
                execution_time_ms INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (stage_run_id) REFERENCES workflow_stage_runs(id)
            );

            CREATE TABLE IF NOT EXISTS iteration_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                prompts_json TEXT,
                recommended_runs INTEGER DEFAULT 5,
                category TEXT DEFAULT 'general',
                is_builtin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER,
                doc_title TEXT,
                log_file TEXT,
                working_dir TEXT,
                status TEXT DEFAULT 'pending',
                exit_code INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    def get_connection(self):
        return self.conn

    def close(self):
        self.conn.close()


@pytest.fixture
def workflow_db():
    """Create a test database for workflows."""
    db = WorkflowTestDatabase()
    yield db
    db.close()


@pytest.fixture
def mock_services():
    """Create mock services for testing."""
    doc_service = MockDocumentService()
    exec_service = MockExecutionService()
    claude_service = MockClaudeService()
    return {
        'document': doc_service,
        'execution': exec_service,
        'claude': claude_service,
    }


class TestStageConfig:
    """Tests for StageConfig dataclass."""

    def test_from_dict_single_mode(self):
        """Test creating StageConfig from dict with single mode."""
        data = {
            'name': 'analyze',
            'mode': 'single',
            'prompt': 'Analyze this input: {{input}}',
        }
        config = StageConfig.from_dict(data)
        assert config.name == 'analyze'
        assert config.mode == ExecutionMode.SINGLE
        assert config.runs == 1
        assert '{{input}}' in config.prompt

    def test_from_dict_parallel_mode(self):
        """Test creating StageConfig from dict with parallel mode."""
        data = {
            'name': 'brainstorm',
            'mode': 'parallel',
            'runs': 3,
            'prompt': 'Generate ideas for: {{input}}',
            'synthesis_prompt': 'Combine these ideas: {{outputs}}',
        }
        config = StageConfig.from_dict(data)
        assert config.name == 'brainstorm'
        assert config.mode == ExecutionMode.PARALLEL
        assert config.runs == 3
        assert config.synthesis_prompt is not None

    def test_from_dict_iterative_mode(self):
        """Test creating StageConfig from dict with iterative mode."""
        data = {
            'name': 'refine',
            'mode': 'iterative',
            'runs': 5,
            'prompts': [
                'Initial draft: {{input}}',
                'Improve this: {{prev}}',
                'Final polish: {{prev}}',
            ],
        }
        config = StageConfig.from_dict(data)
        assert config.name == 'refine'
        assert config.mode == ExecutionMode.ITERATIVE
        assert config.runs == 5
        assert len(config.prompts) == 3

    def test_from_dict_dynamic_mode(self):
        """Test creating StageConfig from dict with dynamic mode."""
        data = {
            'name': 'process_files',
            'mode': 'dynamic',
            'discovery_command': 'find . -name "*.py"',
            'item_variable': 'file',
            'max_concurrent': 3,
            'prompt': 'Process file: {{file}}',
        }
        config = StageConfig.from_dict(data)
        assert config.name == 'process_files'
        assert config.mode == ExecutionMode.DYNAMIC
        assert config.discovery_command == 'find . -name "*.py"'
        assert config.item_variable == 'file'
        assert config.max_concurrent == 3

    def test_to_dict_roundtrip(self):
        """Test that to_dict/from_dict roundtrips correctly."""
        original = StageConfig(
            name='test_stage',
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompt='Test prompt',
            synthesis_prompt='Synthesize: {{outputs}}',
        )
        as_dict = original.to_dict()
        restored = StageConfig.from_dict(as_dict)

        assert restored.name == original.name
        assert restored.mode == original.mode
        assert restored.runs == original.runs
        assert restored.prompt == original.prompt
        assert restored.synthesis_prompt == original.synthesis_prompt


class TestWorkflowExecutorTemplateResolution:
    """Tests for template resolution in ExecutionStrategy."""

    def test_resolve_simple_variable(self):
        """Test resolving simple {{variable}} templates."""
        strategy = SingleExecutionStrategy()
        template = "Hello, {{name}}!"
        context = {'name': 'World'}
        result = strategy.resolve_template(template, context)
        assert result == "Hello, World!"

    def test_resolve_multiple_variables(self):
        """Test resolving multiple variables in same template."""
        strategy = SingleExecutionStrategy()
        template = "{{greeting}}, {{name}}! Welcome to {{place}}."
        context = {'greeting': 'Hello', 'name': 'User', 'place': 'EMDX'}
        result = strategy.resolve_template(template, context)
        assert result == "Hello, User! Welcome to EMDX."

    def test_resolve_missing_variable(self):
        """Test that missing variables resolve to empty string."""
        strategy = SingleExecutionStrategy()
        template = "Value: {{missing}}"
        context = {}
        result = strategy.resolve_template(template, context)
        assert result == "Value: "

    def test_resolve_indexed_access(self):
        """Test resolving indexed access like {{all_prev[0]}}."""
        strategy = SingleExecutionStrategy()
        template = "First: {{items[0]}}, Second: {{items[1]}}"
        context = {'items': ['apple', 'banana', 'cherry']}
        result = strategy.resolve_template(template, context)
        assert result == "First: apple, Second: banana"

    def test_resolve_indexed_access_out_of_bounds(self):
        """Test that out of bounds index resolves to empty string."""
        strategy = SingleExecutionStrategy()
        template = "Item: {{items[10]}}"
        context = {'items': ['only_one']}
        result = strategy.resolve_template(template, context)
        assert result == "Item: "

    def test_resolve_dotted_variable(self):
        """Test resolving dotted variable names like {{stage.output}}."""
        strategy = SingleExecutionStrategy()
        template = "Previous output: {{analyze.output}}"
        context = {'analyze.output': 'Analysis result'}
        result = strategy.resolve_template(template, context)
        assert result == "Previous output: Analysis result"

    def test_resolve_none_template(self):
        """Test that None template returns empty string."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(None, {})
        assert result == ""


class TestStageResult:
    """Tests for StageResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful stage result."""
        result = StageResult(
            success=True,
            output_doc_id=123,
            tokens_used=500,
            execution_time_ms=1500,
        )
        assert result.success is True
        assert result.output_doc_id == 123
        assert result.error_message is None

    def test_failed_result(self):
        """Test creating a failed stage result."""
        result = StageResult(
            success=False,
            error_message="Agent execution failed",
        )
        assert result.success is False
        assert result.output_doc_id is None
        assert result.error_message == "Agent execution failed"

    def test_parallel_result_with_individual_outputs(self):
        """Test stage result with individual outputs from parallel execution."""
        result = StageResult(
            success=True,
            synthesis_doc_id=100,
            individual_outputs=[101, 102, 103],
            tokens_used=1500,
        )
        assert result.success is True
        assert result.synthesis_doc_id == 100
        assert len(result.individual_outputs) == 3


class TestWorkflowExecutorDocIdExtraction:
    """Tests for extracting document IDs from execution logs."""

    def test_extract_doc_id_created_pattern(self):
        """Test extracting doc ID from 'Created document #123' pattern."""
        strategy = SingleExecutionStrategy()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("Some output...\nCreated document #456\nMore output...")
            log_path = Path(f.name)

        try:
            doc_id = strategy._extract_output_doc_id(log_path)
            assert doc_id == 456
        finally:
            log_path.unlink()

    def test_extract_doc_id_saved_pattern(self):
        """Test extracting doc ID from 'Saved as #123' pattern."""
        strategy = SingleExecutionStrategy()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("Processing...\nSaved as #789\nDone!")
            log_path = Path(f.name)

        try:
            doc_id = strategy._extract_output_doc_id(log_path)
            assert doc_id == 789
        finally:
            log_path.unlink()

    def test_extract_doc_id_not_found(self):
        """Test that None is returned when no doc ID pattern found."""
        strategy = SingleExecutionStrategy()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("No document ID in this log")
            log_path = Path(f.name)

        try:
            doc_id = strategy._extract_output_doc_id(log_path)
            assert doc_id is None
        finally:
            log_path.unlink()

    def test_extract_doc_id_missing_file(self):
        """Test that None is returned for missing log file."""
        strategy = SingleExecutionStrategy()
        doc_id = strategy._extract_output_doc_id(Path("/nonexistent/path.log"))
        assert doc_id is None


class TestWorkflowExecutorInit:
    """Tests for WorkflowExecutor initialization."""

    def test_default_max_concurrent(self):
        """Test default max_concurrent value."""
        executor = WorkflowExecutor()
        assert executor.max_concurrent == 10

    def test_custom_max_concurrent(self):
        """Test custom max_concurrent value."""
        executor = WorkflowExecutor(max_concurrent=5)
        assert executor.max_concurrent == 5


class TestExecutionModeEnum:
    """Tests for ExecutionMode enum."""

    def test_all_modes_defined(self):
        """Test that all expected execution modes are defined."""
        modes = [mode.value for mode in ExecutionMode]
        assert 'single' in modes
        assert 'parallel' in modes
        assert 'iterative' in modes
        assert 'adversarial' in modes
        assert 'dynamic' in modes

    def test_mode_from_string(self):
        """Test creating ExecutionMode from string value."""
        mode = ExecutionMode('single')
        assert mode == ExecutionMode.SINGLE

        mode = ExecutionMode('parallel')
        assert mode == ExecutionMode.PARALLEL


class TestWorkflowRunDataclass:
    """Tests for WorkflowRun dataclass."""

    def test_from_db_row(self):
        """Test creating WorkflowRun from database row."""
        import json
        row = {
            'id': 1,
            'workflow_id': 10,
            'status': 'completed',
            'current_stage': 'analyze',
            'current_stage_run': 1,
            'input_doc_id': 100,
            'input_variables': json.dumps({'key': 'value'}),
            'context_json': json.dumps({'result': 'data'}),
            'output_doc_ids': json.dumps([200, 201]),
            'total_tokens_used': 1000,
            'total_execution_time_ms': 5000,
        }

        run = WorkflowRun.from_db_row(row)
        assert run.id == 1
        assert run.workflow_id == 10
        assert run.status == 'completed'
        assert run.input_variables == {'key': 'value'}
        assert run.context == {'result': 'data'}
        assert run.output_doc_ids == [200, 201]

    def test_from_db_row_with_nulls(self):
        """Test creating WorkflowRun with null/missing values."""
        row = {
            'id': 1,
            'workflow_id': 10,
            'status': 'pending',
            'input_variables': None,
            'context_json': None,
            'output_doc_ids': None,
        }

        run = WorkflowRun.from_db_row(row)
        assert run.id == 1
        assert run.input_variables == {}
        assert run.context == {}
        assert run.output_doc_ids == []


class TestWorkflowConfigDataclass:
    """Tests for WorkflowConfig dataclass."""

    def test_from_db_row(self):
        """Test creating WorkflowConfig from database row."""
        import json
        definition = {
            'stages': [
                {'name': 'stage1', 'mode': 'single', 'prompt': 'Do task 1'},
                {'name': 'stage2', 'mode': 'single', 'prompt': 'Do task 2'},
            ],
            'variables': {'default_var': 'value'},
        }
        row = {
            'id': 1,
            'name': 'test-workflow',
            'display_name': 'Test Workflow',
            'description': 'A test workflow',
            'definition_json': json.dumps(definition),
            'category': 'testing',
            'is_builtin': False,
            'is_active': True,
            'usage_count': 5,
            'success_count': 4,
            'failure_count': 1,
        }

        config = WorkflowConfig.from_db_row(row)
        assert config.id == 1
        assert config.name == 'test-workflow'
        assert config.display_name == 'Test Workflow'
        assert len(config.stages) == 2
        assert config.stages[0].name == 'stage1'
        assert config.variables == {'default_var': 'value'}
        assert config.usage_count == 5

    def test_to_definition_json(self):
        """Test serializing workflow config to JSON definition."""
        config = WorkflowConfig(
            id=1,
            name='test',
            display_name='Test',
            description=None,
            stages=[
                StageConfig(name='s1', mode=ExecutionMode.SINGLE, prompt='P1'),
            ],
            variables={'var1': 'val1'},
        )

        json_str = config.to_definition_json()
        import json
        parsed = json.loads(json_str)
        assert 'stages' in parsed
        assert 'variables' in parsed
        assert len(parsed['stages']) == 1
        assert parsed['variables']['var1'] == 'val1'


@pytest.mark.asyncio
class TestWorkflowExecutorDiscovery:
    """Tests for dynamic mode discovery command execution."""

    async def test_run_discovery_success(self):
        """Test successful discovery command execution."""
        strategy = DynamicExecutionStrategy()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            for i in range(3):
                Path(tmpdir, f"file{i}.txt").touch()

            context = {'_working_dir': tmpdir}
            items = await strategy._run_discovery(f"ls {tmpdir}", context)

            assert len(items) == 3
            assert all('file' in item for item in items)

    async def test_run_discovery_with_template(self):
        """Test discovery command with template variable."""
        strategy = DynamicExecutionStrategy()

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.py").touch()
            Path(tmpdir, "test.txt").touch()

            context = {'_working_dir': tmpdir, 'extension': 'py'}
            # Note: Using echo to simulate a templated command
            items = await strategy._run_discovery("echo 'item1\nitem2'", context)

            assert len(items) == 2

    async def test_run_discovery_empty_result(self):
        """Test discovery command that returns no items."""
        strategy = DynamicExecutionStrategy()

        with tempfile.TemporaryDirectory() as tmpdir:
            context = {'_working_dir': tmpdir}
            # List an empty directory with a pattern that won't match
            items = await strategy._run_discovery(f"ls {tmpdir}/*.nonexistent 2>/dev/null || true", context)

            assert items == []

    async def test_run_discovery_failure(self):
        """Test discovery command that fails."""
        strategy = DynamicExecutionStrategy()

        context = {'_working_dir': '/tmp'}
        with pytest.raises(ValueError, match="Discovery command failed"):
            await strategy._run_discovery("exit 1", context)
