"""Comprehensive tests for delegate command (emdx/commands/delegate.py).

Tests cover:
- Basic delegate call with single task
- --synthesize flag for parallel task synthesis
- --chain flag for sequential task execution
- --each/--do flags for dynamic discovery
- --pr flag for pull request creation
- --worktree flag for git worktree isolation
- --doc flag for document context
- Error handling and edge cases
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import typer

from emdx.commands.delegate import (
    PR_INSTRUCTION,
    _load_doc_context,
    _resolve_task,
    _run_chain,
    _run_discovery,
    _run_parallel,
    _run_single,
    _slugify_title,
    delegate,
)
from emdx.services.unified_executor import ExecutionConfig, ExecutionResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_executor_success():
    """Create a mock UnifiedExecutor that returns success."""
    with patch("emdx.commands.delegate.UnifiedExecutor") as mock_cls:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
            output_content="Test output content",
            tokens_used=1000,
            cost_usd=0.05,
            execution_time_ms=5000,
        )
        mock_cls.return_value = mock_executor
        yield mock_executor


@pytest.fixture
def mock_executor_failure():
    """Create a mock UnifiedExecutor that returns failure."""
    with patch("emdx.commands.delegate.UnifiedExecutor") as mock_cls:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Task execution failed",
        )
        mock_cls.return_value = mock_executor
        yield mock_executor


@pytest.fixture
def mock_get_document():
    """Mock get_document to return test documents."""
    with patch("emdx.commands.delegate.get_document") as mock_get:
        mock_get.return_value = {
            "id": 42,
            "title": "Test Document",
            "content": "This is test document content.",
        }
        yield mock_get


@pytest.fixture
def mock_task_helpers():
    """Mock task creation and update helpers."""
    with patch("emdx.commands.delegate._safe_create_task") as mock_create, \
         patch("emdx.commands.delegate._safe_update_task") as mock_update, \
         patch("emdx.commands.delegate._safe_update_execution") as mock_update_exec:
        mock_create.return_value = 1
        yield mock_create, mock_update, mock_update_exec


@pytest.fixture
def mock_worktree():
    """Mock git worktree creation and cleanup."""
    with patch("emdx.commands.delegate.create_worktree") as mock_create, \
         patch("emdx.commands.delegate.cleanup_worktree") as mock_cleanup:
        mock_create.return_value = ("/tmp/worktree-123", "worktree-123")
        yield mock_create, mock_cleanup


# =============================================================================
# Tests for _slugify_title
# =============================================================================


class TestSlugifyTitle:
    """Tests for _slugify_title — converts document titles to git branch slugs."""

    def test_simple_title(self):
        assert _slugify_title("Fix auth bug") == "fix-auth-bug"

    def test_strips_gameplan_prefix(self):
        assert _slugify_title("Gameplan #1: Contextual Save") == "contextual-save"

    def test_strips_feature_prefix(self):
        assert _slugify_title("Feature: Dark Mode Toggle") == "dark-mode-toggle"

    def test_strips_plan_prefix(self):
        assert _slugify_title("Plan #42: Refactor Database") == "refactor-database"

    def test_strips_doc_prefix(self):
        assert _slugify_title("Document: API Design") == "api-design"

    def test_removes_special_characters(self):
        assert _slugify_title("Smart Priming (context-aware)") == "smart-priming-context-aware"

    def test_collapses_whitespace(self):
        assert _slugify_title("fix   the   thing") == "fix-the-thing"

    def test_truncates_long_slugs(self):
        result = _slugify_title("A" * 100)
        assert len(result) <= 50

    def test_empty_after_strip_returns_feature(self):
        assert _slugify_title("Gameplan #1:") == "feature"

    def test_only_special_chars_returns_feature(self):
        assert _slugify_title("!!!???") == "feature"

    def test_no_trailing_hyphens(self):
        result = _slugify_title("test - ")
        assert not result.endswith("-")


# =============================================================================
# Tests for _resolve_task
# =============================================================================


class TestResolveTask:
    """Tests for _resolve_task — resolves doc IDs to content."""

    @patch("emdx.commands.delegate.get_document")
    def test_numeric_id_loads_doc(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Hello world",
        }
        result = _resolve_task("42")
        assert "Hello world" in result
        assert "Test Doc" in result
        mock_get.assert_called_once_with(42)

    @patch("emdx.commands.delegate.get_document")
    def test_numeric_id_with_pr_adds_instructions(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Fix Auth",
            "content": "Fix the authentication bug",
        }
        result = _resolve_task("42", pr=True)
        assert "Fix the authentication bug" in result
        assert "pull request" in result.lower() or "PR" in result
        assert "gh pr create" in result

    @patch("emdx.commands.delegate.get_document")
    def test_numeric_id_with_pr_creates_branch_name(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Gameplan #5: Add Dark Mode",
            "content": "Implement dark mode",
        }
        result = _resolve_task("42", pr=True)
        assert "feat/add-dark-mode" in result

    def test_text_task_returned_as_is(self):
        result = _resolve_task("analyze the auth module")
        assert result == "analyze the auth module"

    @patch("emdx.commands.delegate.get_document")
    def test_missing_doc_falls_back(self, mock_get):
        mock_get.return_value = None
        result = _resolve_task("99999")
        # Should return the string as-is when doc not found
        assert "99999" in result


# =============================================================================
# Tests for _load_doc_context
# =============================================================================


class TestLoadDocContext:
    """Tests for _load_doc_context — loads document and combines with prompt."""

    @patch("emdx.commands.delegate.get_document")
    def test_loads_doc_with_prompt(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Document content here",
        }
        result = _load_doc_context(42, "implement this")
        assert "Document #42" in result
        assert "Test Doc" in result
        assert "Document content here" in result
        assert "implement this" in result
        assert "Task:" in result

    @patch("emdx.commands.delegate.get_document")
    def test_loads_doc_without_prompt(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Document content here",
        }
        result = _load_doc_context(42, None)
        assert "Test Doc" in result
        assert "Document content here" in result
        assert "Execute the following document" in result

    @patch("emdx.commands.delegate.get_document")
    def test_missing_doc_raises_exit(self, mock_get):
        mock_get.return_value = None
        with pytest.raises(typer.Exit):
            _load_doc_context(99999, "prompt")


# =============================================================================
# Tests for _run_discovery
# =============================================================================


class TestRunDiscovery:
    """Tests for _run_discovery — runs shell command to discover items."""

    @patch("subprocess.run")
    def test_successful_discovery(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\nfile2.py\nfile3.py\n",
            stderr="",
        )
        result = _run_discovery("find . -name '*.py'")
        assert result == ["file1.py", "file2.py", "file3.py"]
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_strips_whitespace(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  file1.py  \n  file2.py  \n",
            stderr="",
        )
        result = _run_discovery("ls")
        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_skips_empty_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\n\n\nfile2.py\n\n",
            stderr="",
        )
        result = _run_discovery("ls")
        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_failed_command_exits(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="command not found",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("invalid_command")

    @patch("subprocess.run")
    def test_empty_output_exits(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("ls empty_dir")

    @patch("subprocess.run")
    def test_timeout_exits(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow_cmd", timeout=30)
        with pytest.raises(typer.Exit):
            _run_discovery("slow_cmd")


# =============================================================================
# Tests for _run_single
# =============================================================================


class TestRunSingle:
    """Tests for _run_single — runs a single task via UnifiedExecutor."""

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_successful_single_task(
        self, mock_executor_cls, mock_create, mock_update, mock_update_exec, mock_print
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
            tokens_used=1000,
            cost_usd=0.05,
            execution_time_ms=5000,
        )
        mock_executor_cls.return_value = mock_executor

        doc_id, task_id = _run_single(
            prompt="test task",
            tags=["test"],
            title="Test Title",
            model=None,
            quiet=False,
        )

        assert doc_id == 42
        assert task_id == 1
        mock_create.assert_called_once()
        mock_update.assert_called()
        mock_print.assert_called_once_with(42)

    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_failed_single_task(self, mock_executor_cls, mock_create, mock_update):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=False,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            error_message="Task failed",
        )
        mock_executor_cls.return_value = mock_executor

        doc_id, task_id = _run_single(
            prompt="failing task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert doc_id is None
        assert task_id == 1
        # Check task was updated with failed status
        mock_update.assert_called()
        calls = mock_update.call_args_list
        assert any("failed" in str(c) for c in calls)

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_single_task_with_pr_flag(
        self, mock_executor_cls, mock_create, mock_update, mock_print
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
        )
        mock_executor_cls.return_value = mock_executor

        _run_single(
            prompt="fix bug",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            pr=True,
        )

        # Verify PR instruction was included in the config
        call_args = mock_executor.execute.call_args
        config = call_args[0][0]
        assert PR_INSTRUCTION in config.output_instruction

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_single_task_with_working_dir(
        self, mock_executor_cls, mock_create, mock_update, mock_print
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
        )
        mock_executor_cls.return_value = mock_executor

        _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            working_dir="/custom/path",
        )

        # Verify working_dir was passed to ExecutionConfig
        call_args = mock_executor.execute.call_args
        config = call_args[0][0]
        assert config.working_dir == "/custom/path"


# =============================================================================
# Tests for _run_parallel
# =============================================================================


class TestRunParallel:
    """Tests for _run_parallel — runs multiple tasks in parallel."""

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_parallel_tasks_success(
        self, mock_executor_cls, mock_create, mock_update, mock_print
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        # Each call returns a different doc_id
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20),
            ExecutionResult(success=True, execution_id=3, log_file=Path("/tmp/3.log"), output_doc_id=30),
        ]
        mock_executor_cls.return_value = mock_executor

        doc_ids = _run_parallel(
            tasks=["task1", "task2", "task3"],
            tags=["test"],
            title=None,
            jobs=3,
            synthesize=False,
            model=None,
            quiet=True,
        )

        assert len(doc_ids) == 3
        assert set(doc_ids) == {10, 20, 30}

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_parallel_with_synthesize(
        self, mock_executor_cls, mock_create, mock_update, mock_print, mock_get_doc
    ):
        mock_create.return_value = 1
        mock_get_doc.return_value = {"id": 10, "title": "Test", "content": "Content"}
        mock_executor = MagicMock()
        # 3 tasks + 1 synthesis
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20),
            ExecutionResult(success=True, execution_id=3, log_file=Path("/tmp/3.log"), output_doc_id=30),
            ExecutionResult(success=True, execution_id=4, log_file=Path("/tmp/4.log"), output_doc_id=99),  # synthesis
        ]
        mock_executor_cls.return_value = mock_executor

        doc_ids = _run_parallel(
            tasks=["task1", "task2", "task3"],
            tags=[],
            title=None,
            jobs=3,
            synthesize=True,
            model=None,
            quiet=True,
        )

        # Should include synthesis doc
        assert 99 in doc_ids
        assert len(doc_ids) == 4

    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_parallel_all_failures_exits(
        self, mock_executor_cls, mock_create, mock_update
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=False, execution_id=1, log_file=Path("/tmp/1.log"), error_message="Failed"
        )
        mock_executor_cls.return_value = mock_executor

        with pytest.raises(typer.Exit):
            _run_parallel(
                tasks=["task1", "task2"],
                tags=[],
                title=None,
                jobs=2,
                synthesize=False,
                model=None,
                quiet=True,
            )

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_parallel_with_worktree(
        self, mock_executor_cls, mock_create, mock_update, mock_print,
        mock_create_worktree, mock_cleanup_worktree
    ):
        mock_create.return_value = 1
        mock_create_worktree.return_value = ("/tmp/wt", "branch")
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10
        )
        mock_executor_cls.return_value = mock_executor

        _run_parallel(
            tasks=["task1", "task2"],
            tags=[],
            title=None,
            jobs=2,
            synthesize=False,
            model=None,
            quiet=True,
            worktree=True,
        )

        # Worktree should be created for each task
        assert mock_create_worktree.call_count == 2
        # Worktrees should be cleaned up (not pr mode)
        assert mock_cleanup_worktree.call_count == 2


# =============================================================================
# Tests for _run_chain
# =============================================================================


class TestRunChain:
    """Tests for _run_chain — runs tasks sequentially with output piping."""

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_chain_success(
        self, mock_executor_cls, mock_create, mock_update, mock_get_doc
    ):
        mock_create.return_value = 1
        mock_get_doc.return_value = {"id": 10, "title": "Step", "content": "Step output"}
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20),
            ExecutionResult(success=True, execution_id=3, log_file=Path("/tmp/3.log"), output_doc_id=30),
        ]
        mock_executor_cls.return_value = mock_executor

        doc_ids = _run_chain(
            tasks=["analyze", "plan", "implement"],
            tags=["chain-test"],
            title="Test Chain",
            model=None,
            quiet=True,
        )

        assert len(doc_ids) == 3
        assert doc_ids == [10, 20, 30]

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_chain_pipes_output(
        self, mock_executor_cls, mock_create, mock_update, mock_get_doc
    ):
        """Verify that output from one step is passed to the next."""
        mock_create.return_value = 1
        mock_get_doc.return_value = {"id": 10, "title": "Step", "content": "Previous step output content"}
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20),
        ]
        mock_executor_cls.return_value = mock_executor

        _run_chain(
            tasks=["step1", "step2"],
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        # Second call should include "Previous step output" from first step
        calls = mock_executor.execute.call_args_list
        second_config = calls[1][0][0]
        assert "Previous step output" in second_config.prompt

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_chain_aborts_on_failure(
        self, mock_executor_cls, mock_create, mock_update, mock_get_doc
    ):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=False, execution_id=2, log_file=Path("/tmp/2.log"), error_message="Failed"),
        ]
        mock_executor_cls.return_value = mock_executor
        mock_get_doc.return_value = {"id": 10, "title": "Step", "content": "Step output"}

        doc_ids = _run_chain(
            tasks=["step1", "step2", "step3"],
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        # Should only have first successful step
        assert len(doc_ids) == 1
        assert doc_ids == [10]

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_chain_with_pr_only_last_step(
        self, mock_executor_cls, mock_create, mock_update, mock_get_doc
    ):
        """Verify --pr only applies to the last step."""
        mock_create.return_value = 1
        mock_get_doc.return_value = {"id": 10, "title": "Step", "content": "Content"}
        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10),
            ExecutionResult(success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20),
        ]
        mock_executor_cls.return_value = mock_executor

        _run_chain(
            tasks=["step1", "step2"],
            tags=[],
            title=None,
            model=None,
            quiet=True,
            pr=True,
        )

        calls = mock_executor.execute.call_args_list
        # First step should NOT have PR instruction
        first_config = calls[0][0][0]
        assert PR_INSTRUCTION not in (first_config.output_instruction or "")
        # Last step SHOULD have PR instruction
        last_config = calls[1][0][0]
        assert PR_INSTRUCTION in last_config.output_instruction


# =============================================================================
# Tests for delegate command (CLI entry point)
# =============================================================================


class TestDelegateCommand:
    """Tests for the main delegate command entry point."""

    @patch("emdx.commands.delegate._run_single")
    def test_single_task_invocation(self, mock_run_single):
        """Test basic single task invocation."""
        mock_run_single.return_value = (42, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze the code"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        mock_run_single.assert_called_once()
        call_kwargs = mock_run_single.call_args
        assert "analyze the code" in call_kwargs[1]["prompt"]

    @patch("emdx.commands.delegate._run_parallel")
    def test_multiple_tasks_go_parallel(self, mock_run_parallel):
        """Test that multiple tasks trigger parallel execution."""
        mock_run_parallel.return_value = [10, 20, 30]
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["task1", "task2", "task3"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        mock_run_parallel.assert_called_once()

    @patch("emdx.commands.delegate._run_chain")
    def test_chain_flag_triggers_chain(self, mock_run_chain):
        """Test that --chain flag triggers sequential execution."""
        mock_run_chain.return_value = [10, 20]
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["step1", "step2"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=True,
            each=None,
            do=None,
        )

        mock_run_chain.assert_called_once()

    def test_chain_and_synthesize_mutually_exclusive(self):
        """Test that --chain and --synthesize cannot be used together."""
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        with pytest.raises(typer.Exit):
            delegate(
                ctx=ctx,
                tasks=["task1", "task2"],
                tags=None,
                title=None,
                synthesize=True,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                worktree=False,
                base_branch="main",
                chain=True,
                each=None,
                do=None,
            )

    def test_each_requires_do(self):
        """Test that --each requires --do to be specified."""
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        with pytest.raises(typer.Exit):
            delegate(
                ctx=ctx,
                tasks=None,
                tags=None,
                title=None,
                synthesize=False,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                worktree=False,
                base_branch="main",
                chain=False,
                each="find . -name '*.py'",
                do=None,
            )

    @patch("emdx.commands.delegate._run_discovery")
    @patch("emdx.commands.delegate._run_parallel")
    def test_each_do_discovers_and_runs(self, mock_run_parallel, mock_run_discovery):
        """Test that --each/--do discovers items and creates tasks."""
        mock_run_discovery.return_value = ["file1.py", "file2.py"]
        mock_run_parallel.return_value = [10, 20]
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=None,
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each="find . -name '*.py'",
            do="Review {{item}} for issues",
        )

        mock_run_discovery.assert_called_once_with("find . -name '*.py'")
        # Should create tasks from discovered items
        call_args = mock_run_parallel.call_args
        tasks = call_args[1]["tasks"]
        assert "Review file1.py for issues" in tasks
        assert "Review file2.py for issues" in tasks

    @patch("emdx.commands.delegate._load_doc_context")
    @patch("emdx.commands.delegate._run_single")
    def test_doc_flag_loads_context(self, mock_run_single, mock_load_doc):
        """Test that --doc flag loads document context."""
        mock_load_doc.return_value = "Document context with task"
        mock_run_single.return_value = (42, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["implement this"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=42,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        mock_load_doc.assert_called_once_with(42, "implement this")

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_worktree_flag_creates_worktree(self, mock_run_single, mock_create_wt, mock_cleanup_wt):
        """Test that --worktree flag creates and cleans up worktree."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = (42, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["fix bug"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=True,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        mock_create_wt.assert_called_once_with("main")
        mock_cleanup_wt.assert_called_once_with("/tmp/worktree")

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_pr_implies_worktree(self, mock_run_single, mock_create_wt, mock_cleanup_wt):
        """Test that --pr implicitly creates worktree."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = (42, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["fix bug"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=True,
            worktree=False,  # Not explicitly set, but should be implied
            base_branch="develop",
            chain=False,
            each=None,
            do=None,
        )

        # Worktree should be created even though --worktree not set
        mock_create_wt.assert_called_once_with("develop")
        # Worktree should NOT be cleaned up when --pr is set
        mock_cleanup_wt.assert_not_called()

    @patch("emdx.commands.delegate._run_parallel")
    def test_synthesize_flag_passed_to_parallel(self, mock_run_parallel):
        """Test that --synthesize flag is passed to parallel execution."""
        mock_run_parallel.return_value = [10, 20, 99]
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["task1", "task2"],
            tags=None,
            title=None,
            synthesize=True,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        call_kwargs = mock_run_parallel.call_args[1]
        assert call_kwargs["synthesize"] is True

    def test_no_tasks_exits(self):
        """Test that command exits when no tasks provided."""
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        with pytest.raises(typer.Exit):
            delegate(
                ctx=ctx,
                tasks=None,
                tags=None,
                title=None,
                synthesize=False,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                worktree=False,
                base_branch="main",
                chain=False,
                each=None,
                do=None,
            )

    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_numeric_task_resolved_as_doc_id(self, mock_run_single, mock_get_doc):
        """Test that numeric task arguments are resolved as doc IDs."""
        mock_get_doc.return_value = {
            "id": 42,
            "title": "My Gameplan",
            "content": "Plan content here",
        }
        mock_run_single.return_value = (100, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["42"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        mock_get_doc.assert_called_once_with(42)
        # Prompt should contain doc content
        call_args = mock_run_single.call_args[1]
        assert "Plan content here" in call_args["prompt"]

    @patch("emdx.commands.delegate._run_single")
    def test_tags_flattened(self, mock_run_single):
        """Test that comma-separated tags are properly flattened."""
        mock_run_single.return_value = (42, 1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["task"],
            tags=["analysis,security", "bugfix"],
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            worktree=False,
            base_branch="main",
            chain=False,
            each=None,
            do=None,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["tags"] == ["analysis", "security", "bugfix"]


# =============================================================================
# Tests for PR_INSTRUCTION constant
# =============================================================================


class TestPRInstruction:
    """Tests for PR instruction constant."""

    def test_pr_instruction_mentions_branch(self):
        assert "branch" in PR_INSTRUCTION.lower()

    def test_pr_instruction_mentions_pr_create(self):
        assert "gh pr create" in PR_INSTRUCTION

    def test_pr_instruction_mentions_commit(self):
        assert "commit" in PR_INSTRUCTION.lower()

    def test_pr_instruction_mentions_push(self):
        assert "push" in PR_INSTRUCTION.lower() or "Push" in PR_INSTRUCTION


# =============================================================================
# Tests for error handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in delegate command."""

    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_worktree_creation_failure(self, mock_run_single, mock_create_wt):
        """Test handling of worktree creation failure."""
        mock_create_wt.side_effect = Exception("Git error")
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        with pytest.raises(typer.Exit):
            delegate(
                ctx=ctx,
                tasks=["task"],
                tags=None,
                title=None,
                synthesize=False,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                worktree=True,
                base_branch="main",
                chain=False,
                each=None,
                do=None,
            )

    @patch("emdx.commands.delegate._run_single")
    def test_single_task_failure_exits(self, mock_run_single):
        """Test that single task failure causes exit."""
        mock_run_single.return_value = (None, 1)  # doc_id is None = failure
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        with pytest.raises(typer.Exit):
            delegate(
                ctx=ctx,
                tasks=["failing task"],
                tags=None,
                title=None,
                synthesize=False,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                worktree=False,
                base_branch="main",
                chain=False,
                each=None,
                do=None,
            )
