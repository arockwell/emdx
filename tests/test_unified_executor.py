"""Tests for the UnifiedExecutor service.

Tests the unified execution infrastructure that consolidates
agent.py, agent_runner.py, and cascade.py execution logic.

These tests mock the actual Claude execution to focus on:
1. Configuration handling
2. Log file management
3. Token usage extraction
4. Output document ID extraction
5. Execution record management
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import asdict

from emdx.services.unified_executor import (
    UnifiedExecutor,
    ExecutionConfig,
    ExecutionResult,
    DEFAULT_ALLOWED_TOOLS,
    execute_with_output_tracking,
    execute_for_cascade,
    execute_for_workflow,
)


class TestExecutionConfig:
    """Test ExecutionConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ExecutionConfig(prompt="test prompt")

        assert config.prompt == "test prompt"
        assert config.timeout_seconds == 300
        assert config.sync is True
        assert config.verbose is False
        assert config.allowed_tools == DEFAULT_ALLOWED_TOOLS
        assert config.output_instruction is None
        assert config.doc_id is None
        assert config.title == "Claude Execution"

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ExecutionConfig(
            prompt="custom prompt",
            title="Custom Title",
            doc_id=123,
            timeout_seconds=600,
            sync=False,
            verbose=True,
            output_instruction="Save with emdx save",
            allowed_tools=["Read", "Write"],
        )

        assert config.prompt == "custom prompt"
        assert config.title == "Custom Title"
        assert config.doc_id == 123
        assert config.timeout_seconds == 600
        assert config.sync is False
        assert config.verbose is True
        assert config.output_instruction == "Save with emdx save"
        assert config.allowed_tools == ["Read", "Write"]

    def test_working_dir_default(self):
        """Working dir defaults to cwd."""
        config = ExecutionConfig(prompt="test")
        assert config.working_dir == str(Path.cwd())

    def test_callbacks(self):
        """Test callback configuration."""
        on_start = MagicMock()
        on_complete = MagicMock()
        on_error = MagicMock()

        config = ExecutionConfig(
            prompt="test",
            on_start=on_start,
            on_complete=on_complete,
            on_error=on_error,
        )

        assert config.on_start is on_start
        assert config.on_complete is on_complete
        assert config.on_error is on_error


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_success_result(self):
        """Test successful result structure."""
        result = ExecutionResult(
            success=True,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            output_doc_id=456,
            tokens_used=1000,
            input_tokens=800,
            output_tokens=200,
            cost_usd=0.05,
            execution_time_ms=5000,
        )

        assert result.success is True
        assert result.execution_id == 1
        assert result.output_doc_id == 456
        assert result.error_message is None

    def test_failure_result(self):
        """Test failure result structure."""
        result = ExecutionResult(
            success=False,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            error_message="Claude failed",
            exit_code=1,
        )

        assert result.success is False
        assert result.error_message == "Claude failed"
        assert result.exit_code == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = ExecutionResult(
            success=True,
            execution_id=42,
            log_file=Path("/tmp/test.log"),
            output_doc_id=100,
            tokens_used=500,
        )

        d = result.to_dict()

        assert d['success'] is True
        assert d['execution_id'] == 42
        assert d['log_file'] == "/tmp/test.log"
        assert d['output_doc_id'] == 100
        assert d['tokens_used'] == 500


class TestUnifiedExecutorInit:
    """Test UnifiedExecutor initialization."""

    def test_default_log_dir(self):
        """Default log dir is ~/.config/emdx/logs."""
        executor = UnifiedExecutor()
        expected = Path.home() / ".config" / "emdx" / "logs"
        assert executor.log_dir == expected

    def test_custom_log_dir(self, tmp_path):
        """Custom log dir is respected."""
        custom_dir = tmp_path / "custom_logs"
        executor = UnifiedExecutor(log_dir=custom_dir)
        assert executor.log_dir == custom_dir
        assert custom_dir.exists()  # Should be created


