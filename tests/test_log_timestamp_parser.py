"""Tests for log timestamp parsing functionality."""

from datetime import datetime

from emdx.commands.claude_execute import format_claude_output, format_timestamp
from emdx.ui.log_browser import parse_log_timestamp


class TestParseLogTimestamp:
    """Test the parse_log_timestamp function."""

    def test_valid_timestamp(self):
        """Test parsing valid timestamp at start of line."""
        line = "[14:23:45] Log message"
        result = parse_log_timestamp(line)
        assert result == "[14:23:45]"

    def test_timestamp_with_leading_whitespace(self):
        """Test parsing timestamp with leading whitespace."""
        line = "  [09:15:30] Another log message"
        result = parse_log_timestamp(line)
        assert result == "[09:15:30]"

    def test_timestamp_only(self):
        """Test parsing line with timestamp only."""
        line = "[23:59:59]"
        result = parse_log_timestamp(line)
        assert result == "[23:59:59]"

    def test_no_timestamp(self):
        """Test line without timestamp."""
        line = "Just a log message"
        result = parse_log_timestamp(line)
        assert result is None

    def test_invalid_timestamp_format(self):
        """Test line with invalid timestamp format."""
        line = "14:23:45 Log message"  # Missing brackets
        result = parse_log_timestamp(line)
        assert result is None

    def test_timestamp_not_at_start(self):
        """Test timestamp in middle of line."""
        line = "Some text [14:23:45] in the middle"
        result = parse_log_timestamp(line)
        assert result is None

    def test_empty_line(self):
        """Test empty line."""
        line = ""
        result = parse_log_timestamp(line)
        assert result is None

    def test_none_input(self):
        """Test None input."""
        result = parse_log_timestamp(None)
        assert result is None

    def test_whitespace_only(self):
        """Test whitespace-only line."""
        line = "   \t  "
        result = parse_log_timestamp(line)
        assert result is None

    def test_special_characters_after_timestamp(self):
        """Test timestamp followed by special characters."""
        line = "[10:00:00] 🚀 Claude Code session started"
        result = parse_log_timestamp(line)
        assert result == "[10:00:00]"

    def test_malformed_timestamps(self):
        """Test various malformed timestamp formats."""
        test_cases = [
            "[1:00:00]",      # Single digit hour
            "[10:5:00]",      # Single digit minute
            "[10:00:5]",      # Single digit second
            "[25:00:00]",     # Invalid hour
            "[10:60:00]",     # Invalid minute
            "[10:00:60]",     # Invalid second
            "[10-00-00]",     # Wrong separator
            "(10:00:00)",     # Wrong brackets
        ]

        for line in test_cases:
            result = parse_log_timestamp(line + " message")
            assert result is None, f"Should not parse: {line}"

    def test_unicode_content(self):
        """Test timestamp with unicode content after."""
        line = "[12:34:56] 测试日志消息 🎯"
        result = parse_log_timestamp(line)
        assert result == "[12:34:56]"

    def test_multiline_string(self):
        """Test first line of multiline string."""
        line = "[08:30:00] First line\nSecond line\nThird line"
        result = parse_log_timestamp(line)
        assert result == "[08:30:00]"

    def test_boundary_timestamps(self):
        """Test boundary time values."""
        test_cases = [
            "[00:00:00] Midnight",
            "[23:59:59] Almost midnight",
            "[12:00:00] Noon",
            "[01:01:01] All ones",
        ]

        for line in test_cases:
            result = parse_log_timestamp(line)
            assert result == line.split()[0], f"Failed to parse: {line}"


class TestFormatTimestamp:
    """Test the format_timestamp function."""

    def test_current_time(self):
        """Test formatting current time."""
        result = format_timestamp()
        # Should be in [HH:MM:SS] format
        assert result.startswith("[")
        assert result.endswith("]")
        assert len(result) == 10  # [HH:MM:SS]

        # Parse to verify format
        import re
        pattern = r'^\[(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d\]$'
        assert re.match(pattern, result) is not None

    def test_specific_time(self):
        """Test formatting specific timestamp."""
        # Test with epoch time (2022-01-01 00:00:00 UTC)
        test_time = 1640995200.0
        result = format_timestamp(test_time)

        # Should be properly formatted
        assert result.startswith("[")
        assert result.endswith("]")
        assert len(result) == 10

    def test_none_base_time(self):
        """Test that None base_time uses current time."""
        result1 = format_timestamp(None)
        result2 = format_timestamp()

        # Both should have same format
        assert len(result1) == len(result2) == 10
        assert result1.startswith("[") and result1.endswith("]")


