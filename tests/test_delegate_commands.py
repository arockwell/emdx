"""Comprehensive tests for delegate command (emdx/commands/delegate.py).

Tests cover:
- Basic delegate call with single task
- --synthesize flag for parallel task synthesis
- --each/--do flags for dynamic discovery
- --pr flag for pull request creation
- --worktree flag for git worktree isolation
- --doc flag for document context
- Error handling and edge cases
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

from emdx.commands.delegate import (
    PR_INSTRUCTION_GENERIC,
    SingleResult,
    _extract_pr_url,
    _load_doc_context,
    _make_branch_instruction,
    _make_output_file_id,
    _make_output_file_path,
    _make_pr_instruction,
    _resolve_task,
    _run_discovery,
    _run_parallel,
    _run_single,
    _save_output_fallback,
    delegate,
)
from emdx.services.unified_executor import ExecutionResult
from emdx.utils.git import generate_delegate_branch_name, slugify_for_branch

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
    with (
        patch("emdx.commands.delegate._safe_create_task") as mock_create,
        patch("emdx.commands.delegate._safe_update_task") as mock_update,
        patch("emdx.commands.delegate._safe_update_execution") as mock_update_exec,
    ):
        mock_create.return_value = 1
        yield mock_create, mock_update, mock_update_exec


@pytest.fixture
def mock_worktree():
    """Mock git worktree creation and cleanup."""
    with (
        patch("emdx.commands.delegate.create_worktree") as mock_create,
        patch("emdx.commands.delegate.cleanup_worktree") as mock_cleanup,
    ):
        mock_create.return_value = ("/tmp/worktree-123", "worktree-123")
        yield mock_create, mock_cleanup


# =============================================================================
# Tests for slugify_for_branch / generate_delegate_branch_name
# =============================================================================


class TestSlugifyForBranch:
    """Tests for slugify_for_branch — converts text to git branch slugs."""

    def test_simple_title(self):
        assert slugify_for_branch("Fix auth bug") == "fix-auth-bug"

    def test_strips_gameplan_prefix(self):
        assert slugify_for_branch("Gameplan #1: Contextual Save") == "contextual-save"

    def test_strips_feature_prefix(self):
        assert slugify_for_branch("Feature: Dark Mode Toggle") == "dark-mode-toggle"

    def test_strips_plan_prefix(self):
        assert slugify_for_branch("Plan #42: Refactor Database") == "refactor-database"

    def test_strips_doc_prefix(self):
        assert slugify_for_branch("Document: API Design") == "api-design"

    def test_removes_special_characters(self):
        assert slugify_for_branch("Smart Priming (context-aware)") == "smart-priming-context-aware"

    def test_collapses_whitespace(self):
        assert slugify_for_branch("fix   the   thing") == "fix-the-thing"

    def test_truncates_long_slugs(self):
        result = slugify_for_branch("A" * 100)
        assert len(result) <= 40

    def test_empty_after_strip_returns_task(self):
        assert slugify_for_branch("Gameplan #1:") == "task"

    def test_only_special_chars_returns_task(self):
        assert slugify_for_branch("!!!???") == "task"

    def test_no_trailing_hyphens(self):
        result = slugify_for_branch("test - ")
        assert not result.endswith("-")

    def test_strips_kink_prefix(self):
        assert slugify_for_branch("Kink 5: Unify branch naming") == "unify-branch-naming"


class TestGenerateDelegateBranchName:
    """Tests for generate_delegate_branch_name."""

    def test_follows_delegate_pattern(self):
        name = generate_delegate_branch_name("Fix auth bug")
        assert name.startswith("delegate/")
        assert "fix-auth-bug" in name

    def test_has_hash_suffix(self):
        name = generate_delegate_branch_name("some task")
        # Pattern: delegate/{slug}-{5-char-hash}
        parts = name.split("/", 1)[1]
        assert len(parts.split("-")[-1]) == 5

    def test_unique_for_same_title(self):
        """Two calls with the same title produce different names (timestamp in hash)."""
        import time

        name1 = generate_delegate_branch_name("same task")
        time.sleep(0.01)  # Ensure different timestamp
        name2 = generate_delegate_branch_name("same task")
        assert name1 != name2


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
        assert "delegate/" in result
        assert "add-dark-mode" in result

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

        result = _run_single(
            prompt="test task",
            tags=["test"],
            title="Test Title",
            model=None,
            quiet=False,
        )

        assert result.doc_id == 42
        assert result.task_id == 1
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

        result = _run_single(
            prompt="failing task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id is None
        assert result.task_id == 1
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
        assert (
            "pull request" in config.output_instruction.lower()
            or "gh pr create" in config.output_instruction
        )

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_single_task_with_pr_draft_true(
        self, mock_executor_cls, mock_create, mock_update, mock_print
    ):
        """Test that pr=True with draft=True includes --draft flag."""
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
            draft=True,
        )

        call_args = mock_executor.execute.call_args
        config = call_args[0][0]
        assert "--draft" in config.output_instruction

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_single_task_with_pr_draft_false(
        self, mock_executor_cls, mock_create, mock_update, mock_print
    ):
        """Test that pr=True with draft=False omits --draft flag."""
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
            draft=False,
        )

        call_args = mock_executor.execute.call_args
        config = call_args[0][0]
        assert "--draft" not in config.output_instruction
        assert "gh pr create" in config.output_instruction

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
    def test_parallel_tasks_success(self, mock_executor_cls, mock_create, mock_update, mock_print):
        mock_create.return_value = 1
        mock_executor = MagicMock()
        # Each call returns a different doc_id
        mock_executor.execute.side_effect = [
            ExecutionResult(
                success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10
            ),  # noqa: E501
            ExecutionResult(
                success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20
            ),  # noqa: E501
            ExecutionResult(
                success=True, execution_id=3, log_file=Path("/tmp/3.log"), output_doc_id=30
            ),  # noqa: E501
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
            ExecutionResult(
                success=True, execution_id=1, log_file=Path("/tmp/1.log"), output_doc_id=10
            ),  # noqa: E501
            ExecutionResult(
                success=True, execution_id=2, log_file=Path("/tmp/2.log"), output_doc_id=20
            ),  # noqa: E501
            ExecutionResult(
                success=True, execution_id=3, log_file=Path("/tmp/3.log"), output_doc_id=30
            ),  # noqa: E501
            ExecutionResult(
                success=True, execution_id=4, log_file=Path("/tmp/4.log"), output_doc_id=99
            ),  # synthesis  # noqa: E501
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
    def test_parallel_all_failures_exits(self, mock_executor_cls, mock_create, mock_update):
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
        self,
        mock_executor_cls,
        mock_create,
        mock_update,
        mock_print,
        mock_create_worktree,
        mock_cleanup_worktree,
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
# Tests for delegate command (CLI entry point)
# =============================================================================


class TestDelegateCommand:
    """Tests for the main delegate command entry point."""

    @patch("emdx.commands.delegate._run_single")
    def test_single_task_invocation(self, mock_run_single):
        """Test basic single task invocation."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        mock_run_parallel.assert_called_once()

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
                branch=False,
                worktree=False,
                base_branch="main",
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
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
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
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
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,
            worktree=True,
            base_branch="main",
            each=None,
            do=None,
        )

        mock_create_wt.assert_called_once_with("main", task_title="fix bug")
        mock_cleanup_wt.assert_called_once_with("/tmp/worktree")

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_pr_implies_worktree(self, mock_run_single, mock_create_wt, mock_cleanup_wt):
        """Test that --pr implicitly creates worktree."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,
            worktree=False,  # Not explicitly set, but should be implied
            base_branch="develop",
            each=None,
            do=None,
        )

        # Worktree should be created even though --worktree not set
        mock_create_wt.assert_called_once_with("develop", task_title="fix bug")
        # Worktree IS cleaned up after PR (branch already pushed to remote)
        mock_cleanup_wt.assert_called_once_with("/tmp/worktree")

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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        call_kwargs = mock_run_parallel.call_args[1]
        assert call_kwargs["synthesize"] is True

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_draft_flag_passed_to_run_single(
        self, mock_run_single, mock_create_wt, mock_cleanup_wt
    ):
        """Test that --draft flag is passed to _run_single."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=True,
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["draft"] is True

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_no_draft_flag_passed_to_run_single(
        self, mock_run_single, mock_create_wt, mock_cleanup_wt
    ):
        """Test that --no-draft flag is passed to _run_single as draft=False."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,  # --no-draft
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["draft"] is False

    @patch("emdx.commands.delegate._run_parallel")
    def test_draft_flag_passed_to_run_parallel(self, mock_run_parallel):
        """Test that --draft flag is passed to _run_parallel."""
        mock_run_parallel.return_value = [10, 20]
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["task1", "task2"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=True,
            branch=False,
            draft=False,  # --no-draft
            worktree=True,
            base_branch="main",
            each=None,
            do=None,
        )

        call_kwargs = mock_run_parallel.call_args[1]
        assert call_kwargs["draft"] is False

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
                draft=False,
                worktree=False,
                base_branch="main",
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
        mock_run_single.return_value = SingleResult(doc_id=100, task_id=1)
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
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
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
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
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["tags"] == ["analysis", "security", "bugfix"]


# =============================================================================
# Tests for PR instruction helpers
# =============================================================================


class TestPRInstruction:
    """Tests for PR instruction generation and URL extraction."""

    def test_generic_instruction_mentions_branch(self):
        assert "branch" in PR_INSTRUCTION_GENERIC.lower()

    def test_generic_instruction_mentions_pr_create(self):
        assert "gh pr create" in PR_INSTRUCTION_GENERIC

    def test_generic_instruction_mentions_commit(self):
        assert "commit" in PR_INSTRUCTION_GENERIC.lower()

    def test_generic_instruction_mentions_push(self):
        text = PR_INSTRUCTION_GENERIC.lower()
        assert "push" in text

    def test_generic_instruction_no_draft_by_default(self):
        """Test that PR_INSTRUCTION_GENERIC does not include --draft flag."""
        assert "--draft" not in PR_INSTRUCTION_GENERIC

    def test_make_pr_instruction_with_branch(self):
        result = _make_pr_instruction("fix/my-branch-1")
        assert "fix/my-branch-1" in result
        assert "gh pr create" in result
        assert "git push" in result

    def test_make_pr_instruction_without_branch(self):
        """Test that without branch uses generic instruction (no draft by default)."""
        result = _make_pr_instruction(None)
        # Without branch, draft defaults to False
        assert "--draft" not in result
        assert "gh pr create" in result

    def test_make_pr_instruction_with_draft_true(self):
        """Test that draft=True adds --draft flag."""
        result = _make_pr_instruction("fix/my-branch", draft=True)
        assert "--draft" in result
        assert "gh pr create --draft" in result

    def test_make_pr_instruction_with_draft_false(self):
        """Test that draft=False omits --draft flag."""
        result = _make_pr_instruction("fix/my-branch", draft=False)
        assert "--draft" not in result
        assert "gh pr create --title" in result

    def test_make_pr_instruction_no_branch_draft_true(self):
        """Test without branch with draft=True."""
        result = _make_pr_instruction(None, draft=True)
        assert "--draft" in result

    def test_make_pr_instruction_no_branch_draft_false(self):
        """Test without branch with draft=False."""
        result = _make_pr_instruction(None, draft=False)
        assert "--draft" not in result

    def test_extract_pr_url_found(self):
        text = "Created PR: https://github.com/user/repo/pull/123 done"
        assert _extract_pr_url(text) == "https://github.com/user/repo/pull/123"

    def test_extract_pr_url_not_found(self):
        assert _extract_pr_url("no url here") is None

    def test_extract_pr_url_none_input(self):
        assert _extract_pr_url(None) is None


# =============================================================================
# Tests for --branch flag and branch instruction
# =============================================================================


class TestBranchInstruction:
    """Tests for branch (push-only) instruction generation."""

    def test_make_branch_instruction_with_branch_name(self):
        result = _make_branch_instruction("feat/my-branch")
        assert "feat/my-branch" in result
        assert "git push" in result
        assert "gh pr create" not in result

    def test_make_branch_instruction_without_branch_name(self):
        result = _make_branch_instruction(None)
        assert "git push" in result
        assert "gh pr create" not in result
        assert "branch-name" in result or "branch name" in result.lower()

    def test_make_branch_instruction_no_pr(self):
        """Branch instruction must never mention PR creation."""
        for branch_name in [None, "feat/test"]:
            result = _make_branch_instruction(branch_name)
            assert "pull request" not in result.lower()
            assert "gh pr" not in result


class TestBranchFlag:
    """Tests for --branch flag in delegate command."""

    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_branch_implies_worktree(self, mock_run_single, mock_create_wt, mock_cleanup_wt):
        """Test that --branch implicitly creates worktree."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1, branch_name="feat/test")
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["add feature"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            branch=True,
            draft=False,
            worktree=False,
            base_branch="main",
            each=None,
            do=None,
        )

        # Worktree should be created
        mock_create_wt.assert_called_once_with("main", task_title="add feature")
        # Worktree should NOT be cleaned up when --branch is set
        mock_cleanup_wt.assert_not_called()

    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._run_single")
    def test_branch_with_base_branch(self, mock_run_single, mock_create_wt):
        """Test that --branch respects --base-branch / -b."""
        mock_create_wt.return_value = ("/tmp/worktree", "branch")
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1, branch_name="feat/test")
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["add feature"],
            tags=None,
            title=None,
            synthesize=False,
            jobs=None,
            model=None,
            quiet=False,
            doc=None,
            pr=False,
            branch=True,
            draft=False,
            worktree=False,
            base_branch="develop",
            each=None,
            do=None,
        )

        mock_create_wt.assert_called_once_with("develop", task_title="add feature")

    def test_branch_and_pr_mutually_exclusive(self):
        """Test that --branch and --pr cannot be used together."""
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
                pr=True,
                branch=True,
                draft=False,
                worktree=False,
                base_branch="main",
                each=None,
                do=None,
            )

    @patch("emdx.commands.delegate._run_single")
    def test_branch_passed_to_run_single(self, mock_run_single):
        """Test that branch=True is passed through to _run_single."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1, branch_name="feat/test")
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        # Need worktree mock since --branch implies worktree
        with patch("emdx.utils.git.create_worktree") as mock_wt:
            mock_wt.return_value = ("/tmp/wt", "br")
            delegate(
                ctx=ctx,
                tasks=["add feature"],
                tags=None,
                title=None,
                synthesize=False,
                jobs=None,
                model=None,
                quiet=False,
                doc=None,
                pr=False,
                branch=True,
                draft=False,
                worktree=False,
                base_branch="main",
                each=None,
                do=None,
            )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["branch"] is True
        assert call_kwargs["pr"] is False


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
                branch=False,
                worktree=True,
                base_branch="main",
                each=None,
                do=None,
            )

    @patch("emdx.commands.delegate._run_single")
    def test_single_task_failure_exits(self, mock_run_single):
        """Test that single task failure causes exit."""
        mock_run_single.return_value = SingleResult(task_id=1)  # doc_id is None = failure
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
                branch=False,
                worktree=False,
                base_branch="main",
                each=None,
                do=None,
            )


# =============================================================================
# Tests for output file helpers (kink 1 — file-based output fallback)
# =============================================================================


class TestOutputFileId:
    """Tests for _make_output_file_id — generates traceable IDs for output files."""

    def test_uses_worktree_basename(self):
        """When working_dir is a worktree path, extract its basename."""
        result = _make_output_file_id("/Users/alex/dev/worktrees/emdx-worktree-123-456-789", seq=1)
        assert result == "emdx-worktree-123-456-789"

    def test_falls_back_to_pid_seq_timestamp(self):
        """When working_dir is not a worktree path, use pid-seq-timestamp."""
        result = _make_output_file_id("/some/regular/path", seq=5)
        parts = result.split("-")
        assert len(parts) == 3
        # First part is PID (int), second is seq, third is timestamp
        assert parts[1] == "5"

    def test_none_working_dir(self):
        """When working_dir is None, use pid-seq-timestamp."""
        result = _make_output_file_id(None, seq=0)
        parts = result.split("-")
        assert len(parts) == 3
        assert parts[1] == "0"


class TestMakeOutputFilePath:
    """Tests for _make_output_file_path — builds /tmp path for output file."""

    def test_path_in_tmp(self):
        path = _make_output_file_path("emdx-worktree-123-456-789")
        assert str(path).startswith("/tmp/")
        assert "emdx-delegate-" in str(path)

    def test_md_extension(self):
        path = _make_output_file_path("test-id")
        assert str(path).endswith(".md")

    def test_contains_file_id(self):
        path = _make_output_file_path("my-unique-id")
        assert "my-unique-id" in str(path)


class TestSaveOutputFallback:
    """Tests for _save_output_fallback — three-tier fallback save."""

    @patch("emdx.commands.delegate.save_document")
    def test_prefers_file_over_content(self, mock_save, tmp_path):
        """File content takes priority over output_content."""
        output_file = tmp_path / "output.md"
        output_file.write_text("file content")
        mock_save.return_value = 42

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content="captured content",
            title="Test",
            tags=["test"],
        )

        assert doc_id == 42
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["content"] == "file content"

    @patch("emdx.commands.delegate.save_document")
    def test_falls_back_to_content(self, mock_save, tmp_path):
        """When file doesn't exist, falls back to output_content."""
        output_file = tmp_path / "nonexistent.md"
        mock_save.return_value = 43

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content="captured content",
            title="Test",
            tags=["test"],
        )

        assert doc_id == 43
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["content"] == "captured content"

    def test_returns_none_when_nothing_available(self, tmp_path):
        """When no file and no content, returns None without saving."""
        output_file = tmp_path / "nonexistent.md"

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content=None,
            title="Test",
            tags=["test"],
        )

        assert doc_id is None

    def test_returns_none_for_empty_content(self, tmp_path):
        """Whitespace-only content is treated as empty."""
        output_file = tmp_path / "nonexistent.md"

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content="   \n  ",
            title="Test",
            tags=["test"],
        )

        assert doc_id is None

    @patch("emdx.commands.delegate.save_document")
    def test_skips_empty_file(self, mock_save, tmp_path):
        """Empty file is skipped, falls back to content."""
        output_file = tmp_path / "empty.md"
        output_file.write_text("")
        mock_save.return_value = 44

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content="fallback content",
            title="Test",
            tags=["test"],
        )

        assert doc_id == 44
        call_kwargs = mock_save.call_args[1]
        assert call_kwargs["content"] == "fallback content"

    @patch("emdx.commands.delegate.save_document")
    def test_handles_save_failure(self, mock_save, tmp_path):
        """When save_document raises, returns None gracefully."""
        output_file = tmp_path / "output.md"
        output_file.write_text("good content")
        mock_save.side_effect = Exception("DB error")

        doc_id = _save_output_fallback(
            output_file=output_file,
            output_content=None,
            title="Test",
            tags=["test"],
        )

        assert doc_id is None


