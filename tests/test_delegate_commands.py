"""Comprehensive tests for delegate command (emdx/commands/delegate.py).

Tests cover:
- Basic delegate call with single task
- --synthesize flag for parallel task synthesis
- --pr flag for pull request creation
- --worktree flag for git worktree isolation
- --doc flag for document context
- Error handling and edge cases
- --retry flag for transient failure retry with exponential backoff
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
import typer

from emdx.commands.delegate import (
    PR_INSTRUCTION_GENERIC,
    RETRY_BACKOFF_BASE,
    RETRY_BACKOFF_MAX,
    SingleResult,
    _compute_backoff,
    _extract_pr_url,
    _is_retryable_failure,
    _load_doc_context,
    _make_branch_instruction,
    _make_pr_instruction,
    _resolve_task,
    _run_parallel,
    _run_single,
    delegate,
)
from emdx.utils.git import generate_delegate_branch_name, slugify_for_branch

# =============================================================================
# Fixtures
# =============================================================================


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
    """Mock task creation, update, and execution helpers."""
    with (
        patch("emdx.commands.delegate._safe_create_task") as mock_create,
        patch("emdx.commands.delegate._safe_update_task") as mock_update,
        patch("emdx.commands.delegate._safe_create_execution") as mock_create_exec,
        patch("emdx.commands.delegate._safe_update_execution_status") as mock_update_exec,
    ):
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        yield mock_create, mock_update, mock_create_exec, mock_update_exec


@pytest.fixture
def mock_worktree():
    """Mock git worktree creation and cleanup."""
    with (
        patch("emdx.commands.delegate.create_worktree") as mock_create,
        patch("emdx.commands.delegate.cleanup_worktree") as mock_cleanup,
    ):
        mock_create.return_value = ("/tmp/worktree-123", "worktree-123")
        yield mock_create, mock_cleanup


def _mock_subprocess_success(doc_id: int = 42) -> MagicMock:
    """Create a mock subprocess.run result for a successful delegate."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = f"Task completed. Output saved as doc #{doc_id}."
    mock_result.stderr = ""
    return mock_result


def _mock_subprocess_failure(error: str = "Task failed") -> MagicMock:
    """Create a mock subprocess.run result for a failed delegate."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = error
    return mock_result


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
# Tests for _run_single
# =============================================================================


class TestRunSingle:
    """Tests for _run_single — runs a single task via subprocess + hooks."""

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_successful_single_task(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)
        mock_read_batch.return_value = 42

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

    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_failed_single_task(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
    ):
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_failure("Task failed")
        mock_read_batch.return_value = None

        result = _run_single(
            prompt="failing task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id is None
        assert result.task_id == 1
        assert not result.success
        # Check task was updated with failed status
        mock_update.assert_called()
        calls = mock_update.call_args_list
        assert any("failed" in str(c) for c in calls)

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_flag(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = 42

        _run_single(
            prompt="fix bug",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            pr=True,
        )

        # Verify PR instruction was included in the prompt piped to subprocess
        call_args = mock_subprocess.run.call_args
        prompt_input = call_args[1]["input"]
        assert "pull request" in prompt_input.lower() or "gh pr create" in prompt_input

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_draft_true(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        """Test that pr=True with draft=True includes --draft flag in prompt."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = 42

        _run_single(
            prompt="fix bug",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            pr=True,
            draft=True,
        )

        call_args = mock_subprocess.run.call_args
        prompt_input = call_args[1]["input"]
        assert "--draft" in prompt_input

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_draft_false(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        """Test that pr=True with draft=False omits --draft flag."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = 42

        _run_single(
            prompt="fix bug",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            pr=True,
            draft=False,
        )

        call_args = mock_subprocess.run.call_args
        prompt_input = call_args[1]["input"]
        assert "--draft" not in prompt_input
        assert "gh pr create" in prompt_input

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_working_dir(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = 42

        _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            working_dir="/custom/path",
        )

        # Verify working_dir was passed to subprocess.run
        call_args = mock_subprocess.run.call_args
        assert call_args[1]["cwd"] == "/custom/path"


# =============================================================================
# Tests for _run_parallel
# =============================================================================


class TestRunParallel:
    """Tests for _run_parallel — runs multiple tasks in parallel."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_tasks_success(self, mock_create, mock_update, mock_print, mock_run_single):
        mock_create.return_value = 1
        mock_run_single.side_effect = [
            SingleResult(doc_id=10, task_id=1),
            SingleResult(doc_id=20, task_id=2),
            SingleResult(doc_id=30, task_id=3),
        ]

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

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_with_synthesize(
        self, mock_create, mock_update, mock_print, mock_get_doc, mock_run_single
    ):
        mock_create.return_value = 1
        mock_get_doc.return_value = {"id": 10, "title": "Test", "content": "Content"}
        # 3 tasks + 1 synthesis
        mock_run_single.side_effect = [
            SingleResult(doc_id=10, task_id=1),
            SingleResult(doc_id=20, task_id=2),
            SingleResult(doc_id=30, task_id=3),
            SingleResult(doc_id=99, task_id=4),  # synthesis
        ]

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

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_all_failures_exits(self, mock_create, mock_update, mock_run_single):
        mock_create.return_value = 1
        mock_run_single.return_value = SingleResult(
            task_id=1, success=False, error_message="Failed"
        )

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

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.utils.git.cleanup_worktree")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_with_worktree(
        self,
        mock_create,
        mock_update,
        mock_print,
        mock_create_worktree,
        mock_cleanup_worktree,
        mock_run_single,
    ):
        mock_create.return_value = 1
        mock_create_worktree.return_value = ("/tmp/wt", "branch")
        mock_run_single.return_value = SingleResult(doc_id=10, task_id=1)

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
        )

        mock_run_parallel.assert_called_once()

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
            )