class TestFormatClaudeOutput:
    """Test the format_claude_output function."""

    def test_already_timestamped_lines(self):
        """Test that lines with timestamps are returned as-is."""
        start_time = datetime.now().timestamp()

        # Valid timestamps should be preserved
        test_cases = [
            "[14:23:45] Already timestamped",
            "  [00:00:00] With whitespace",
            "[23:59:59] End of day",
        ]

        for line in test_cases:
            result = format_claude_output(line, start_time)
            assert result == line.strip()

    def test_json_system_messages(self):
        """Test formatting of system JSON messages."""
        start_time = datetime.now().timestamp()

        # System init
        json_line = '{"type": "system", "subtype": "init"}'
        result = format_claude_output(json_line, start_time)
        assert "🚀 Claude Code session started" in result
        assert result.startswith("[")

        # Other system messages should be skipped
        json_line = '{"type": "system", "subtype": "other"}'
        result = format_claude_output(json_line, start_time)
        assert result is None

    def test_json_assistant_messages(self):
        """Test formatting of assistant messages."""
        start_time = datetime.now().timestamp()

        # Text message
        json_line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}'
        result = format_claude_output(json_line, start_time)
        assert "🤖 Claude: Hello world" in result
        assert result.startswith("[")

        # Tool use
        json_line = '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}}'
        result = format_claude_output(json_line, start_time)
        assert "📖 Using tool: Read" in result

    def test_json_error_messages(self):
        """Test formatting of error messages."""
        start_time = datetime.now().timestamp()

        json_line = '{"type": "error", "error": {"message": "Something went wrong"}}'
        result = format_claude_output(json_line, start_time)
        assert "❌ Error: Something went wrong" in result
        assert result.startswith("[")

    def test_empty_and_whitespace(self):
        """Test handling of empty lines and whitespace."""
        start_time = datetime.now().timestamp()

        assert format_claude_output("", start_time) is None
        assert format_claude_output("   ", start_time) is None
        assert format_claude_output("\t\n", start_time) is None

    def test_malformed_json(self):
        """Test handling of malformed JSON."""
        start_time = datetime.now().timestamp()

        # Incomplete JSON
        result = format_claude_output("{incomplete", start_time)
        assert "⚠️  Malformed JSON" in result

        # Invalid JSON syntax
        result = format_claude_output('{"key": invalid}', start_time)
        assert "⚠️  Malformed JSON" in result

    def test_plain_text_handling(self):
        """Test handling of plain text lines."""
        start_time = datetime.now().timestamp()

        # Regular text
        result = format_claude_output("Just a plain text message", start_time)
        assert "💬 Just a plain text message" in result
        assert result.startswith("[")

        # Text that starts with { but isn't JSON
        result = format_claude_output("{not valid json at all}", start_time)
        assert "⚠️  Malformed JSON" in result

    def test_timestamp_consistency(self):
        """Test that timestamps are consistent for a given start_time."""
        # Use a fixed time for reproducible tests
        start_time = 1640995200.0  # 2022-01-01 00:00:00 UTC

        # Generate multiple outputs
        messages = [
            '{"type": "system", "subtype": "init"}',
            '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Test"}]}}',
            "Plain text message",
        ]

        results = []
        for msg in messages:
            result = format_claude_output(msg, start_time)
            if result:
                results.append(result)

        # Extract timestamps and verify they're all the same
        import re
        timestamps = []
        for result in results:
            match = re.match(r'(\[[0-9:]+\])', result)
            if match:
                timestamps.append(match.group(1))

        # All timestamps should be identical since they use same start_time
        assert len(set(timestamps)) == 1, f"Inconsistent timestamps: {timestamps}"

    def test_long_tool_results(self):
        """Test truncation of long tool results."""
        start_time = datetime.now().timestamp()

        long_content = "x" * 200
        json_line = f'{{"type": "user", "message": {{"role": "user", "content": [{{"content": "{long_content}"}}]}}}}'
        result = format_claude_output(json_line, start_time)

        assert "📄 Tool result:" in result
        assert "..." in result
        assert len(result) < 150  # Should be truncated
