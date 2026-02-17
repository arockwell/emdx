"""
Structured logging system for EMDX with process synchronization.

This module provides a centralized logging solution that:
1. Uses structured JSON format for all log entries
2. Includes process identification and context
3. Ensures atomic writes to prevent interleaving
4. Supports filtering and searching in the TUI
"""

import json
import os
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Union


class LogLevel(Enum):
    """Log levels for structured logging."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProcessType(Enum):
    """Types of processes that write logs."""

    MAIN = "main"
    WRAPPER = "wrapper"
    CLAUDE = "claude"
    TUI = "tui"


class StructuredLogger:
    """Thread-safe structured logger for EMDX processes."""

    def __init__(
        self, log_file: Union[str, Path], process_type: ProcessType, process_id: int | None = None
    ):
        """Initialize the structured logger.

        Args:
            log_file: Path to the log file
            process_type: Type of process (main, wrapper, claude, tui)
            process_id: Process ID (defaults to current PID)
        """
        self.log_file = Path(log_file)
        self.process_type = process_type
        self.process_id = process_id or os.getpid()
        self._lock = threading.Lock()

        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _create_entry(
        self, level: LogLevel, message: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a structured log entry.

        Args:
            level: Log level
            message: Log message
            context: Additional context data

        Returns:
            Structured log entry as a dict
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.value,
            "process": {
                "type": self.process_type.value,
                "pid": self.process_id,
                "name": f"{self.process_type.value}-{self.process_id}",
            },
            "message": message,
        }

        if context:
            entry["context"] = context

        return entry

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """Write a log entry atomically to the log file.

        Args:
            entry: Log entry to write
        """
        with self._lock:
            try:
                # Write as a single JSON line with newline
                json_line = json.dumps(entry, separators=(",", ":")) + "\n"

                # Open in append mode and write atomically
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json_line)
                    f.flush()  # Ensure immediate write
                    os.fsync(f.fileno())  # Force write to disk

            except Exception as e:
                # If we can't write to log, at least print to stderr
                import sys

                print(f"Failed to write log entry: {e}", file=sys.stderr)

    def log(self, level: LogLevel, message: str, context: dict[str, Any] | None = None) -> None:
        """Write a log entry.

        Args:
            level: Log level
            message: Log message
            context: Additional context data
        """
        entry = self._create_entry(level, message, context)
        self._write_entry(entry)

    def debug(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Write a debug log entry."""
        self.log(LogLevel.DEBUG, message, context)

    def info(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Write an info log entry."""
        self.log(LogLevel.INFO, message, context)

    def warning(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Write a warning log entry."""
        self.log(LogLevel.WARNING, message, context)

    def error(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Write an error log entry."""
        self.log(LogLevel.ERROR, message, context)

    def critical(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Write a critical log entry."""
        self.log(LogLevel.CRITICAL, message, context)

    def log_claude_output(self, json_data: dict[str, Any]) -> None:
        """Log Claude's JSON output with proper formatting.

        Args:
            json_data: Parsed JSON data from Claude
        """
        # Extract message type and content
        msg_type = json_data.get("type", "unknown")

        if msg_type == "content":
            # Text content from Claude
            content = json_data.get("content", "")
            self.info(f"Claude: {content}", {"claude_type": "content"})

        elif msg_type == "tool_use":
            # Tool usage
            tool_name = json_data.get("name", "unknown")
            tool_params = json_data.get("parameters", {})
            self.info(
                f"Tool use: {tool_name}",
                {"claude_type": "tool_use", "tool": tool_name, "parameters": tool_params},
            )

        elif msg_type == "tool_result":
            # Tool result
            tool_name = json_data.get("tool", "unknown")
            result = json_data.get("result", "")
            # Truncate very long results
            if isinstance(result, str) and len(result) > 1000:
                result = result[:1000] + "... (truncated)"
            self.info(
                f"Tool result: {tool_name}",
                {"claude_type": "tool_result", "tool": tool_name, "result": result},
            )

        elif msg_type == "error":
            # Error from Claude
            error = json_data.get("error", {}).get("message", "Unknown error")
            self.error(f"Claude error: {error}", {"claude_type": "error"})

        elif msg_type == "result":
            # Final result
            subtype = json_data.get("subtype", "unknown")
            if subtype == "success":
                self.info(
                    "Task completed successfully", {"claude_type": "result", "subtype": "success"}
                )  # noqa: E501
            else:
                result = json_data.get("result", "Unknown error")
                self.error(
                    f"Task failed: {result}", {"claude_type": "result", "subtype": "failure"}
                )  # noqa: E501
        else:
            # Unknown type - log for debugging
            self.debug(f"Unknown Claude message type: {msg_type}", {"claude_data": json_data})

    def log_execution_start(self, exec_id: int, doc_title: str, working_dir: str) -> None:
        """Log the start of an execution with metadata."""
        self.info(
            f"Starting execution #{exec_id}: {doc_title}",
            {
                "event": "execution_start",
                "exec_id": exec_id,
                "doc_title": doc_title,
                "working_dir": working_dir,
            },
        )

    def log_execution_complete(self, exec_id: int, exit_code: int, duration: float) -> None:
        """Log the completion of an execution."""
        status = "success" if exit_code == 0 else "failure"
        self.info(
            f"Execution #{exec_id} completed with {status} (exit code: {exit_code})",
            {
                "event": "execution_complete",
                "exec_id": exec_id,
                "exit_code": exit_code,
                "status": status,
                "duration_seconds": duration,
            },
        )

    def log_process_lifecycle(self, event: str, details: dict[str, Any] | None = None) -> None:
        """Log process lifecycle events (start, heartbeat, stop)."""
        self.info(f"Process {event}", {"event": f"process_{event}", "details": details or {}})
