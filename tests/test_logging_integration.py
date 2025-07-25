"""Integration tests for the complete logging system."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from emdx.utils.structured_logger import StructuredLogger, ProcessType
from emdx.ui.log_parser import LogParser


class TestLoggingIntegration:
    """Integration tests for logging system."""
    
    def test_wrapper_subprocess_logging(self):
        """Test that wrapper subprocess logging works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test_execution.log"
            
            # Create a mock Claude command that outputs JSON
            mock_claude = Path(tmpdir) / "mock_claude.py"
            with open(mock_claude, 'w') as f:
                f.write('''#!/usr/bin/env python3
import json
import sys
import time

# Output some JSON messages like Claude would
messages = [
    {"type": "content", "content": "Starting task..."},
    {"type": "tool_use", "name": "Read", "parameters": {"file": "test.py"}},
    {"type": "tool_result", "tool": "Read", "result": "File contents"},
    {"type": "content", "content": "Task complete!"},
    {"type": "result", "subtype": "success"}
]

for msg in messages:
    print(json.dumps(msg))
    sys.stdout.flush()
    time.sleep(0.1)
''')
            os.chmod(mock_claude, 0o755)
            
            # Create wrapper script to test
            wrapper_cmd = [
                sys.executable,
                str(Path(__file__).parent.parent / "emdx" / "utils" / "claude_wrapper.py"),
                "123",  # exec_id
                str(log_file),
                str(mock_claude)
            ]
            
            # Run wrapper
            result = subprocess.run(wrapper_cmd, capture_output=True, text=True)
            
            # Check execution completed
            assert result.returncode == 0, f"Wrapper failed: {result.stderr}"
            
            # Parse log file
            parser = LogParser(log_file)
            entries = parser.parse()
            
            # Should have entries from wrapper and mocked Claude output
            assert len(entries) > 0
            
            # Check for key events
            messages = [e.message for e in entries]
            
            # Should see execution lifecycle
            assert any("Starting execution #123" in m for m in messages)
            assert any("completed with success" in m for m in messages)
            
            # Should see Claude output
            assert any("Starting task..." in m for m in messages)
            assert any("Tool use: Read" in m for m in messages)
            assert any("Task complete!" in m for m in messages)
    
    def test_concurrent_process_logging(self):
        """Test that multiple processes can log concurrently without corruption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "concurrent.log"
            
            # Create multiple processes that log concurrently
            scripts = []
            for i in range(3):
                script = Path(tmpdir) / f"logger_{i}.py"
                process_type = ["MAIN", "WRAPPER", "CLAUDE"][i]
                with open(script, 'w') as f:
                    f.write(f'''#!/usr/bin/env python3
import sys
sys.path.insert(0, "{Path(__file__).parent.parent}")

from emdx.utils.structured_logger import StructuredLogger, ProcessType

logger = StructuredLogger("{log_file}", ProcessType.{process_type}, {1000 + i})

for j in range(10):
    logger.info(f"Message {{j}} from process {i}")
''')
                os.chmod(script, 0o755)
                scripts.append(script)
            
            # Run all scripts concurrently
            processes = []
            for script in scripts:
                p = subprocess.Popen([sys.executable, str(script)])
                processes.append(p)
            
            # Wait for completion
            for p in processes:
                p.wait()
            
            # Parse and verify
            parser = LogParser(log_file)
            entries = parser.parse()
            
            # Should have 30 entries total
            assert len(entries) == 30
            
            # Count by process type
            summary = parser.get_execution_summary()
            assert summary["processes"]["main"] == 10
            assert summary["processes"]["wrapper"] == 10
            assert summary["processes"]["claude"] == 10
            
            # Verify no corruption - all entries should be valid
            for entry in entries:
                assert entry.timestamp is not None
                assert entry.level == "INFO"
                assert entry.process_type in ["main", "wrapper", "claude"]
                assert "Message" in entry.message
    
    def test_log_filtering_and_display(self):
        """Test that log filtering works correctly for display."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "filter_test.log"
            
            # Create structured logger and write various entries
            logger = StructuredLogger(log_file, ProcessType.WRAPPER)
            
            # Write mix of entries
            logger.info("Starting Claude process")  # Wrapper noise
            logger.error("Failed to connect")  # Important error
            logger.log_claude_output({
                "type": "content",
                "content": "Hello, I'm Claude"
            })
            logger.info("Database updated successfully")  # Wrapper noise
            logger.log_claude_output({
                "type": "tool_use",
                "name": "Read",
                "parameters": {"file": "test.py"}
            })
            
            # Parse with different filters
            parser = LogParser(log_file)
            
            # No filtering
            all_entries = parser.get_filtered_entries()
            assert len(all_entries) == 5
            
            # Filter wrapper noise
            no_noise = parser.get_filtered_entries(show_wrapper_noise=False)
            assert len(no_noise) == 3  # Error and 2 Claude messages
            
            # Filter by level
            errors_only = parser.get_filtered_entries(level_filter="ERROR")
            assert len(errors_only) == 1
            assert errors_only[0].message == "Failed to connect"
            
            # Check display formatting
            for entry in no_noise:
                display = entry.format_for_display(show_process=True)
                assert "[wrapper]" in display
                if entry.context.get("claude_type") == "tool_use":
                    assert "📖" in display  # Read tool emoji
    
    def test_log_migration_compatibility(self):
        """Test that legacy logs can be migrated and parsed correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_log = Path(tmpdir) / "legacy.log"
            migrated_log = Path(tmpdir) / "migrated.log"
            
            # Create legacy format log
            with open(legacy_log, 'w') as f:
                f.write("[10:30:45] 🚀 Starting Claude process...\n")
                f.write("[10:30:46] 💬 Hello from Claude\n")
                f.write("[10:30:47] 🛠️ Using tool: Read\n")
                f.write("[10:30:48] ❌ Error: File not found\n")
                f.write("[10:30:49] ✅ Task completed successfully!\n")
            
            # Import and use migration
            from emdx.utils.log_migration import migrate_log_file
            
            entries_migrated = migrate_log_file(legacy_log, migrated_log)
            assert entries_migrated == 5
            
            # Parse migrated log
            parser = LogParser(migrated_log)
            entries = parser.parse()
            
            assert len(entries) == 5
            
            # Check conversion
            assert entries[0].process_type == "wrapper"
            assert "Starting Claude process" in entries[0].message
            
            assert entries[1].process_type == "claude"
            assert "Hello from Claude" in entries[1].message
            
            assert entries[3].level == "ERROR"
            assert "File not found" in entries[3].message
            
            # Check that tool use was detected
            tool_entry = entries[2]
            assert tool_entry.context.get("claude_type") == "tool_use"
            assert tool_entry.context.get("tool") == "Read"