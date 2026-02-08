"""Tests for the UnifiedExecutor service."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from emdx.services.unified_executor import (
    UnifiedExecutor,
    ExecutionConfig,
    ExecutionResult,
    DEFAULT_ALLOWED_TOOLS,
)


class TestExecutionConfig:
    """Test ExecutionConfig dataclass."""

    def test_default_values(self):
        config = ExecutionConfig(prompt="test prompt")
        assert config.prompt == "test prompt"
        assert config.timeout_seconds == 300
        assert config.allowed_tools == DEFAULT_ALLOWED_TOOLS
        assert config.output_instruction is None
        assert config.doc_id is None
        assert config.title == "CLI Execution"

    def test_custom_values(self):
        config = ExecutionConfig(
            prompt="custom prompt",
            title="Custom Title",
            doc_id=123,
            timeout_seconds=600,
            output_instruction="Save with emdx save",
            allowed_tools=["Read", "Write"],
        )
        assert config.prompt == "custom prompt"
        assert config.title == "Custom Title"
        assert config.doc_id == 123
        assert config.timeout_seconds == 600
        assert config.output_instruction == "Save with emdx save"
        assert config.allowed_tools == ["Read", "Write"]

    def test_working_dir_default(self):
        config = ExecutionConfig(prompt="test")
        assert config.working_dir == str(Path.cwd())


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            output_doc_id=456,
            tokens_used=1000,
        )
        assert result.success is True
        assert result.execution_id == 1
        assert result.output_doc_id == 456
        assert result.error_message is None

    def test_failure_result(self):
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


class TestUnifiedExecutor:
    """Test UnifiedExecutor."""

    def test_default_log_dir(self):
        executor = UnifiedExecutor()
        expected = Path.home() / ".config" / "emdx" / "logs"
        assert executor.log_dir == expected

    def test_custom_log_dir(self, tmp_path):
        custom_dir = tmp_path / "custom_logs"
        executor = UnifiedExecutor(log_dir=custom_dir)
        assert executor.log_dir == custom_dir
        assert custom_dir.exists()

    @patch('subprocess.Popen')
    @patch('emdx.services.unified_executor.get_cli_executor')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    def test_execution_success(
        self, mock_update_status, mock_create_exec, mock_get_executor, mock_popen, tmp_path,
    ):
        from emdx.services.cli_executor.base import CliCommand, CliResult

        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.validate_environment.return_value = (True, {})
        mock_executor.build_command.return_value = CliCommand(args=["claude", "--print-prompt"], cwd=str(tmp_path))
        mock_executor.parse_output.return_value = CliResult(success=True, output='Done', exit_code=0)
        mock_get_executor.return_value = mock_executor

        # Setup mock process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ['']  # No output
        mock_process.poll.return_value = 0
        mock_process.stdout.__iter__ = lambda self: iter([])
        mock_process.stderr.read.return_value = ''
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        mock_create_exec.return_value = 42

        executor = UnifiedExecutor(log_dir=tmp_path)
        result = executor.execute(ExecutionConfig(prompt="test task"))

        assert result.success is True
        assert result.execution_id == 42
        mock_update_status.assert_called_with(42, 'completed', 0)

    @patch('subprocess.Popen')
    @patch('emdx.services.unified_executor.get_cli_executor')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    def test_execution_failure(
        self, mock_update_status, mock_create_exec, mock_get_executor, mock_popen, tmp_path,
    ):
        from emdx.services.cli_executor.base import CliCommand, CliResult

        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.validate_environment.return_value = (True, {})
        mock_executor.build_command.return_value = CliCommand(args=["claude", "--print-prompt"], cwd=str(tmp_path))
        mock_executor.parse_output.return_value = CliResult(success=False, output='', error='Failed', exit_code=1)
        mock_get_executor.return_value = mock_executor

        # Setup mock process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ['']
        mock_process.poll.return_value = 1
        mock_process.stdout.__iter__ = lambda self: iter([])
        mock_process.stderr.read.return_value = ''
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        mock_create_exec.return_value = 42

        executor = UnifiedExecutor(log_dir=tmp_path)
        result = executor.execute(ExecutionConfig(prompt="test task"))

        assert result.success is False
        assert result.error_message == 'Failed'
        mock_update_status.assert_called_with(42, 'failed', 1)

    @patch('subprocess.Popen')
    @patch('emdx.services.unified_executor.get_cli_executor')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    def test_output_instruction_appended(
        self, mock_update_status, mock_create_exec, mock_get_executor, mock_popen, tmp_path,
    ):
        from emdx.services.cli_executor.base import CliCommand, CliResult

        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.validate_environment.return_value = (True, {})
        mock_executor.build_command.return_value = CliCommand(args=["claude", "--print-prompt"], cwd=str(tmp_path))
        mock_executor.parse_output.return_value = CliResult(success=True, output='Done', exit_code=0)
        mock_get_executor.return_value = mock_executor

        # Setup mock process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ['']
        mock_process.poll.return_value = 0
        mock_process.stdout.__iter__ = lambda self: iter([])
        mock_process.stderr.read.return_value = ''
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        mock_create_exec.return_value = 1

        executor = UnifiedExecutor(log_dir=tmp_path)
        config = ExecutionConfig(prompt="Base", output_instruction="\n\nSave it")
        executor.execute(config)

        # Verify the prompt was passed to build_command with instruction appended
        call_args = mock_executor.build_command.call_args
        assert "Base" in call_args.kwargs['prompt']
        assert "Save it" in call_args.kwargs['prompt']

    @patch('subprocess.Popen')
    @patch('emdx.services.unified_executor.get_cli_executor')
    @patch('emdx.services.unified_executor.create_execution')
    @patch('emdx.services.unified_executor.update_execution_status')
    def test_exception_handling(
        self, mock_update_status, mock_create_exec, mock_get_executor, mock_popen, tmp_path,
    ):
        from emdx.services.cli_executor.base import CliCommand

        # Setup mock executor
        mock_executor = MagicMock()
        mock_executor.validate_environment.return_value = (True, {})
        mock_executor.build_command.return_value = CliCommand(args=["claude", "--print-prompt"], cwd=str(tmp_path))
        mock_get_executor.return_value = mock_executor

        # Make Popen raise an exception
        mock_popen.side_effect = Exception("Unexpected")

        mock_create_exec.return_value = 42

        executor = UnifiedExecutor(log_dir=tmp_path)
        result = executor.execute(ExecutionConfig(prompt="test"))

        assert result.success is False
        assert "Unexpected" in result.error_message
        mock_update_status.assert_called_with(42, 'failed', -1)


class TestDefaultAllowedTools:
    """Test default allowed tools."""

    def test_default_tools_list(self):
        expected = ["Bash", "Edit", "Glob", "Grep", "LS", "MultiEdit", "Read", "Task", "TodoRead", "TodoWrite", "WebFetch", "WebSearch", "Write"]
        assert DEFAULT_ALLOWED_TOOLS == expected

    def test_config_gets_copy(self):
        config1 = ExecutionConfig(prompt="test1")
        config2 = ExecutionConfig(prompt="test2")
        config1.allowed_tools.append("Custom")
        assert "Custom" not in config2.allowed_tools
        assert "Custom" not in DEFAULT_ALLOWED_TOOLS
