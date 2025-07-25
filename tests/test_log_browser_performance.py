"""Performance tests for log browser timestamp parsing."""

import tempfile
import time
from datetime import datetime
from pathlib import Path

import pytest

from emdx.commands.claude_execute import format_claude_output, parse_log_timestamp
from emdx.ui.log_browser import LogBrowser


class TestLogBrowserPerformance:
    """Test performance of timestamp parsing in log browser."""

    def test_large_log_performance(self):
        """Test performance with large log files."""
        # Create a large log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = Path(f.name)

            # Write header
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Version: 1.0.0\n")
            f.write("==================================================\n\n")

            # Generate 10,000 log lines
            start_time = time.time()
            for i in range(10000):
                hour = 10 + (i // 3600)
                minute = (i // 60) % 60
                second = i % 60

                # Mix of timestamped lines and JSON lines
                if i % 3 == 0:
                    f.write(f"[{hour:02d}:{minute:02d}:{second:02d}] Log entry {i}\n")
                elif i % 3 == 1:
                    f.write(f'{{"type": "text", "text": "Processing item {i}"}}\n')
                else:
                    f.write(f"Regular log line without timestamp {i}\n")

            generation_time = time.time() - start_time
            print(f"\nGenerated 10,000 log lines in {generation_time:.2f}s")

        try:
            # Test parsing performance
            start_time = time.time()

            with open(log_file) as f:
                lines = f.readlines()

            last_timestamp = None
            formatted_count = 0

            for line in lines:
                # Skip header lines
                if line.startswith("===") or line.startswith("Version:") or not line.strip():
                    continue

                # Parse timestamp
                parsed_timestamp = parse_log_timestamp(line)
                if parsed_timestamp:
                    last_timestamp = parsed_timestamp

                # Format line
                timestamp_to_use = parsed_timestamp or last_timestamp or time.time()
                formatted = format_claude_output(line, timestamp_to_use)
                if formatted:
                    formatted_count += 1

            parsing_time = time.time() - start_time

            print(f"Parsed and formatted {formatted_count} lines in {parsing_time:.2f}s")
            print(f"Average time per line: {(parsing_time / len(lines)) * 1000:.3f}ms")

            # Performance assertions
            assert parsing_time < 2.0, f"Parsing took too long: {parsing_time:.2f}s"
            assert formatted_count > 0, "No lines were formatted"

        finally:
            log_file.unlink(missing_ok=True)

    def test_timestamp_parsing_performance(self):
        """Test performance of timestamp parsing alone."""
        # Test various timestamp formats
        test_lines = [
            "[14:32:15] Standard timestamp",
            "  [09:05:30] With whitespace",
            "No timestamp here",
            "[23:45:00] Late night",
            '{"type": "text", "text": "JSON content"}',
            "[00:00:00] Midnight",
            "Another line without timestamp",
            "[12:34:56] Another timestamp"
        ]

        # Run parsing 10,000 times
        iterations = 10000
        start_time = time.time()

        for _ in range(iterations):
            for line in test_lines:
                parse_log_timestamp(line)

        elapsed = time.time() - start_time
        total_parses = iterations * len(test_lines)

        print(f"\nParsed {total_parses} lines in {elapsed:.2f}s")
        print(f"Average time per parse: {(elapsed / total_parses) * 1000000:.1f}μs")

        # Should be very fast
        assert elapsed < 1.0, f"Parsing too slow: {elapsed:.2f}s for {total_parses} parses"

    def test_format_output_performance(self):
        """Test performance of format_claude_output."""
        test_lines = [
            '[14:32:15] Already has timestamp',
            '{"type": "text", "text": "Hello world"}',
            '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Response"}]}}',
            '{"type": "tool_use", "name": "Read"}',
            'Plain text line',
            '{"type": "error", "error": {"message": "Test error"}}',
            'Malformed JSON {{{',
            '{"type": "result", "subtype": "success"}'
        ]

        # Test timestamp
        test_timestamp = datetime(2024, 1, 1, 14, 32, 15).timestamp()

        # Run formatting 10,000 times
        iterations = 10000
        start_time = time.time()

        for _ in range(iterations):
            for line in test_lines:
                format_claude_output(line, test_timestamp)

        elapsed = time.time() - start_time
        total_formats = iterations * len(test_lines)

        print(f"\nFormatted {total_formats} lines in {elapsed:.2f}s")
        print(f"Average time per format: {(elapsed / total_formats) * 1000000:.1f}μs")

        # Should be fast even with JSON parsing
        assert elapsed < 2.0, f"Formatting too slow: {elapsed:.2f}s for {total_formats} formats"

    def test_real_world_log_patterns(self):
        """Test with realistic log patterns from Claude executions."""
        # Create a realistic log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_file = Path(f.name)

            # Simulate a real Claude execution log
            f.write("=== EMDX Claude Execution ===\n")
            f.write("Version: 1.2.0\n")
            f.write("Build ID: abc123\n")
            f.write("Doc ID: 456\n")
            f.write("Execution ID: exec-2024-01-01\n")
            f.write("Worktree: /tmp/exec-workspace\n")
            f.write("Started: 2024-01-01 14:00:00 UTC\n")
            f.write("==================================================\n\n")
            f.write("[14:00:00] 🎯 GAMEPLAN execution started\n")
            f.write("[14:00:00] 📋 Available tools: Read, Write, Edit, Bash\n")
            f.write("[14:00:01] 🚀 Starting Claude process...\n")

            # Add realistic Claude output
            for i in range(100):
                base_time = 14 * 3600 + i  # Start at 14:00:00
                hour = 14 + (base_time // 3600)
                minute = (base_time // 60) % 60
                second = base_time % 60

                # Mix of different output types
                if i % 10 == 0:
                    f.write(f'[{hour:02d}:{minute:02d}:{second:02d}] {"="*60}\n')
                elif i % 10 == 1:
                    f.write(
                        f'[{hour:02d}:{minute:02d}:{second:02d}] '
                        '📝 Prompt being sent to Claude:\n')
                elif i % 10 == 2:
                    f.write('Implement the authentication system for the web application\n')
                elif i % 10 == 3:
                    f.write(f'[{hour:02d}:{minute:02d}:{second:02d}] {"="*60}\n')
                elif i % 10 == 4:
                    f.write('{"type": "assistant", "message": {"content": '
                            '[{"type": "text", "text": "I\'ll help you implement '
                            'the authentication system. Let me start by examining '
                            'the current codebase structure."}]}}\n')
                elif i % 10 == 5:
                    f.write(
                        f'{{"type": "assistant", "message": {{"content": '
                        f'[{{"type": "tool_use", "name": "Grep", '
                        f'"id": "tool_{i}"}}]}}}}\n')
                elif i % 10 == 6:
                    f.write('{"type": "user", "message": {"role": "user", '
                            '"content": [{"type": "tool_result", '
                            '"content": "Found 5 matches in auth.py"}]}}\n')
                elif i % 10 == 7:
                    f.write('{"type": "text", "text": "Analyzing the authentication flow..."}\n')
                elif i % 10 == 8:
                    f.write(f'[{hour:02d}:{minute:02d}:{second:02d}] 📖 Using tool: Read\n')
                else:
                    f.write(f'[{hour:02d}:{minute:02d}:{second:02d}] Processing step {i}\n')

            f.write("[14:01:40] ✅ GAMEPLAN execution completed successfully!\n")
            f.write("[14:01:40] 🎯 All tasks finished\n")

        try:
            # Process the realistic log
            start_time = time.time()

            with open(log_file) as f:
                content = f.read()

            lines = content.splitlines()

            # Simulate log browser processing
            formatted_lines = []
            last_timestamp = None

            # Filter wrapper noise
            log_browser = LogBrowser()
            filtered_lines = []

            for line in lines:
                if not log_browser._is_wrapper_noise(line):
                    filtered_lines.append(line)

            # Process filtered lines
            for line in filtered_lines:
                if not line.strip():
                    continue

                parsed_timestamp = parse_log_timestamp(line)
                if parsed_timestamp:
                    last_timestamp = parsed_timestamp

                timestamp_to_use = parsed_timestamp or last_timestamp or time.time()

                formatted = format_claude_output(line, timestamp_to_use)
                if formatted:
                    formatted_lines.append(formatted)
                else:
                    formatted_lines.append(line)

            processing_time = time.time() - start_time

            print(f"\nProcessed realistic log with {len(lines)} lines in {processing_time:.3f}s")
            print(f"Filtered to {len(filtered_lines)} lines")
            print(f"Generated {len(formatted_lines)} formatted lines")
            print(f"Average time per line: {(processing_time / len(lines)) * 1000:.2f}ms")

            # Should handle realistic logs quickly
            assert processing_time < 0.5, f"Processing too slow: {processing_time:.3f}s"
            assert len(formatted_lines) > 50, "Too few lines formatted"

        finally:
            log_file.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

