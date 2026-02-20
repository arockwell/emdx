"""Unified executor for CLI execution paths.

This module provides a unified interface for executing tasks with the
Claude CLI. It provides consistent execution tracking and result handling.

Uses stream-json output format by default for real-time log streaming.
"""

import logging
import queue
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from ..config.cli_config import DEFAULT_ALLOWED_TOOLS
from ..config.constants import EMDX_LOG_DIR
from ..models.executions import create_execution, update_execution_status
from ..utils.environment import get_subprocess_env
from .cli_executor import get_cli_executor
from .types import ExecutionResultDict

logger = logging.getLogger(__name__)


class ProcResult:
    """Mock result object for subprocess compatibility."""

    stdout: str
    stderr: str
    returncode: int | None

    def __init__(self) -> None:
        self.stdout = ""
        self.stderr = ""
        self.returncode = None


# Tool emojis for log formatting
TOOL_EMOJIS = {
    "Read": "📖",
    "Write": "📝",
    "Edit": "✏️",
    "MultiEdit": "✏️",
    "Bash": "💻",
    "Glob": "🔍",
    "Grep": "🔎",
    "LS": "📂",
    "Task": "📋",
    "TodoWrite": "✅",
    "WebFetch": "🌐",
    "WebSearch": "🔍",
}


def format_timestamp(ts: float) -> str:
    """Format timestamp as [HH:MM:SS]."""
    dt = datetime.fromtimestamp(ts)
    return f"[{dt.strftime('%H:%M:%S')}]"


def format_stream_message(msg: Mapping[str, Any], timestamp: float) -> str | None:
    """Format a pre-parsed stream message into readable log output.

    Accepts the dict returned by CliExecutor.parse_stream_line().
    Typed as Mapping[str, Any] because the function reads keys from multiple
    message types; type safety is enforced at the construction site.
    """
    msg_type = msg.get("type")
    ts = format_timestamp(timestamp)

    if msg_type == "system":
        if msg.get("subtype") == "init":
            model = msg.get("model", "Unknown")
            return f"{ts} 🚀 Session started (model: {model})"
        return None

    elif msg_type == "thinking":
        if msg.get("subtype") == "completed":
            return f"{ts} 💭 Thinking completed"
        # Skip delta messages (too spammy)
        return None

    elif msg_type == "assistant":
        text = msg.get("text", "").strip()
        if text:
            if len(text) > 200:
                text = text[:200] + "..."
            return f"{ts} 🤖 Assistant: {text}"
        # Check for tool uses
        tool_uses = msg.get("tool_uses", [])
        if tool_uses:
            tool_name = tool_uses[0].get("name", "Unknown")
            emoji = TOOL_EMOJIS.get(tool_name, "🛠️")
            return f"{ts} {emoji} Using tool: {tool_name}"

    elif msg_type == "tool_call":
        subtype = msg.get("subtype")
        tool_call = msg.get("tool_call", {})

        if subtype == "started":
            if "shellToolCall" in tool_call:
                cmd = tool_call["shellToolCall"].get("args", {}).get("command", "")[:60]
                return f"{ts} 💻 Running: {cmd}..."
            elif "readToolCall" in tool_call:
                path = tool_call["readToolCall"].get("args", {}).get("path", "")
                return f"{ts} 📖 Reading: {path}"
            elif "globToolCall" in tool_call:
                pattern = tool_call["globToolCall"].get("args", {}).get("globPattern", "")
                return f"{ts} 🔍 Glob: {pattern}"
            else:
                return f"{ts} 🛠️ Tool call started"

        elif subtype == "completed":
            result = tool_call.get("result", {})
            if "success" in result:
                return f"{ts} ✅ Tool completed"
            elif "error" in result:
                err = result.get("error", {}).get("message", "Unknown error")[:100]
                return f"{ts} ❌ Tool error: {err}"

    elif msg_type == "result":
        success = msg.get("success", True)
        duration = msg.get("duration_ms", 0)
        raw_line = msg.get("raw_line", "")
        if not success:
            result_text = (msg.get("result") or "Unknown error")[:100]
            return f"{ts} ❌ Failed ({duration}ms): {result_text}\n__RAW_RESULT_JSON__:{raw_line}"  # noqa: E501
        else:
            return f"{ts} ✅ Completed ({duration}ms)\n__RAW_RESULT_JSON__:{raw_line}"  # noqa: E501

    elif msg_type == "error":
        error = msg.get("error", {}).get("message", "Unknown error")
        return f"{ts} ❌ Error: {error}"

    # Unknown type or user message - skip
    return None


def _reader_thread(pipe: IO[str], line_queue: queue.Queue[str | None]) -> None:
    """Read lines from a pipe and put them on a queue.

    Runs in a background thread. Using simple iteration (``for line in pipe``)
    is reliable across platforms, unlike ``select.select()`` which doesn't
    work with ``subprocess.Popen`` pipes on macOS.
    """
    try:
        for line in pipe:
            line_queue.put(line)
    except ValueError:
        pass  # pipe closed
    finally:
        line_queue.put(None)  # sentinel: EOF


