"""Test timestamp parsing for log browser."""

import time
from datetime import datetime, timedelta
from emdx.commands.claude_execute import parse_log_timestamp, format_timestamp


def test_parse_log_timestamp_basic():
    """Test basic timestamp parsing."""
    line = "[14:30:45] This is a log message"
    timestamp = parse_log_timestamp(line)
    
    assert timestamp is not None
    dt = datetime.fromtimestamp(timestamp)
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.second == 45


def test_parse_log_timestamp_no_timestamp():
    """Test parsing line without timestamp."""
    line = "This is a log message without timestamp"
    timestamp = parse_log_timestamp(line)
    assert timestamp is None


def test_parse_log_timestamp_empty():
    """Test parsing empty line."""
    assert parse_log_timestamp("") is None
    assert parse_log_timestamp(None) is None


def test_parse_log_timestamp_malformed():
    """Test parsing malformed timestamps."""
    assert parse_log_timestamp("[14:30] Too short") is None
    assert parse_log_timestamp("[14:30:45:00] Too long") is None
    assert parse_log_timestamp("[25:30:45] Invalid hour") is None
    assert parse_log_timestamp("[14:61:45] Invalid minute") is None


def test_parse_log_timestamp_midnight_rollover():
    """Test timestamp parsing handles midnight rollover correctly."""
    # Create a timestamp from just before midnight
    now = datetime.now()
    late_night = now.replace(hour=23, minute=59, second=30)
    
    # If current time is early morning, a late night timestamp should be from yesterday
    if now.hour < 12:
        line = "[23:59:30] Late night message"
        timestamp = parse_log_timestamp(line)
        dt = datetime.fromtimestamp(timestamp)
        
        # Should be from yesterday
        assert dt.date() < now.date()


def test_format_timestamp_with_value():
    """Test formatting a specific timestamp."""
    # Create a known timestamp
    dt = datetime(2024, 1, 15, 14, 30, 45)
    timestamp = dt.timestamp()
    
    formatted = format_timestamp(timestamp)
    assert formatted == "[14:30:45]"


def test_format_timestamp_without_value():
    """Test formatting current timestamp."""
    before = datetime.now()
    formatted = format_timestamp()
    after = datetime.now()
    
    # Extract time from formatted string
    import re
    match = re.match(r'\[(\d{2}):(\d{2}):(\d{2})\]', formatted)
    assert match is not None
    
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3))
    
    # Should be between before and after times
    assert before.hour <= hour <= after.hour
    if before.hour == hour == after.hour:
        assert before.minute <= minute <= after.minute


def test_timestamp_parsing_integration():
    """Test parsing and formatting round-trip."""
    # Create a log line with known timestamp
    original_time = datetime.now().replace(microsecond=0)
    original_formatted = original_time.strftime("[%H:%M:%S]")
    log_line = f"{original_formatted} Test message"
    
    # Parse it
    parsed_timestamp = parse_log_timestamp(log_line)
    assert parsed_timestamp is not None
    
    # Format it back
    formatted_back = format_timestamp(parsed_timestamp)
    assert formatted_back == original_formatted


if __name__ == "__main__":
    # Run tests
    test_parse_log_timestamp_basic()
    test_parse_log_timestamp_no_timestamp()
    test_parse_log_timestamp_empty()
    test_parse_log_timestamp_malformed()
    test_parse_log_timestamp_midnight_rollover()
    test_format_timestamp_with_value()
    test_format_timestamp_without_value()
    test_timestamp_parsing_integration()
    
    print("All tests passed!")