# =============================================================================
# Tests for hooks integration (batch file doc ID collection)
# =============================================================================


class TestRunSingleHooksIntegration:
    """Tests for _run_single hooks integration (batch file doc ID)."""

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_doc_id_from_batch_file(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        """When hook writes doc ID to batch file, _run_single picks it up."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = 99

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id == 99

    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_no_doc_id_when_hook_didnt_save(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
    ):
        """When hook doesn't write to batch file, doc_id is None."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_subprocess.run.return_value = _mock_subprocess_success()
        mock_read_batch.return_value = None

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id is None


# =============================================================================
# Tests for retry logic
# =============================================================================


class TestIsRetryableFailure:
    """Tests for _is_retryable_failure — determines if a failure is retryable."""

    def test_timeout_pattern_in_stderr_is_retryable(self):
        assert _is_retryable_failure(1, "request timed out") is True

    def test_rate_limit_stderr_is_retryable(self):
        assert _is_retryable_failure(1, "Error: rate limit exceeded") is True

    def test_http_429_stderr_is_retryable(self):
        assert _is_retryable_failure(1, "HTTP 429 Too Many Requests") is True

    def test_connection_reset_is_retryable(self):
        assert _is_retryable_failure(1, "connection reset by peer") is True

    def test_server_503_is_retryable(self):
        assert _is_retryable_failure(1, "503 Service Unavailable") is True

    def test_overloaded_is_retryable(self):
        assert _is_retryable_failure(1, "API is overloaded") is True

    def test_exit_code_2_is_not_retryable(self):
        """Exit code 2 = user abort / validation error — never retry."""
        assert _is_retryable_failure(2, "rate limit") is False

    def test_clean_failure_is_not_retryable(self):
        assert _is_retryable_failure(1, "syntax error in config") is False

    def test_empty_stderr_is_not_retryable(self):
        assert _is_retryable_failure(1, "") is False


class TestComputeBackoff:
    """Tests for _compute_backoff — exponential backoff with jitter."""

    def test_first_attempt_base_backoff(self):
        backoff = _compute_backoff(0)
        # Base is 2s + up to 1s jitter
        assert RETRY_BACKOFF_BASE <= backoff <= RETRY_BACKOFF_BASE + 1.0

    def test_second_attempt_doubles(self):
        backoff = _compute_backoff(1)
        # 2 * 2^1 = 4s + up to 1s jitter
        assert 4.0 <= backoff <= 5.0

    def test_backoff_capped_at_max(self):
        backoff = _compute_backoff(100)
        # Should never exceed max + jitter
        assert backoff <= RETRY_BACKOFF_MAX + 1.0

    def test_backoff_always_positive(self):
        for attempt in range(10):
            assert _compute_backoff(attempt) > 0


class TestRetryInRunSingle:
    """Tests for retry loop integration in _run_single."""

    @patch("emdx.commands.delegate.time.sleep")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_retry_succeeds_on_second_attempt(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
        mock_sleep,
    ):
        """Transient failure on first attempt, success on retry."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = 42

        # First call: retryable failure (rate limit)
        fail_result = _mock_subprocess_failure("429 Too Many Requests")
        # Second call: success
        success_result = _mock_subprocess_success()
        mock_subprocess.run.side_effect = [fail_result, success_result]

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=2,
        )

        assert result.success is True
        assert result.doc_id == 42
        assert mock_subprocess.run.call_count == 2
        mock_sleep.assert_called_once()  # Slept once between attempts

    @patch("emdx.commands.delegate.time.sleep")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_retry_exhausted_fails(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_sleep,
    ):
        """All retries fail — should report failure."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = None

        # All 3 attempts fail with retryable error
        fail_result = _mock_subprocess_failure("rate limit exceeded")
        mock_subprocess.run.return_value = fail_result

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=2,
        )

        assert result.success is False
        assert mock_subprocess.run.call_count == 3  # 1 initial + 2 retries
        assert mock_sleep.call_count == 2

    @patch("emdx.commands.delegate.time.sleep")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_non_retryable_failure_no_retry(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_sleep,
    ):
        """Non-retryable failure should not retry."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = None

        # Non-retryable failure (validation error, no retryable pattern)
        fail_result = _mock_subprocess_failure("syntax error in config")
        mock_subprocess.run.return_value = fail_result

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=3,
        )

        assert result.success is False
        assert mock_subprocess.run.call_count == 1  # No retries
        mock_sleep.assert_not_called()

    @patch("emdx.commands.delegate.time.sleep")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_timeout_retried(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_sleep,
    ):
        """TimeoutExpired is retried, then succeeds."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = 42

        # First call: timeout, second call: success
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        mock_subprocess.run.side_effect = [
            subprocess.TimeoutExpired(["claude"], 30),
            _mock_subprocess_success(),
        ]

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=1,
        )

        assert result.success is True
        assert mock_subprocess.run.call_count == 2
        mock_sleep.assert_called_once()

    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_retry_zero_no_retry(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_print,
    ):
        """retry=0 (default) means no retries even on retryable failure."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = None

        fail_result = _mock_subprocess_failure("rate limit exceeded")
        mock_subprocess.run.return_value = fail_result

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=0,
        )

        assert result.success is False
        assert mock_subprocess.run.call_count == 1

    @patch("emdx.commands.delegate.time.sleep")
    @patch("emdx.commands.delegate._read_batch_doc_id")
    @patch("emdx.commands.delegate._safe_update_execution_status")
    @patch("emdx.commands.delegate._safe_create_execution")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_exit_code_2_not_retried(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_create_exec,
        mock_update_exec,
        mock_read_batch,
        mock_sleep,
    ):
        """Exit code 2 (user abort) should never retry even with retryable stderr."""
        mock_create.return_value = 1
        mock_create_exec.return_value = 100
        mock_read_batch.return_value = None

        fail_result = MagicMock()
        fail_result.returncode = 2
        fail_result.stdout = ""
        fail_result.stderr = "rate limit exceeded"
        mock_subprocess.run.return_value = fail_result

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
            retry=3,
        )

        assert result.success is False
        assert mock_subprocess.run.call_count == 1
        mock_sleep.assert_not_called()
