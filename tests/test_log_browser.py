"""Tests for log browser timestamp functionality."""

import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from emdx.models.executions import Execution
from emdx.ui.log_browser import LogBrowser


class TestLogBrowserTimestamps:
    """Test log browser timestamp display functionality."""

    @pytest.fixture
    def temp_log_file(self):
        """Create a temporary log file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            # Write sample log content with timestamps
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Version: 1.0.0\n")
            f.write("Doc ID: 123\n")
            f.write("Started: 2023-12-15 14:00:00\n")
            f.write("=" * 50 + "\n\n")
            f.write("[14:00:01] 🚀 Claude Code session started\n")
            f.write("[14:00:02] 📋 Available tools: Read, Write, Edit\n")
            f.write("[14:00:05] 🤖 Claude: Starting to analyze the code\n")
            f.write("[14:00:10] 📖 Using tool: Read\n")
            f.write("[14:00:15] 📄 Tool result: File content loaded\n")
            f.write("[14:00:20] 🤖 Claude: Found the issue in the code\n")
            f.write("[14:00:25] ✏️ Using tool: Edit\n")
            f.write("[14:00:30] ✅ Task completed successfully!\n")
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup after test
        if temp_path.exists():
            temp_path.unlink()

    @pytest.fixture
    def mock_execution(self, temp_log_file):
        """Create a mock execution object."""
        return Execution(
            id=1,
            doc_id=123,
            doc_title="Test Document",
            status="completed",
            started_at=datetime(2023, 12, 15, 14, 0, 0),
            completed_at=datetime(2023, 12, 15, 14, 0, 30),
            log_file=str(temp_log_file),
            working_dir="/tmp/test-worktree"
        )

    @pytest.mark.asyncio
    async def test_log_browser_preserves_timestamps(self, temp_log_file, mock_execution):
        """Test that log browser preserves original timestamps from log files."""
        # Create log browser instance
        browser = LogBrowser()

        # Mock the query_one method to return mock widgets
        mock_log_content = MagicMock()
        mock_log_content.clear = MagicMock()
        mock_log_content.write = MagicMock()
        mock_log_content.scroll_to = MagicMock()
        mock_log_content.scroll_end = MagicMock()

        mock_details_panel = MagicMock()
        mock_details_panel.clear = MagicMock()
        mock_details_panel.write = MagicMock()

        def mock_query_one(selector, widget_type):
            if selector == "#log-content":
                return mock_log_content
            elif selector == "#log-details":
                return mock_details_panel
            return MagicMock()

        browser.query_one = mock_query_one
        browser.live_mode = False

        # Load the execution log
        await browser.load_execution_log(mock_execution)

        # Verify that timestamps were preserved in the output
        write_calls = mock_log_content.write.call_args_list

        # Find timestamp-containing lines
        timestamp_lines = []
        for call in write_calls:
            if call[0][0] and isinstance(call[0][0], str) and "[14:" in call[0][0]:
                timestamp_lines.append(call[0][0])

        # Verify original timestamps are preserved
        assert any("[14:00:01]" in line for line in timestamp_lines)
        assert any("[14:00:05]" in line for line in timestamp_lines)
        assert any("[14:00:30]" in line for line in timestamp_lines)

        # Verify that current time is NOT used
        current_time = datetime.now().strftime("[%H:%M:")
        # Only check if not 14:00 (unlikely but possible in tests)
        if not current_time.startswith("[14:00:"):
            assert not any(current_time in line for line in timestamp_lines)

    @pytest.mark.asyncio
    async def test_log_browser_handles_missing_timestamps(self, mock_execution):
        """Test that log browser handles lines without timestamps gracefully."""
        # Create a log file with mixed content
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            f.write("[14:00:01] First line with timestamp\n")
            f.write("This line has no timestamp\n")
            f.write("[14:00:05] Another line with timestamp\n")
            f.write("Another line without timestamp\n")
            temp_file = Path(f.name)

        try:
            # Update execution to use this log file
            mock_execution.log_file = str(temp_file)

            # Create log browser instance
            browser = LogBrowser()

            # Mock the query_one method
            mock_log_content = MagicMock()
            mock_details_panel = MagicMock()

            def mock_query_one(selector, widget_type):
                if selector == "#log-content":
                    return mock_log_content
                elif selector == "#log-details":
                    return mock_details_panel
                return MagicMock()

            browser.query_one = mock_query_one
            browser.live_mode = False

            # Load the execution log
            await browser.load_execution_log(mock_execution)

            # Verify all lines were written (no exceptions)
            assert mock_log_content.write.call_count > 0

        finally:
            temp_file.unlink()

    def test_timestamp_continuity_across_lines(self):
        """Test that timestamps maintain continuity when missing."""
        from emdx.commands.claude_execute import parse_log_timestamp

        # Simulate processing multiple lines
        lines = [
            "[14:00:01] First line",
            "Continuation without timestamp",
            "[14:00:05] New timestamped line",
            "Another continuation",
            "[14:00:10] Final line"
        ]

        last_timestamp = None
        processed_timestamps = []

        for line in lines:
            parsed = parse_log_timestamp(line)
            if parsed:
                last_timestamp = parsed
            timestamp_to_use = parsed or last_timestamp or time.time()
            processed_timestamps.append(timestamp_to_use)

        # Verify timestamps are maintained
        assert processed_timestamps[0] == processed_timestamps[1]  # Continuation uses previous
        assert processed_timestamps[2] != processed_timestamps[0]  # New timestamp
        assert processed_timestamps[3] == processed_timestamps[2]  # Another continuation
        assert processed_timestamps[4] != processed_timestamps[2]  # Final new timestamp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
