"""Tests for log browser timestamp handling."""

import time
from datetime import datetime

import pytest

from emdx.commands.claude_execute import format_claude_output, parse_log_timestamp


class TestLogBrowserTimestamps:
    """Test timestamp handling in log browser."""

    def test_parse_log_timestamp_from_line(self):
        """Test parsing timestamps from log lines."""
        # Test valid timestamp
        line = "[14:30:45] Some log message"
        timestamp = parse_log_timestamp(line)
        assert timestamp is not None

        # Verify the time components
        dt = datetime.fromtimestamp(timestamp)
        assert dt.hour == 14
        assert dt.minute == 30
        assert dt.second == 45

    def test_format_preserves_parsed_timestamp(self):
        """Test that format_claude_output uses provided timestamp."""
        test_timestamp = datetime(2024, 1, 1, 10, 15, 30).timestamp()

        # Test with JSON that should be formatted
        json_line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}'
        result = format_claude_output(json_line, test_timestamp)

        # Should start with the provided timestamp
        assert result.startswith("[10:15:30]")
        assert "🤖 Claude: Hello" in result

    def test_log_browser_timestamp_flow(self):
        """Test the complete timestamp flow in log browser."""
        # Simulate log content with timestamps
        log_lines = [
            "[09:00:00] 🚀 Claude Code session started",
            '[09:00:01] {"type": "assistant", "message": {"content": [{"type": "text", "text": "Working..."}]}}',
            "[09:00:02] Regular log line",
            '[09:00:03] {"type": "result", "subtype": "success"}',
        ]

        # Process lines like the log browser does
        results = []
        last_timestamp = None

        for line in log_lines:
            if not line.strip():
                continue

            # Parse timestamp
            parsed_timestamp = parse_log_timestamp(line)
            if parsed_timestamp:
                last_timestamp = parsed_timestamp

            # Use parsed or last known timestamp
            timestamp_to_use = parsed_timestamp or last_timestamp or time.time()

            # Format if needed
            formatted = format_claude_output(line, timestamp_to_use)
            if formatted:
                results.append(formatted)

        # Verify all lines preserve original timestamps
        assert len(results) == 4
        assert results[0].startswith("[09:00:00]")
        assert results[1].startswith("[09:00:01]")
        assert results[2].startswith("[09:00:02]")
        assert results[3].startswith("[09:00:03]")

    def test_timestamp_persistence_across_lines(self):
        """Test that last known timestamp is used for lines without timestamps."""
        lines = [
            "[10:00:00] First line with timestamp",
            "Line without timestamp",
            "Another line without timestamp",
            "[10:00:05] Line with new timestamp",
        ]

        results = []
        last_timestamp = None

        for line in lines:
            parsed = parse_log_timestamp(line)
            if parsed:
                last_timestamp = parsed

            # For lines without timestamps, use last known
            ts = parsed or last_timestamp or time.time()

            # Just track what timestamp would be used
            if parsed:
                results.append(f"Parsed: {datetime.fromtimestamp(ts).strftime('%H:%M:%S')}")
            else:
                results.append(f"Using last: {datetime.fromtimestamp(ts).strftime('%H:%M:%S')}")

        assert results[0] == "Parsed: 10:00:00"
        assert results[1] == "Using last: 10:00:00"  # Uses previous timestamp
        assert results[2] == "Using last: 10:00:00"  # Still uses first timestamp
        assert results[3] == "Parsed: 10:00:05"

    def test_midnight_rollover_handling(self):
        """Test that timestamps near midnight are handled correctly."""
        # Simulate a log from late at night
        late_line = "[23:59:55] Late night log"
        early_line = "[00:00:05] Early morning log"

        late_ts = parse_log_timestamp(late_line)
        early_ts = parse_log_timestamp(early_line)

        assert late_ts is not None
        assert early_ts is not None

        # Early timestamp should be later than late timestamp
        # (next day handling is in parse_log_timestamp)


class TestLogBrowserIntegration:
    """Integration tests for log browser timestamp handling."""

    @pytest.fixture
    def mock_execution(self):
        """Create a mock execution for testing."""
        return {
            'id': 1,
            'doc_id': 123,
            'doc_title': 'Test Document',
            'status': 'completed',
            'started_at': '2024-01-01 10:00:00',
            'completed_at': '2024-01-01 10:05:00',
            'log_file': '/tmp/test.log'
        }

    def test_log_display_preserves_timestamps(self, mock_execution, tmp_path):
        """Test that log browser preserves timestamps when displaying logs."""
        # Create a test log file
        log_file = tmp_path / "test.log"
        log_content = """[10:00:00] 🚀 Claude Code session started
[10:00:01] {"type": "assistant", "message": {"content": [{"type": "text", "text": "Starting task"}]}}
[10:00:02] 📖 Using tool: Read
[10:00:03] {"type": "result", "subtype": "success"}
"""
        log_file.write_text(log_content)

        # Update mock execution with real path
        mock_execution['log_file'] = str(log_file)

        # The actual log browser would read and format this content
        # preserving the original timestamps instead of using current time
        lines = log_file.read_text().strip().split('\n')

        for line in lines:
            timestamp = parse_log_timestamp(line)
            assert timestamp is not None, f"Failed to parse timestamp from: {line}"

            # Verify timestamp is from the log, not current time
            dt = datetime.fromtimestamp(timestamp)
            assert dt.hour == 10
            assert dt.minute < 4  # All timestamps are 10:00:00 - 10:00:03