class TestRunSingleFallback:
    """Tests for _run_single fallback integration."""

    @patch("emdx.commands.delegate._save_output_fallback")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_fallback_called_when_no_doc_id(
        self, mock_executor_cls, mock_create, mock_update, mock_print, mock_fallback
    ):
        """When executor returns no doc_id, fallback is attempted."""
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=None,
            output_content="some captured output",
        )
        mock_executor_cls.return_value = mock_executor
        mock_fallback.return_value = 99

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        mock_fallback.assert_called_once()
        assert result.doc_id == 99

    @patch("emdx.commands.delegate._save_output_fallback")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_fallback_not_called_when_doc_id_present(
        self, mock_executor_cls, mock_create, mock_update, mock_print, mock_fallback
    ):
        """When executor returns a doc_id, fallback is NOT called."""
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
        )
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        mock_fallback.assert_not_called()
        assert result.doc_id == 42

    @patch("emdx.commands.delegate._save_output_fallback")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.UnifiedExecutor")
    def test_fallback_returns_none_still_fails(
        self, mock_executor_cls, mock_create, mock_update, mock_fallback
    ):
        """When fallback also returns None, doc_id stays None."""
        mock_create.return_value = 1
        mock_executor = MagicMock()
        mock_executor.execute.return_value = ExecutionResult(
            success=True,
            execution_id=100,
            log_file=Path("/tmp/test.log"),
            output_doc_id=None,
        )
        mock_executor_cls.return_value = mock_executor
        mock_fallback.return_value = None

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id is None


