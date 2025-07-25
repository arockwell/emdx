"""Tests for the log parser module."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from emdx.ui.log_parser import LogEntry, LogParser


class TestLogEntry:
    """Test cases for LogEntry class."""
    
    def test_basic_properties(self):
        """Test basic LogEntry properties."""
        timestamp = datetime.now(timezone.utc)
        entry = LogEntry(
            timestamp=timestamp,
            level="INFO",
            process_type="main",
            process_pid=1234,
            message="Test message"
        )
        
        assert entry.formatted_time == timestamp.strftime("[%H:%M:%S]")
        assert entry.process_name == "main-1234"
        assert entry.message == "Test message"
    
    def test_wrapper_noise_detection(self):
        """Test wrapper noise detection."""
        # Should be noise
        noise_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Database updated successfully",
            context={}
        )
        assert noise_entry.is_wrapper_noise()
        
        # Process start event should be noise
        start_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Starting",
            context={"event": "process_start"}
        )
        assert start_entry.is_wrapper_noise()
        
        # Non-wrapper should not be noise
        main_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="main",
            process_pid=1234,
            message="Database updated successfully",
            context={}
        )
        assert not main_entry.is_wrapper_noise()
        
        # Wrapper with important message should not be noise
        important_entry = LogEntry(
            timestamp=datetime.now(),
            level="ERROR",
            process_type="wrapper",
            process_pid=1234,
            message="Critical error occurred",
            context={}
        )
        assert not important_entry.is_wrapper_noise()
    
    def test_claude_content_detection(self):
        """Test Claude content detection."""
        # Claude process type
        claude_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="claude",
            process_pid=1234,
            message="Test"
        )
        assert claude_entry.is_claude_content()
        
        # Claude content type
        content_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Test",
            context={"claude_type": "content"}
        )
        assert content_entry.is_claude_content()
        
        # Tool use
        tool_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Tool use",
            context={"claude_type": "tool_use"}
        )
        assert tool_entry.is_claude_content()
        
        # Non-Claude
        other_entry = LogEntry(
            timestamp=datetime.now(),
            level="INFO",
            process_type="main",
            process_pid=1234,
            message="Test"
        )
        assert not other_entry.is_claude_content()
    
    def test_format_for_display(self):
        """Test display formatting."""
        timestamp = datetime.now(timezone.utc)
        
        # Basic message
        entry = LogEntry(
            timestamp=timestamp,
            level="INFO",
            process_type="main",
            process_pid=1234,
            message="Test message"
        )
        display = entry.format_for_display(show_process=False)
        assert display == f"{entry.formatted_time} Test message"
        
        # With process
        display_with_process = entry.format_for_display(show_process=True)
        assert display_with_process == f"{entry.formatted_time} [main] Test message"
        
        # Tool use
        tool_entry = LogEntry(
            timestamp=timestamp,
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Using Read",
            context={"claude_type": "tool_use", "tool": "Read"}
        )
        display = tool_entry.format_for_display()
        assert "📖 Using tool: Read" in display
        
        # Error
        error_entry = LogEntry(
            timestamp=timestamp,
            level="ERROR",
            process_type="main",
            process_pid=1234,
            message="Something failed"
        )
        display = error_entry.format_for_display()
        assert "❌ Something failed" in display
        
        # Claude content
        claude_entry = LogEntry(
            timestamp=timestamp,
            level="INFO",
            process_type="wrapper",
            process_pid=1234,
            message="Claude: Hello world"
        )
        display = claude_entry.format_for_display()
        assert "💬 Hello world" in display


class TestLogParser:
    """Test cases for LogParser class."""
    
    def test_parse_structured_log(self):
        """Test parsing structured JSON log."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Write structured entries
            entries_data = [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "process": {"type": "main", "pid": 1234, "name": "main-1234"},
                    "message": "First message"
                },
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "process": {"type": "wrapper", "pid": 5678, "name": "wrapper-5678"},
                    "message": "Error message",
                    "context": {"error_code": 1}
                }
            ]
            
            with open(log_file, 'w') as f:
                for entry in entries_data:
                    f.write(json.dumps(entry) + '\n')
            
            # Parse
            parser = LogParser(log_file)
            entries = parser.parse()
            
            assert len(entries) == 2
            assert entries[0].message == "First message"
            assert entries[0].process_type == "main"
            assert entries[1].level == "ERROR"
            assert entries[1].context["error_code"] == 1
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_parse_legacy_log(self):
        """Test parsing legacy format log."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Write legacy entries
            with open(log_file, 'w') as f:
                f.write("[10:30:45] Starting process\n")
                f.write("[10:30:46] ❌ Error occurred\n")
                f.write("No timestamp line\n")
                f.write("\n")  # Empty line
                f.write("[10:30:47] ⚠️ Warning message\n")
            
            # Parse
            parser = LogParser(log_file)
            entries = parser.parse()
            
            # Empty lines should be skipped
            assert len(entries) == 4
            
            # Check timestamp parsing
            assert entries[0].timestamp.hour == 10
            assert entries[0].timestamp.minute == 30
            assert entries[0].timestamp.second == 45
            
            # Check level detection
            assert entries[0].level == "INFO"
            assert entries[1].level == "ERROR"
            assert entries[3].level == "WARNING"
            
            # Check messages
            assert "Starting process" in entries[0].message
            assert "No timestamp line" in entries[2].message
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_filtered_entries(self):
        """Test entry filtering."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Write mixed entries
            entries_data = [
                # Wrapper noise
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "process": {"type": "wrapper", "pid": 1234, "name": "wrapper-1234"},
                    "message": "Database updated successfully"
                },
                # Important wrapper message
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "ERROR",
                    "process": {"type": "wrapper", "pid": 1234, "name": "wrapper-1234"},
                    "message": "Failed to start Claude"
                },
                # Main process
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "process": {"type": "main", "pid": 5678, "name": "main-5678"},
                    "message": "Execution started"
                },
                # Claude content
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "process": {"type": "claude", "pid": 9999, "name": "claude-9999"},
                    "message": "Processing request"
                }
            ]
            
            with open(log_file, 'w') as f:
                for entry in entries_data:
                    f.write(json.dumps(entry) + '\n')
            
            parser = LogParser(log_file)
            
            # Test wrapper noise filtering
            entries = parser.get_filtered_entries(show_wrapper_noise=False)
            assert len(entries) == 3  # Noise filtered out
            
            entries_with_noise = parser.get_filtered_entries(show_wrapper_noise=True)
            assert len(entries_with_noise) == 4  # All entries
            
            # Test process filtering
            main_entries = parser.get_filtered_entries(process_filter="main")
            assert len(main_entries) == 1
            assert main_entries[0].process_type == "main"
            
            # Test level filtering
            error_entries = parser.get_filtered_entries(level_filter="ERROR")
            assert len(error_entries) == 1
            assert error_entries[0].level == "ERROR"
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_execution_summary(self):
        """Test execution summary generation."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Create entries with time spread
            base_time = datetime.now(timezone.utc)
            entries_data = []
            
            # Add entries over 10 seconds
            for i in range(5):
                entries_data.append({
                    "timestamp": base_time.isoformat(),
                    "level": "INFO" if i != 2 else "ERROR",
                    "process": {"type": "main" if i < 2 else "wrapper", "pid": 1234},
                    "message": f"Message {i}"
                })
                base_time = base_time.replace(second=base_time.second + 2)
            
            with open(log_file, 'w') as f:
                for entry in entries_data:
                    f.write(json.dumps(entry) + '\n')
            
            parser = LogParser(log_file)
            summary = parser.get_execution_summary()
            
            assert summary["total_entries"] == 5
            assert summary["processes"]["main"] == 2
            assert summary["processes"]["wrapper"] == 3
            assert summary["error_count"] == 1
            assert summary["duration"] == 8.0  # 4 intervals of 2 seconds
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_empty_log(self):
        """Test handling of empty log file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Empty file
            parser = LogParser(log_file)
            entries = parser.parse()
            assert len(entries) == 0
            
            summary = parser.get_execution_summary()
            assert summary["total_entries"] == 0
            assert summary["start_time"] is None
            assert summary["duration"] is None
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_nonexistent_log(self):
        """Test handling of non-existent log file."""
        parser = LogParser("/tmp/nonexistent_log_file_12345.log")
        entries = parser.parse()
        assert len(entries) == 0