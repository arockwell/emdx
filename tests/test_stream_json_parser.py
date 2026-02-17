"""Tests for stream JSON parser."""

import json

from emdx.utils.stream_json_parser import (
    StreamEvent,
    extract_text_from_stream_json,
    filter_stream_json_for_display,
    format_live_log_line,
    parse_and_format_live_logs,
    parse_stream_json_line,
    parse_stream_json_line_rich,
)


class TestParseStreamJsonLine:
    """Test parse_stream_json_line function."""

    def test_empty_line(self):
        assert parse_stream_json_line("") == ("skip", "")

    def test_whitespace_only(self):
        assert parse_stream_json_line("   ") == ("skip", "")

    def test_plain_text(self):
        assert parse_stream_json_line("Hello world") == ("plain", "Hello world")

    def test_non_json_text(self):
        assert parse_stream_json_line("not json at all") == ("plain", "not json at all")

    def test_assistant_text_message(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello from Claude"}]},
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "text"
        assert text == "Hello from Claude"

    def test_assistant_multiple_text_blocks(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "First block"},
                    {"type": "text", "text": "Second block"},
                ]
            },
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "text"
        assert "First block" in text
        assert "Second block" in text

    def test_assistant_empty_text(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": ""}]},
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_assistant_tool_use_skipped(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Read", "input": {"file": "test.py"}}]
            },
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_content_block_delta(self):
        obj = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "streaming chunk"},
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "text"
        assert text == "streaming chunk"

    def test_content_block_delta_empty(self):
        obj = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": ""},
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_content_block_delta_non_text(self):
        obj = {
            "type": "content_block_delta",
            "delta": {"type": "input_json_delta", "partial_json": "{}"},
        }
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_result_message(self):
        obj = {"type": "result", "result": "Task completed successfully"}
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "result"
        assert text == "Task completed successfully"

    def test_result_empty(self):
        obj = {"type": "result", "result": ""}
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_system_message_skipped(self):
        obj = {"type": "system", "subtype": "init", "model": "claude-3"}
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_user_message_skipped(self):
        obj = {"type": "user", "message": {"content": "test"}}
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"

    def test_invalid_json(self):
        content_type, text = parse_stream_json_line("{invalid json")
        assert content_type == "plain"
        assert text == "{invalid json"

    def test_json_without_type(self):
        obj = {"key": "value"}
        content_type, text = parse_stream_json_line(json.dumps(obj))
        assert content_type == "skip"


class TestExtractTextFromStreamJson:
    """Test extract_text_from_stream_json function."""

    def test_empty_content(self):
        assert extract_text_from_stream_json("") == ""

    def test_single_text_line(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        }
        result = extract_text_from_stream_json(json.dumps(obj))
        assert "Hello" in result

    def test_multiple_lines(self):
        lines = []
        for text in ["First", "Second"]:
            obj = {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]},
            }
            lines.append(json.dumps(obj))
        content = "\n".join(lines)
        result = extract_text_from_stream_json(content)
        assert "First" in result
        assert "Second" in result

    def test_result_included(self):
        obj = {"type": "result", "result": "Done"}
        result = extract_text_from_stream_json(json.dumps(obj))
        assert "Done" in result
        assert "Result" in result

    def test_skips_system_messages(self):
        lines = [
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "Hello"}]},
                }
            ),
        ]
        result = extract_text_from_stream_json("\n".join(lines))
        assert "Hello" in result

    def test_plain_text_lines(self):
        result = extract_text_from_stream_json("plain text here")
        assert "plain text here" in result

    def test_cleans_triple_newlines(self):
        obj1 = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "A"}]},
        }
        obj2 = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "B"}]},
        }
        content = json.dumps(obj1) + "\n\n\n" + json.dumps(obj2)
        result = extract_text_from_stream_json(content)
        assert "\n\n\n" not in result


class TestFilterStreamJsonForDisplay:
    """Test filter_stream_json_for_display function."""

    def test_empty_content(self):
        assert filter_stream_json_for_display("") == []

    def test_text_lines(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        }
        lines = filter_stream_json_for_display(json.dumps(obj))
        assert "Hello" in lines

    def test_result_formatted(self):
        obj = {"type": "result", "result": "Done"}
        lines = filter_stream_json_for_display(json.dumps(obj))
        assert "--- Result ---" in lines
        assert "Done" in lines

    def test_plain_text(self):
        lines = filter_stream_json_for_display("plain text")
        assert "plain text" in lines

    def test_multiline_text_split(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Line 1\nLine 2\nLine 3"}]},
        }
        lines = filter_stream_json_for_display(json.dumps(obj))
        assert "Line 1" in lines
        assert "Line 2" in lines
        assert "Line 3" in lines


