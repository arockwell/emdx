"""Tests for claude_execute module."""

import time
from datetime import datetime
from unittest.mock import patch

import pytest

from emdx.commands.claude_execute import format_claude_output, format_timestamp, parse_log_timestamp


class TestTimestampParsing:
    """Test timestamp parsing functionality."""

    def test_parse_valid_timestamp(self):
        """Test parsing a valid timestamp from log line."""
        line = "[14:32:15] 🤖 Claude: Processing request"
        timestamp = parse_log_timestamp(line)

        assert timestamp is not None
        dt = datetime.fromtimestamp(timestamp)
        assert dt.hour == 14
        assert dt.minute == 32
        assert dt.second == 15

    def test_parse_timestamp_with_whitespace(self):
        """Test parsing timestamp with leading whitespace."""
        line = "  [09:05:30] Starting execution"
        timestamp = parse_log_timestamp(line)

        assert timestamp is not None
        dt = datetime.fromtimestamp(timestamp)
        assert dt.hour == 9
        assert dt.minute == 5
        assert dt.second == 30

    def test_parse_no_timestamp(self):
        """Test parsing line without timestamp."""
        line = "This is a regular log line without timestamp"
        timestamp = parse_log_timestamp(line)

        assert timestamp is None

    def test_parse_empty_line(self):
        """Test parsing empty line."""
        assert parse_log_timestamp("") is None
        assert parse_log_timestamp(None) is None

    def test_parse_malformed_timestamp(self):
        """Test parsing malformed timestamps."""
        assert parse_log_timestamp("[14:32] Missing seconds") is None
        assert parse_log_timestamp("[14:32:] Empty seconds") is None
        assert parse_log_timestamp("[14::15] Missing minutes") is None
        assert parse_log_timestamp("[25:32:15] Invalid hour") is None

    @patch('emdx.commands.claude_execute.datetime')
    def test_parse_timestamp_before_midnight(self, mock_datetime):
        """Test parsing timestamp from before midnight when current time is after."""
        # Mock current time as 00:30:00
        mock_now = datetime(2023, 12, 15, 0, 30, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.fromtimestamp = datetime.fromtimestamp

        # Parse a timestamp from 23:45:00 (should be from yesterday)
        line = "[23:45:00] Late night log"
        timestamp = parse_log_timestamp(line)

        assert timestamp is not None
        dt = datetime.fromtimestamp(timestamp)
        # Should be from December 14th
        assert dt.day == 14
        assert dt.hour == 23
        assert dt.minute == 45


class TestTimestampFormatting:
    """Test timestamp formatting functionality."""

    def test_format_timestamp_current_time(self):
        """Test formatting current timestamp."""
        with patch('emdx.commands.claude_execute.datetime') as mock_datetime:
            mock_now = datetime(2023, 12, 15, 14, 32, 15)
            mock_datetime.now.return_value = mock_now

            result = format_timestamp()
            assert result == "[14:32:15]"

    def test_format_timestamp_with_epoch(self):
        """Test formatting specific epoch timestamp."""
        # Create a known timestamp
        dt = datetime(2023, 12, 15, 9, 5, 30)
        epoch_time = dt.timestamp()

        result = format_timestamp(epoch_time)
        assert result == "[09:05:30]"

    def test_format_timestamp_none(self):
        """Test formatting with None timestamp uses current time."""
        with patch('emdx.commands.claude_execute.datetime') as mock_datetime:
            mock_now = datetime(2023, 12, 15, 10, 20, 30)
            mock_datetime.now.return_value = mock_now

            result = format_timestamp(None)
            assert result == "[10:20:30]"


class TestFormatClaudeOutput:
    """Test Claude output formatting with timestamps."""

    def test_format_with_existing_timestamp(self):
        """Test formatting line that already has timestamp."""
        line = "[14:32:15] Already formatted line"
        result = format_claude_output(line, 0)

        # Should return as-is
        assert result == line

    def test_format_json_with_parsed_timestamp(self):
        """Test formatting JSON output with parsed timestamp."""
        line = '{"type": "text", "text": "Hello world"}'

        # Use a specific timestamp
        dt = datetime(2023, 12, 15, 14, 32, 15)
        timestamp = dt.timestamp()

        with patch('emdx.commands.claude_execute.datetime') as mock_datetime:
            mock_datetime.fromtimestamp.return_value = dt

            result = format_claude_output(line, timestamp)
            assert result == "[14:32:15] 🤖 Claude: Hello world"

    def test_format_tool_use_with_timestamp(self):
        """Test formatting tool use with specific timestamp."""
        line = ('{"type": "assistant", "message": '
                '{"content": [{"type": "tool_use", "name": "Read"}]}}')

        dt = datetime(2023, 12, 15, 9, 5, 30)
        timestamp = dt.timestamp()

        with patch('emdx.commands.claude_execute.datetime') as mock_datetime:
            mock_datetime.fromtimestamp.return_value = dt

            result = format_claude_output(line, timestamp)
            assert result == "[09:05:30] 📖 Using tool: Read"

    def test_format_empty_line(self):
        """Test formatting empty line."""
        assert format_claude_output("", 0) is None
        assert format_claude_output("   ", 0) is None


class TestLogBrowserTimestamps:
    """Test that log browser preserves original timestamps."""

    def test_timestamp_preservation_during_display(self):
        """Test that timestamps are preserved when displaying logs."""
        # Create a mock log content with mixed timestamps
        log_content = """[14:32:15] Starting execution
{"type": "text", "text": "Processing request..."}
[14:32:16] Claude is thinking
{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello from Claude"}]}}
[14:32:17] Execution complete"""

        # Process the log lines as the log browser would
        lines = log_content.strip().split('\n')
        formatted_lines = []
        last_timestamp = None

        for line in lines:
            if not line.strip():
                continue

            # Parse timestamp from log line if available
            parsed_timestamp = parse_log_timestamp(line)
            if parsed_timestamp:
                last_timestamp = parsed_timestamp

            # Use parsed timestamp or last known timestamp
            timestamp_to_use = parsed_timestamp or last_timestamp or time.time()

            # Format the line
            formatted = format_claude_output(line, timestamp_to_use)
            if formatted:
                formatted_lines.append(formatted)
            else:
                formatted_lines.append(line)

        # Verify all lines have consistent timestamps
        assert len(formatted_lines) == 5
        assert "[14:32:15]" in formatted_lines[0]
        assert "[14:32:15]" in formatted_lines[1]  # Should use last known timestamp
        assert "[14:32:16]" in formatted_lines[2]
        assert "[14:32:16]" in formatted_lines[3]  # Should use last known timestamp
        assert "[14:32:17]" in formatted_lines[4]

    def test_real_time_streaming_timestamps(self):
        """Test timestamp preservation during real-time log streaming."""
        # Simulate real-time streaming with delays

        # First batch of lines
        lines_batch1 = [
            "[10:00:00] Starting execution",
            '{"type": "text", "text": "First message"}'
        ]

        # Process first batch
        formatted_batch1 = []
        last_timestamp = None

        for line in lines_batch1:
            parsed_timestamp = parse_log_timestamp(line)
            if parsed_timestamp:
                last_timestamp = parsed_timestamp

            timestamp_to_use = parsed_timestamp or last_timestamp or time.time()
            formatted = format_claude_output(line, timestamp_to_use)
            if formatted:
                formatted_batch1.append(formatted)

        # Simulate delay
        time.sleep(0.1)

        # Second batch of lines (arrives later)
        lines_batch2 = [
            "[10:00:05] Processing continues",
            '{"type": "text", "text": "Second message"}'
        ]

        # Process second batch with preserved context
        formatted_batch2 = []
        for line in lines_batch2:
            parsed_timestamp = parse_log_timestamp(line)
            if parsed_timestamp:
                last_timestamp = parsed_timestamp

            timestamp_to_use = parsed_timestamp or last_timestamp or time.time()
            formatted = format_claude_output(line, timestamp_to_use)
            if formatted:
                formatted_batch2.append(formatted)

        # Verify timestamps are preserved correctly
        assert "[10:00:00]" in formatted_batch1[0]
        assert "[10:00:00]" in formatted_batch1[1]  # Uses last known timestamp
        assert "[10:00:05]" in formatted_batch2[0]
        assert "[10:00:05]" in formatted_batch2[1]  # Uses last known timestamp


if __name__ == "__main__":
    pytest.main([__file__])

