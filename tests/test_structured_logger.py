"""Tests for the structured logging system."""

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from emdx.utils.structured_logger import (
    LogLevel,
    ProcessType,
    StructuredLogger,
    parse_structured_log,
)


class TestStructuredLogger:
    """Test cases for StructuredLogger."""
    
    def test_basic_logging(self):
        """Test basic log entry creation."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            logger = StructuredLogger(log_file, ProcessType.MAIN, 12345)
            
            # Log different levels
            logger.debug("Debug message", {"key": "value"})
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")
            
            # Parse and verify
            entries = parse_structured_log(log_file)
            assert len(entries) == 5
            
            # Check first entry
            entry = entries[0]
            assert entry["level"] == "DEBUG"
            assert entry["message"] == "Debug message"
            assert entry["context"]["key"] == "value"
            assert entry["process"]["type"] == "main"
            assert entry["process"]["pid"] == 12345
            
            # Check levels
            assert entries[1]["level"] == "INFO"
            assert entries[2]["level"] == "WARNING"
            assert entries[3]["level"] == "ERROR"
            assert entries[4]["level"] == "CRITICAL"
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_claude_output_logging(self):
        """Test logging Claude's JSON output."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            logger = StructuredLogger(log_file, ProcessType.WRAPPER)
            
            # Test content message
            logger.log_claude_output({
                "type": "content",
                "content": "Hello from Claude"
            })
            
            # Test tool use
            logger.log_claude_output({
                "type": "tool_use",
                "name": "Read",
                "parameters": {"file": "test.py"}
            })
            
            # Test tool result
            logger.log_claude_output({
                "type": "tool_result",
                "tool": "Read",
                "result": "File contents here"
            })
            
            # Test error
            logger.log_claude_output({
                "type": "error",
                "error": {"message": "Something went wrong"}
            })
            
            # Test success result
            logger.log_claude_output({
                "type": "result",
                "subtype": "success"
            })
            
            entries = parse_structured_log(log_file)
            assert len(entries) == 5
            
            # Verify Claude content
            assert "Claude: Hello from Claude" in entries[0]["message"]
            assert entries[0]["context"]["claude_type"] == "content"
            
            # Verify tool use
            assert "Tool use: Read" in entries[1]["message"]
            assert entries[1]["context"]["tool"] == "Read"
            assert entries[1]["context"]["parameters"]["file"] == "test.py"
            
            # Verify tool result
            assert "Tool result: Read" in entries[2]["message"]
            assert "File contents here" in entries[2]["context"]["result"]
            
            # Verify error
            assert entries[3]["level"] == "ERROR"
            assert "Something went wrong" in entries[3]["message"]
            
            # Verify success
            assert "Task completed successfully" in entries[4]["message"]
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_execution_lifecycle_logging(self):
        """Test execution lifecycle logging."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            logger = StructuredLogger(log_file, ProcessType.WRAPPER)
            
            # Log execution start
            logger.log_execution_start(42, "Test Document", "/tmp/work")
            
            # Log process lifecycle
            logger.log_process_lifecycle("start", {"command": ["claude", "--help"]})
            logger.log_process_lifecycle("heartbeat")
            
            # Log execution complete
            logger.log_execution_complete(42, 0, 10.5)
            
            entries = parse_structured_log(log_file)
            assert len(entries) == 4
            
            # Check execution start
            assert "Starting execution #42" in entries[0]["message"]
            assert entries[0]["context"]["exec_id"] == 42
            assert entries[0]["context"]["doc_title"] == "Test Document"
            
            # Check process start
            assert "Process start" in entries[1]["message"]
            assert entries[1]["context"]["event"] == "process_start"
            
            # Check completion
            assert "completed with success" in entries[3]["message"]
            assert entries[3]["context"]["duration_seconds"] == 10.5
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_concurrent_logging(self):
        """Test thread-safe concurrent logging."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Create multiple loggers simulating different processes
            main_logger = StructuredLogger(log_file, ProcessType.MAIN, 1000)
            wrapper_logger = StructuredLogger(log_file, ProcessType.WRAPPER, 2000)
            
            # Function to log from thread
            def log_from_thread(logger, thread_id, count):
                for i in range(count):
                    logger.info(f"Message {i} from thread {thread_id}")
                    time.sleep(0.001)  # Small delay to encourage interleaving
            
            # Start threads
            threads = []
            threads.append(threading.Thread(target=log_from_thread, args=(main_logger, "main", 10)))
            threads.append(threading.Thread(target=log_from_thread, args=(wrapper_logger, "wrapper", 10)))
            
            for t in threads:
                t.start()
            
            for t in threads:
                t.join()
            
            # Parse and verify
            entries = parse_structured_log(log_file)
            assert len(entries) == 20
            
            # Verify no corruption - each entry should be valid JSON
            for entry in entries:
                assert "timestamp" in entry
                assert "level" in entry
                assert "process" in entry
                assert "message" in entry
            
            # Count entries by process
            main_count = sum(1 for e in entries if e["process"]["type"] == "main")
            wrapper_count = sum(1 for e in entries if e["process"]["type"] == "wrapper")
            
            assert main_count == 10
            assert wrapper_count == 10
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_parse_mixed_format_log(self):
        """Test parsing logs with both structured and legacy formats."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            # Write mixed format log
            with open(log_file, 'w') as f:
                # Legacy format
                f.write("[10:30:45] Starting process\n")
                f.write("[10:30:46] ❌ Error occurred\n")
                
                # Structured format
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "process": {"type": "main", "pid": 1234, "name": "main-1234"},
                    "message": "Structured message"
                }
                f.write(json.dumps(entry) + "\n")
                
                # More legacy
                f.write("[10:30:47] Process complete\n")
                
                # Invalid JSON (should be handled gracefully)
                f.write("{broken json\n")
                
                # Empty line
                f.write("\n")
            
            # Parse
            entries = parse_structured_log(log_file)
            
            # Should have 5 entries (empty line excluded)
            assert len(entries) == 5
            
            # Check legacy entries were converted
            assert entries[0]["process"]["type"] == "legacy"
            assert "Starting process" in entries[0]["message"]
            
            assert entries[1]["process"]["type"] == "legacy"
            assert "Error occurred" in entries[1]["message"]
            
            # Check structured entry
            assert entries[2]["process"]["type"] == "main"
            assert entries[2]["process"]["pid"] == 1234
            
            # Check broken JSON was handled
            assert entries[4]["process"]["type"] == "legacy"
            assert "{broken json" in entries[4]["message"]
            
        finally:
            log_file.unlink(missing_ok=True)
    
    def test_long_result_truncation(self):
        """Test that very long tool results are truncated."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            log_file = Path(f.name)
        
        try:
            logger = StructuredLogger(log_file, ProcessType.WRAPPER)
            
            # Create a very long result
            long_result = "x" * 2000
            
            logger.log_claude_output({
                "type": "tool_result",
                "tool": "Read",
                "result": long_result
            })
            
            entries = parse_structured_log(log_file)
            assert len(entries) == 1
            
            # Check truncation
            result = entries[0]["context"]["result"]
            assert len(result) == 1000 + len("... (truncated)")
            assert result.endswith("... (truncated)")
            
        finally:
            log_file.unlink(missing_ok=True)