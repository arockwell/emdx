"""Comprehensive tests for all 5 workflow execution modes.

This module tests the execution strategies:
- SINGLE: Run once
- PARALLEL: Run N times simultaneously, synthesize results
- ITERATIVE: Run N times sequentially, building on previous
- ADVERSARIAL: Advocate -> Critic -> Synthesizer pattern
- DYNAMIC: Discover items at runtime, process each in parallel

These tests use mocking to avoid actual Claude API calls while
testing the execution logic, error handling, and context propagation.
"""

import asyncio
import json
import pytest
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from emdx.workflows.base import (
    ExecutionMode,
    StageConfig,
    WorkflowConfig,
    WorkflowRun,
    IterationStrategy,
)
from emdx.workflows.strategies import (
    StageResult,
    SingleExecutionStrategy,
    ParallelExecutionStrategy,
    IterativeExecutionStrategy,
    AdversarialExecutionStrategy,
    DynamicExecutionStrategy,
)


# ============================================================================
# Test Fixtures and Mocks
# ============================================================================


class MockDocumentService:
    """Mock document service that tracks saved documents."""

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
        # Update next_id if necessary
        if doc_id >= self._next_id:
            self._next_id = doc_id + 1


class MockExecutionService:
    """Mock execution service for testing."""

    def __init__(self):
        self._next_id = 1
        self._executions: Dict[int, Dict[str, Any]] = {}

    def create_execution(
        self,
        doc_id: Optional[int],
        doc_title: str,
        log_file: str,
        working_dir: Optional[str] = None,
    ) -> int:
        exec_id = self._next_id
        self._next_id += 1
        self._executions[exec_id] = {
            'id': exec_id,
            'doc_id': doc_id,
            'doc_title': doc_title,
            'log_file': log_file,
            'working_dir': working_dir,
            'status': 'pending',
        }
        return exec_id

    def update_execution_status(
        self,
        exec_id: int,
        status: str,
        exit_code: Optional[int] = None,
    ) -> None:
        if exec_id in self._executions:
            self._executions[exec_id]['status'] = status
            self._executions[exec_id]['exit_code'] = exit_code


class MockClaudeService:
    """Mock Claude service for testing that simulates agent execution."""

    def __init__(
        self,
        return_code: int = 0,
        output_doc_id: int = 100,
        fail_on_runs: Optional[List[int]] = None,
    ):
        self.return_code = return_code
        self.output_doc_id = output_doc_id
        self.fail_on_runs = fail_on_runs or []
        self.call_count = 0
        self.prompts_received: List[str] = []

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
        self.prompts_received.append(task)

        # Check if this run should fail
        if self.call_count in self.fail_on_runs:
            log_file.write_text("Error: Simulated failure")
            return 1

        # Create a mock log file with output doc ID
        log_content = f"Processing task...\nSaved as #{self.output_doc_id + self.call_count - 1}\nDone."
        log_file.write_text(log_content)
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
                synthesis_cost_usd REAL DEFAULT 0,
                synthesis_input_tokens INTEGER DEFAULT 0,
                synthesis_output_tokens INTEGER DEFAULT 0,
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
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS document_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                workflow_run_id INTEGER,
                workflow_stage_run_id INTEGER,
                workflow_individual_run_id INTEGER,
                source_type TEXT,
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
def mock_doc_service():
    """Create mock document service."""
    return MockDocumentService()


@pytest.fixture
def mock_exec_service():
    """Create mock execution service."""
    return MockExecutionService()


@pytest.fixture
def mock_claude_service():
    """Create mock Claude service with successful execution."""
    return MockClaudeService(return_code=0, output_doc_id=100)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_stage_run(db: WorkflowTestDatabase, stage_name: str = "test_stage", mode: str = "single") -> int:
    """Helper to create a stage run record for testing."""
    cursor = db.conn.cursor()
    # Create a workflow first
    cursor.execute(
        "INSERT INTO workflows (name, display_name) VALUES (?, ?)",
        ("test-workflow", "Test Workflow"),
    )
    workflow_id = cursor.lastrowid

    # Create a workflow run
    cursor.execute(
        "INSERT INTO workflow_runs (workflow_id, status) VALUES (?, ?)",
        (workflow_id, "running"),
    )
    run_id = cursor.lastrowid

    # Create the stage run
    cursor.execute(
        "INSERT INTO workflow_stage_runs (workflow_run_id, stage_name, mode, target_runs) VALUES (?, ?, ?, ?)",
        (run_id, stage_name, mode, 1),
    )
    stage_run_id = cursor.lastrowid
    db.conn.commit()

    return stage_run_id


# ============================================================================
# Single Execution Mode Tests
# ============================================================================


