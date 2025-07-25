#!/usr/bin/env python3
"""Manual validation script for multi-process logging improvements."""

import os
import sys
import tempfile
import time
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from emdx.commands.claude_execute import format_timestamp, parse_log_timestamp
from emdx.utils.claude_wrapper import log_to_file


def test_millisecond_timestamps():
    """Test millisecond timestamp formatting."""
    print("Testing millisecond timestamps...")
    
    # Test format_timestamp
    ts1 = format_timestamp()
    print(f"  Current timestamp: {ts1}")
    assert ts1.startswith("[") and ts1.endswith("]")
    assert "." in ts1  # Should have milliseconds
    
    # Test specific timestamp
    test_time = 1234567890.123456
    ts2 = format_timestamp(test_time)
    print(f"  Formatted timestamp: {ts2}")
    assert ".123" in ts2  # Should have milliseconds
    
    # Test parsing
    parsed = parse_log_timestamp(ts1)
    assert parsed is not None
    print(f"  ✅ Millisecond timestamps working correctly")


def test_wrapper_logging():
    """Test wrapper logging with process identification."""
    print("\nTesting wrapper logging...")
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
        log_file = Path(f.name)
    
    try:
        # Test log_to_file
        log_to_file(log_file, "Test message 1")
        log_to_file(log_file, "Test message 2")
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        print(f"  Log content ({len(lines)} lines):")
        for line in lines:
            print(f"    {line}")
        
        # Verify format
        assert len(lines) == 2
        assert all("[wrapper]" in line for line in lines)
        assert all(parse_log_timestamp(line) is not None for line in lines)
        
        print(f"  ✅ Wrapper logging working correctly")
    finally:
        log_file.unlink()


def test_log_ordering():
    """Test that log entries maintain chronological order."""
    print("\nTesting log ordering...")
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
        log_file = Path(f.name)
    
    try:
        # Write multiple messages
        for i in range(5):
            log_to_file(log_file, f"Message {i}")
            time.sleep(0.01)  # Small delay
        
        content = log_file.read_text()
        lines = content.strip().split('\n')
        
        # Extract timestamps
        timestamps = []
        for line in lines:
            ts = parse_log_timestamp(line)
            assert ts is not None
            timestamps.append(ts)
        
        # Verify chronological order
        assert timestamps == sorted(timestamps)
        print(f"  ✅ Log ordering maintained ({len(lines)} entries)")
    finally:
        log_file.unlink()


def test_log_filtering():
    """Test log filtering logic."""
    print("\nTesting log filtering...")
    
    from emdx.ui.log_browser import LogBrowser
    
    log_browser = LogBrowser()
    
    # Test wrapper messages that should be filtered
    wrapper_messages = [
        "[10:00:00.123] [wrapper] 🚀 Starting Claude process...",
        "[10:00:00.124] [wrapper] 🔍 Working directory: /tmp",
        "[10:00:00.125] [wrapper] ✅ Claude process finished with exit code: 0"
    ]
    
    filtered_count = sum(1 for msg in wrapper_messages if log_browser._is_wrapper_noise(msg))
    print(f"  Filtered {filtered_count}/{len(wrapper_messages)} wrapper messages")
    
    # Test Claude messages that should NOT be filtered
    claude_messages = [
        "[10:00:01.000] 🤖 Claude: Starting task execution",
        "[10:00:02.000] 📖 Using tool: Read",
        "[10:00:03.000] ✅ Task completed successfully!"
    ]
    
    passed_count = sum(1 for msg in claude_messages if not log_browser._is_wrapper_noise(msg))
    print(f"  Passed {passed_count}/{len(claude_messages)} Claude messages")
    
    assert filtered_count == len(wrapper_messages)
    assert passed_count == len(claude_messages)
    print(f"  ✅ Log filtering working correctly")


def main():
    """Run all validation tests."""
    print("=== Multi-Process Logging Validation ===\n")
    
    try:
        test_millisecond_timestamps()
        test_wrapper_logging()
        test_log_ordering()
        test_log_filtering()
        
        print("\n✅ All validation tests passed!")
        return 0
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())