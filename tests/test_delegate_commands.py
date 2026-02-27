# mypy: disable-error-code="no-untyped-def"
"""Comprehensive tests for delegate command (emdx/commands/delegate.py).

Tests cover:
- Basic delegate call with single task
- --synthesize flag for parallel task synthesis
- --pr flag for pull request creation
- --worktree flag for git worktree isolation
- --doc flag for document context
- --json flag for structured output
- Duration formatting and summary lines
- Error handling and edge cases
"""

from unittest.mock import MagicMock, patch

import pytest
import typer

from emdx.commands.delegate import (
    PR_INSTRUCTION_GENERIC,
    ParallelResult,
    SingleResult,
    _extract_pr_url,
    _format_duration,
    _format_summary_line,
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
    """Mock task creation, update, and save helpers."""
    with (
        patch("emdx.commands.delegate._safe_create_task") as mock_create,
        patch("emdx.commands.delegate._safe_update_task") as mock_update,
        patch("emdx.commands.delegate._safe_save_document") as mock_save_doc,
    ):
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        yield mock_create, mock_update, mock_save_doc


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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_successful_single_task(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

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
        mock_save_doc.assert_called_once()

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_failed_single_task(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        mock_create.return_value = 1
        mock_save_doc.return_value = None
        mock_subprocess.run.return_value = _mock_subprocess_failure("Task failed")

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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_flag(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_draft_true(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Test that pr=True with draft=True includes --draft flag in prompt."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_draft_false(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Test that pr=True with draft=False omits --draft flag."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_working_dir(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

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

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_includes_epic_id(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Test that pr=True with epic task includes epic_id in PR instruction."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

        with patch("emdx.models.tasks.get_task") as mock_get_task:
            mock_get_task.return_value = {
                "id": 1,
                "epic_key": "ARCH",
                "epic_seq": 11,
            }
            _run_single(
                prompt="fix bug",
                tags=[],
                title=None,
                model=None,
                quiet=False,
                pr=True,
            )

        call_args = mock_subprocess.run.call_args
        prompt_input = call_args[1]["input"]
        assert "(ARCH-11)" in prompt_input

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_single_task_with_pr_no_epic_when_no_key(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Test that pr=True without epic_key does not include epic_id."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success()

        with patch("emdx.models.tasks.get_task") as mock_get_task:
            mock_get_task.return_value = {
                "id": 1,
                "epic_key": None,
                "epic_seq": None,
            }
            _run_single(
                prompt="fix bug",
                tags=[],
                title=None,
                model=None,
                quiet=False,
                pr=True,
            )

        call_args = mock_subprocess.run.call_args
        prompt_input = call_args[1]["input"]
        assert "ARCH-" not in prompt_input
        assert "<short title>" in prompt_input


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

        result = _run_parallel(
            tasks=["task1", "task2", "task3"],
            tags=["test"],
            title=None,
            jobs=3,
            synthesize=False,
            model=None,
            quiet=True,
        )

        assert len(result.doc_ids) == 3
        assert set(result.doc_ids) == {10, 20, 30}

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

        result = _run_parallel(
            tasks=["task1", "task2", "task3"],
            tags=[],
            title=None,
            jobs=3,
            synthesize=True,
            model=None,
            quiet=True,
        )

        # Should include synthesis doc
        assert 99 in result.doc_ids
        assert len(result.doc_ids) == 4

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

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_streams_output_as_tasks_complete(
        self, mock_create, mock_update, mock_print, mock_run_single, capsys
    ):
        """Test that parallel mode prints each task's output as it completes."""
        mock_create.return_value = 1
        mock_run_single.side_effect = [
            SingleResult(doc_id=10, task_id=1),
            SingleResult(doc_id=20, task_id=2),
        ]

        _run_parallel(
            tasks=["check auth", "review tests"],
            tags=[],
            title=None,
            jobs=2,
            synthesize=False,
            model=None,
            quiet=False,
        )

        captured = capsys.readouterr()
        # Headers should appear in stdout (order depends on thread scheduling)
        assert "=== Task" in captured.out
        assert "check auth" in captured.out
        assert "review tests" in captured.out
        # _print_doc_content should be called from the as_completed loop
        assert mock_print.call_count == 2

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_streams_failures_immediately(
        self, mock_create, mock_update, mock_print, mock_run_single, capsys
    ):
        """Test that failed tasks surface immediately with error info."""
        mock_create.return_value = 1
        mock_run_single.side_effect = [
            SingleResult(doc_id=10, task_id=1),
            SingleResult(task_id=2, success=False, error_message="connection timeout"),
        ]

        _run_parallel(
            tasks=["check auth", "scan network"],
            tags=[],
            title=None,
            jobs=2,
            synthesize=False,
            model=None,
            quiet=False,
        )

        captured = capsys.readouterr()
        assert "[FAILED]" in captured.out
        assert "connection timeout" in captured.out

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_quiet_suppresses_streaming(
        self, mock_create, mock_update, mock_print, mock_run_single, capsys
    ):
        """Test that quiet=True suppresses streaming output."""
        mock_create.return_value = 1
        mock_run_single.side_effect = [
            SingleResult(doc_id=10, task_id=1),
            SingleResult(doc_id=20, task_id=2),
        ]

        _run_parallel(
            tasks=["task1", "task2"],
            tags=[],
            title=None,
            jobs=2,
            synthesize=False,
            model=None,
            quiet=True,
        )

        captured = capsys.readouterr()
        assert "=== Task" not in captured.out
        # _print_doc_content should NOT be called (quiet mode)
        assert mock_print.call_count == 0

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._print_doc_content")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    def test_parallel_streams_raw_output_fallback(
        self, mock_create, mock_update, mock_print, mock_run_single, capsys
    ):
        """Test that raw_output is printed when no doc_id (hook didn't save).

        Note: a result with no doc_id triggers the "all failures" exit path,
        but the raw output is still surfaced to stdout before that happens.
        """
        mock_create.return_value = 1
        mock_run_single.side_effect = [
            SingleResult(doc_id=None, task_id=1, raw_output="raw result text"),
        ]

        with pytest.raises(typer.Exit):
            _run_parallel(
                tasks=["task1"],
                tags=[],
                title=None,
                jobs=1,
                synthesize=False,
                model=None,
                quiet=False,
            )

        captured = capsys.readouterr()
        assert "raw result text" in captured.out


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
            json_output=False,
        )

        mock_run_single.assert_called_once()
        call_kwargs = mock_run_single.call_args
        assert "analyze the code" in call_kwargs[1]["prompt"]

    @patch("emdx.commands.delegate._run_parallel")
    def test_multiple_tasks_go_parallel(self, mock_run_parallel):
        """Test that multiple tasks trigger parallel execution."""
        mock_run_parallel.return_value = ParallelResult(doc_ids=[10, 20, 30])
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
            json_output=False,
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
            json_output=False,
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
            json_output=False,
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
            json_output=False,
        )

        # Worktree should be created even though --worktree not set
        mock_create_wt.assert_called_once_with("develop", task_title="fix bug")
        # Worktree IS cleaned up after PR (branch already pushed to remote)
        mock_cleanup_wt.assert_called_once_with("/tmp/worktree")

    @patch("emdx.commands.delegate._run_parallel")
    def test_synthesize_flag_passed_to_parallel(self, mock_run_parallel):
        """Test that --synthesize flag is passed to parallel execution."""
        mock_run_parallel.return_value = ParallelResult(doc_ids=[10, 20, 99])
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
            json_output=False,
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
            json_output=False,
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
            json_output=False,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["draft"] is False

    @patch("emdx.commands.delegate._run_parallel")
    def test_draft_flag_passed_to_run_parallel(self, mock_run_parallel):
        """Test that --draft flag is passed to _run_parallel."""
        mock_run_parallel.return_value = ParallelResult(doc_ids=[10, 20])
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
            json_output=False,
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
                branch=False,
                draft=False,
                worktree=False,
                base_branch="main",
                json_output=False,
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
            json_output=False,
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
            json_output=False,
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

    def test_make_pr_instruction_with_epic_id(self):
        """Test that epic_id is included in PR title example."""
        result = _make_pr_instruction("fix/my-branch", epic_id="ARCH-11")
        assert "(ARCH-11)" in result
        assert "feat: <short description> (ARCH-11)" in result

    def test_make_pr_instruction_with_epic_id_no_branch(self):
        """Test epic_id without branch name."""
        result = _make_pr_instruction(None, epic_id="FEAT-5")
        assert "(FEAT-5)" in result
        assert "feat: <short description> (FEAT-5)" in result

    def test_make_pr_instruction_without_epic_id(self):
        """Test that without epic_id, a generic title placeholder is used."""
        result = _make_pr_instruction("fix/my-branch")
        assert "<short title>" in result
        assert "ARCH-" not in result
        assert "FEAT-" not in result

    def test_extract_pr_url_found(self):
        text = "Created PR: https://github.com/user/repo/pull/123 done"
        assert _extract_pr_url(text) == "https://github.com/user/repo/pull/123"

    def test_extract_pr_url_not_found(self):
        assert _extract_pr_url("no url here") is None

    def test_extract_pr_url_none_input(self):
        assert _extract_pr_url(None) is None

    def test_extract_pr_url_empty_string(self):
        assert _extract_pr_url("") is None


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
            json_output=False,
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
            json_output=False,
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
                json_output=False,
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
                json_output=False,
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
                draft=False,
                worktree=True,
                base_branch="main",
                json_output=False,
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
                draft=False,
                worktree=False,
                base_branch="main",
                json_output=False,
            )


# =============================================================================
# Tests for hooks integration (batch file doc ID collection)
# =============================================================================


class TestRunSingleHooksIntegration:
    """Tests for _run_single hooks integration (batch file doc ID)."""

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_doc_id_from_batch_file(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Inline save produces a doc_id in the result."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 99
        mock_subprocess.run.return_value = _mock_subprocess_success()

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id == 99

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_no_doc_id_when_hook_didnt_save(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """When inline save fails, doc_id is None."""
        mock_create.return_value = 1
        mock_save_doc.return_value = None
        mock_subprocess.run.return_value = _mock_subprocess_success()

        result = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=False,
        )

        assert result.doc_id is None


# =============================================================================
# Tests for _format_duration
# =============================================================================


class TestFormatDuration:
    """Tests for _format_duration — formats seconds into human-readable strings."""

    def test_none_returns_question_mark(self):
        assert _format_duration(None) == "?"

    def test_seconds_only(self):
        assert _format_duration(45) == "45s"

    def test_zero_seconds(self):
        assert _format_duration(0) == "0s"

    def test_minutes_and_seconds(self):
        assert _format_duration(192) == "3m12s"

    def test_exact_minute(self):
        assert _format_duration(60) == "1m00s"

    def test_hours(self):
        assert _format_duration(3661) == "1h01m01s"

    def test_large_duration(self):
        assert _format_duration(7200) == "2h00m00s"


# =============================================================================
# Tests for _format_summary_line
# =============================================================================


class TestFormatSummaryLine:
    """Tests for _format_summary_line — formats a summary line for delegate output."""

    def test_successful_result(self):
        result = SingleResult(
            doc_id=42,
            task_id=1,
            exit_code=0,
            duration_seconds=192.5,
            execution_id=100,
        )
        line = _format_summary_line(result)
        assert "delegate: done" in line
        assert "task_id:1" in line
        assert "doc_id:42" in line
        assert "exit:0" in line
        assert "duration:3m12s" in line
        assert "exec_id:100" in line

    def test_failed_result(self):
        result = SingleResult(
            task_id=1,
            success=False,
            exit_code=1,
            duration_seconds=5.0,
            error_message="command not found",
        )
        line = _format_summary_line(result)
        assert "delegate: FAILED" in line
        assert "exit:1" in line
        assert "error:command not found" in line

    def test_result_with_pr_url(self):
        result = SingleResult(
            doc_id=42,
            task_id=1,
            pr_url="https://github.com/user/repo/pull/123",
            exit_code=0,
            duration_seconds=60.0,
        )
        line = _format_summary_line(result)
        assert "pr:https://github.com/user/repo/pull/123" in line

    def test_result_with_branch(self):
        result = SingleResult(
            doc_id=42,
            task_id=1,
            branch_name="feat/test",
            exit_code=0,
            duration_seconds=60.0,
        )
        line = _format_summary_line(result)
        assert "branch:feat/test" in line

    def test_pr_takes_precedence_over_branch(self):
        """When both pr_url and branch_name exist, only pr is shown."""
        result = SingleResult(
            doc_id=42,
            task_id=1,
            pr_url="https://github.com/user/repo/pull/123",
            branch_name="feat/test",
            exit_code=0,
            duration_seconds=60.0,
        )
        line = _format_summary_line(result)
        assert "pr:" in line
        assert "branch:" not in line


# =============================================================================
# Tests for SingleResult.to_dict
# =============================================================================


class TestSingleResultToDict:
    """Tests for SingleResult.to_dict — JSON serialization."""

    def test_basic_success(self):
        result = SingleResult(
            doc_id=42,
            task_id=1,
            exit_code=0,
            duration_seconds=192.5,
            execution_id=100,
            output_doc_id=42,
        )
        d = result.to_dict()
        assert d["task_id"] == 1
        assert d["doc_id"] == 42
        assert d["exit_code"] == 0
        assert d["success"] is True
        assert d["duration_seconds"] == 192.5
        assert d["duration"] == "3m12s"
        assert d["execution_id"] == 100

    def test_failure_includes_error(self):
        result = SingleResult(
            task_id=1,
            success=False,
            exit_code=1,
            error_message="task failed",
        )
        d = result.to_dict()
        assert d["success"] is False
        assert d["error"] == "task failed"

    def test_pr_url_included(self):
        result = SingleResult(
            doc_id=42,
            task_id=1,
            pr_url="https://github.com/user/repo/pull/123",
        )
        d = result.to_dict()
        assert d["pr_url"] == "https://github.com/user/repo/pull/123"

    def test_no_pr_url_when_absent(self):
        result = SingleResult(doc_id=42, task_id=1)
        d = result.to_dict()
        assert "pr_url" not in d

    def test_none_duration(self):
        result = SingleResult(doc_id=42, task_id=1)
        d = result.to_dict()
        assert d["duration_seconds"] is None
        assert d["duration"] is None


# =============================================================================
# Tests for ParallelResult.to_dict
# =============================================================================


class TestParallelResultToDict:
    """Tests for ParallelResult.to_dict — JSON serialization for parallel runs."""

    def test_basic_parallel(self):
        results = {
            0: SingleResult(doc_id=10, task_id=1, exit_code=0, duration_seconds=60.0),
            1: SingleResult(doc_id=20, task_id=2, exit_code=0, duration_seconds=90.0),
        }
        pr = ParallelResult(
            parent_task_id=100,
            results=results,
            doc_ids=[10, 20],
            total_duration_seconds=150.0,
            succeeded=2,
            failed=0,
        )
        d = pr.to_dict()
        assert d["parent_task_id"] == 100
        assert d["task_count"] == 2
        assert d["succeeded"] == 2
        assert d["failed"] == 0
        assert d["doc_ids"] == [10, 20]
        assert len(d["tasks"]) == 2  # type: ignore[arg-type]
        assert d["total_duration"] == "2m30s"

    def test_partial_failure(self):
        results = {
            0: SingleResult(doc_id=10, task_id=1, exit_code=0, duration_seconds=60.0),
            1: SingleResult(
                task_id=2,
                success=False,
                exit_code=1,
                error_message="failed",
                duration_seconds=5.0,
            ),
        }
        pr = ParallelResult(
            parent_task_id=100,
            results=results,
            doc_ids=[10],
            total_duration_seconds=65.0,
            succeeded=1,
            failed=1,
        )
        d = pr.to_dict()
        assert d["succeeded"] == 1
        assert d["failed"] == 1
        tasks = d["tasks"]
        assert isinstance(tasks, list)
        assert len(tasks) == 2
        # Task at index 1 should have error
        task_1 = tasks[1]
        assert isinstance(task_1, dict)
        assert task_1["success"] is False
        assert "error" in task_1


# =============================================================================
# Tests for --json flag in delegate command
# =============================================================================


class TestJsonOutput:
    """Tests for --json flag in delegate command."""

    @patch("emdx.commands.delegate._run_single")
    def test_json_flag_outputs_json(self, mock_run_single, capsys):
        """Test that --json flag outputs structured JSON to stdout."""
        mock_run_single.return_value = SingleResult(
            doc_id=42,
            task_id=1,
            exit_code=0,
            duration_seconds=60.0,
            execution_id=100,
            output_doc_id=42,
        )
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze code"],
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
            json_output=True,
        )

        import json as json_mod

        captured = capsys.readouterr()
        data = json_mod.loads(captured.out)
        assert data["task_id"] == 1
        assert data["doc_id"] == 42
        assert data["exit_code"] == 0
        assert data["success"] is True

    @patch("emdx.commands.delegate._run_single")
    def test_json_flag_implies_quiet(self, mock_run_single):
        """Test that --json suppresses stderr metadata (passes quiet to _run_single)."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze code"],
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
            json_output=True,
        )

        # _run_single should have been called with quiet=True (effective_quiet)
        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["quiet"] is True

    @patch("emdx.commands.delegate._run_parallel")
    def test_json_flag_parallel(self, mock_run_parallel, capsys):
        """Test that --json works for parallel tasks."""
        mock_run_parallel.return_value = ParallelResult(
            parent_task_id=100,
            results={
                0: SingleResult(doc_id=10, task_id=1),
                1: SingleResult(doc_id=20, task_id=2),
            },
            doc_ids=[10, 20],
            total_duration_seconds=120.0,
            succeeded=2,
            failed=0,
        )
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
            pr=False,
            branch=False,
            draft=False,
            worktree=False,
            base_branch="main",
            json_output=True,
        )

        import json as json_mod

        captured = capsys.readouterr()
        data = json_mod.loads(captured.out)
        assert data["parent_task_id"] == 100
        assert data["succeeded"] == 2
        assert data["doc_ids"] == [10, 20]


# =============================================================================
# Tests for _run_single timing and new fields
# =============================================================================


class TestRunSingleNewFields:
    """Tests for new fields in _run_single results."""

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_successful_result_has_timing(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Successful _run_single should populate duration, exit_code, execution_id."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

        result = _run_single(
            prompt="test task",
            tags=["test"],
            title="Test Title",
            model=None,
            quiet=True,
        )

        assert result.exit_code == 0
        assert result.execution_id is None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0
        assert result.output_doc_id == 42

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_failed_result_has_timing(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Failed _run_single should still populate duration and exit_code."""
        mock_create.return_value = 1
        mock_save_doc.return_value = None
        mock_subprocess.run.return_value = _mock_subprocess_failure("Task failed")

        result = _run_single(
            prompt="failing task",
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        assert result.exit_code == 1
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0
        assert result.execution_id is None
        assert not result.success

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_timeout_result_has_timing(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Timed-out _run_single should populate duration and exit_code=-1."""
        import subprocess as sp

        mock_create.return_value = 1
        mock_subprocess.run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=30)
        mock_subprocess.TimeoutExpired = sp.TimeoutExpired

        result = _run_single(
            prompt="slow task",
            tags=[],
            title=None,
            model=None,
            quiet=True,
            timeout=1,
        )

        assert result.exit_code == -1
        assert result.duration_seconds is not None
        assert result.error_message == "timeout"
        assert result.execution_id is None


# =============================================================================
# Tests for subcommand routing fix (FIX-3)
# =============================================================================


class TestSubcommandRouting:
    """Test that 'delegate list', 'delegate show', etc. route to subcommands."""

    @patch("emdx.commands.delegate._run_single")
    def test_subcommand_routed_when_task_matches_subcommand_name(self, mock_run_single):
        """When tasks[0] matches a registered subcommand, route to it."""
        import click

        # Create a mock MultiCommand that recognizes "list" as a subcommand
        mock_subcmd = MagicMock()
        mock_sub_ctx = MagicMock()
        mock_subcmd.make_context.return_value = mock_sub_ctx
        mock_sub_ctx.__enter__ = MagicMock(return_value=mock_sub_ctx)
        mock_sub_ctx.__exit__ = MagicMock(return_value=False)

        ctx = MagicMock(spec=click.Context)
        ctx.invoked_subcommand = None
        # Make ctx.command a MultiCommand that returns our mock for "list"
        ctx.command = MagicMock(spec=click.Group)
        ctx.command.get_command.return_value = mock_subcmd

        with pytest.raises(typer.Exit) as exc_info:
            delegate(
                ctx=ctx,
                tasks=["list"],
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
                json_output=False,
            )

        assert exc_info.value.exit_code == 0
        # Should route to subcommand, NOT call _run_single
        mock_run_single.assert_not_called()
        ctx.command.get_command.assert_called_once_with(ctx, "list")
        mock_subcmd.invoke.assert_called_once()

    @patch("emdx.commands.delegate._run_single")
    def test_non_subcommand_task_runs_normally(self, mock_run_single):
        """When tasks[0] is NOT a subcommand, run it as a normal task."""
        import click

        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)

        ctx = MagicMock(spec=click.Context)
        ctx.invoked_subcommand = None
        ctx.command = MagicMock(spec=click.Group)
        ctx.command.get_command.return_value = None  # "analyze code" is not a subcommand

        delegate(
            ctx=ctx,
            tasks=["analyze code"],
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
            json_output=False,
        )

        # Should run as a normal task
        mock_run_single.assert_called_once()
        assert "analyze code" in mock_run_single.call_args[1]["prompt"]


# =============================================================================
# Tests for allowedTools separator (FIX-6)
# =============================================================================


class TestAllowedToolsSeparator:
    """Test that --allowedTools uses comma separators to avoid space ambiguity."""

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_allowed_tools_uses_comma_separator(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """allowedTools should use commas, not spaces, to avoid splitting patterns."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

        _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        cmd = mock_subprocess.run.call_args[0][0]
        tools_idx = cmd.index("--allowedTools")
        tools_value = cmd[tools_idx + 1]
        # Must use commas, not spaces
        assert "," in tools_value
        assert " " not in tools_value

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_pr_flag_adds_gh_permission(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """--pr should add Bash(gh:*) to allowed tools."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

        _run_single(
            prompt="fix bug",
            tags=[],
            title=None,
            model=None,
            quiet=True,
            pr=True,
        )

        cmd = mock_subprocess.run.call_args[0][0]
        tools_idx = cmd.index("--allowedTools")
        tools_value = cmd[tools_idx + 1]
        assert "Bash(gh:*)" in tools_value

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_extra_tools_appended(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """extra_tools should be appended to the allowed tools list."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

        _run_single(
            prompt="analyze PR",
            tags=[],
            title=None,
            model=None,
            quiet=True,
            extra_tools=["WebFetch", "NotebookEdit", "Bash(gh:*)"],
        )

        cmd = mock_subprocess.run.call_args[0][0]
        tools_idx = cmd.index("--allowedTools")
        tools_value = cmd[tools_idx + 1]
        assert "WebFetch" in tools_value.split(",")
        assert "NotebookEdit" in tools_value.split(",")
        assert "Bash(gh:*)" in tools_value.split(",")
        # Base tools still present
        assert "Bash(git:*)" in tools_value.split(",")
        assert "Read" in tools_value.split(",")

    @patch("emdx.commands.delegate._safe_save_document")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate.subprocess")
    def test_extra_tools_deduplicates(
        self,
        mock_subprocess,
        mock_create,
        mock_update,
        mock_save_doc,
    ):
        """Duplicate tool patterns should not appear twice."""
        mock_create.return_value = 1
        mock_save_doc.return_value = 42
        mock_subprocess.run.return_value = _mock_subprocess_success(doc_id=42)

        _run_single(
            prompt="test dedup",
            tags=[],
            title=None,
            model=None,
            quiet=True,
            extra_tools=["Bash(git:*)", "Read"],  # both already in base
        )

        cmd = mock_subprocess.run.call_args[0][0]
        tools_idx = cmd.index("--allowedTools")
        tools_value = cmd[tools_idx + 1]
        tools_list = tools_value.split(",")
        assert tools_list.count("Bash(git:*)") == 1
        assert tools_list.count("Read") == 1


# =============================================================================
# Tests for build_allowed_tools (delegate_config.py)
# =============================================================================


class TestBuildAllowedTools:
    """Test build_allowed_tools combines base, config, and extra tools."""

    def test_base_tools_always_present(self):
        """Base Bash tools are always included."""
        from emdx.config.delegate_config import BASE_ALLOWED_TOOLS, build_allowed_tools

        result = build_allowed_tools()
        for tool in BASE_ALLOWED_TOOLS:
            assert tool in result

    def test_pr_adds_gh(self):
        """pr=True adds Bash(gh:*)."""
        from emdx.config.delegate_config import build_allowed_tools

        result = build_allowed_tools(pr=True)
        assert "Bash(gh:*)" in result

    def test_branch_adds_gh(self):
        """branch=True adds Bash(gh:*)."""
        from emdx.config.delegate_config import build_allowed_tools

        result = build_allowed_tools(branch=True)
        assert "Bash(gh:*)" in result

    def test_file_operation_tools_in_base(self):
        """File operation tools are included in base set (#913)."""
        from emdx.config.delegate_config import BASE_ALLOWED_TOOLS

        for tool in ("Read", "Write", "Edit", "Glob", "Grep"):
            assert tool in BASE_ALLOWED_TOOLS, f"{tool} missing from BASE_ALLOWED_TOOLS"

    def test_extra_tools_appended(self):
        """Extra tools are appended to the list."""
        from emdx.config.delegate_config import build_allowed_tools

        result = build_allowed_tools(extra_tools=["WebFetch", "NotebookEdit"])
        assert "WebFetch" in result
        assert "NotebookEdit" in result

    def test_deduplication(self):
        """Duplicate tools are not repeated."""
        from emdx.config.delegate_config import build_allowed_tools

        result = build_allowed_tools(extra_tools=["Bash(git:*)", "Read"])
        assert result.count("Bash(git:*)") == 1
        assert result.count("Read") == 1

    @patch("emdx.config.delegate_config.load_delegate_config")
    def test_config_file_tools_loaded(self, mock_config):
        """Tools from config file are included."""
        from emdx.config.delegate_config import build_allowed_tools

        mock_config.return_value = {"allowed_tools": ["Bash(npm:*)", "WebFetch"]}
        result = build_allowed_tools()
        assert "Bash(npm:*)" in result
        assert "WebFetch" in result

    @patch("emdx.config.delegate_config.load_delegate_config")
    def test_config_plus_extra_deduplicates(self, mock_config):
        """Config and extra tools are deduplicated against each other."""
        from emdx.config.delegate_config import build_allowed_tools

        mock_config.return_value = {"allowed_tools": ["WebFetch"]}
        result = build_allowed_tools(extra_tools=["WebFetch", "NotebookEdit"])
        assert result.count("WebFetch") == 1
        assert "NotebookEdit" in result


# =============================================================================
# Tests for --tool CLI flag
# =============================================================================


class TestToolFlag:
    """Test --tool flag passes extra_tools to _run_single."""

    @patch("emdx.commands.delegate._run_single")
    def test_tool_flag_passed_to_run_single(self, mock_run_single):
        """--tool list should be flattened and passed as extra_tools."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze the PR"],
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
            json_output=False,
            tool=["Read", "Bash(gh:*)"],
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["extra_tools"] == ["Read", "Bash(gh:*)"]

    @patch("emdx.commands.delegate._run_single")
    def test_tool_flag_comma_separated(self, mock_run_single):
        """--tool with comma-separated values should be flattened."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze code"],
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
            json_output=False,
            tool=["Read,Grep,Glob"],
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["extra_tools"] == ["Read", "Grep", "Glob"]

    @patch("emdx.commands.delegate._run_single")
    def test_no_tool_flag_passes_none(self, mock_run_single):
        """Without --tool, extra_tools should be None."""
        mock_run_single.return_value = SingleResult(doc_id=42, task_id=1)
        ctx = MagicMock()
        ctx.invoked_subcommand = None

        delegate(
            ctx=ctx,
            tasks=["analyze code"],
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
            json_output=False,
            tool=None,
        )

        call_kwargs = mock_run_single.call_args[1]
        assert call_kwargs["extra_tools"] is None
