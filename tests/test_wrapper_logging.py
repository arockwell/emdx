"""Test the claude wrapper logging functionality."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from emdx.utils.claude_wrapper import format_timestamp, log_to_file, main


class TestWrapperLogging:
    """Test wrapper logging functionality."""

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        timestamp = format_timestamp()
        # Should be in format [HH:MM:SS]
        assert timestamp.startswith("[")
        assert timestamp.endswith("]")
        assert len(timestamp) == 10  # [HH:MM:SS]
        assert timestamp[3] == ":"
        assert timestamp[6] == ":"

    def test_log_to_file(self, tmp_path):
        """Test logging to file."""
        log_file = tmp_path / "test.log"
        
        # Test basic logging
        log_to_file(log_file, "Test message")
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content
        assert "[" in content  # Should have timestamp
        
        # Test appending
        log_to_file(log_file, "Second message")
        content = log_file.read_text()
        assert "Test message" in content
        assert "Second message" in content
        
    def test_log_to_file_error_handling(self):
        """Test logging error handling."""
        # Try to write to a read-only directory
        with patch("builtins.open", side_effect=PermissionError):
            with patch("builtins.print") as mock_print:
                log_to_file(Path("/nonexistent/file.log"), "Test")
                # Should print to stderr
                mock_print.assert_called_once()
                assert "Failed to write to log" in str(mock_print.call_args)

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_main_success(self, mock_update_status, mock_popen, tmp_path):
        """Test successful wrapper execution."""
        log_file = tmp_path / "test.log"
        
        # Mock the subprocess
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.stdout = iter(["Line 1\n", "Line 2\n"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        
        # Mock shutil.which to find claude
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            # Simulate command line args
            test_args = ["wrapper.py", "123", str(log_file), "claude", "test"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with success code
                assert exc_info.value.code == 0
        
        # Check log file content
        content = log_file.read_text()
        assert "=== EMDX Execution #123 ===" in content
        assert "Started:" in content
        assert "Wrapper PID:" in content
        assert "Working Directory:" in content
        assert "🚀 Starting Claude process..." in content
        assert "✅ Claude process completed" in content
        assert "📊 Exit code: 0" in content
        
        # Check database update was called
        mock_update_status.assert_called_with(123, "completed", 0)

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_main_failure(self, mock_update_status, mock_popen, tmp_path):
        """Test wrapper execution with failure."""
        log_file = tmp_path / "test.log"
        
        # Mock the subprocess to fail
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 1
        mock_process.stdout = iter(["Error occurred\n"])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        
        # Mock shutil.which to find claude
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            # Simulate command line args
            test_args = ["wrapper.py", "456", str(log_file), "claude", "test"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with failure code
                assert exc_info.value.code == 1
        
        # Check log file content
        content = log_file.read_text()
        assert "📊 Exit code: 1" in content
        
        # Check database update was called with failed status
        mock_update_status.assert_called_with(456, "failed", 1)

    @patch("shutil.which", return_value=None)
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_command_not_found(self, mock_update_status, tmp_path):
        """Test wrapper when claude command is not found."""
        log_file = tmp_path / "test.log"
        
        # Simulate command line args
        test_args = ["wrapper.py", "789", str(log_file), "claude", "test"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            # Should exit with command not found code
            assert exc_info.value.code == 127
        
        # Check log file content
        content = log_file.read_text()
        assert "❌ Command 'claude' not found in PATH" in content
        assert "💡 PATH:" in content
        
        # Check database update was called
        mock_update_status.assert_called_with(789, "failed", 127)

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_timeout(self, mock_update_status, mock_popen, tmp_path):
        """Test wrapper timeout handling."""
        log_file = tmp_path / "test.log"
        
        # Mock subprocess to raise timeout
        mock_popen.side_effect = subprocess.TimeoutExpired("claude", 30)
        
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            test_args = ["wrapper.py", "111", str(log_file), "claude", "test"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with timeout code
                assert exc_info.value.code == 124
        
        # Check log file content
        content = log_file.read_text()
        assert "⏱️ Process timed out" in content
        
        # Check database update
        mock_update_status.assert_called_with(111, "failed", 124)

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_keyboard_interrupt(self, mock_update_status, mock_popen, tmp_path):
        """Test wrapper keyboard interrupt handling."""
        log_file = tmp_path / "test.log"
        
        # Mock subprocess to raise KeyboardInterrupt
        mock_popen.side_effect = KeyboardInterrupt()
        
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            test_args = ["wrapper.py", "222", str(log_file), "claude", "test"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should exit with SIGINT code
                assert exc_info.value.code == 130
        
        # Check log file content
        content = log_file.read_text()
        assert "⚠️ Process interrupted by user" in content
        
        # Check database update
        mock_update_status.assert_called_with(222, "failed", 130)

    def test_wrapper_invalid_args(self):
        """Test wrapper with invalid arguments."""
        # Not enough arguments
        test_args = ["wrapper.py", "123"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            # Should exit with error code
            assert exc_info.value.code == 1

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status")
    def test_wrapper_process_tracking(self, mock_update_status, mock_popen, tmp_path):
        """Test that wrapper properly tracks process information."""
        log_file = tmp_path / "test.log"
        
        # Mock the subprocess
        mock_process = Mock()
        mock_process.pid = 54321
        mock_process.returncode = 0
        mock_process.stdout = iter([])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            with patch("os.getpid", return_value=11111):
                test_args = ["wrapper.py", "333", str(log_file), "claude", "test"]
                with patch.object(sys, "argv", test_args):
                    with pytest.raises(SystemExit):
                        main()
        
        # Check log file content for process tracking
        content = log_file.read_text()
        assert "Wrapper PID: 11111" in content
        assert "🔍 Claude process started with PID: 54321" in content
        assert "🔍 Parent (wrapper) PID: 11111" in content

    @patch("subprocess.Popen")
    @patch("emdx.models.executions.update_execution_status", side_effect=Exception("DB Error"))
    def test_wrapper_db_update_failure(self, mock_update_status, mock_popen, tmp_path):
        """Test wrapper continues even if database update fails."""
        log_file = tmp_path / "test.log"
        
        # Mock successful subprocess
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.stdout = iter([])
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            test_args = ["wrapper.py", "444", str(log_file), "claude", "test"]
            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                
                # Should still exit with subprocess exit code
                assert exc_info.value.code == 0
        
        # Check log file shows DB error
        content = log_file.read_text()
        assert "❌ Failed to update database: DB Error" in content
        assert "✅ Claude process completed" in content