# =============================================================================
# Retry Flag Tests
# =============================================================================


class TestIsRetryableError:
    """Test retryable error classification."""

    def test_success_not_retryable(self) -> None:
        """Success results are not retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(success=True, execution_id=1, log_file=Path("/tmp/test.log"))
        assert is_retryable_error(result) is False

    def test_timeout_is_retryable(self) -> None:
        """Timeout errors are retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Timeout after 300 seconds",
        )
        assert is_retryable_error(result) is True

    def test_rate_limit_is_retryable(self) -> None:
        """Rate limit errors are retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Rate limit exceeded",
        )
        assert is_retryable_error(result) is True

    def test_429_is_retryable(self) -> None:
        """HTTP 429 errors are retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="HTTP 429 Too Many Requests",
        )
        assert is_retryable_error(result) is True

    def test_rate_limit_with_exit_code_1_is_retryable(self) -> None:
        """Exit code 1 with rate in error message is retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="API rate exceeded",
            exit_code=1,
        )
        assert is_retryable_error(result) is True

    def test_validation_error_not_retryable(self) -> None:
        """Validation errors are not retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Invalid prompt format",
        )
        assert is_retryable_error(result) is False

    def test_environment_error_not_retryable(self) -> None:
        """Environment errors are not retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Environment validation failed: claude not found",
        )
        assert is_retryable_error(result) is False

    def test_generic_error_not_retryable(self) -> None:
        """Generic unknown errors are not retryable."""
        from emdx.services.unified_executor import is_retryable_error

        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Something unexpected happened",
        )
        assert is_retryable_error(result) is False


class TestRetryBehavior:
    """Integration tests for retry behavior."""

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.time.sleep")
    def test_retry_on_timeout(
        self,
        mock_sleep: MagicMock,
        mock_update: MagicMock,
        mock_create: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Test that timeout triggers retry."""
        mock_create.return_value = 1

        # First call fails with timeout, second succeeds
        fail_result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Timeout after 300 seconds",
        )
        success_result = ExecutionResult(
            success=True,
            execution_id=2,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
            output_content="test output",
        )

        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [fail_result, success_result]
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test",
            tags=[],
            title="Test",
            model=None,
            quiet=True,
            max_retries=3,
        )

        assert result.success is True
        assert result.doc_id == 42
        assert mock_executor.execute.call_count == 2
        assert mock_sleep.call_count == 1  # One retry = one sleep

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    def test_no_retry_on_validation_error(
        self,
        mock_update: MagicMock,
        mock_create: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Test that validation errors don't trigger retry."""
        mock_create.return_value = 1

        fail_result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Invalid prompt",
        )

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fail_result
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test",
            tags=[],
            title="Test",
            model=None,
            quiet=True,
            max_retries=3,
        )

        assert result.success is False
        assert mock_executor.execute.call_count == 1  # No retries

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.time.sleep")
    def test_max_retries_exhausted(
        self,
        mock_sleep: MagicMock,
        mock_update: MagicMock,
        mock_create: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Test behavior when all retries fail."""
        mock_create.return_value = 1

        fail_result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Timeout after 300 seconds",
        )

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fail_result
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test",
            tags=[],
            title="Test",
            model=None,
            quiet=True,
            max_retries=2,
        )

        assert result.success is False
        # 1 initial + 2 retries = 3 calls
        assert mock_executor.execute.call_count == 3
        assert mock_sleep.call_count == 2  # 2 retries = 2 sleeps

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    def test_no_retry_when_max_retries_zero(
        self,
        mock_update: MagicMock,
        mock_create: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Test that max_retries=0 means no retries."""
        mock_create.return_value = 1

        fail_result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Timeout after 300 seconds",
        )

        mock_executor = MagicMock()
        mock_executor.execute.return_value = fail_result
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test",
            tags=[],
            title="Test",
            model=None,
            quiet=True,
            max_retries=0,
        )

        assert result.success is False
        assert mock_executor.execute.call_count == 1  # Just the initial attempt

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.time.sleep")
    def test_retry_on_rate_limit(
        self,
        mock_sleep: MagicMock,
        mock_update: MagicMock,
        mock_create: MagicMock,
        mock_executor_cls: MagicMock,
    ) -> None:
        """Test that rate limit triggers retry."""
        mock_create.return_value = 1

        # First two calls fail with rate limit, third succeeds
        rate_limit_result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="rate limit exceeded",
        )
        success_result = ExecutionResult(
            success=True,
            execution_id=3,
            log_file=Path("/tmp/test.log"),
            output_doc_id=42,
        )

        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            rate_limit_result,
            rate_limit_result,
            success_result,
        ]
        mock_executor_cls.return_value = mock_executor

        result = _run_single(
            prompt="test",
            tags=[],
            title="Test",
            model=None,
            quiet=True,
            max_retries=5,
        )

        assert result.success is True
        assert result.doc_id == 42
        assert mock_executor.execute.call_count == 3
        assert mock_sleep.call_count == 2


class TestBackoffTiming:
    """Test exponential backoff calculations."""

    def test_backoff_sequence(self) -> None:
        """Verify exponential backoff timing (without jitter)."""
        base_delay = 2.0
        max_delay = 60.0

        expected = [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]

        for attempt, expected_delay in enumerate(expected, start=1):
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            assert delay == expected_delay