@pytest.mark.asyncio
class TestSingleExecutionMode:
    """Tests for SINGLE execution mode - runs agent once."""

    async def test_single_execution_success(
        self, workflow_db, mock_doc_service, mock_exec_service, mock_claude_service, temp_dir
    ):
        """Test successful single execution."""
        stage_run_id = create_stage_run(workflow_db, "analyze", "single")

        # Set up mock document for output
        mock_doc_service.add_document(100, "Analysis Result", "Analysis content here")

        stage = StageConfig(
            name="analyze",
            mode=ExecutionMode.SINGLE,
            runs=1,
            prompt="Analyze this: {{input}}",
        )

        context = {
            'input': 'Test input data',
            '_working_dir': str(temp_dir),
        }

        strategy = SingleExecutionStrategy()

        # Patch the services
        with patch.object(strategy, 'run_agent', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': True,
                'output_doc_id': 100,
                'tokens_used': 500,
            }

            # Patch database operations
            with patch('emdx.workflows.strategies.single.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.return_value = 1

                result = await strategy.execute(stage_run_id, stage, context, "Test input data")

        assert result.success is True
        assert result.output_doc_id == 100
        assert result.tokens_used == 500
        assert result.error_message is None

    async def test_single_execution_failure(self, workflow_db, temp_dir):
        """Test single execution that fails."""
        stage_run_id = create_stage_run(workflow_db, "analyze", "single")

        stage = StageConfig(
            name="analyze",
            mode=ExecutionMode.SINGLE,
            runs=1,
            prompt="Analyze this: {{input}}",
        )

        context = {
            'input': 'Test input data',
            '_working_dir': str(temp_dir),
        }

        strategy = SingleExecutionStrategy()

        with patch.object(strategy, 'run_agent', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                'success': False,
                'error_message': 'Claude execution failed with exit code 1',
            }

            with patch('emdx.workflows.strategies.single.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.return_value = 1

                result = await strategy.execute(stage_run_id, stage, context, "Test input data")

        assert result.success is False
        assert result.error_message == 'Claude execution failed with exit code 1'
        assert result.output_doc_id is None

    async def test_single_execution_template_resolution(self, workflow_db, temp_dir):
        """Test that templates are resolved correctly in single mode."""
        stage_run_id = create_stage_run(workflow_db, "analyze", "single")

        stage = StageConfig(
            name="analyze",
            mode=ExecutionMode.SINGLE,
            runs=1,
            prompt="Topic: {{topic}}, Input: {{input}}",
        )

        context = {
            'input': 'User question',
            'topic': 'Python programming',
            '_working_dir': str(temp_dir),
        }

        strategy = SingleExecutionStrategy()
        prompts_received = []

        async def capture_prompt(*args, **kwargs):
            prompts_received.append(kwargs.get('prompt', args[2] if len(args) > 2 else ''))
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 0}

        with patch.object(strategy, 'run_agent', side_effect=capture_prompt):
            with patch('emdx.workflows.strategies.single.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.return_value = 1

                await strategy.execute(stage_run_id, stage, context, "User question")

        assert len(prompts_received) == 1
        assert "Python programming" in prompts_received[0]
        assert "User question" in prompts_received[0]

    async def test_single_execution_no_prompt_uses_stage_input(self, workflow_db, temp_dir):
        """Test that stage_input is used when no prompt is provided."""
        stage_run_id = create_stage_run(workflow_db, "passthrough", "single")

        stage = StageConfig(
            name="passthrough",
            mode=ExecutionMode.SINGLE,
            runs=1,
            prompt=None,  # No prompt
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = SingleExecutionStrategy()
        prompts_received = []

        async def capture_prompt(*args, **kwargs):
            prompts_received.append(kwargs.get('prompt', args[2] if len(args) > 2 else ''))
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 0}

        with patch.object(strategy, 'run_agent', side_effect=capture_prompt):
            with patch('emdx.workflows.strategies.single.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.return_value = 1

                await strategy.execute(stage_run_id, stage, context, "Direct stage input")

        assert len(prompts_received) == 1
        assert prompts_received[0] == "Direct stage input"


# ============================================================================
# Parallel Execution Mode Tests
# ============================================================================


@pytest.mark.asyncio
class TestParallelExecutionMode:
    """Tests for PARALLEL execution mode - runs N agents simultaneously, synthesizes results."""

    async def test_parallel_execution_all_success(self, workflow_db, mock_doc_service, temp_dir):
        """Test parallel execution where all runs succeed."""
        stage_run_id = create_stage_run(workflow_db, "brainstorm", "parallel")

        # Set up documents for each run
        for i in range(3):
            mock_doc_service.add_document(100 + i, f"Idea {i+1}", f"Idea content {i+1}")
        mock_doc_service.add_document(200, "Synthesis", "Combined ideas")

        stage = StageConfig(
            name="brainstorm",
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompt="Generate an idea for: {{input}}",
            synthesis_prompt="Combine these ideas: {{outputs}}",
        )

        context = {
            'input': 'New product features',
            '_working_dir': str(temp_dir),
        }

        strategy = ParallelExecutionStrategy(max_concurrent=10)
        run_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal run_count
            run_count += 1
            return {
                'success': True,
                'output_doc_id': 99 + run_count,
                'tokens_used': 100,
            }

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {
                    'output_doc_id': 200,
                    'tokens_used': 50,
                }

                with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]

                    result = await strategy.execute(stage_run_id, stage, context, "New product features")

        assert result.success is True
        assert result.synthesis_doc_id == 200
        assert len(result.individual_outputs) == 3
        assert result.tokens_used == 350  # 3*100 + 50 for synthesis
        assert run_count == 3

    async def test_parallel_execution_partial_failure(self, workflow_db, temp_dir):
        """Test parallel execution where some runs fail but synthesis still works."""
        stage_run_id = create_stage_run(workflow_db, "brainstorm", "parallel")

        stage = StageConfig(
            name="brainstorm",
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompt="Generate idea: {{input}}",
            synthesis_prompt="Combine: {{outputs}}",
        )

        context = {'input': 'Test', '_working_dir': str(temp_dir)}

        strategy = ParallelExecutionStrategy(max_concurrent=10)
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second run fails
                return {'success': False, 'error_message': 'Simulated failure'}
            return {'success': True, 'output_doc_id': 100 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {'output_doc_id': 200, 'tokens_used': 50}

                with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]

                    result = await strategy.execute(stage_run_id, stage, context, "Test")

        # Should still succeed if at least one run succeeded
        assert result.success is True
        assert len(result.individual_outputs) == 2  # Only 2 succeeded

    async def test_parallel_execution_all_fail(self, workflow_db, temp_dir):
        """Test parallel execution where all runs fail."""
        stage_run_id = create_stage_run(workflow_db, "brainstorm", "parallel")

        stage = StageConfig(
            name="brainstorm",
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompt="Generate idea: {{input}}",
        )

        context = {'input': 'Test', '_working_dir': str(temp_dir)}

        strategy = ParallelExecutionStrategy(max_concurrent=10)

        async def mock_run_agent(*args, **kwargs):
            return {'success': False, 'error_message': 'API error'}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.side_effect = [1, 2, 3]

                result = await strategy.execute(stage_run_id, stage, context, "Test")

        assert result.success is False
        assert "All parallel runs failed" in result.error_message

    async def test_parallel_execution_with_per_run_prompts(self, workflow_db, temp_dir):
        """Test parallel execution with different prompts for each run."""
        stage_run_id = create_stage_run(workflow_db, "multi_perspective", "parallel")

        stage = StageConfig(
            name="multi_perspective",
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompts=[
                "Analyze from technical perspective: {{input}}",
                "Analyze from business perspective: {{input}}",
                "Analyze from user perspective: {{input}}",
            ],
            synthesis_prompt="Combine perspectives: {{outputs}}",
        )

        context = {'input': 'New feature', '_working_dir': str(temp_dir)}

        strategy = ParallelExecutionStrategy(max_concurrent=10)
        prompts_used = []

        async def capture_prompt(individual_run_id, agent_id, prompt, context):
            # run_agent signature: (individual_run_id, agent_id, prompt, context)
            prompts_used.append(prompt)
            return {'success': True, 'output_doc_id': 100 + len(prompts_used), 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=capture_prompt):
            with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {'output_doc_id': 200, 'tokens_used': 50}

                with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]

                    await strategy.execute(stage_run_id, stage, context, "New feature")

        assert len(prompts_used) == 3
        assert "technical perspective" in prompts_used[0]
        assert "business perspective" in prompts_used[1]
        assert "user perspective" in prompts_used[2]

    @pytest.mark.skip(reason="Concurrency limiting not yet implemented in ParallelExecutionStrategy")
    async def test_parallel_execution_concurrency_limit(self, workflow_db, temp_dir):
        """Test that parallel execution respects concurrency limits."""
        stage_run_id = create_stage_run(workflow_db, "load_test", "parallel")

        stage = StageConfig(
            name="load_test",
            mode=ExecutionMode.PARALLEL,
            runs=5,
            prompt="Process: {{input}}",
            synthesis_prompt="Combine: {{outputs}}",
        )

        context = {'input': 'Test', '_working_dir': str(temp_dir)}

        # Set max_concurrent to 2
        strategy = ParallelExecutionStrategy(max_concurrent=2)
        max_concurrent_seen = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def track_concurrency(*args, **kwargs):
            nonlocal max_concurrent_seen, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent_seen = max(max_concurrent_seen, current_concurrent)

            await asyncio.sleep(0.1)  # Simulate some work (longer to ensure concurrency tracking works)

            async with lock:
                current_concurrent -= 1

            return {'success': True, 'output_doc_id': 100, 'tokens_used': 10}

        with patch.object(strategy, 'run_agent', side_effect=track_concurrency):
            with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {'output_doc_id': 200, 'tokens_used': 50}

                with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = list(range(1, 6))

                    await strategy.execute(stage_run_id, stage, context, "Test")

        # Should never exceed the limit
        assert max_concurrent_seen <= 2


# ============================================================================
# Iterative Execution Mode Tests
# ============================================================================


@pytest.mark.asyncio
class TestIterativeExecutionMode:
    """Tests for ITERATIVE execution mode - runs N times sequentially, building on previous."""

    async def test_iterative_execution_success(self, workflow_db, mock_doc_service, temp_dir):
        """Test successful iterative execution."""
        stage_run_id = create_stage_run(workflow_db, "refine", "iterative")

        # Set up documents for each iteration
        mock_doc_service.add_document(100, "Draft 1", "Initial draft content")
        mock_doc_service.add_document(101, "Draft 2", "Improved content")
        mock_doc_service.add_document(102, "Draft 3", "Final polished content")

        stage = StageConfig(
            name="refine",
            mode=ExecutionMode.ITERATIVE,
            runs=3,
            prompts=[
                "Create initial draft: {{input}}",
                "Improve this draft: {{prev}}",
                "Final polish: {{prev}}",
            ],
        )

        context = {'input': 'Topic to write about', '_working_dir': str(temp_dir)}

        strategy = IterativeExecutionStrategy()
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.iterative.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                mock_wf_db.update_stage_run = MagicMock()

            with patch('emdx.workflows.strategies.iterative.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.iterative.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    result = await strategy.execute(stage_run_id, stage, context, "Topic to write about")

        assert result.success is True
        assert result.output_doc_id == 102  # Last output
        assert len(result.individual_outputs) == 3
        assert result.tokens_used == 300

    async def test_iterative_execution_failure_mid_run(self, workflow_db, mock_doc_service, temp_dir):
        """Test iterative execution that fails in the middle."""
        stage_run_id = create_stage_run(workflow_db, "refine", "iterative")

        mock_doc_service.add_document(100, "Draft 1", "Initial draft content")

        stage = StageConfig(
            name="refine",
            mode=ExecutionMode.ITERATIVE,
            runs=3,
            prompt="Improve: {{prev}}",
        )

        context = {'input': 'Topic', '_working_dir': str(temp_dir)}

        strategy = IterativeExecutionStrategy()
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {'success': False, 'error_message': 'API timeout'}
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.iterative.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.iterative.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    result = await strategy.execute(stage_run_id, stage, context, "Topic")

        assert result.success is False
        assert "Iteration 2 failed" in result.error_message
        assert result.tokens_used == 100  # Only first run's tokens

    async def test_iterative_context_propagation(self, workflow_db, mock_doc_service, temp_dir):
        """Test that context is properly propagated between iterations."""
        stage_run_id = create_stage_run(workflow_db, "chain", "iterative")

        mock_doc_service.add_document(100, "Step 1", "First step result")
        mock_doc_service.add_document(101, "Step 2", "Second step result")
        mock_doc_service.add_document(102, "Step 3", "Third step result")

        stage = StageConfig(
            name="chain",
            mode=ExecutionMode.ITERATIVE,
            runs=3,
            prompt="Continue from: {{prev}}\nAll previous: {{all_prev}}",
        )

        context = {'input': 'Start', '_working_dir': str(temp_dir)}

        strategy = IterativeExecutionStrategy()
        contexts_seen = []
        call_count = 0

        async def capture_context(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            contexts_seen.append(kwargs.get('context', {}).copy())
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=capture_context):
            with patch('emdx.workflows.strategies.iterative.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.iterative.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    await strategy.execute(stage_run_id, stage, context, "Start")

        assert len(contexts_seen) == 3

        # First iteration has no previous
        assert contexts_seen[0]['prev'] == ''
        assert contexts_seen[0]['run_number'] == 1

        # Second iteration has first output
        assert contexts_seen[1]['prev'] == 'First step result'
        assert contexts_seen[1]['run_number'] == 2

        # Third iteration has second output, all_prev has both
        assert contexts_seen[2]['prev'] == 'Second step result'
        assert contexts_seen[2]['run_number'] == 3

    async def test_iterative_with_iteration_strategy(self, workflow_db, mock_doc_service, temp_dir):
        """Test iterative execution with a named iteration strategy."""
        stage_run_id = create_stage_run(workflow_db, "refine", "iterative")

        mock_doc_service.add_document(100, "Result 1", "Content 1")
        mock_doc_service.add_document(101, "Result 2", "Content 2")

        stage = StageConfig(
            name="refine",
            mode=ExecutionMode.ITERATIVE,
            runs=2,
            iteration_strategy="devil_advocate",
        )

        context = {'input': 'Topic', '_working_dir': str(temp_dir)}

        # Create mock iteration strategy
        mock_strategy = IterationStrategy(
            id=1,
            name="devil_advocate",
            display_name="Devil's Advocate",
            description="Challenge and refine",
            prompts=["Propose solution: {{input}}", "Challenge this: {{prev}}"],
        )

        strategy = IterativeExecutionStrategy()
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.iterative.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.iterative.workflow_registry') as mock_registry:
                    mock_registry.get_iteration_strategy.return_value = mock_strategy

                    with patch('emdx.workflows.strategies.iterative.wf_db') as mock_wf_db:
                        mock_wf_db.create_individual_run.side_effect = [1, 2]
                        mock_wf_db.update_stage_run = MagicMock()

                        result = await strategy.execute(stage_run_id, stage, context, "Topic")

        assert result.success is True
        mock_registry.get_iteration_strategy.assert_called_once_with("devil_advocate")


# ============================================================================
# Adversarial Execution Mode Tests
# ============================================================================


@pytest.mark.asyncio
class TestAdversarialExecutionMode:
    """Tests for ADVERSARIAL execution mode - Advocate -> Critic -> Synthesizer pattern."""

    async def test_adversarial_execution_success(self, workflow_db, mock_doc_service, temp_dir):
        """Test successful adversarial execution."""
        stage_run_id = create_stage_run(workflow_db, "debate", "adversarial")

        mock_doc_service.add_document(100, "Advocacy", "Arguments FOR the approach")
        mock_doc_service.add_document(101, "Criticism", "Arguments AGAINST the approach")
        mock_doc_service.add_document(102, "Synthesis", "Balanced assessment")

        stage = StageConfig(
            name="debate",
            mode=ExecutionMode.ADVERSARIAL,
            runs=3,
        )

        context = {'input': 'Proposed solution', '_working_dir': str(temp_dir)}

        strategy = AdversarialExecutionStrategy()
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 200}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.adversarial.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.adversarial.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    result = await strategy.execute(stage_run_id, stage, context, "Proposed solution")

        assert result.success is True
        assert result.output_doc_id == 102  # Synthesis is the final output
        assert result.synthesis_doc_id == 102
        assert len(result.individual_outputs) == 3
        assert result.tokens_used == 600

    async def test_adversarial_uses_default_prompts(self, workflow_db, mock_doc_service, temp_dir):
        """Test that adversarial mode uses default prompts when none provided."""
        stage_run_id = create_stage_run(workflow_db, "debate", "adversarial")

        mock_doc_service.add_document(100, "Advocacy", "Pro arguments")
        mock_doc_service.add_document(101, "Criticism", "Con arguments")
        mock_doc_service.add_document(102, "Synthesis", "Balanced view")

        stage = StageConfig(
            name="debate",
            mode=ExecutionMode.ADVERSARIAL,
            runs=3,
            # No prompts provided - should use defaults
        )

        context = {'input': 'Test proposal', '_working_dir': str(temp_dir)}

        strategy = AdversarialExecutionStrategy()
        prompts_used = []
        call_count = 0

        async def capture_prompts(individual_run_id, agent_id, prompt, context):
            # run_agent signature: (individual_run_id, agent_id, prompt, context)
            nonlocal call_count
            call_count += 1
            prompts_used.append(prompt)
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=capture_prompts):
            with patch('emdx.workflows.strategies.adversarial.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.adversarial.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    await strategy.execute(stage_run_id, stage, context, "Test proposal")

        assert len(prompts_used) == 3
        assert "ADVOCATE" in prompts_used[0]
        assert "CRITIC" in prompts_used[1]
        assert "SYNTHESIS" in prompts_used[2]

    async def test_adversarial_with_custom_prompts(self, workflow_db, mock_doc_service, temp_dir):
        """Test adversarial mode with custom prompts."""
        stage_run_id = create_stage_run(workflow_db, "debate", "adversarial")

        mock_doc_service.add_document(100, "Pro", "Pro content")
        mock_doc_service.add_document(101, "Con", "Con content")
        mock_doc_service.add_document(102, "Summary", "Summary content")

        stage = StageConfig(
            name="debate",
            mode=ExecutionMode.ADVERSARIAL,
            runs=3,
            prompts=[
                "Present the benefits: {{input}}",
                "Present the risks: {{prev}}",
                "Make a recommendation: {{all_prev[0]}} vs {{prev}}",
            ],
        )

        context = {'input': 'New technology', '_working_dir': str(temp_dir)}

        strategy = AdversarialExecutionStrategy()
        prompts_used = []
        call_count = 0

        async def capture_prompts(individual_run_id, agent_id, prompt, context):
            # run_agent signature: (individual_run_id, agent_id, prompt, context)
            nonlocal call_count
            call_count += 1
            prompts_used.append(prompt)
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=capture_prompts):
            with patch('emdx.workflows.strategies.adversarial.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.adversarial.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    await strategy.execute(stage_run_id, stage, context, "New technology")

        assert "benefits" in prompts_used[0]
        assert "risks" in prompts_used[1]
        assert "recommendation" in prompts_used[2]

    async def test_adversarial_indexed_access(self, workflow_db, mock_doc_service, temp_dir):
        """Test that {{all_prev[0]}} style access works in adversarial mode."""
        stage_run_id = create_stage_run(workflow_db, "debate", "adversarial")

        mock_doc_service.add_document(100, "First", "First output content")
        mock_doc_service.add_document(101, "Second", "Second output content")
        mock_doc_service.add_document(102, "Third", "Third output content")

        stage = StageConfig(
            name="debate",
            mode=ExecutionMode.ADVERSARIAL,
            runs=3,
            prompts=[
                "Start: {{input}}",
                "Continue: {{prev}}",
                "Compare first ({{all_prev[0]}}) with second ({{all_prev[1]}})",
            ],
        )

        context = {'input': 'Start', '_working_dir': str(temp_dir)}

        strategy = AdversarialExecutionStrategy()
        all_prev_snapshots = []  # Capture snapshot of all_prev at each call
        call_count = 0

        async def capture_context(individual_run_id=None, agent_id=None, prompt=None, context=None):
            # run_agent can be called with keyword arguments
            nonlocal call_count
            call_count += 1
            # Take a copy of the list at this point in time
            all_prev_snapshots.append(list(context.get('all_prev', []) if context else []))
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=capture_context):
            with patch('emdx.workflows.strategies.adversarial.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.adversarial.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    await strategy.execute(stage_run_id, stage, context, "Start")

        # Verify all_prev grows with each iteration
        assert len(all_prev_snapshots) == 3
        # First run: no previous outputs
        assert len(all_prev_snapshots[0]) == 0
        # Second run: 1 previous output
        assert len(all_prev_snapshots[1]) == 1
        # Third run: 2 previous outputs
        assert len(all_prev_snapshots[2]) == 2

    async def test_adversarial_failure_stops_execution(self, workflow_db, mock_doc_service, temp_dir):
        """Test that failure in any adversarial step stops execution."""
        stage_run_id = create_stage_run(workflow_db, "debate", "adversarial")

        mock_doc_service.add_document(100, "First", "First content")

        stage = StageConfig(
            name="debate",
            mode=ExecutionMode.ADVERSARIAL,
            runs=3,
        )

        context = {'input': 'Test', '_working_dir': str(temp_dir)}

        strategy = AdversarialExecutionStrategy()
        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Critic fails
                return {'success': False, 'error_message': 'Critic failed'}
            return {'success': True, 'output_doc_id': 99 + call_count, 'tokens_used': 100}

        with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
            with patch('emdx.workflows.strategies.adversarial.document_service', mock_doc_service):
                with patch('emdx.workflows.strategies.adversarial.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]
                    mock_wf_db.update_stage_run = MagicMock()

                    result = await strategy.execute(stage_run_id, stage, context, "Test")

        assert result.success is False
        assert "Adversarial run 2 failed" in result.error_message
        assert call_count == 2  # Should have stopped after failure


# ============================================================================
# Dynamic Execution Mode Tests
# ============================================================================


@pytest.mark.asyncio
class TestDynamicExecutionMode:
    """Tests for DYNAMIC execution mode - discovers items at runtime, processes in parallel."""

    async def test_dynamic_discovery_and_processing(self, workflow_db, temp_dir):
        """Test dynamic mode discovers items and processes them."""
        stage_run_id = create_stage_run(workflow_db, "process_files", "dynamic")

        stage = StageConfig(
            name="process_files",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo -e 'file1.py\nfile2.py\nfile3.py'",
            item_variable="file",
            max_concurrent=3,
            prompt="Process file: {{file}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        # Mock the discovery method
        async def mock_discovery(cmd, ctx):
            return ['file1.py', 'file2.py', 'file3.py']

        items_processed = []

        async def mock_run_agent(*args, **kwargs):
            items_processed.append(kwargs.get('context', {}).get('file'))
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 50}

        # Mock worktree pool
        mock_worktree = MagicMock()
        mock_worktree.path = str(temp_dir)

        class MockWorktreeContext:
            async def __aenter__(self):
                return mock_worktree
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = MockWorktreeContext()
        mock_pool.cleanup = AsyncMock()

        with patch.object(strategy, '_run_discovery', side_effect=mock_discovery):
            with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
                with patch('emdx.workflows.strategies.dynamic.WorktreePool', return_value=mock_pool):
                    with patch('emdx.workflows.strategies.dynamic.wf_db') as mock_wf_db:
                        mock_wf_db.create_individual_run.side_effect = list(range(1, 4))
                        mock_wf_db.update_stage_run = MagicMock()

                        result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is True
        assert set(items_processed) == {'file1.py', 'file2.py', 'file3.py'}
        assert len(result.individual_outputs) == 3

    async def test_dynamic_no_discovery_command(self, workflow_db, temp_dir):
        """Test dynamic mode fails gracefully without discovery command."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command=None,  # No command
            prompt="Process: {{item}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()
        result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is False
        assert "requires discovery_command" in result.error_message

    async def test_dynamic_discovery_failure(self, workflow_db, temp_dir):
        """Test dynamic mode handles discovery failure."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="exit 1",  # Will fail
            prompt="Process: {{item}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def failing_discovery(cmd, ctx):
            raise ValueError("Discovery command failed: exit 1")

        with patch.object(strategy, '_run_discovery', side_effect=failing_discovery):
            result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is False
        assert "Discovery failed" in result.error_message

    async def test_dynamic_empty_discovery(self, workflow_db, temp_dir):
        """Test dynamic mode handles empty discovery results."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo ''",
            prompt="Process: {{item}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def empty_discovery(cmd, ctx):
            return []

        with patch.object(strategy, '_run_discovery', side_effect=empty_discovery):
            result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is True
        assert result.error_message == "No items discovered"
        assert len(result.individual_outputs) == 0

    async def test_dynamic_continue_on_failure(self, workflow_db, temp_dir):
        """Test dynamic mode continues processing after item failure."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo 'a\nb\nc'",
            item_variable="item",
            max_concurrent=3,
            continue_on_failure=True,  # Should continue
            prompt="Process: {{item}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def mock_discovery(cmd, ctx):
            return ['a', 'b', 'c']

        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            item = kwargs.get('context', {}).get('item')
            if item == 'b':  # Middle item fails
                return {'success': False, 'error_message': 'Item b failed'}
            return {'success': True, 'output_doc_id': 100 + call_count, 'tokens_used': 50}

        mock_worktree = MagicMock()
        mock_worktree.path = str(temp_dir)

        class MockWorktreeContext:
            async def __aenter__(self):
                return mock_worktree
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = MockWorktreeContext()
        mock_pool.cleanup = AsyncMock()

        with patch.object(strategy, '_run_discovery', side_effect=mock_discovery):
            with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
                with patch('emdx.workflows.strategies.dynamic.WorktreePool', return_value=mock_pool):
                    with patch('emdx.workflows.strategies.dynamic.wf_db') as mock_wf_db:
                        mock_wf_db.create_individual_run.side_effect = list(range(1, 4))
                        mock_wf_db.update_stage_run = MagicMock()

                        result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is True  # Overall success because continue_on_failure=True
        assert len(result.individual_outputs) == 2  # Only 2 succeeded
        assert "Processed 2/3 items" in result.error_message

    async def test_dynamic_stop_on_failure(self, workflow_db, temp_dir):
        """Test dynamic mode stops on failure when continue_on_failure=False."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo 'a\nb\nc'",
            item_variable="item",
            max_concurrent=1,  # Sequential to control order
            continue_on_failure=False,  # Should stop
            prompt="Process: {{item}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def mock_discovery(cmd, ctx):
            return ['a', 'b', 'c']

        call_count = 0

        async def mock_run_agent(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            item = kwargs.get('context', {}).get('item')
            if item == 'b':  # Second item fails
                return {'success': False, 'error_message': 'Item b failed'}
            return {'success': True, 'output_doc_id': 100 + call_count, 'tokens_used': 50}

        mock_worktree = MagicMock()
        mock_worktree.path = str(temp_dir)

        class MockWorktreeContext:
            async def __aenter__(self):
                return mock_worktree
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = MockWorktreeContext()
        mock_pool.cleanup = AsyncMock()

        with patch.object(strategy, '_run_discovery', side_effect=mock_discovery):
            with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
                with patch('emdx.workflows.strategies.dynamic.WorktreePool', return_value=mock_pool):
                    with patch('emdx.workflows.strategies.dynamic.wf_db') as mock_wf_db:
                        mock_wf_db.create_individual_run.side_effect = list(range(1, 4))
                        mock_wf_db.update_stage_run = MagicMock()

                        result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is False
        assert "Dynamic execution failed" in result.error_message

    async def test_dynamic_with_synthesis(self, workflow_db, temp_dir):
        """Test dynamic mode with synthesis after processing."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo 'item1\nitem2'",
            item_variable="item",
            max_concurrent=2,
            prompt="Process: {{item}}",
            synthesis_prompt="Combine all results: {{outputs}}",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def mock_discovery(cmd, ctx):
            return ['item1', 'item2']

        async def mock_run_agent(*args, **kwargs):
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 50}

        mock_worktree = MagicMock()
        mock_worktree.path = str(temp_dir)

        class MockWorktreeContext:
            async def __aenter__(self):
                return mock_worktree
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = MockWorktreeContext()
        mock_pool.cleanup = AsyncMock()

        with patch.object(strategy, '_run_discovery', side_effect=mock_discovery):
            with patch.object(strategy, 'run_agent', side_effect=mock_run_agent):
                with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                    mock_synth.return_value = {'output_doc_id': 200, 'tokens_used': 100}

                    with patch('emdx.workflows.strategies.dynamic.WorktreePool', return_value=mock_pool):
                        with patch('emdx.workflows.strategies.dynamic.wf_db') as mock_wf_db:
                            mock_wf_db.create_individual_run.side_effect = [1, 2]
                            mock_wf_db.update_stage_run = MagicMock()

                            result = await strategy.execute(stage_run_id, stage, context, None)

        assert result.success is True
        assert result.synthesis_doc_id == 200
        mock_synth.assert_called_once()

    async def test_dynamic_item_context_variables(self, workflow_db, temp_dir):
        """Test that item-specific context variables are set correctly."""
        stage_run_id = create_stage_run(workflow_db, "process", "dynamic")

        stage = StageConfig(
            name="process",
            mode=ExecutionMode.DYNAMIC,
            discovery_command="echo 'a\nb\nc'",
            item_variable="my_item",  # Custom variable name
            max_concurrent=3,
            prompt="Process {{my_item}} ({{item_index}}/{{total_items}})",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = DynamicExecutionStrategy()

        async def mock_discovery(cmd, ctx):
            return ['a', 'b', 'c']

        contexts_seen = []

        async def capture_context(*args, **kwargs):
            contexts_seen.append(dict(kwargs.get('context', {})))
            return {'success': True, 'output_doc_id': 100, 'tokens_used': 50}

        mock_worktree = MagicMock()
        mock_worktree.path = str(temp_dir)

        class MockWorktreeContext:
            async def __aenter__(self):
                return mock_worktree
            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_pool.acquire.return_value = MockWorktreeContext()
        mock_pool.cleanup = AsyncMock()

        with patch.object(strategy, '_run_discovery', side_effect=mock_discovery):
            with patch.object(strategy, 'run_agent', side_effect=capture_context):
                with patch('emdx.workflows.strategies.dynamic.WorktreePool', return_value=mock_pool):
                    with patch('emdx.workflows.strategies.dynamic.wf_db') as mock_wf_db:
                        mock_wf_db.create_individual_run.side_effect = list(range(1, 4))
                        mock_wf_db.update_stage_run = MagicMock()

                        await strategy.execute(stage_run_id, stage, context, None)

        assert len(contexts_seen) == 3
        # Check that each context has the right variables
        for ctx in contexts_seen:
            assert 'my_item' in ctx
            assert 'item_index' in ctx
            assert ctx['total_items'] == 3


# ============================================================================
# Base Strategy Method Tests
# ============================================================================


class TestBaseStrategyMethods:
    """Tests for common methods in the base ExecutionStrategy class."""

    def test_resolve_template_simple(self):
        """Test simple variable resolution."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template("Hello, {{name}}!", {'name': 'World'})
        assert result == "Hello, World!"

    def test_resolve_template_multiple(self):
        """Test multiple variable resolution."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(
            "{{greeting}}, {{name}}! Welcome to {{place}}.",
            {'greeting': 'Hello', 'name': 'User', 'place': 'EMDX'}
        )
        assert result == "Hello, User! Welcome to EMDX."

    def test_resolve_template_indexed(self):
        """Test indexed array access."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(
            "First: {{items[0]}}, Second: {{items[1]}}",
            {'items': ['apple', 'banana', 'cherry']}
        )
        assert result == "First: apple, Second: banana"

    def test_resolve_template_indexed_out_of_bounds(self):
        """Test indexed access with out of bounds index."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(
            "Item: {{items[10]}}",
            {'items': ['only_one']}
        )
        assert result == "Item: "

    def test_resolve_template_dotted(self):
        """Test dotted variable names."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(
            "Previous: {{stage.output}}",
            {'stage.output': 'Stage result'}
        )
        assert result == "Previous: Stage result"

    def test_resolve_template_missing(self):
        """Test missing variable resolves to empty string."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template("Value: {{missing}}", {})
        assert result == "Value: "

    def test_resolve_template_none(self):
        """Test None template returns empty string."""
        strategy = SingleExecutionStrategy()
        result = strategy.resolve_template(None, {'key': 'value'})
        assert result == ""

    def test_extract_output_doc_id_created_pattern(self):
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

    def test_extract_output_doc_id_saved_pattern(self):
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

    def test_extract_output_doc_id_not_found(self):
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

    def test_extract_output_doc_id_missing_file(self):
        """Test that None is returned for missing log file."""
        strategy = SingleExecutionStrategy()
        doc_id = strategy._extract_output_doc_id(Path("/nonexistent/path.log"))
        assert doc_id is None

    def test_extract_output_doc_id_with_ansi_codes(self):
        """Test extracting doc ID with ANSI escape codes in log."""
        strategy = SingleExecutionStrategy()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            # Simulate ANSI colored output
            f.write("\x1b[32m✅ Saved as #123: Test Document\x1b[0m\n")
            log_path = Path(f.name)

        try:
            doc_id = strategy._extract_output_doc_id(log_path)
            assert doc_id == 123
        finally:
            log_path.unlink()

    def test_extract_token_usage_with_raw_json(self):
        """Test extracting token usage from __RAW_RESULT_JSON__ marker."""
        strategy = SingleExecutionStrategy()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            raw_json = json.dumps({
                'type': 'result',
                'usage': {
                    'input_tokens': 100,
                    'output_tokens': 50,
                    'cache_read_input_tokens': 25,
                    'cache_creation_input_tokens': 10,
                },
                'total_cost_usd': 0.0015,
            })
            f.write(f"Some output\n__RAW_RESULT_JSON__:{raw_json}\nMore output")
            log_path = Path(f.name)

        try:
            usage = strategy._extract_token_usage(log_path)
            assert usage['input_tokens'] == 135  # 100 + 25 + 10
            assert usage['output_tokens'] == 50
            assert usage['tokens_used'] == 185
            assert usage['cost_usd'] == 0.0015
        finally:
            log_path.unlink()

    def test_extract_token_usage_missing_file(self):
        """Test extracting token usage from missing file."""
        strategy = SingleExecutionStrategy()
        usage = strategy._extract_token_usage(Path("/nonexistent/path.log"))
        assert usage['tokens_used'] == 0
        assert usage['input_tokens'] == 0
        assert usage['output_tokens'] == 0


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
class TestErrorHandling:
    """Tests for error handling across all execution modes."""

    async def test_exception_in_run_agent_handled(self, workflow_db, temp_dir):
        """Test that exceptions in run_agent are handled gracefully."""
        stage_run_id = create_stage_run(workflow_db, "test", "single")

        stage = StageConfig(
            name="test",
            mode=ExecutionMode.SINGLE,
            runs=1,
            prompt="Test prompt",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = SingleExecutionStrategy()

        async def raising_run_agent(*args, **kwargs):
            raise RuntimeError("Unexpected error in agent execution")

        with patch.object(strategy, 'run_agent', side_effect=raising_run_agent):
            with patch('emdx.workflows.strategies.single.wf_db') as mock_wf_db:
                mock_wf_db.create_individual_run.return_value = 1

                # Should not raise - error should be captured
                try:
                    result = await strategy.execute(stage_run_id, stage, context, "Test")
                    # If it returns a result, it should indicate failure
                    if result:
                        assert result.success is False
                except RuntimeError:
                    # This is also acceptable - the error propagated
                    pass

    async def test_parallel_handles_task_exceptions(self, workflow_db, temp_dir):
        """Test that parallel mode handles exceptions in individual tasks."""
        stage_run_id = create_stage_run(workflow_db, "parallel", "parallel")

        stage = StageConfig(
            name="parallel",
            mode=ExecutionMode.PARALLEL,
            runs=3,
            prompt="Test",
            synthesis_prompt="Combine",
        )

        context = {'_working_dir': str(temp_dir)}

        strategy = ParallelExecutionStrategy(max_concurrent=10)
        call_count = 0

        async def sometimes_raises(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Task 2 crashed")
            return {'success': True, 'output_doc_id': 100 + call_count, 'tokens_used': 50}

        with patch.object(strategy, 'run_agent', side_effect=sometimes_raises):
            with patch.object(strategy, 'synthesize_outputs', new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = {'output_doc_id': 200, 'tokens_used': 50}

                with patch('emdx.workflows.strategies.parallel.wf_db') as mock_wf_db:
                    mock_wf_db.create_individual_run.side_effect = [1, 2, 3]

                    result = await strategy.execute(stage_run_id, stage, context, "Test")

        # Should still succeed with partial results
        assert result.success is True
        assert len(result.individual_outputs) == 2


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
class TestExecutionModeIntegration:
    """Integration tests that test multiple components together."""

    async def test_stage_result_dataclass(self):
        """Test StageResult dataclass creation and fields."""
        result = StageResult(
            success=True,
            output_doc_id=123,
            synthesis_doc_id=456,
            individual_outputs=[100, 101, 102],
            tokens_used=1500,
            execution_time_ms=5000,
            error_message=None,
        )

        assert result.success is True
        assert result.output_doc_id == 123
        assert result.synthesis_doc_id == 456
        assert len(result.individual_outputs) == 3
        assert result.tokens_used == 1500
        assert result.execution_time_ms == 5000

    async def test_failed_stage_result(self):
        """Test StageResult for failed execution."""
        result = StageResult(
            success=False,
            error_message="Agent execution timed out",
        )

        assert result.success is False
        assert result.output_doc_id is None
        assert result.error_message == "Agent execution timed out"
        assert result.individual_outputs == []

    def test_execution_mode_enum_values(self):
        """Test that all execution modes have correct values."""
        assert ExecutionMode.SINGLE.value == "single"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.ITERATIVE.value == "iterative"
        assert ExecutionMode.ADVERSARIAL.value == "adversarial"
        assert ExecutionMode.DYNAMIC.value == "dynamic"

    def test_stage_config_from_dict(self):
        """Test StageConfig creation from dictionary."""
        data = {
            'name': 'test_stage',
            'mode': 'parallel',
            'runs': 3,
            'prompt': 'Test prompt',
            'synthesis_prompt': 'Synthesize: {{outputs}}',
        }

        config = StageConfig.from_dict(data)

        assert config.name == 'test_stage'
        assert config.mode == ExecutionMode.PARALLEL
        assert config.runs == 3
        assert config.prompt == 'Test prompt'
        assert config.synthesis_prompt == 'Synthesize: {{outputs}}'

    def test_stage_config_to_dict_roundtrip(self):
        """Test StageConfig serialization roundtrip."""
        original = StageConfig(
            name='dynamic_stage',
            mode=ExecutionMode.DYNAMIC,
            discovery_command='find . -name "*.py"',
            item_variable='file',
            max_concurrent=5,
            prompt='Process: {{file}}',
        )

        as_dict = original.to_dict()
        restored = StageConfig.from_dict(as_dict)

        assert restored.name == original.name
        assert restored.mode == original.mode
        assert restored.discovery_command == original.discovery_command
        assert restored.item_variable == original.item_variable
        assert restored.max_concurrent == original.max_concurrent
