"""Tests for log timestamp parsing functionality."""

import pytest
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