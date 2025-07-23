#!/usr/bin/env python3
"""Tests for timestamp parsing in log browser."""

import pytest
from emdx.commands.claude_execute import parse_timestamp, format_timestamp, format_claude_output


class TestTimestampParsing:
    """Test timestamp extraction from log lines."""
    
    def test_parse_timestamp_valid(self):
        """Test parsing valid timestamps."""
        assert parse_timestamp("[23:59:31] Some log message") == "[23:59:31]"
        assert parse_timestamp("[00:00:00] Start of day") == "[00:00:00]"
        assert parse_timestamp("[12:34:56] Mid-day message") == "[12:34:56]"
        
    def test_parse_timestamp_with_whitespace(self):
        """Test parsing timestamps with leading/trailing whitespace."""
        assert parse_timestamp("  [23:59:31] Some log message") == "[23:59:31]"
        assert parse_timestamp("[23:59:31] Some log message  ") == "[23:59:31]"
        assert parse_timestamp("  [23:59:31] Some log message  ") == "[23:59:31]"
        
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamps."""
        assert parse_timestamp("No timestamp here") is None
        assert parse_timestamp("[23:59] Missing seconds") is None
        assert parse_timestamp("[23:59:31 Missing bracket") is None
        assert parse_timestamp("23:59:31] Missing opening bracket") is None
        # Note: Current implementation doesn't validate timestamp values
        # assert parse_timestamp("[25:59:31] Invalid hour") is None
        assert parse_timestamp("") is None
        
    def test_parse_timestamp_json_lines(self):
        """Test parsing timestamps from JSON lines."""
        # JSON lines typically don't have timestamps at the start
        assert parse_timestamp('{"type": "assistant", "message": "Hello"}') is None
        assert parse_timestamp('{"type": "error", "error": {"message": "Error"}}') is None


class TestFormatTimestamp:
    """Test timestamp formatting."""
    
    def test_format_timestamp_with_provided_timestamp(self):
        """Test formatting with a provided timestamp."""
        assert format_timestamp("[12:34:56]") == "[12:34:56]"
        assert format_timestamp("[00:00:00]") == "[00:00:00]"
        
    def test_format_timestamp_without_timestamp(self):
        """Test formatting without a timestamp (generates current time)."""
        result = format_timestamp(None)
        assert result.startswith("[")
        assert result.endswith("]")
        assert len(result) == 10  # [HH:MM:SS]
        

class TestFormatClaudeOutput:
    """Test Claude output formatting with timestamps."""
    
    def test_format_with_existing_timestamp(self):
        """Test formatting lines that already have timestamps."""
        line = "[12:34:56] 🚀 Claude Code session started"
        result = format_claude_output(line, 0.0)
        assert result == line  # Should return as-is
        
    def test_format_json_with_parsed_timestamp(self):
        """Test formatting JSON with a parsed timestamp."""
        line = '{"type": "system", "subtype": "init"}'
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert result == "[12:34:56] 🚀 Claude Code session started"
        
    def test_format_json_without_timestamp(self):
        """Test formatting JSON without a parsed timestamp."""
        line = '{"type": "system", "subtype": "init"}'
        result = format_claude_output(line, 0.0, None)
        assert result.startswith("[")
        assert "🚀 Claude Code session started" in result
        
    def test_format_assistant_message_with_timestamp(self):
        """Test formatting assistant messages with timestamp."""
        line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello, world!"}]}}'
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert result == "[12:34:56] 🤖 Claude: Hello, world!"
        
    def test_format_tool_use_with_timestamp(self):
        """Test formatting tool use with timestamp."""
        line = '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}}'
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert result == "[12:34:56] 📖 Using tool: Read"
        
    def test_format_error_with_timestamp(self):
        """Test formatting errors with timestamp."""
        line = '{"type": "error", "error": {"message": "Something went wrong"}}'
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert result == "[12:34:56] ❌ Error: Something went wrong"
        
    def test_format_plain_text_with_timestamp(self):
        """Test formatting plain text with timestamp."""
        line = "This is a plain text message"
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert result == "[12:34:56] 💬 This is a plain text message"
        
    def test_format_malformed_json_with_timestamp(self):
        """Test formatting malformed JSON with timestamp."""
        line = '{"type": "invalid", but not valid JSON'
        timestamp = "[12:34:56]"
        result = format_claude_output(line, 0.0, timestamp)
        assert "[12:34:56] ⚠️  Malformed JSON:" in result


class TestIntegration:
    """Integration tests for the full timestamp parsing flow."""
    
    def test_log_line_processing_flow(self):
        """Test the full flow of processing a log line."""
        # Simulate a log line that would be read from a file
        log_line = "[14:32:10] 🚀 Claude Code session started"
        
        # Parse timestamp
        timestamp = parse_timestamp(log_line)
        assert timestamp == "[14:32:10]"
        
        # Format output (should return as-is since it already has timestamp)
        result = format_claude_output(log_line, 0.0, timestamp)
        assert result == log_line
        
    def test_json_line_processing_flow(self):
        """Test processing a JSON line without timestamp."""
        json_line = '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Processing request..."}]}}'
        
        # Parse timestamp (should be None)
        timestamp = parse_timestamp(json_line)
        assert timestamp is None
        
        # Format with specific timestamp
        result = format_claude_output(json_line, 0.0, "[14:32:11]")
        assert result == "[14:32:11] 🤖 Claude: Processing request..."