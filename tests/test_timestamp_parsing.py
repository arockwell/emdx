"""Tests for timestamp parsing in log browser."""

import pytest
from datetime import datetime

from emdx.commands.claude_execute import parse_timestamp_from_line, format_timestamp


class TestTimestampParsing:
    """Test timestamp parsing functions."""
    
    def test_parse_time_format(self):
        """Test parsing [HH:MM:SS] format."""
        # Test valid time
        result = parse_timestamp_from_line("[10:30:45] Some log message")
        assert result == 10 * 3600 + 30 * 60 + 45  # 37845 seconds
        
        # Test midnight
        result = parse_timestamp_from_line("[00:00:00] Midnight log")
        assert result == 0
        
        # Test end of day
        result = parse_timestamp_from_line("[23:59:59] End of day")
        assert result == 23 * 3600 + 59 * 60 + 59
        
    def test_parse_datetime_format(self):
        """Test parsing [YYYY-MM-DD HH:MM:SS] format."""
        # Test valid datetime
        result = parse_timestamp_from_line("[2025-07-15 10:30:45] Some log message")
        expected = datetime(2025, 7, 15, 10, 30, 45).timestamp()
        assert result == expected
        
        # Test with different date
        result = parse_timestamp_from_line("[2024-12-25 08:00:00] Christmas morning")
        expected = datetime(2024, 12, 25, 8, 0, 0).timestamp()
        assert result == expected
        
    def test_parse_invalid_formats(self):
        """Test parsing invalid formats returns None."""
        # No timestamp
        assert parse_timestamp_from_line("Just a regular log line") is None
        
        # Invalid time format
        assert parse_timestamp_from_line("[25:00:00] Invalid hour") is None
        assert parse_timestamp_from_line("[10:60:00] Invalid minute") is None
        
        # Invalid date format
        assert parse_timestamp_from_line("[2025-13-01 10:00:00] Invalid month") is None
        assert parse_timestamp_from_line("[2025-02-30 10:00:00] Invalid day") is None
        
        # Malformed brackets
        assert parse_timestamp_from_line("10:30:45] Missing opening bracket") is None
        assert parse_timestamp_from_line("[10:30:45 Missing closing bracket") is None
        
    def test_parse_with_whitespace(self):
        """Test parsing handles whitespace correctly."""
        # Leading whitespace
        result = parse_timestamp_from_line("  [10:30:45] With leading space")
        assert result == 10 * 3600 + 30 * 60 + 45
        
        # Trailing whitespace
        result = parse_timestamp_from_line("[10:30:45] With trailing space  ")
        assert result == 10 * 3600 + 30 * 60 + 45
        
    def test_format_timestamp_seconds_since_midnight(self):
        """Test formatting seconds since midnight."""
        # Test various times
        assert format_timestamp(0) == "[00:00:00]"
        assert format_timestamp(3661) == "[01:01:01]"  # 1 hour, 1 minute, 1 second
        assert format_timestamp(43200) == "[12:00:00]"  # Noon
        assert format_timestamp(86399) == "[23:59:59]"  # End of day
        
    def test_format_timestamp_epoch(self):
        """Test formatting epoch timestamps."""
        # Test a known epoch timestamp
        # July 15, 2025, 10:30:45 UTC
        epoch = datetime(2025, 7, 15, 10, 30, 45).timestamp()
        result = format_timestamp(epoch)
        # Should format as local time
        assert result.startswith("[") and result.endswith("]")
        assert len(result) == 10  # [HH:MM:SS]
        
    def test_format_timestamp_none(self):
        """Test formatting with None uses current time."""
        result = format_timestamp(None)
        # Should be current time
        assert result.startswith("[") and result.endswith("]")
        assert len(result) == 10  # [HH:MM:SS]
        
    def test_roundtrip_time_format(self):
        """Test parsing and formatting roundtrip for time format."""
        original = "[14:25:30]"
        parsed = parse_timestamp_from_line(f"{original} Some message")
        formatted = format_timestamp(parsed)
        assert formatted == original
        
    def test_edge_cases(self):
        """Test edge cases in timestamp handling."""
        # Empty line
        assert parse_timestamp_from_line("") is None
        
        # Just timestamp
        result = parse_timestamp_from_line("[10:30:45]")
        assert result == 10 * 3600 + 30 * 60 + 45
        
        # Multiple timestamps (should only parse first)
        result = parse_timestamp_from_line("[10:30:45] Message [11:00:00]")
        assert result == 10 * 3600 + 30 * 60 + 45