class TestParseStreamJsonLineRich:
    """Test parse_stream_json_line_rich function."""

    def test_empty_line(self):
        event = parse_stream_json_line_rich("")
        assert event.event_type == "skip"
        assert event.content == ""

    def test_plain_text(self):
        event = parse_stream_json_line_rich("Hello world")
        assert event.event_type == "text"
        assert event.content == "Hello world"

    def test_structured_logger_format(self):
        obj = {
            "timestamp": "2025-01-10T10:30:00",
            "level": "INFO",
            "process": "main",
            "message": "Starting task",
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "status"
        assert "[INFO]" in event.content
        assert "Starting task" in event.content
        assert event.timestamp is not None

    def test_structured_logger_with_timezone(self):
        obj = {
            "timestamp": "2025-01-10T10:30:00+00:00",
            "level": "DEBUG",
            "process": "worker",
            "message": "Processing",
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "status"
        assert event.timestamp is not None
        assert event.timestamp.year == 2025
        assert event.timestamp.month == 1
        assert event.timestamp.day == 10
        assert "[DEBUG]" in event.content
        assert "Processing" in event.content

    def test_structured_logger_with_z_suffix(self):
        obj = {
            "timestamp": "2025-01-10T10:30:00Z",
            "level": "INFO",
            "process": "main",
            "message": "Done",
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "status"
        assert event.timestamp is not None
        assert event.timestamp.year == 2025
        assert event.timestamp.hour == 10
        assert event.timestamp.minute == 30
        assert "[INFO]" in event.content
        assert "Done" in event.content

    def test_structured_logger_invalid_timestamp(self):
        obj = {
            "timestamp": "not-a-date",
            "level": "INFO",
            "process": "main",
            "message": "Test",
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "status"
        assert event.timestamp is None

    def test_assistant_tool_use(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/tmp/test.py"},
                    }
                ]
            },
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "tool"
        assert event.tool_name == "Read"
        assert "/tmp/test.py" in event.content

    def test_assistant_tool_use_command(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    }
                ]
            },
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "tool"
        assert event.tool_name == "Bash"
        assert "ls -la" in event.content

    def test_assistant_tool_use_long_command_truncated(self):
        long_cmd = "x" * 100
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": long_cmd},
                    }
                ]
            },
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "tool"
        assert "..." in event.content

    def test_assistant_tool_use_pattern(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Glob",
                        "input": {"pattern": "**/*.py"},
                    }
                ]
            },
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "tool"
        assert "**/*.py" in event.content

    def test_assistant_text_message(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello from Claude"}]},
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "text"
        assert event.content == "Hello from Claude"

    def test_content_block_delta(self):
        obj = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "streaming"},
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "text"
        assert event.content == "streaming"

    def test_result(self):
        obj = {"type": "result", "result": "All done"}
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "result"
        assert event.content == "All done"

    def test_system_init(self):
        obj = {"type": "system", "subtype": "init", "model": "claude-3-opus"}
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "status"
        assert "claude-3-opus" in event.content

    def test_unknown_type_skipped(self):
        obj = {"type": "unknown_type", "data": "stuff"}
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "skip"

    def test_invalid_json(self):
        event = parse_stream_json_line_rich("{bad json")
        assert event.event_type == "text"
        assert event.content == "{bad json"

    def test_raw_line_preserved(self):
        line = json.dumps({"type": "result", "result": "test"})
        event = parse_stream_json_line_rich(line)
        assert event.raw_line == line

    def test_todo_write_tool(self):
        obj = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "TodoWrite",
                        "input": {
                            "todos": [
                                {"status": "completed", "content": "First task"},
                                {"status": "in_progress", "content": "Second task"},
                                {"status": "pending", "content": "Third task"},
                            ]
                        },
                    }
                ]
            },
        }
        event = parse_stream_json_line_rich(json.dumps(obj))
        assert event.event_type == "tool"
        assert event.tool_name == "TodoWrite"


class TestFormatLiveLogLine:
    """Test format_live_log_line function."""

    def test_skip_event(self):
        event = StreamEvent(event_type="skip", content="")
        assert format_live_log_line(event) == ""

    def test_status_event(self):
        event = StreamEvent(event_type="status", content="[INFO] Starting")
        result = format_live_log_line(event)
        assert "[bold blue]" in result
        assert "[INFO] Starting" in result

    def test_tool_event(self):
        event = StreamEvent(event_type="tool", content="Read: test.py")
        result = format_live_log_line(event)
        assert "[yellow]" in result
        assert "Read: test.py" in result

    def test_result_event(self):
        event = StreamEvent(event_type="result", content="Done")
        result = format_live_log_line(event)
        assert "[bold green]" in result
        assert "Done" in result

    def test_text_event_no_timestamp(self):
        event = StreamEvent(event_type="text", content="Hello")
        result = format_live_log_line(event)
        assert result == "Hello"

    def test_event_with_timestamp(self):
        from datetime import datetime, timezone

        ts = datetime(2025, 1, 10, 10, 30, 0, tzinfo=timezone.utc)
        event = StreamEvent(event_type="text", content="Hello", timestamp=ts)
        result = format_live_log_line(event)
        assert "Hello" in result
        assert "[dim]" in result


class TestParseAndFormatLiveLogs:
    """Test parse_and_format_live_logs function."""

    def test_empty_content(self):
        assert parse_and_format_live_logs("") == []

    def test_filters_skip_events(self):
        obj = {"type": "system", "subtype": "init", "model": "test"}
        # System init becomes a status event, not skip
        lines = parse_and_format_live_logs(json.dumps(obj))
        # Should have status line with model info
        assert len(lines) == 1
        assert "Session started" in lines[0]
        assert "test" in lines[0]  # model name

    def test_formats_text(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Hello"}]},
        }
        lines = parse_and_format_live_logs(json.dumps(obj))
        assert any("Hello" in line for line in lines)

    def test_multiline_split(self):
        obj = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "Line1\nLine2"}]},
        }
        lines = parse_and_format_live_logs(json.dumps(obj))
        assert len(lines) >= 2