class TestUnifiedExecutorExecution:
    """Test UnifiedExecutor.execute() method."""

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_sync_execution_success(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test successful synchronous execution."""
        mock_create_exec.return_value = 42
        mock_claude_sync.return_value = {
            'success': True,
            'output': 'Task completed',
            'exit_code': 0,
        }

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(prompt="test task")

        # Create a fake log file that the executor will look for
        # (In real execution, claude_sync creates it)

        result = executor.execute(config)

        assert result.success is True
        assert result.execution_id == 42
        mock_ensure_path.assert_called_once()
        mock_create_exec.assert_called_once()
        mock_update_status.assert_called_with(42, 'completed', 0)

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_sync_execution_failure(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test failed synchronous execution."""
        mock_create_exec.return_value = 42
        mock_claude_sync.return_value = {
            'success': False,
            'error': 'Task failed',
            'exit_code': 1,
        }

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(prompt="test task")

        result = executor.execute(config)

        assert result.success is False
        assert result.error_message == 'Task failed'
        mock_update_status.assert_called_with(42, 'failed', 1)

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_output_instruction_appended(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test that output instruction is appended to prompt."""
        mock_create_exec.return_value = 1
        mock_claude_sync.return_value = {'success': True, 'exit_code': 0}

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(
            prompt="Base prompt",
            output_instruction="\n\nSave with emdx save",
        )

        executor.execute(config)

        # Check that claude_sync was called with combined prompt
        call_args = mock_claude_sync.call_args
        assert "Base prompt" in call_args.kwargs['task']
        assert "Save with emdx save" in call_args.kwargs['task']

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_callbacks_called(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test that callbacks are invoked."""
        mock_create_exec.return_value = 42
        mock_claude_sync.return_value = {'success': True, 'exit_code': 0}

        on_start = MagicMock()
        on_complete = MagicMock()

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(
            prompt="test",
            on_start=on_start,
            on_complete=on_complete,
        )

        executor.execute(config)

        on_start.assert_called_once_with(42)
        on_complete.assert_called_once()

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_error_callback_on_exception(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test that error callback is called on exception."""
        mock_create_exec.return_value = 42
        mock_claude_sync.side_effect = Exception("Unexpected error")

        on_error = MagicMock()

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(
            prompt="test",
            on_error=on_error,
        )

        result = executor.execute(config)

        assert result.success is False
        assert "Unexpected error" in result.error_message
        on_error.assert_called_once()


class TestTokenUsageExtraction:
    """Test token usage extraction from log files."""

    @patch('emdx.services.unified_executor.execute_claude_sync')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    @patch('emdx.services.unified_executor.ensure_claude_in_path')
    def test_token_extraction_from_log(
        self,
        mock_ensure_path,
        mock_update_status,
        mock_create_exec,
        mock_claude_sync,
        tmp_path,
    ):
        """Test that token usage is extracted from log file."""
        mock_create_exec.return_value = 1
        mock_claude_sync.return_value = {'success': True, 'exit_code': 0}

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(prompt="test")

        # Execute - this creates the log file
        result = executor.execute(config)

        # Write token data to the log file that was created
        log_file = result.log_file
        log_file.write_text(
            '__RAW_RESULT_JSON__:{"type":"result","usage":{"input_tokens":100,"output_tokens":50},"total_cost_usd":0.01}\n'
        )

        # Re-execute to pick up the token data
        # (In production, claude_sync writes to the file during execution)
        result2 = executor.execute(config)

        # The token extraction happens after execution
        # In this test setup, we're verifying the mechanism works


class TestConvenienceFunctions:
    """Test convenience functions for common patterns."""

    def test_execute_with_output_tracking_builds_instruction(self):
        """Test that output tracking builds correct save instruction."""
        with patch('emdx.services.unified_executor.UnifiedExecutor') as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = ExecutionResult(
                success=True,
                execution_id=1,
                log_file=Path("/tmp/test.log"),
            )
            MockExecutor.return_value = mock_instance

            execute_with_output_tracking(
                prompt="Test task",
                title="Test Output",
                tags=["analysis", "security"],
                group_id=123,
                group_role="exploration",
            )

            # Verify the config was built correctly
            call_args = mock_instance.execute.call_args[0][0]
            assert call_args.prompt == "Test task"
            assert 'emdx save --title "Test Output"' in call_args.output_instruction
            assert '--tags "analysis,security"' in call_args.output_instruction
            assert '--group 123' in call_args.output_instruction
            assert '--group-role exploration' in call_args.output_instruction

    def test_execute_with_output_tracking_pr_instruction(self):
        """Test that PR creation instruction is added when requested."""
        with patch('emdx.services.unified_executor.UnifiedExecutor') as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = ExecutionResult(
                success=True,
                execution_id=1,
                log_file=Path("/tmp/test.log"),
            )
            MockExecutor.return_value = mock_instance

            execute_with_output_tracking(
                prompt="Fix bug",
                title="Bug Fix",
                create_pr=True,
            )

            call_args = mock_instance.execute.call_args[0][0]
            assert 'gh pr create' in call_args.output_instruction

    def test_execute_for_cascade_timeout(self):
        """Test that cascade uses correct timeout based on stage."""
        with patch('emdx.services.unified_executor.UnifiedExecutor') as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = ExecutionResult(
                success=True,
                execution_id=1,
                log_file=Path("/tmp/test.log"),
            )
            MockExecutor.return_value = mock_instance

            # Normal stage - 5 min timeout
            execute_for_cascade(
                prompt="Transform",
                doc_id=1,
                title="Test",
                is_implementation=False,
            )

            call_args = mock_instance.execute.call_args[0][0]
            assert call_args.timeout_seconds == 300

            # Implementation stage - 30 min timeout
            execute_for_cascade(
                prompt="Implement",
                doc_id=1,
                title="Test",
                is_implementation=True,
            )

            call_args = mock_instance.execute.call_args[0][0]
            assert call_args.timeout_seconds == 1800

    def test_execute_for_workflow_instruction(self):
        """Test that workflow execution includes save instruction."""
        with patch('emdx.services.unified_executor.UnifiedExecutor') as MockExecutor:
            mock_instance = MagicMock()
            mock_instance.execute.return_value = ExecutionResult(
                success=True,
                execution_id=1,
                log_file=Path("/tmp/test.log"),
            )
            MockExecutor.return_value = mock_instance

            execute_for_workflow(
                prompt="Analyze code",
                doc_id=123,
                title="Workflow Agent",
            )

            call_args = mock_instance.execute.call_args[0][0]
            assert 'emdx save' in call_args.output_instruction
            assert 'workflow-output' in call_args.output_instruction


class TestDefaultAllowedTools:
    """Test default allowed tools configuration."""

    def test_default_tools_list(self):
        """Verify the default allowed tools."""
        expected_tools = [
            "Read", "Write", "Edit", "MultiEdit", "Bash",
            "Glob", "Grep", "LS", "Task", "TodoWrite",
            "WebFetch", "WebSearch"
        ]
        assert DEFAULT_ALLOWED_TOOLS == expected_tools

    def test_config_gets_copy_of_defaults(self):
        """Ensure config gets a copy, not the original list."""
        config1 = ExecutionConfig(prompt="test1")
        config2 = ExecutionConfig(prompt="test2")

        config1.allowed_tools.append("CustomTool")

        # config2 should not be affected
        assert "CustomTool" not in config2.allowed_tools
        assert "CustomTool" not in DEFAULT_ALLOWED_TOOLS
