"""Integration tests for log browser timestamp display."""

import tempfile
from pathlib import Path
from datetime import datetime
import pytest
from unittest.mock import Mock, patch, MagicMock

from emdx.ui.log_browser import LogBrowser
from emdx.models.executions import Execution


class TestLogBrowserTimestampDisplay:
    """Test log browser preserves original timestamps."""
    
    @pytest.fixture
    def mock_execution(self):
        """Create a mock execution with a test log file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            # Write test log content with various timestamp formats
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Version: 1.0.0\n")
            f.write("Started: 2025-01-23 10:00:00 UTC\n")
            f.write("====================\n\n")
            f.write("[10:00:01] 🚀 Claude Code session started\n")
            f.write("[10:00:02] 📋 Available tools: Read, Write, Edit\n")
            f.write("[10:00:03] 🤖 Claude: Starting task execution\n")
            f.write("[10:00:05] 📖 Using tool: Read\n")
            f.write("Some output without timestamp\n")
            f.write("[10:00:10] ✅ Execution completed successfully\n")
            f.write("  [10:00:11] ⏱️  Duration: 10.0s\n")  # Indented timestamp
            
            log_file = f.name
        
        # Create mock execution
        execution = Mock(spec=Execution)
        execution.id = "test-123"
        execution.doc_title = "Test Document"
        execution.status = "completed"
        execution.started_at = datetime(2025, 1, 23, 10, 0, 0)
        execution.completed_at = datetime(2025, 1, 23, 10, 0, 11)
        execution.working_dir = "/test/dir"
        execution.log_file = log_file
        
        yield execution
        
        # Cleanup
        Path(log_file).unlink(missing_ok=True)
    
    @patch('emdx.ui.log_browser.get_recent_executions')
    async def test_preserves_original_timestamps(self, mock_get_executions, mock_execution):
        """Test that original timestamps are preserved in display."""
        mock_get_executions.return_value = [mock_execution]
        
        # Create log browser instance
        browser = LogBrowser()
        
        # Mock the RichLog widget
        mock_log_content = Mock()
        written_lines = []
        mock_log_content.write = lambda x: written_lines.append(x)
        mock_log_content.clear = Mock()
        
        # Mock query_one to return our mock widget
        browser.query_one = Mock(side_effect=lambda selector, widget_type: mock_log_content if selector == "#log-content" else Mock())
        
        # Load the execution log
        await browser.load_execution_log(mock_execution)
        
        # Check that timestamps were preserved
        timestamped_lines = [line for line in written_lines if line.strip().startswith('[')]
        
        # Verify original timestamps are present
        assert any('[10:00:01]' in line for line in timestamped_lines)
        assert any('[10:00:02]' in line for line in timestamped_lines)
        assert any('[10:00:03]' in line for line in timestamped_lines)
        assert any('[10:00:05]' in line for line in timestamped_lines)
        assert any('[10:00:10]' in line for line in timestamped_lines)
        assert any('[10:00:11]' in line for line in timestamped_lines)
        
        # Verify no current timestamps were generated
        # Current time would be very different from 10:00:xx
        import time
        current_hour = time.localtime().tm_hour
        if current_hour != 10:
            assert not any(f'[{current_hour:02d}:' in line for line in timestamped_lines)
    
    @patch('emdx.ui.log_browser.get_recent_executions')
    async def test_handles_mixed_content(self, mock_get_executions, mock_execution):
        """Test handling of lines with and without timestamps."""
        # Modify log content
        with open(mock_execution.log_file, 'w') as f:
            f.write("[09:00:00] First line with timestamp\n")
            f.write("Line without timestamp\n")
            f.write("Another line without timestamp\n")
            f.write("[09:00:05] Another timestamped line\n")
            f.write("JSON output: {\"type\": \"tool\", \"name\": \"Read\"}\n")
            f.write("[09:00:10] Final timestamped line\n")
        
        mock_get_executions.return_value = [mock_execution]
        
        browser = LogBrowser()
        mock_log_content = Mock()
        written_lines = []
        mock_log_content.write = lambda x: written_lines.append(x)
        mock_log_content.clear = Mock()
        browser.query_one = Mock(side_effect=lambda selector, widget_type: mock_log_content if selector == "#log-content" else Mock())
        
        await browser.load_execution_log(mock_execution)
        
        # Find lines in output
        output_text = '\n'.join(written_lines)
        
        # Timestamped lines should appear as-is
        assert "[09:00:00] First line with timestamp" in output_text
        assert "[09:00:05] Another timestamped line" in output_text
        assert "[09:00:10] Final timestamped line" in output_text
        
        # Non-timestamped lines should also appear
        assert "Line without timestamp" in output_text or any("Line without timestamp" in line for line in written_lines)
    
    async def test_empty_log_file(self):
        """Test handling of empty log file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = f.name
        
        execution = Mock(spec=Execution)
        execution.log_file = log_file
        execution.id = "empty-test"
        execution.doc_title = "Empty Test"
        execution.status = "running"
        execution.started_at = datetime.now()
        execution.completed_at = None
        execution.working_dir = "/test"
        
        browser = LogBrowser()
        mock_log_content = Mock()
        written_lines = []
        mock_log_content.write = lambda x: written_lines.append(x)
        mock_log_content.clear = Mock()
        browser.query_one = Mock(side_effect=lambda selector, widget_type: mock_log_content if selector == "#log-content" else Mock())
        
        await browser.load_execution_log(execution)
        
        # Should show "no content" message
        assert any("No log content yet" in line for line in written_lines)
        
        Path(log_file).unlink(missing_ok=True)