@dataclass
class ExecutionConfig:
    """Configuration for a CLI execution."""

    prompt: str
    working_dir: str = field(default_factory=lambda: str(Path.cwd()))
    title: str = "CLI Execution"
    doc_id: int | None = None
    output_instruction: str | None = None
    allowed_tools: list[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy())
    timeout_seconds: int = 300
    cli_tool: str = "claude"
    model: str | None = None  # Override default model for the CLI
    verbose: bool = False  # Stream output in real-time


@dataclass
class ExecutionResult:
    """Result of a CLI execution."""

    success: bool
    execution_id: int
    log_file: Path
    output_doc_id: int | None = None
    output_content: str | None = None
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    execution_time_ms: int = 0
    error_message: str | None = None
    exit_code: int | None = None
    cli_tool: str = "claude"  # Which CLI was used

    def to_dict(self) -> ExecutionResultDict:
        return {
            "success": self.success,
            "execution_id": self.execution_id,
            "log_file": str(self.log_file),
            "output_doc_id": self.output_doc_id,
            "output_content": self.output_content,
            "tokens_used": self.tokens_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "exit_code": self.exit_code,
            "cli_tool": self.cli_tool,
        }


class UnifiedExecutor:
    """Unified executor for all CLI execution paths."""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or EMDX_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, config: ExecutionConfig) -> ExecutionResult:
        """Execute a task with the configured CLI tool.

        Args:
            config: Execution configuration including prompt, cli_tool, etc.

        Returns:
            ExecutionResult with success status, output, and metrics.
        """
        import subprocess

        from ..utils.output_parser import extract_output_doc_id, extract_token_usage_detailed

        # Get the appropriate executor for the CLI tool
        executor = get_cli_executor(config.cli_tool)

        # Validate environment
        is_valid, env_info = executor.validate_environment()
        if not is_valid:
            errors = env_info.get("errors", ["Unknown error"])
            return ExecutionResult(
                success=False,
                execution_id=0,
                log_file=Path("/dev/null"),
                error_message=f"Environment validation failed: {'; '.join(errors)}",
                cli_tool=config.cli_tool,
            )

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        thread_id = threading.get_ident()
        log_file = self.log_dir / f"unified-{config.cli_tool}-{timestamp}-{thread_id}.log"

        exec_id = create_execution(
            doc_id=config.doc_id,
            doc_title=config.title,
            log_file=str(log_file),
            working_dir=config.working_dir,
        )

        full_prompt = config.prompt
        if config.output_instruction:
            full_prompt = config.prompt + config.output_instruction

        start_time = time.time()

        try:
            # Build command using the CLI executor
            # stream-json is the default from config - enables real-time log streaming
            cmd = executor.build_command(
                prompt=full_prompt,
                model=config.model,
                allowed_tools=config.allowed_tools,
                working_dir=config.working_dir,
            )

            logger.debug(f"Executing {config.cli_tool} command: {' '.join(cmd.args[:3])}...")

            # Ensure log file directory exists
            log_file.parent.mkdir(parents=True, exist_ok=True)

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            if config.verbose:
                # Stream output in real-time using Popen + reader thread
                import sys

                deadline = start_time + config.timeout_seconds

                with open(log_file, "w") as f:
                    process = subprocess.Popen(
                        cmd.args,
                        stdin=subprocess.PIPE if cmd.stdin_data else None,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=cmd.cwd,
                        env=get_subprocess_env(),
                    )

                    # Feed prompt via stdin then close to signal EOF
                    if cmd.stdin_data and process.stdin:
                        process.stdin.write(cmd.stdin_data)
                        process.stdin.close()

                    # Read stdout via background thread (reliable on macOS)
                    stdout_q: queue.Queue[str | None] = queue.Queue()
                    reader = threading.Thread(
                        target=_reader_thread,
                        args=(process.stdout, stdout_q),
                        daemon=True,
                    )
                    reader.start()

                    while True:
                        if time.time() > deadline:
                            process.kill()
                            process.wait()
                            raise subprocess.TimeoutExpired(cmd.args, config.timeout_seconds)

                        try:
                            line = stdout_q.get(timeout=1.0)
                        except queue.Empty:
                            continue

                        if line is None:  # EOF sentinel
                            break

                        stdout_lines.append(line)
                        parsed = executor.parse_stream_line(line)
                        formatted = format_stream_message(parsed, time.time()) if parsed else None
                        if formatted:
                            f.write(formatted + "\n")
                            f.flush()
                            sys.stdout.write(formatted + "\n")
                            sys.stdout.flush()

                    reader.join(timeout=5.0)
                    process.wait()

                    # Capture stderr
                    if process.stderr:
                        stderr_output = process.stderr.read()
                        if stderr_output:
                            stderr_lines.append(stderr_output)
                            f.write(f"\n--- STDERR ---\n{stderr_output}\n")

                    exit_code = process.returncode

                # Create a mock result object for compatibility
                proc_result = ProcResult()
                proc_result.stdout = "".join(stdout_lines)
                proc_result.stderr = "".join(stderr_lines)
                proc_result.returncode = exit_code
            else:
                # Stream output to log file in real-time (without terminal output)
                # This enables Activity browser to show live logs
                stdout_lines = []
                stderr_lines = []
                deadline = start_time + config.timeout_seconds

                with open(log_file, "w") as f:
                    process = subprocess.Popen(
                        cmd.args,
                        stdin=subprocess.PIPE if cmd.stdin_data else None,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=cmd.cwd,
                        env=get_subprocess_env(),
                    )

                    # Feed prompt via stdin then close to signal EOF
                    if cmd.stdin_data and process.stdin:
                        process.stdin.write(cmd.stdin_data)
                        process.stdin.close()

                    # Read stdout via background thread (reliable on macOS)
                    stdout_q = queue.Queue()
                    reader = threading.Thread(
                        target=_reader_thread,
                        args=(process.stdout, stdout_q),
                        daemon=True,
                    )
                    reader.start()

                    while True:
                        if time.time() > deadline:
                            process.kill()
                            process.wait()
                            raise subprocess.TimeoutExpired(cmd.args, config.timeout_seconds)

                        try:
                            line = stdout_q.get(timeout=1.0)
                        except queue.Empty:
                            continue

                        if line is None:  # EOF sentinel
                            break

                        stdout_lines.append(line)
                        parsed = executor.parse_stream_line(line)
                        formatted = format_stream_message(parsed, time.time()) if parsed else None
                        if formatted:
                            f.write(formatted + "\n")
                            f.flush()  # Flush immediately for live viewing

                    reader.join(timeout=5.0)
                    process.wait()

                    # Capture stderr
                    if process.stderr:
                        stderr_output = process.stderr.read()
                        if stderr_output:
                            stderr_lines.append(stderr_output)
                            f.write(f"\n--- STDERR ---\n{stderr_output}\n")

                    exit_code = process.returncode

                # Create a mock result object for compatibility
                proc_result = ProcResult()
                proc_result.stdout = "".join(stdout_lines)
                proc_result.stderr = "".join(stderr_lines)
                proc_result.returncode = exit_code

            # Parse the result
            cli_result = executor.parse_output(
                proc_result.stdout,
                proc_result.stderr,
                proc_result.returncode,
            )

            success = cli_result.success
            exit_code = cli_result.exit_code
            status = "completed" if success else "failed"
            update_execution_status(exec_id, status, exit_code)

            result = ExecutionResult(
                success=success,
                execution_id=exec_id,
                log_file=log_file,
                exit_code=exit_code,
                cli_tool=config.cli_tool,
            )

            if success:
                result.output_doc_id = extract_output_doc_id(log_file)
                result.output_content = cli_result.output
                if cli_result.output:
                    from ..models.executions import update_execution

                    update_execution(exec_id, output_text=cli_result.output)
            else:
                result.error_message = cli_result.error or "Unknown error"

            result.execution_time_ms = int((time.time() - start_time) * 1000)

            # Get token usage from CLI result
            result.tokens_used = cli_result.total_tokens
            result.input_tokens = cli_result.input_tokens + cli_result.cache_read_tokens
            result.output_tokens = cli_result.output_tokens
            result.cost_usd = cli_result.cost_usd

            # Try to extract from log file as fallback (for stream-json format)
            if result.tokens_used == 0 and log_file.exists():
                usage = extract_token_usage_detailed(log_file)
                if usage.get("total", 0) > 0:
                    result.tokens_used = int(usage.get("total", 0))
                    result.input_tokens = (
                        int(usage.get("input", 0))
                        + int(usage.get("cache_in", 0))
                        + int(usage.get("cache_create", 0))
                    )  # noqa: E501
                    result.output_tokens = int(usage.get("output", 0))
                    result.cost_usd = usage.get("cost_usd", 0.0)

            # Persist metrics to execution record
            if result.tokens_used > 0 or result.cost_usd > 0:
                try:
                    from ..models.executions import update_execution

                    update_execution(
                        exec_id,
                        cost_usd=result.cost_usd,
                        tokens_used=result.tokens_used,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                    )
                except Exception:
                    logger.debug("Could not persist execution metrics", exc_info=True)

            return result

        except subprocess.TimeoutExpired:
            logger.error(f"Execution timed out after {config.timeout_seconds}s")
            update_execution_status(exec_id, "failed", -1)
            return ExecutionResult(
                success=False,
                execution_id=exec_id,
                log_file=log_file,
                error_message=f"Timeout after {config.timeout_seconds} seconds",
                execution_time_ms=int((time.time() - start_time) * 1000),
                cli_tool=config.cli_tool,
            )

        except Exception as e:
            logger.exception("Execution failed: %s", e)
            update_execution_status(exec_id, "failed", -1)
            return ExecutionResult(
                success=False,
                execution_id=exec_id,
                log_file=log_file,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
                cli_tool=config.cli_tool,
            )
