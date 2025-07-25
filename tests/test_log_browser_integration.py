"""Integration tests for log browser timestamp preservation."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from textual.app import App
from textual.widgets import DataTable, RichLog

from emdx.models.executions import Execution
from emdx.ui.log_browser import LogBrowser


class MockApp(App):
    """Mock app for testing."""
    CSS = ""

    def compose(self):
        yield LogBrowser()


class TestLogBrowserIntegration:
    """Integration tests for log browser timestamp preservation."""

    @pytest.mark.asyncio
    async def test_log_browser_preserves_timestamps(self):
        """Test that log browser preserves timestamps when loading logs."""
        # Create a mock execution with a log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = Path(f.name)
            # Write log content with timestamps
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Version: 1.0.0\n")
            f.write("Build ID: test\n")
            f.write("Doc ID: 123\n")
            f.write("Execution ID: test-exec\n")
            f.write("Started: 2024-01-01 14:32:00\n")
            f.write("==================================================\n\n")
            f.write("[14:32:15] Starting execution\n")
            f.write('{"type": "text", "text": "Processing..."}\n')
            f.write("[14:32:16] Claude is working\n")
            f.write('{"type": "assistant", "message": '
                    '{"content": [{"type": "text", "text": "Done"}]}}\n')
            f.write("[14:32:17] Execution complete\n")

        try:
            # Create mock execution
            mock_execution = Execution(
                id=1,
                doc_id=123,
                doc_title="Test Document",
                log_file=str(log_file),
                working_dir="/tmp/test",
                status="completed",
                started_at=datetime(2024, 1, 1, 14, 32, 0),
                completed_at=datetime(2024, 1, 1, 14, 32, 17)
            )

            # Create log browser and test loading
            log_browser = LogBrowser()

            # Mock the RichLog widget
            mock_log_content = MagicMock(spec=RichLog)
            written_lines = []

            def mock_write(line):
                written_lines.append(line)

            mock_log_content.write = mock_write
            mock_log_content.clear = Mock()

            # Patch query_one to return our mock
            with patch.object(log_browser, 'query_one') as mock_query:
                def query_side_effect(selector, widget_type=None):
                    if selector == "#log-content":
                        return mock_log_content
                    elif selector == "#log-details":
                        return MagicMock(spec=RichLog)
                    return MagicMock()

                mock_query.side_effect = query_side_effect

                # Load the execution log
                await log_browser.load_execution_log(mock_execution)

            # Verify that timestamps were preserved
            # Should have the header and then formatted lines
            assert len(written_lines) > 0

            # Find the JSON lines and verify they have the correct timestamps
            json_lines = [line for line in written_lines if "🤖" in line or "Using tool" in line]

            # The JSON line after [14:32:15] should have [14:32:15] timestamp
            assert any("[14:32:15]" in line and "Processing..." in line for line in json_lines)

            # The JSON line after [14:32:16] should have [14:32:16] timestamp
            assert any("[14:32:16]" in line and "Done" in line for line in json_lines)

        finally:
            # Clean up
            log_file.unlink(missing_ok=True)

    def test_wrapper_noise_filtering(self):
        """Test that wrapper orchestration messages are filtered out."""
        log_browser = LogBrowser()

        # Test various wrapper noise patterns
        assert log_browser._is_wrapper_noise("🔄 Wrapper script started")
        assert log_browser._is_wrapper_noise("📋 Command: claude execute")
        assert log_browser._is_wrapper_noise("🚀 Starting Claude process...")
        assert log_browser._is_wrapper_noise("✅ Claude process finished")
        assert log_browser._is_wrapper_noise("📊 Updating execution status")
        assert log_browser._is_wrapper_noise("✅ Database updated successfully")
        assert log_browser._is_wrapper_noise(
            "────────────────────────────────────────────────────────────")

        # Test that actual content is not filtered
        assert not log_browser._is_wrapper_noise("[14:32:15] Real log entry")
        assert not log_browser._is_wrapper_noise("Processing user request")
        assert not log_browser._is_wrapper_noise('{"type": "text", "text": "Hello"}')

    @pytest.mark.asyncio
    async def test_live_mode_timestamp_preservation(self):
        """Test that timestamps are preserved in live mode."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = Path(f.name)
            # Initial log content
            f.write("[10:00:00] Initial log entry\n")

        try:
            mock_execution = Execution(
                id=1,
                doc_id=123,
                doc_title="Test Live",
                log_file=str(log_file),
                working_dir="/tmp/test",
                status="running",
                started_at=datetime.now()
            )

            log_browser = LogBrowser()
            log_browser.live_mode = True
            log_browser.executions = [mock_execution]

            # Mock components
            mock_log_content = MagicMock(spec=RichLog)
            written_lines = []

            def mock_write(line):
                written_lines.append(line)

            mock_log_content.write = mock_write
            mock_log_content.clear = Mock()
            mock_log_content.scroll_end = Mock()

            with patch.object(log_browser, 'query_one') as mock_query:
                def query_side_effect(selector, widget_type=None):
                    if selector == "#log-content":
                        return mock_log_content
                    elif selector == "#log-details":
                        return MagicMock(spec=RichLog)
                    elif selector == "#log-table":
                        mock_table = MagicMock(spec=DataTable)
                        mock_table.cursor_row = 0
                        return mock_table
                    return MagicMock()

                mock_query.side_effect = query_side_effect

                # Load initial content
                await log_browser.load_execution_log(mock_execution)
                # initial_lines = len(written_lines)  # Not used

                # Simulate new content being added
                with open(log_file, 'a') as f:
                    f.write("[10:00:05] New log entry\n")
                    f.write('{"type": "text", "text": "Live update"}\n')

                # Clear written lines and reload
                written_lines.clear()
                await log_browser.load_execution_log(mock_execution)

                # Verify new content has correct timestamps
                json_lines = [line for line in written_lines if "🤖" in line]
                assert any("[10:00:05]" in line and "Live update" in line for line in json_lines)

                # Verify scroll_end was called (live mode behavior)
                mock_log_content.scroll_end.assert_called()

        finally:
            log_file.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

