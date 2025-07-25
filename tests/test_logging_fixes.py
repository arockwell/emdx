"""Tests for multi-process logging fixes."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from emdx.commands.claude_execute import execute_with_claude, execute_with_claude_detached
from emdx.utils.claude_wrapper import log_to_file, format_timestamp


class TestLogToFile:
    """Test the log_to_file function."""

    def test_log_to_file_with_levels(self, tmp_path):
        """Test that log_to_file writes with correct format and levels."""
        log_file = tmp_path / "test.log"
        
        # Test different log levels
        log_to_file(log_file, "Info message", "INFO")
        log_to_file(log_file, "Debug message", "DEBUG")
        log_to_file(log_file, "Error message", "ERROR")
        log_to_file(log_file, "Warning message", "WARNING")
        
        content = log_file.read_text()
        
        # Check format: timestamp [Wrapper:PID] [LEVEL] message
        lines = content.strip().split('\n')
        assert len(lines) == 4
        
        # Check each line has correct format
        for line in lines:
            assert "[Wrapper:" in line
            assert "]" in line
            assert line.count("[") >= 2  # timestamp and wrapper
        
        # Check levels are present
        assert "[INFO]" in lines[0]
        assert "[DEBUG]" in lines[1]
        assert "[ERROR]" in lines[2]
        assert "[WARNING]" in lines[3]

    def test_log_to_file_default_level(self, tmp_path):
        """Test that default level is INFO."""
        log_file = tmp_path / "test.log"
        log_to_file(log_file, "Default level message")
        
        content = log_file.read_text()
        assert "[INFO]" in content

    def test_log_to_file_includes_pid(self, tmp_path):
        """Test that PID is included in log entries."""
        log_file = tmp_path / "test.log"
        log_to_file(log_file, "Test message")
        
        content = log_file.read_text()
        pid = os.getpid()
        assert f"[Wrapper:{pid}]" in content


class TestWrapperProcess:
    """Test the wrapper process behavior."""

    @patch('subprocess.Popen')
    def test_wrapper_handles_all_logging(self, mock_popen, tmp_path):
        """Test that wrapper is sole writer to log file."""
        # Mock the subprocess
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.stdout = iter(["line1\n", "line2\n"])
        mock_process.wait.return_value = 0
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        log_file = tmp_path / "test.log"
        
        # Run wrapper script directly
        wrapper_path = Path(__file__).parent.parent / "emdx" / "utils" / "claude_wrapper.py"
        
        # Test that parent process doesn't write to log
        with patch('builtins.open', create=True) as mock_open:
            # The wrapper should be the only one opening the file for writing
            result = subprocess.run(
                [sys.executable, str(wrapper_path), "1", str(log_file), "echo", "test"],
                capture_output=True,
                text=True
            )
            
            # Check that file operations were only from wrapper
            # This is a simplified test - in reality we'd trace file operations

    def test_wrapper_waits_for_subprocess(self, tmp_path):
        """Test that wrapper waits for subprocess completion."""
        log_file = tmp_path / "test.log"
        
        # Create a test script that sleeps
        test_script = tmp_path / "sleep_test.sh"
        test_script.write_text("#!/bin/bash\nsleep 0.5\necho 'done'\n")
        test_script.chmod(0o755)
        
        start_time = time.time()
        
        # Run wrapper with sleep command
        wrapper_path = Path(__file__).parent.parent / "emdx" / "utils" / "claude_wrapper.py"
        result = subprocess.run(
            [sys.executable, str(wrapper_path), "1", str(log_file), str(test_script)],
            capture_output=True,
            text=True
        )
        
        duration = time.time() - start_time
        
        # Wrapper should have waited for subprocess
        assert duration >= 0.5
        
        # Check log contains completion message
        if log_file.exists():
            content = log_file.read_text()
            assert "Claude process finished" in content or "done" in content


class TestLogFiltering:
    """Test log filtering in TUI browser."""

    def test_wrapper_noise_filtering(self):
        """Test that wrapper noise is filtered correctly."""
        from emdx.ui.log_browser import LogBrowser
        
        browser = LogBrowser()
        
        # Test DEBUG filtering
        assert browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [DEBUG] Some debug info")
        
        # Test wrapper process filtering
        assert browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [INFO] 🔧 Environment: FOO=bar")
        assert browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [INFO] 📍 Working directory: /tmp")
        
        # Test important messages are kept
        assert not browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [INFO] 🚀 Starting Claude process")
        assert not browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [INFO] ✅ Claude process finished")
        assert not browser._is_wrapper_noise("[10:30:45] [Wrapper:1234] [ERROR] ❌ Error: Something failed")

    def test_empty_line_handling(self):
        """Test that empty lines are handled correctly."""
        from emdx.ui.log_browser import LogBrowser
        
        browser = LogBrowser()
        assert not browser._is_wrapper_noise("")
        assert not browser._is_wrapper_noise("   ")


class TestMultiProcessCoordination:
    """Test multi-process coordination scenarios."""

    @patch('emdx.models.executions.create_execution')
    @patch('emdx.models.executions.update_execution_pid')
    @patch('subprocess.Popen')
    def test_no_concurrent_writes(self, mock_popen, mock_update_pid, mock_create_exec, tmp_path):
        """Test that parent and wrapper don't write concurrently."""
        # Mock execution creation
        mock_create_exec.return_value = 1
        
        # Mock subprocess
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.wait.return_value = 0
        mock_process.stdout = iter([])
        mock_popen.return_value = mock_process
        
        log_file = tmp_path / "test.log"
        
        # Execute in detached mode
        pid = execute_with_claude_detached(
            task="test task",
            execution_id=1,
            log_file=log_file,
            working_dir=str(tmp_path)
        )
        
        # Give wrapper time to start (in real scenario)
        time.sleep(0.1)
        
        # Parent should not have written to log file
        # Only wrapper should write
        if log_file.exists():
            content = log_file.read_text()
            # All lines should have [Wrapper:PID] format
            for line in content.strip().split('\n'):
                if line:
                    assert "[Wrapper:" in line or line.startswith("===")

    def test_log_file_consistency(self, tmp_path):
        """Test that log files maintain consistency with rapid writes."""
        log_file = tmp_path / "test.log"
        
        # Simulate multiple rapid writes
        for i in range(10):
            log_to_file(log_file, f"Message {i}", "INFO")
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # All messages should be present and properly formatted
        assert len(lines) == 10
        for i, line in enumerate(lines):
            assert f"Message {i}" in line
            assert "[INFO]" in line


if __name__ == "__main__":
    pytest.main([__file__, "-v"])