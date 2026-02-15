"""Parser for Claude CLI stream-json output format.

The stream-json format outputs one JSON object per line with types like:
- system: initialization info
- assistant: Claude's text responses
- content_block_delta: streaming text chunks
- user: tool results
- result: final output

This module extracts just the human-readable text content.

For LIVE LOGS display, use parse_stream_json_line_rich() which returns
structured data including timestamps, event types, and tool info.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Structured event from stream-json parsing."""

    event_type: str  # "text", "tool", "status", "result", "skip"
    content: str  # Main content to display
    timestamp: datetime | None = None  # From StructuredLogger lines
    tool_name: str | None = None  # For tool_use events
    tool_input: str | None = None  # Brief summary of tool input
    raw_line: str = ""  # Original line for debugging


def parse_stream_json_line(line: str) -> Tuple[str, str]:
    """Parse a single stream-json line and extract text content.

    Args:
        line: A single line from stream-json output

    Returns:
        Tuple of (content_type, text) where:
        - content_type is one of: "text", "result", "skip", "plain"
        - text is the extracted content (empty string for "skip")
    """
    line = line.strip()
    if not line:
        return ("skip", "")

    if not line.startswith("{"):
        # Plain text line
        return ("plain", line)

    try:
        obj = json.loads(line)
        msg_type = obj.get("type", "")

        # Extract text from assistant messages
        if msg_type == "assistant" and "message" in obj:
            msg = obj["message"]
            if "content" in msg:
                texts = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            texts.append(text)
                if texts:
                    return ("text", "\n".join(texts))

        # Handle content_block_delta for streaming text
        elif msg_type == "content_block_delta":
            delta = obj.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    return ("text", text)

        # Handle result message (final output)
        elif msg_type == "result":
            result_text = obj.get("result", "")
            if result_text:
                return ("result", result_text)

        # Skip all other JSON types (system, user, tool_use, etc.)
        return ("skip", "")

    except json.JSONDecodeError:
        # Not valid JSON, treat as plain text
        return ("plain", line)


def extract_text_from_stream_json(content: str) -> str:
    """Extract all text content from stream-json format.

    Args:
        content: Raw log content with stream-json lines

    Returns:
        Extracted plain text content with proper paragraph separation
    """
    text_parts = []

    for line in content.split("\n"):
        content_type, text = parse_stream_json_line(line)

        if content_type == "text":
            if text:
                # Add paragraph break between separate text blocks
                if text_parts and text_parts[-1] and not text_parts[-1].endswith("\n"):
                    text_parts.append("\n\n")
                text_parts.append(text)
        elif content_type == "result":
            text_parts.append("\n\n---\n\n**Result:**\n\n" + text)
        elif content_type == "plain":
            text_parts.append(text + "\n")
        # Skip "skip" type

    result = "".join(text_parts)

    # Clean up excessive newlines
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")

    return result.strip()


def filter_stream_json_for_display(content: str) -> List[str]:
    """Filter stream-json content and return lines suitable for display.

    Args:
        content: Raw log content with stream-json lines

    Returns:
        List of text lines to display
    """
    lines = []

    for line in content.split("\n"):
        content_type, text = parse_stream_json_line(line)

        if content_type == "text":
            # Split multi-line text blocks
            lines.extend(text.split("\n"))
        elif content_type == "result":
            lines.append("")
            lines.append("--- Result ---")
            lines.extend(text.split("\n"))
        elif content_type == "plain":
            lines.append(text)
        # Skip "skip" type

    return lines


