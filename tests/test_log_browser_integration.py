"""Integration tests for log browser timestamp handling."""

import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest
from textual.pilot import Pilot
from textual.app import App
from textual.widgets import DataTable, RichLog

from emdx.ui.log_browser import LogBrowser
from emdx.models.executions import Execution, save_execution


class LogBrowserTestApp(App):
    """Test app for LogBrowser widget."""
    
    def compose(self):
        yield LogBrowser()


@pytest.mark.asyncio
async def test_log_browser_preserves_timestamps():
    """Test that log browser preserves original timestamps from log files."""
    # Create a test log file with known timestamps
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        
        # Write log content with various timestamp formats
        log_content = """=== EMDX Claude Execution ===
Version: 0.6.0
Build ID: 0.6.0-ba5bd0c2
Doc ID: 123
Execution ID: claude-123-1753244683
Started: 2025-07-23 00:24:43
==================================================

[00:24:43] 🚀 Claude Code session started
[00:24:44] 📋 Available tools: Read, Write, Edit
[00:24:45] 🤖 Claude: Starting execution
[00:25:00] 📖 Using tool: Read
[00:25:01] 📄 Tool result: File content...
[00:25:30] ✏️ Using tool: Edit
[00:26:00] 🤖 Claude: Task completed
[00:26:01] ✅ Task completed successfully! Duration: 78.0s
"""
        
        with open(log_file, 'w') as f:
            f.write(log_content)
        
        # Create a test execution record
        execution = Execution(
            id="claude-123-1753244683",
            doc_id=123,
            doc_title="Test Document",
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            log_file=str(log_file),
            working_dir="/tmp/test"
        )
        
        # Create app and test
        app = LogBrowserTestApp()
        async with app.run_test() as pilot:
            # Get the log browser widget
            log_browser = app.query_one(LogBrowser)
            
            # Set up test execution
            log_browser.executions = [execution]
            
            # Load the execution log
            await log_browser.load_execution_log(execution)
            
            # Get the log content widget
            log_content = app.query_one("#log-content", RichLog)
            
            # Check that timestamps are preserved
            # The log content should contain the original timestamps
            content_lines = []
            for line in log_content._lines:
                content_lines.append(str(line))
            
            content_text = "\n".join(content_lines)
            
            # Verify original timestamps are preserved
            assert "[00:24:43]" in content_text
            assert "[00:24:44]" in content_text
            assert "[00:24:45]" in content_text
            assert "[00:25:00]" in content_text
            assert "[00:25:01]" in content_text
            assert "[00:25:30]" in content_text
            assert "[00:26:00]" in content_text
            assert "[00:26:01]" in content_text
            
            # Verify content is formatted correctly with emojis
            assert "🚀 Claude Code session started" in content_text
            assert "📋 Available tools" in content_text
            assert "🤖 Claude: Starting execution" in content_text
            assert "📖 Using tool: Read" in content_text
            assert "✏️ Using tool: Edit" in content_text
            assert "✅ Task completed successfully" in content_text


@pytest.mark.asyncio
async def test_log_browser_handles_missing_timestamps():
    """Test that log browser handles lines without timestamps gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        
        # Write log content with mixed timestamp presence
        log_content = """=== EMDX Claude Execution ===
Doc ID: 123
Started: 2025-07-23 00:24:43
==================================================

[00:24:43] 🚀 Claude Code session started
This line has no timestamp
[00:24:44] 📋 Available tools: Read, Write
Another line without timestamp
[00:24:45] 🤖 Claude: Processing
Multi-line
content
without timestamps
[00:24:46] ✅ Done
"""
        
        with open(log_file, 'w') as f:
            f.write(log_content)
        
        # Create test execution
        execution = Execution(
            id="claude-123-1753244683",
            doc_id=123,
            doc_title="Test Document",
            status="completed",
            started_at=datetime.now(timezone.utc),
            log_file=str(log_file),
            working_dir="/tmp/test"
        )
        
        app = LogBrowserTestApp()
        async with app.run_test() as pilot:
            log_browser = app.query_one(LogBrowser)
            log_browser.executions = [execution]
            
            await log_browser.load_execution_log(execution)
            
            log_content = app.query_one("#log-content", RichLog)
            content_lines = []
            for line in log_content._lines:
                content_lines.append(str(line))
            
            content_text = "\n".join(content_lines)
            
            # Verify all content is present
            assert "This line has no timestamp" in content_text
            assert "Another line without timestamp" in content_text
            assert "Multi-line" in content_text
            assert "content" in content_text
            assert "without timestamps" in content_text
            
            # Verify timestamped lines are preserved
            assert "[00:24:43]" in content_text
            assert "[00:24:44]" in content_text
            assert "[00:24:45]" in content_text
            assert "[00:24:46]" in content_text


@pytest.mark.asyncio
async def test_log_browser_performance_with_large_logs():
    """Test that log browser handles large log files efficiently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "large.log"
        
        # Generate a large log file
        with open(log_file, 'w') as f:
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Started: 2025-07-23 00:00:00\n")
            f.write("==================================================\n\n")
            
            # Generate 1000 log entries
            for i in range(1000):
                hour = i // 3600
                minute = (i % 3600) // 60
                second = i % 60
                f.write(f"[{hour:02d}:{minute:02d}:{second:02d}] 🤖 Processing item {i}\n")
                if i % 10 == 0:
                    f.write(f"[{hour:02d}:{minute:02d}:{second:02d}] 📖 Using tool: Read\n")
                if i % 50 == 0:
                    f.write(f"Progress: {i/10}%\n")  # Line without timestamp
        
        execution = Execution(
            id="claude-123-large",
            doc_id=123,
            doc_title="Large Test",
            status="completed",
            started_at=datetime.now(timezone.utc),
            log_file=str(log_file),
            working_dir="/tmp/test"
        )
        
        app = LogBrowserTestApp()
        async with app.run_test() as pilot:
            log_browser = app.query_one(LogBrowser)
            log_browser.executions = [execution]
            
            # Measure load time
            import time
            start = time.time()
            await log_browser.load_execution_log(execution)
            load_time = time.time() - start
            
            # Should load within reasonable time (less than 1 second)
            assert load_time < 1.0
            
            # Verify content loaded
            log_content = app.query_one("#log-content", RichLog)
            assert len(log_content._lines) > 1000  # Should have all lines