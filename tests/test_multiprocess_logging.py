"""Test multi-process logging scenarios."""
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from emdx.utils.claude_wrapper import log_to_file


class TestMultiProcessLogging:
    """Test multi-process logging scenarios."""

    def test_concurrent_log_writes(self, tmp_path):
        """Test that concurrent writes don't corrupt the log file."""
        log_file = tmp_path / "concurrent.log"
        
        def write_logs(process_id, count):
            """Write logs from a simulated process."""
            for i in range(count):
                log_to_file(log_file, f"Process {process_id}: Message {i}")
                time.sleep(0.001)  # Small delay to increase chance of interleaving
        
        # Start multiple threads writing to the same log
        threads = []
        for i in range(5):
            thread = threading.Thread(target=write_logs, args=(i, 20))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check log file integrity
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # Should have all lines
        assert len(lines) == 100  # 5 processes * 20 messages each
        
        # Each line should be complete (not corrupted)
        for line in lines:
            assert line.count('[') == 1  # One timestamp
            assert line.count(']') == 1
            assert "Process" in line
            assert "Message" in line

    def test_wrapper_as_sole_writer(self, tmp_path):
        """Test that wrapper is the sole writer to the log file."""
        log_file = tmp_path / "sole_writer.log"
        
        # Simulate parent process creating the file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Wrapper should clear and write its own header
        from emdx.utils.claude_wrapper import main
        
        # Mock subprocess to simulate a quick process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.stdout = iter(["Test output\n"])
        mock_process.wait.return_value = None
        
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("shutil.which", return_value="/usr/local/bin/claude"):
                with patch("emdx.models.executions.update_execution_status"):
                    test_args = ["wrapper.py", "123", str(log_file), "claude", "test"]
                    with patch.object(sys, "argv", test_args):
                        with pytest.raises(SystemExit):
                            main()
        
        # Check that log file has clean wrapper-written content
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # First line should be the header
        assert lines[0] == "=== EMDX Execution #123 ==="
        assert any("Started:" in line for line in lines)
        assert any("Wrapper PID:" in line for line in lines)

    def test_log_file_locking_simulation(self, tmp_path):
        """Test that log writes are atomic at the OS level."""
        log_file = tmp_path / "atomic.log"
        
        # Write a large message that might not be atomic
        large_message = "X" * 10000  # 10KB message
        
        def write_large_logs(process_id):
            """Write large log entries."""
            for i in range(10):
                log_to_file(log_file, f"Process {process_id}: {large_message}")
        
        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=write_large_logs, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check that all lines are complete
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        assert len(lines) == 30  # 3 processes * 10 messages
        
        # Each line should have the full message
        for line in lines:
            # Extract the message part after "Process N: "
            if "Process" in line:
                msg_start = line.find(": X")
                if msg_start > 0:
                    message_part = line[msg_start + 2:]  # Skip ": "
                    assert len(message_part) == 10000

    def test_log_rotation_not_needed(self, tmp_path):
        """Test that log files don't grow unbounded."""
        log_file = tmp_path / "size_test.log"
        
        # Write many messages
        for i in range(1000):
            log_to_file(log_file, f"Message {i}: " + "A" * 100)
        
        # Check file size
        size = log_file.stat().st_size
        
        # Should be reasonable (less than 200KB for 1000 lines)
        assert size < 200 * 1024
        
        # All messages should be present
        content = log_file.read_text()
        assert "Message 0:" in content
        assert "Message 999:" in content

    @patch("builtins.open")
    def test_file_write_error_handling(self, mock_open, tmp_path):
        """Test handling of file write errors."""
        log_file = tmp_path / "error.log"
        
        # Mock file write to fail
        mock_open.side_effect = IOError("Disk full")
        
        with patch("builtins.print") as mock_print:
            log_to_file(log_file, "Test message")
            
            # Should print error to stderr
            mock_print.assert_called_once()
            assert "Failed to write to log" in str(mock_print.call_args)

    def test_unicode_in_logs(self, tmp_path):
        """Test that unicode characters are handled correctly."""
        log_file = tmp_path / "unicode.log"
        
        # Write various unicode characters
        test_strings = [
            "Normal ASCII text",
            "Emojis: 🚀 ✅ ❌ 📊 ⏱️",
            "Chinese: 你好世界",
            "Arabic: مرحبا بالعالم",
            "Special chars: →←↑↓♠♣♥♦",
        ]
        
        for msg in test_strings:
            log_to_file(log_file, msg)
        
        # Read back and verify
        content = log_file.read_text(encoding='utf-8')
        
        for msg in test_strings:
            assert msg in content

    def test_log_timestamp_ordering(self, tmp_path):
        """Test that timestamps are in correct order."""
        log_file = tmp_path / "timestamp.log"
        
        # Write messages with small delays
        timestamps = []
        for i in range(10):
            log_to_file(log_file, f"Message {i}")
            time.sleep(0.01)  # 10ms delay
        
        # Parse timestamps from log
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        for line in lines:
            # Extract timestamp [HH:MM:SS]
            if line.startswith('[') and ']' in line:
                timestamp = line[1:line.index(']')]
                timestamps.append(timestamp)
        
        # Verify timestamps are in order
        for i in range(1, len(timestamps)):
            # Simple string comparison works for HH:MM:SS format
            assert timestamps[i] >= timestamps[i-1]

    def test_wrapper_clears_existing_content(self, tmp_path):
        """Test that wrapper clears any existing log content."""
        log_file = tmp_path / "clear_test.log"
        
        # Write some initial content
        log_file.write_text("Old content that should be cleared\n")
        
        # Run wrapper
        from emdx.utils.claude_wrapper import main
        
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.returncode = 0
        mock_process.stdout = iter([])
        mock_process.wait.return_value = None
        
        with patch("subprocess.Popen", return_value=mock_process):
            with patch("shutil.which", return_value="/usr/local/bin/claude"):
                with patch("emdx.models.executions.update_execution_status"):
                    test_args = ["wrapper.py", "555", str(log_file), "claude", "test"]
                    with patch.object(sys, "argv", test_args):
                        with pytest.raises(SystemExit):
                            main()
        
        # Check that old content is gone
        content = log_file.read_text()
        assert "Old content" not in content
        assert "=== EMDX Execution #555 ===" in content