def parse_stream_json_line_rich(line: str) -> StreamEvent:
    """Parse a stream-json line and return structured event data.

    This is the LIVE LOGS parser that extracts timestamps, tool calls,
    and provides rich formatting data for display.

    Args:
        line: A single line from stream-json output

    Returns:
        StreamEvent with structured data for display
    """
    line = line.strip()
    if not line:
        return StreamEvent(event_type="skip", content="", raw_line=line)

    if not line.startswith("{"):
        # Plain text line
        return StreamEvent(event_type="text", content=line, raw_line=line)

    try:
        obj = json.loads(line)
        msg_type = obj.get("type", "")

        # Check for StructuredLogger format (has timestamp, level, process)
        if "timestamp" in obj and "level" in obj and "process" in obj:
            try:
                ts_str = obj["timestamp"]
                # Parse ISO format timestamp
                if "+" in ts_str or ts_str.endswith("Z"):
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    ts = datetime.fromisoformat(ts_str)
            except (ValueError, TypeError):
                ts = None

            level = obj.get("level", "INFO")
            message = obj.get("message", "")
            return StreamEvent(
                event_type="status",
                content=f"[{level}] {message}",
                timestamp=ts,
                raw_line=line,
            )

        # Claude stream-json: assistant message with tool_use
        if msg_type == "assistant" and "message" in obj:
            msg = obj["message"]
            if "content" in msg:
                texts = []
                tools = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            texts.append(text)
                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        # Summarize input based on tool type
                        if isinstance(tool_input, dict):
                            if tool_name == "TodoWrite" and "todos" in tool_input:
                                # Format todos nicely
                                todos = tool_input["todos"]
                                if isinstance(todos, list) and todos:
                                    todo_lines = []
                                    for t in todos[:5]:  # Show up to 5 todos
                                        status = t.get("status", "pending")
                                        content = t.get("content", "")[:40]
                                        icon = "✅" if status == "completed" else "⏳" if status == "in_progress" else "○"
                                        todo_lines.append(f"{icon} {content}")
                                    summary = " | ".join(todo_lines)
                                    if len(todos) > 5:
                                        summary += f" (+{len(todos)-5} more)"
                                else:
                                    summary = "empty"
                            elif "file_path" in tool_input:
                                summary = tool_input["file_path"]
                            elif "command" in tool_input:
                                cmd = tool_input["command"]
                                summary = cmd[:50] + "..." if len(cmd) > 50 else cmd
                            elif "pattern" in tool_input:
                                summary = f"pattern: {tool_input['pattern']}"
                            else:
                                # First key-value
                                keys = list(tool_input.keys())[:2]
                                summary = ", ".join(f"{k}={tool_input[k]!r:.30}" for k in keys)
                        else:
                            summary = str(tool_input)[:50]
                        tools.append((tool_name, summary))

                if tools:
                    # Return tool event
                    tool_name, tool_summary = tools[0]
                    return StreamEvent(
                        event_type="tool",
                        content=f"🔧 {tool_name}: {tool_summary}",
                        tool_name=tool_name,
                        tool_input=tool_summary,
                        raw_line=line,
                    )
                elif texts:
                    return StreamEvent(
                        event_type="text",
                        content="\n".join(texts),
                        raw_line=line,
                    )

        # Claude stream-json: content_block_delta (streaming text chunks)
        elif msg_type == "content_block_delta":
            delta = obj.get("delta", {})
            if delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    return StreamEvent(
                        event_type="text",
                        content=text,
                        raw_line=line,
                    )

        # Claude stream-json: result
        elif msg_type == "result":
            result_text = obj.get("result", "")
            if result_text:
                return StreamEvent(
                    event_type="result",
                    content=result_text,
                    raw_line=line,
                )

        # Claude stream-json: system init
        elif msg_type == "system" and obj.get("subtype") == "init":
            model = obj.get("model", "unknown")
            return StreamEvent(
                event_type="status",
                content=f"🚀 Session started (model: {model})",
                raw_line=line,
            )

        # Skip other types
        return StreamEvent(event_type="skip", content="", raw_line=line)

    except json.JSONDecodeError:
        # Not valid JSON, treat as plain text
        return StreamEvent(event_type="text", content=line, raw_line=line)


def format_live_log_line(event: StreamEvent) -> str:
    """Format a StreamEvent for live log display with timestamps.

    Args:
        event: Parsed stream event

    Returns:
        Formatted string for RichLog display
    """
    if event.event_type == "skip":
        return ""

    # Format timestamp if available
    ts_prefix = ""
    if event.timestamp:
        # Convert to local time and format
        local_ts = event.timestamp.astimezone() if event.timestamp.tzinfo else event.timestamp
        ts_prefix = f"[dim]{local_ts.strftime('%H:%M:%S')}[/dim] "

    if event.event_type == "status":
        return f"{ts_prefix}[bold blue]{event.content}[/bold blue]"
    elif event.event_type == "tool":
        return f"{ts_prefix}[yellow]{event.content}[/yellow]"
    elif event.event_type == "result":
        return f"{ts_prefix}[bold green]--- Result ---[/bold green]\n{event.content}"
    else:
        # Plain text
        return f"{ts_prefix}{event.content}" if ts_prefix else event.content


def parse_and_format_live_logs(content: str) -> List[str]:
    """Parse stream-json content and return formatted lines for live display.

    This is the main function for LIVE LOGS rendering. It parses the content
    and returns Rich-formatted lines with timestamps and styling.

    Args:
        content: Raw log content with stream-json lines

    Returns:
        List of Rich-formatted strings ready for RichLog.write()
    """
    lines = []

    for line in content.split("\n"):
        event = parse_stream_json_line_rich(line)
        if event.event_type != "skip":
            formatted = format_live_log_line(event)
            if formatted:
                # Split multi-line content
                for subline in formatted.split("\n"):
                    if subline:
                        lines.append(subline)

    return lines
