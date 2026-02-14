"""Tests for delegate command helper functions."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import typer

from emdx.commands.delegate import (
    _slugify_title,
    _resolve_task,
    _run_discovery,
    _load_doc_context,
    _run_single,
    _run_parallel,
    _run_chain,
    _safe_create_task,
    _safe_update_task,
    PR_INSTRUCTION,
)


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

    def test_text_task_returned_as_is(self):
        result = _resolve_task("analyze the auth module")
        assert result == "analyze the auth module"

    @patch("emdx.commands.delegate.get_document")
    def test_missing_doc_falls_back(self, mock_get):
        mock_get.return_value = None
        result = _resolve_task("99999")
        # Should return the string as-is when doc not found
        assert "99999" in result


class TestPRInstruction:
    """Tests for PR instruction constant."""

    def test_pr_instruction_mentions_branch(self):
        assert "branch" in PR_INSTRUCTION.lower()

    def test_pr_instruction_mentions_pr_create(self):
        assert "gh pr create" in PR_INSTRUCTION


class TestLoadDocContext:
    """Tests for _load_doc_context — loads document and combines with prompt."""

    @patch("emdx.commands.delegate.get_document")
    def test_doc_with_prompt(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Document content here",
        }
        result = _load_doc_context(42, "implement this")
        assert "Document #42" in result
        assert "Test Doc" in result
        assert "Document content here" in result
        assert "Task: implement this" in result

    @patch("emdx.commands.delegate.get_document")
    def test_doc_without_prompt(self, mock_get):
        mock_get.return_value = {
            "id": 42,
            "title": "Test Doc",
            "content": "Document content here",
        }
        result = _load_doc_context(42, None)
        assert "Execute the following document" in result
        assert "Test Doc" in result
        assert "Document content here" in result

    @patch("emdx.commands.delegate.get_document")
    def test_missing_doc_raises_exit(self, mock_get):
        mock_get.return_value = None
        with pytest.raises(typer.Exit):
            _load_doc_context(99999, "test prompt")


class TestRunDiscovery:
    """Tests for _run_discovery — runs shell command to discover items."""

    @patch("subprocess.run")
    def test_successful_discovery(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\nfile2.py\nfile3.py",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py", "file3.py"]
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_discovery_strips_whitespace(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  file1.py  \n  file2.py  \n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_discovery_filters_empty_lines(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="file1.py\n\nfile2.py\n\n",
            stderr="",
        )
        result = _run_discovery("fd -e py")
        assert result == ["file1.py", "file2.py"]

    @patch("subprocess.run")
    def test_discovery_failure_exits(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="command not found",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("invalid_command")

    @patch("subprocess.run")
    def test_discovery_empty_result_exits(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        with pytest.raises(typer.Exit):
            _run_discovery("fd -e nonexistent")

    @patch("subprocess.run")
    def test_discovery_timeout_exits(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow_cmd", timeout=30)
        with pytest.raises(typer.Exit):
            _run_discovery("slow_cmd")


class TestSafeTaskHelpers:
    """Tests for _safe_create_task and _safe_update_task — never fail delegate."""

    @patch("emdx.models.tasks.create_task")
    def test_safe_create_task_success(self, mock_create):
        mock_create.return_value = 42
        result = _safe_create_task(title="Test", prompt="test prompt")
        assert result == 42

    @patch("emdx.models.tasks.create_task")
    def test_safe_create_task_handles_exception(self, mock_create):
        mock_create.side_effect = Exception("Database error")
        result = _safe_create_task(title="Test", prompt="test prompt")
        assert result is None

    @patch("emdx.models.tasks.update_task")
    def test_safe_update_task_success(self, mock_update):
        _safe_update_task(42, status="done")
        mock_update.assert_called_once_with(42, status="done")

    @patch("emdx.models.tasks.update_task")
    def test_safe_update_task_handles_exception(self, mock_update):
        mock_update.side_effect = Exception("Database error")
        # Should not raise, just silently fail
        _safe_update_task(42, status="done")

    def test_safe_update_task_with_none_id(self):
        # Should return early without calling update_task
        _safe_update_task(None, status="done")


class TestRunSingle:
    """Tests for _run_single — executes a single task via UnifiedExecutor."""

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_single_success(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_executor_class
    ):
        mock_create_task.return_value = 1

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_doc_id = 42
        mock_result.execution_id = 100
        mock_result.tokens_used = 500
        mock_result.cost_usd = 0.01
        mock_result.execution_time_ms = 1000

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        mock_get_doc.return_value = {"content": "Output content"}

        doc_id, task_id = _run_single(
            prompt="test task",
            tags=["test"],
            title="Test Task",
            model=None,
            quiet=True,
        )

        assert doc_id == 42
        assert task_id == 1
        mock_executor.execute.assert_called_once()

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    def test_run_single_failure(
        self, mock_update_task, mock_create_task, mock_executor_class
    ):
        mock_create_task.return_value = 1

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Execution failed"
        mock_result.execution_id = 100

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        doc_id, task_id = _run_single(
            prompt="test task",
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        assert doc_id is None
        assert task_id == 1
        # Should mark task as failed
        mock_update_task.assert_any_call(1, status="failed", error="Execution failed")

    @patch("emdx.commands.delegate.UnifiedExecutor")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_single_with_pr_flag(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_executor_class
    ):
        mock_create_task.return_value = 1

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output_doc_id = 42
        mock_result.execution_id = 100
        mock_result.tokens_used = 500
        mock_result.cost_usd = 0.01
        mock_result.execution_time_ms = 1000

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_result
        mock_executor_class.return_value = mock_executor

        mock_get_doc.return_value = {"content": "Output content"}

        _run_single(
            prompt="fix the bug",
            tags=[],
            title=None,
            model=None,
            quiet=True,
            pr=True,
        )

        # Check that PR instruction was included
        call_args = mock_executor.execute.call_args
        config = call_args[0][0]
        assert "pull request" in config.output_instruction.lower() or "PR" in config.output_instruction


class TestRunParallel:
    """Tests for _run_parallel — runs multiple tasks in parallel."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_parallel_basic(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.return_value = 1
        mock_run_single.side_effect = [(10, 2), (11, 3), (12, 4)]
        mock_get_doc.return_value = {"content": "Task output"}

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
        assert 10 in doc_ids
        assert 11 in doc_ids
        assert 12 in doc_ids
        assert mock_run_single.call_count == 3

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_parallel_with_synthesize(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.return_value = 1
        # First 2 calls are the parallel tasks, 3rd is the synthesis task
        mock_run_single.side_effect = [(10, 2), (11, 3), (99, 5)]
        mock_get_doc.return_value = {"content": "Task output"}

        doc_ids = _run_parallel(
            tasks=["task1", "task2"],
            tags=["test"],
            title=None,
            jobs=2,
            synthesize=True,
            model=None,
            quiet=True,
        )

        # Should have 2 task docs + 1 synthesis doc
        assert len(doc_ids) == 3
        assert 99 in doc_ids  # synthesis doc

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    def test_run_parallel_all_fail(
        self, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.return_value = 1
        mock_run_single.side_effect = [(None, 2), (None, 3)]

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
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.utils.git.cleanup_worktree")
    def test_run_parallel_with_worktree(
        self, mock_cleanup, mock_create_wt, mock_get_doc, mock_update_task,
        mock_create_task, mock_run_single
    ):
        mock_create_task.return_value = 1
        mock_run_single.side_effect = [(10, 2), (11, 3)]
        mock_get_doc.return_value = {"content": "Task output"}
        mock_create_wt.return_value = ("/tmp/worktree", "branch-name")

        doc_ids = _run_parallel(
            tasks=["task1", "task2"],
            tags=[],
            title=None,
            jobs=2,
            synthesize=False,
            model=None,
            quiet=True,
            worktree=True,
        )

        assert len(doc_ids) == 2
        assert mock_create_wt.call_count == 2
        # Worktrees should be cleaned up (since pr=False)
        assert mock_cleanup.call_count == 2


class TestRunChain:
    """Tests for _run_chain — runs tasks sequentially with output piping."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_chain_basic(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.side_effect = [1, 2, 3]  # parent + 2 steps
        mock_run_single.side_effect = [(10, 2), (11, 3)]
        mock_get_doc.return_value = {"content": "Step output"}

        doc_ids = _run_chain(
            tasks=["analyze", "implement"],
            tags=["test"],
            title="Test Chain",
            model=None,
            quiet=True,
        )

        assert len(doc_ids) == 2
        assert 10 in doc_ids
        assert 11 in doc_ids

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_chain_passes_previous_output(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.side_effect = [1, 2, 3]
        mock_run_single.side_effect = [(10, 2), (11, 3)]
        mock_get_doc.side_effect = [
            {"content": "First step output"},
            {"content": "Second step output"},
        ]

        _run_chain(
            tasks=["step1", "step2"],
            tags=[],
            title=None,
            model=None,
            quiet=True,
        )

        # Check that second call includes previous output
        calls = mock_run_single.call_args_list
        second_call_prompt = calls[1][1]["prompt"]
        assert "Previous step output" in second_call_prompt
        assert "First step output" in second_call_prompt

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    def test_run_chain_aborts_on_failure(
        self, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.side_effect = [1, 2, 3, 4]  # parent + 3 steps
        # First succeeds, second fails
        mock_run_single.side_effect = [(10, 2), (None, 3)]

        from unittest.mock import patch as m_patch
        with m_patch("emdx.commands.delegate.get_document") as mock_get_doc:
            mock_get_doc.return_value = {"content": "Step output"}

            doc_ids = _run_chain(
                tasks=["step1", "step2", "step3"],
                tags=[],
                title=None,
                model=None,
                quiet=True,
            )

        # Only first step should have succeeded
        assert len(doc_ids) == 1
        assert 10 in doc_ids

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._safe_create_task")
    @patch("emdx.commands.delegate._safe_update_task")
    @patch("emdx.commands.delegate.get_document")
    def test_run_chain_pr_only_on_last_step(
        self, mock_get_doc, mock_update_task, mock_create_task, mock_run_single
    ):
        mock_create_task.side_effect = [1, 2, 3]
        mock_run_single.side_effect = [(10, 2), (11, 3)]
        mock_get_doc.return_value = {"content": "Step output"}

        _run_chain(
            tasks=["analyze", "implement"],
            tags=[],
            title=None,
            model=None,
            quiet=True,
            pr=True,
        )

        calls = mock_run_single.call_args_list
        # First step should have pr=False
        assert calls[0][1]["pr"] is False
        # Last step should have pr=True
        assert calls[1][1]["pr"] is True


class TestDelegateCommandIntegration:
    """Integration tests for the delegate command main function."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    def test_single_task_execution(self, mock_get_doc, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "test task"])

        # Should call _run_single for single task
        mock_run_single.assert_called_once()

    @patch("emdx.commands.delegate._run_parallel")
    def test_multiple_tasks_parallel(self, mock_run_parallel):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_parallel.return_value = [42, 43, 44]

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "task1", "task2", "task3"])

        mock_run_parallel.assert_called_once()

    @patch("emdx.commands.delegate._run_chain")
    def test_chain_flag(self, mock_run_chain):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_chain.return_value = [42, 43]

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--chain", "step1", "step2"])

        mock_run_chain.assert_called_once()

    @patch("emdx.commands.delegate._run_discovery")
    @patch("emdx.commands.delegate._run_parallel")
    def test_each_do_flags(self, mock_run_parallel, mock_discovery):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_discovery.return_value = ["file1.py", "file2.py"]
        mock_run_parallel.return_value = [42, 43]

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["-q", "--each", "fd -e py", "--do", "Review {{item}}"]
        )

        mock_discovery.assert_called_once_with("fd -e py")
        mock_run_parallel.assert_called_once()
        # Check that tasks were generated from template
        call_args = mock_run_parallel.call_args
        tasks = call_args[1]["tasks"]
        assert "Review file1.py" in tasks
        assert "Review file2.py" in tasks

    def test_each_without_do_fails(self):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        runner = CliRunner()
        result = runner.invoke(app, ["--each", "fd -e py"])

        assert result.exit_code != 0
        assert "requires --do" in result.output.lower() or result.exit_code == 1

    def test_chain_and_synthesize_mutually_exclusive(self):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        runner = CliRunner()
        result = runner.invoke(app, ["--chain", "--synthesize", "task1", "task2"])

        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.utils.git.cleanup_worktree")
    def test_worktree_flag_creates_and_cleans(
        self, mock_cleanup, mock_create_wt, mock_get_doc, mock_run_single
    ):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_create_wt.return_value = ("/tmp/worktree", "branch-name")
        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--worktree", "test task"])

        mock_create_wt.assert_called_once()
        # Worktree should be cleaned up after (since no --pr)
        mock_cleanup.assert_called_once()

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.utils.git.cleanup_worktree")
    def test_pr_flag_implies_worktree(
        self, mock_cleanup, mock_create_wt, mock_get_doc, mock_run_single
    ):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_create_wt.return_value = ("/tmp/worktree", "branch-name")
        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--pr", "fix bug"])

        # --pr implies --worktree
        mock_create_wt.assert_called_once()
        # But worktree should NOT be cleaned up with --pr (to preserve the PR branch)
        mock_cleanup.assert_not_called()

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._load_doc_context")
    @patch("emdx.commands.delegate.get_document")
    def test_doc_flag_loads_context(self, mock_get_doc, mock_load_context, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_load_context.return_value = "Document context with task"
        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--doc", "123", "implement this"])

        mock_load_context.assert_called_once_with(123, "implement this")

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate._load_doc_context")
    @patch("emdx.commands.delegate.get_document")
    def test_doc_flag_without_task_executes_doc(self, mock_get_doc, mock_load_context, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_load_context.return_value = "Execute document content"
        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--doc", "123"])

        # When no task provided, doc context is loaded with None prompt
        mock_load_context.assert_called_once_with(123, None)

    def test_no_tasks_shows_error(self):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        runner = CliRunner()
        result = runner.invoke(app, [])

        assert result.exit_code != 0
        assert "no tasks" in result.output.lower() or "error" in result.output.lower()


class TestWorktreeIntegration:
    """Tests for worktree creation and cleanup in delegate."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.utils.git.cleanup_worktree")
    def test_worktree_cleanup_on_success(
        self, mock_cleanup, mock_create_wt, mock_get_doc, mock_run_single
    ):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_create_wt.return_value = ("/tmp/worktree-123", "worktree-123")
        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--worktree", "test task"])

        mock_cleanup.assert_called_once_with("/tmp/worktree-123")

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    @patch("emdx.utils.git.create_worktree")
    @patch("emdx.utils.git.cleanup_worktree")
    def test_worktree_cleanup_on_failure(
        self, mock_cleanup, mock_create_wt, mock_get_doc, mock_run_single
    ):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_create_wt.return_value = ("/tmp/worktree-123", "worktree-123")
        mock_run_single.return_value = (None, 1)  # Failure
        mock_get_doc.return_value = None

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--worktree", "test task"])

        # Worktree should still be cleaned up even on failure
        mock_cleanup.assert_called_once_with("/tmp/worktree-123")

    @patch("emdx.utils.git.create_worktree")
    def test_worktree_creation_failure_exits(self, mock_create_wt):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_create_wt.side_effect = Exception("Git error")

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--worktree", "test task"])

        assert result.exit_code != 0


class TestTagHandling:
    """Tests for tag parsing and flattening."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    def test_single_tag(self, mock_get_doc, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--tags", "test", "task"])

        call_args = mock_run_single.call_args
        assert "test" in call_args[1]["tags"]

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    def test_comma_separated_tags(self, mock_get_doc, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--tags", "test,analysis,review", "task"])

        call_args = mock_run_single.call_args
        tags = call_args[1]["tags"]
        assert "test" in tags
        assert "analysis" in tags
        assert "review" in tags


class TestModelOption:
    """Tests for --model option."""

    @patch("emdx.commands.delegate._run_single")
    @patch("emdx.commands.delegate.get_document")
    def test_model_passed_to_executor(self, mock_get_doc, mock_run_single):
        from typer.testing import CliRunner
        from emdx.commands.delegate import app

        mock_run_single.return_value = (42, 1)
        mock_get_doc.return_value = {"content": "Output"}

        runner = CliRunner()
        result = runner.invoke(app, ["-q", "--model", "sonnet", "task"])

        call_args = mock_run_single.call_args
        assert call_args[1]["model"] == "sonnet"
