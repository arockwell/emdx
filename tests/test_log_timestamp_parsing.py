"""Tests for log timestamp parsing and preservation."""

import pytest
from emdx.commands.claude_execute import parse_timestamp, format_claude_output, format_timestamp


class TestTimestampParsing:
    """Test timestamp parsing functionality."""
    
    def test_parse_timestamp_valid(self):
        """Test parsing valid timestamps."""
        assert parse_timestamp("[10:15:30] Some log message") == "[10:15:30]"
        assert parse_timestamp("[23:59:59] End of day") == "[23:59:59]"
        assert parse_timestamp("[00:00:00] Midnight") == "[00:00:00]"
    
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamps."""
        assert parse_timestamp("No timestamp here") is None
        assert parse_timestamp("10:15:30 No brackets") is None
        assert parse_timestamp("[10:15] Missing seconds") is None
        assert parse_timestamp("[] Empty brackets") is None
        assert parse_timestamp("[10:15:30:00] Too many parts") is None
    
    def test_parse_timestamp_edge_cases(self):
        """Test edge cases for timestamp parsing."""
        assert parse_timestamp("") is None
        assert parse_timestamp("   [10:15:30] With leading spaces") == "[10:15:30]"
        assert parse_timestamp("\t[10:15:30] With tab") == "[10:15:30]"
        # Technically invalid time but matches format
        assert parse_timestamp("[99:99:99] Invalid time values") == "[99:99:99]"


class TestFormatTimestamp:
    """Test timestamp formatting functionality."""
    
    def test_format_timestamp_with_value(self):
        """Test formatting with provided timestamp."""
        assert format_timestamp("[11:22:33]") == "[11:22:33]"
        assert format_timestamp("[00:00:00]") == "[00:00:00]"
    
    def test_format_timestamp_without_value(self):
        """Test formatting without timestamp generates current time."""
        result = format_timestamp(None)
        assert result.startswith("[")
        assert result.endswith("]")
        assert len(result) == 10  # [HH:MM:SS]
        assert result.count(":") == 2


class TestFormatClaudeOutput:
    """Test Claude output formatting with timestamps."""
    
    def test_format_line_with_existing_timestamp(self):
        """Test that lines with timestamps are returned as-is."""
        line = "[10:15:30] Already has timestamp"
        result = format_claude_output(line, 0)
        assert result == line
    
    def test_format_json_assistant_message(self):
        """Test formatting assistant JSON messages."""
        line = '{"type":"assistant","message":{"content":[{"type":"text","text":"Hello"}]}}'
        result = format_claude_output(line, 0, "[10:15:30]")
        assert result == "[10:15:30] 🤖 Claude: Hello"
    
    def test_format_json_tool_use(self):
        """Test formatting tool use JSON messages."""
        line = '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read"}]}}'
        result = format_claude_output(line, 0, "[10:15:30]")
        assert result == "[10:15:30] 📖 Using tool: Read"
    
    def test_format_plain_text_with_timestamp(self):
        """Test formatting plain text with provided timestamp."""
        line = "Plain text message"
        result = format_claude_output(line, 0, "[10:15:30]")
        assert result == "[10:15:30] 💬 Plain text message"
    
    def test_format_plain_text_without_timestamp(self):
        """Test formatting plain text without timestamp uses current time."""
        line = "Plain text message"
        result = format_claude_output(line, 0)
        assert result.startswith("[")
        assert "💬 Plain text message" in result


class TestLogBrowserTimestampTracking:
    """Test the log browser's timestamp tracking logic."""
    
    def simulate_log_processing(self, lines):
        """Simulate the log browser's processing logic."""
        results = []
        last_timestamp = None
        
        for line in lines:
            parsed_timestamp = parse_timestamp(line)
            if parsed_timestamp:
                last_timestamp = parsed_timestamp
            
            timestamp_to_use = parsed_timestamp or last_timestamp
            formatted = format_claude_output(line, 0, timestamp_to_use)
            if formatted:
                results.append(formatted)
        
        return results
    
    def test_timestamp_tracking(self):
        """Test that timestamps are tracked and reused for subsequent lines."""
        lines = [
            "[10:15:30] First message with timestamp",
            '{"type":"assistant","message":{"content":[{"type":"text","text":"JSON without timestamp"}]}}',
            "Plain text without timestamp",
            "[10:15:35] New timestamp",
            '{"type":"assistant","message":{"content":[{"type":"text","text":"After new timestamp"}]}}'
        ]
        
        results = self.simulate_log_processing(lines)
        
        assert results[0] == "[10:15:30] First message with timestamp"
        assert results[1] == "[10:15:30] 🤖 Claude: JSON without timestamp"
        assert results[2] == "[10:15:30] 💬 Plain text without timestamp"
        assert results[3] == "[10:15:35] New timestamp"
        assert results[4] == "[10:15:35] 🤖 Claude: After new timestamp"
    
    def test_no_initial_timestamp(self):
        """Test handling when no initial timestamp is present."""
        lines = [
            '{"type":"assistant","message":{"content":[{"type":"text","text":"No timestamp yet"}]}}',
            "[10:15:30] First timestamp appears",
            "Text after timestamp"
        ]
        
        results = self.simulate_log_processing(lines)
        
        # First line should use current time (we can't check exact value)
        assert "🤖 Claude: No timestamp yet" in results[0]
        assert results[1] == "[10:15:30] First timestamp appears"
        assert results[2] == "[10:15:30] 💬 Text after timestamp"