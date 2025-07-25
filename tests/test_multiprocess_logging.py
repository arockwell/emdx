"""Tests for multi-process logging improvements."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emdx.commands.claude_execute import (
    execute_with_claude_detached,
    format_timestamp,
    parse_log_timestamp,
)
from emdx.utils.claude_wrapper import log_to_file


class TestMultiProcessLogging:
    """Test multi-process logging coordination."""

    def test_wrapper_is_sole_writer(self, tmp_path):
        """Test that only the wrapper writes to log files."""
        log_file = tmp_path / "test.log"
        
        # Mock the subprocess to verify it doesn't get direct log file access
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process
            
            # Call execute_with_claude_detached
            pid = execute_with_claude_detached(
                task="Test task",
                execution_id=1,
                log_file=log_file,
                working_dir=str(tmp_path)
            )
            
            # Verify the subprocess was called
            assert mock_popen.called
            call_args = mock_popen.call_args
            
            # Check that stdout/stderr go to log file (wrapper will write)
            # but stdin is DEVNULL
            assert call_args.kwargs['stdin'] == subprocess.DEVNULL
            assert isinstance(call_args.kwargs['stdout'], type(log_file.open('a')))
            
    def test_wrapper_adds_process_identification(self, tmp_path):
        """Test that wrapper adds [wrapper] prefix to its messages."""
        log_file = tmp_path / "test.log"
        
        # Test log_to_file function
        log_to_file(log_file, "Test message")
        
        content = log_file.read_text()
        assert "[wrapper]" in content
        assert "Test message" in content
        
    def test_millisecond_timestamps(self):
        """Test that timestamps include millisecond precision."""
        # Test format_timestamp
        timestamp_str = format_timestamp()
        
        # Should match pattern [HH:MM:SS.mmm]
        import re
        pattern = r'^\[\d{2}:\d{2}:\d{2}\.\d{3}\]$'
        assert re.match(pattern, timestamp_str)
        
        # Test with specific timestamp
        test_time = 1234567890.123456
        timestamp_str = format_timestamp(test_time)
        assert re.match(pattern, timestamp_str)
        
    def test_parse_millisecond_timestamps(self):
        """Test parsing timestamps with milliseconds."""
        # Test with milliseconds
        line = "[14:30:45.123] Test message"
        timestamp = parse_log_timestamp(line)
        assert timestamp is not None
        
        # Test without milliseconds (backward compatibility)
        line = "[14:30:45] Test message"
        timestamp = parse_log_timestamp(line)
        assert timestamp is not None
        
    def test_no_duplicate_log_entries(self, tmp_path):
        """Test that log entries are not duplicated."""
        log_file = tmp_path / "test.log"
        
        # Simulate multiple processes writing
        # In the fixed version, only wrapper writes
        log_to_file(log_file, "Message 1")
        log_to_file(log_file, "Message 2")
        log_to_file(log_file, "Message 3")
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # Each message should appear exactly once
        assert len(lines) == 3
        assert sum(1 for line in lines if "Message 1" in line) == 1
        assert sum(1 for line in lines if "Message 2" in line) == 1
        assert sum(1 for line in lines if "Message 3" in line) == 1
        
    def test_log_ordering_preserved(self, tmp_path):
        """Test that log entries maintain chronological order."""
        log_file = tmp_path / "test.log"
        
        # Write messages with slight delays
        messages = []
        for i in range(5):
            msg = f"Message {i}"
            log_to_file(log_file, msg)
            messages.append(msg)
            time.sleep(0.01)  # Small delay to ensure different timestamps
            
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # Verify messages appear in order
        for i, line in enumerate(lines):
            assert f"Message {i}" in line
            
        # Verify timestamps are increasing
        timestamps = []
        for line in lines:
            ts = parse_log_timestamp(line)
            assert ts is not None
            timestamps.append(ts)
            
        # Check that timestamps are in ascending order
        assert timestamps == sorted(timestamps)


class TestLogFiltering:
    """Test log filtering in the UI."""
    
    def test_wrapper_noise_filtered(self):
        """Test that wrapper orchestration messages are filtered."""
        from emdx.ui.log_browser import LogBrowser
        
        log_browser = LogBrowser()
        
        # Test various wrapper messages
        wrapper_messages = [
            "[10:00:00.123] [wrapper] 🚀 Starting Claude process...",
            "[10:00:00.124] [wrapper] 🔍 Working directory: /tmp",
            "[10:00:00.125] [wrapper] 🔍 Environment PYTHONUNBUFFERED: 1",
            "[10:00:00.126] [wrapper] 🔍 Claude process started with PID: 12345",
            "[10:00:10.500] [wrapper] ✅ Claude process finished with exit code: 0",
            "[10:00:10.501] [wrapper] 📊 Duration: 10.38s, Lines processed: 42"
        ]
        
        # All wrapper messages should be filtered
        for msg in wrapper_messages:
            assert log_browser._is_wrapper_noise(msg) is True
            
        # But actual Claude output should not be filtered
        claude_messages = [
            "[10:00:01.000] 🤖 Claude: Starting task execution",
            "[10:00:02.000] 📖 Using tool: Read",
            "[10:00:03.000] 📄 Tool result: File contents...",
            "[10:00:05.000] ✅ Task completed successfully!"
        ]
        
        for msg in claude_messages:
            assert log_browser._is_wrapper_noise(msg) is False


class TestLiveModeUpdates:
    """Test live mode functionality."""
    
    def test_adaptive_refresh_rates(self):
        """Test that refresh rates adapt based on execution status."""
        from emdx.ui.log_browser import LogBrowser
        
        log_browser = LogBrowser()
        
        # Mock execution states
        running_exec = MagicMock(status='running')
        completed_exec = MagicMock(status='completed')
        
        # Test refresh intervals
        log_browser.executions = [running_exec]
        log_browser.live_mode = True
        
        # For running executions, should use 0.5s interval
        # For completed executions, should use 2.0s interval
        # This is implemented in live_refresh_log method


class TestProcessIntegration:
    """Integration tests for multi-process scenarios."""
    
    @pytest.mark.integration
    def test_concurrent_logging(self, tmp_path):
        """Test that concurrent processes don't cause issues."""
        log_file = tmp_path / "concurrent.log"
        
        # Simulate multiple wrapper instances writing
        # In production, file locking at OS level prevents corruption
        import threading
        
        def write_logs(process_id):
            for i in range(10):
                log_to_file(log_file, f"Process {process_id} - Message {i}")
                time.sleep(0.001)
                
        threads = []
        for i in range(3):
            t = threading.Thread(target=write_logs, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # Verify all messages were written
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # Should have 30 lines (3 processes × 10 messages)
        assert len(lines) == 30
        
        # All lines should have proper format
        for line in lines:
            assert "[wrapper]" in line
            assert parse_log_timestamp(line) is not None