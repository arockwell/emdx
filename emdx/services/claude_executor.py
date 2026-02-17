"""CLI execution service - handles spawning and managing CLI agent processes.

This module provides the core execution logic for running CLI agent processes
using the Claude CLI. Used by both:
- commands/claude_execute.py (CLI interface)
- services/task_runner.py (programmatic task execution)

This separation breaks the bidirectional dependency between commands and services.

IMPORTANT: All execution functions use stream-json output format by default.
This enables real-time log streaming. The format is configured in cli_config.py.
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from ..config.cli_config import DEFAULT_ALLOWED_TOOLS
from ..utils.environment import ensure_claude_in_path
from ..utils.structured_logger import ProcessType, StructuredLogger
from .cli_executor import get_cli_executor

logger = logging.getLogger(__name__)

# Re-export for backward compatibility - prefer importing from cli_config
__all__ = [
    "DEFAULT_ALLOWED_TOOLS",
    "execute_cli_sync",
    "execute_claude_detached",
    "parse_task_content",
]  # noqa: E501


def parse_task_content(task: str) -> str:
    """Parse task string, expanding @filename references.

    Args:
        task: Task description potentially containing @filename references

    Returns:
        Expanded task content with file contents included
    """
    # Find all @filename references
    pattern = r"@([^\s]+)"

    def replace_file_reference(match: re.Match[str]) -> str:
        filename = match.group(1)
        filepath = Path(filename)

        if filepath.exists() and filepath.is_file():
            try:
                content = filepath.read_text()
                return f"\n\nHere is the content of {filename}:\n\n```\n{content}\n```"
            except (OSError, UnicodeDecodeError) as e:
                logger.debug("Failed to read file %s: %s", filename, e)
                return f"[File not found: {filename}]"
        else:
            return f"[File not found: {filename}]"

    # Replace all @filename references
    expanded = re.sub(pattern, replace_file_reference, task)
    return expanded


def execute_claude_detached(
    task: str,
    execution_id: int,
    log_file: Path,
    allowed_tools: list[str] | None = None,
    working_dir: str | None = None,
    doc_id: str | None = None,
    cli_tool: str = "claude",
    model: str | None = None,
) -> int:
    """Execute a task with a CLI tool in a fully detached background process.

    This function starts the CLI and returns immediately without waiting.
    The subprocess continues running independently of the parent process.

    Uses stream-json output format by default for real-time log streaming.

    Args:
        task: The task prompt to execute
        execution_id: Numeric database execution ID
        log_file: Path to the log file
        allowed_tools: List of allowed tools (defaults to DEFAULT_ALLOWED_TOOLS)
        working_dir: Working directory for execution
        doc_id: Document ID (for logging)
        cli_tool: Which CLI to use ("claude")
        model: Model to use (None = default for the CLI)

    Returns:
        The process ID of the started subprocess.

    Raises:
        RuntimeError: If environment validation fails.
    """
    if allowed_tools is None:
        allowed_tools = list(DEFAULT_ALLOWED_TOOLS)

    # Get the appropriate executor
    executor = get_cli_executor(cli_tool)

    # Validate environment first
    is_valid, env_info = executor.validate_environment()
    if not is_valid:
        error_msg = "; ".join(env_info.get("errors", ["Unknown error"]))
        raise RuntimeError(f"Environment validation failed: {error_msg}")

    # Ensure claude is in PATH (for Claude CLI)
    if cli_tool == "claude":
        ensure_claude_in_path()

    # Expand @filename references
    expanded_task = parse_task_content(task)

    # Build command using the executor (uses stream-json by default from config)
    cli_cmd = executor.build_command(
        prompt=expanded_task,
        model=model,
        allowed_tools=allowed_tools,
        working_dir=working_dir,
    )
    cmd = cli_cmd.args

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize structured logger for main process
    main_logger = StructuredLogger(log_file, ProcessType.MAIN, os.getpid())
    main_logger.info(
        f"Preparing to execute document #{doc_id or 'unknown'}",
        {
            "doc_id": doc_id,
            "cli_tool": cli_tool,
            "working_dir": working_dir,
            "allowed_tools": allowed_tools,
        },
    )

    # Start subprocess in detached mode using wrapper
    try:
        # Get the wrapper script path
        wrapper_path = Path(__file__).parent.parent / "utils" / "claude_wrapper.py"

        # Build wrapper command: wrapper.py exec_id log_file claude_command...
        # Use the Python interpreter from the current environment
        # If we're in pipx, use the underlying venv Python
        python_path = sys.executable
        if "pipx" in python_path and "venvs" in python_path:
            # We're running from pipx, use the venv's python directly
            import sysconfig

            venv_bin = Path(sysconfig.get_path("scripts"))
            python_path = str(venv_bin / "python")

        wrapper_cmd = [
            python_path,
            str(wrapper_path),
            str(execution_id),  # Convert numeric ID to string for command line
            str(log_file),
        ] + cmd

        # Use nohup for true detachment
        nohup_cmd = ["nohup"] + wrapper_cmd

        # Ensure PATH contains the claude binary location
        # Use get_subprocess_env() to strip CLAUDECODE (allows nested sessions)
        from ..utils.environment import get_subprocess_env

        env = get_subprocess_env()
        env["PYTHONUNBUFFERED"] = "1"
        # Make sure PATH is preserved
        if "PATH" not in env:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin"

        # Open log file for appending - use context manager to ensure cleanup on error
        with open(log_file, "a") as log_handle:
            process = subprocess.Popen(
                nohup_cmd,
                stdin=subprocess.DEVNULL,  # Critical: no stdin blocking
                stdout=log_handle,  # Direct to file, no pipe
                stderr=subprocess.STDOUT,
                cwd=working_dir,
                env=env,
                start_new_session=True,  # Better than preexec_fn
                close_fds=True,  # Don't inherit file descriptors
            )
        # File handle automatically closed when exiting context manager

        # Return immediately - don't wait or read from pipes
        # Note: Don't use console.print here as stdout might be redirected
        # Print to stderr instead to avoid log pollution
        print(
            f"\033[32m✅ Claude started in background (PID: {process.pid})\033[0m", file=sys.stderr
        )  # noqa: E501
        print(f"Monitor with: emdx exec show {execution_id}", file=sys.stderr)

        return process.pid

    except FileNotFoundError as e:
        # Handle missing nohup
        if "nohup" in str(e):
            # Fallback without nohup - use context manager for safe cleanup
            with open(log_file, "a") as log_handle:
                process = subprocess.Popen(
                    wrapper_cmd,  # Use wrapper even without nohup
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    cwd=working_dir,
                    env=env,  # Use same env as nohup version
                    start_new_session=True,
                    close_fds=True,
                )
            # File handle automatically closed when exiting context manager

            # Print to stderr to avoid log pollution
            print(
                f"\033[32m✅ Claude started in background (PID: {process.pid}) [no nohup]\033[0m",
                file=sys.stderr,
            )  # noqa: E501
            return process.pid
        else:
            raise


def execute_cli_sync(
    task: str,
    execution_id: int,
    log_file: Path,
    cli_tool: str = "claude",
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    working_dir: str | None = None,
    doc_id: str | None = None,
    timeout: int = 300,
) -> dict:
    """Execute a task with specified CLI tool synchronously, waiting for completion.

    This is the unified function that supports CLI tools.
    Uses stream-json output format by default for real-time log streaming.

    Args:
        task: The task prompt to execute
        execution_id: Numeric database execution ID
        log_file: Path to the log file
        cli_tool: Which CLI to use ("claude")
        model: Model to use (None = default for the CLI)
        allowed_tools: List of allowed tools (defaults to DEFAULT_ALLOWED_TOOLS)
        working_dir: Working directory for execution
        doc_id: Document ID (for logging)
        timeout: Maximum seconds to wait (default 300 = 5 minutes)

    Returns:
        Dict with 'success' (bool), 'output' (str) or 'error' (str), and 'exit_code' (int)
    """
    if allowed_tools is None:
        allowed_tools = list(DEFAULT_ALLOWED_TOOLS)

    # Get the appropriate executor
    executor = get_cli_executor(cli_tool)

    # Validate environment
    is_valid, env_info = executor.validate_environment()
    if not is_valid:
        errors = env_info.get("errors", ["Unknown error"])
        return {"success": False, "error": f"Environment validation failed: {'; '.join(errors)}"}

    # Expand @filename references
    expanded_task = parse_task_content(task)

    # Build command using the executor
    # stream-json is the default from config - enables real-time log streaming
    cmd = executor.build_command(
        prompt=expanded_task,
        model=model,
        allowed_tools=allowed_tools,
        working_dir=working_dir,
    )

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize structured logger
    main_logger = StructuredLogger(log_file, ProcessType.MAIN, os.getpid())
    main_logger.info(
        f"Preparing to execute document #{doc_id or 'unknown'} (synchronous)",
        {
            "doc_id": doc_id,
            "cli_tool": cli_tool,
            "working_dir": working_dir,
            "allowed_tools": allowed_tools,
            "mode": "synchronous",
        },
    )

    try:
        import select
        import time

        # Run with streaming output to log file for live viewing
        # Use Popen to stream stdout to file in real-time
        from ..utils.environment import get_subprocess_env

        process = subprocess.Popen(
            cmd.args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cmd.cwd or working_dir,
            env=get_subprocess_env(),
        )

        # Track PID so we can detect zombies if parent dies
        from ..models.executions import update_execution_pid

        update_execution_pid(execution_id, process.pid)

        # Stream stdout to file and capture it with timeout protection
        stdout_lines = []
        start_time = time.time()
        with open(log_file, "a") as f:
            f.write("\n--- STDOUT ---\n")
            f.flush()

            while True:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    process.kill()
                    raise subprocess.TimeoutExpired(cmd.args, timeout)

                # Check if process has finished
                retcode = process.poll()

                # Try to read a line (non-blocking check via select on Unix)
                if process.stdout:
                    # Use select for non-blocking read with timeout
                    ready, _, _ = select.select([process.stdout], [], [], 1.0)
                    if ready:
                        line = process.stdout.readline()
                        if line:
                            f.write(line)
                            f.flush()  # Flush immediately for live viewing
                            stdout_lines.append(line)
                        elif retcode is not None:
                            # Empty line and process finished - we're done
                            break
                    elif retcode is not None:
                        # No data ready and process finished - we're done
                        break

        # Get any remaining stderr
        _, stderr = process.communicate(timeout=5)  # Short timeout since process should be done
        stdout = "".join(stdout_lines)

        # Log stderr if any
        if stderr:
            with open(log_file, "a") as f:
                f.write(f"\n--- STDERR ---\n{stderr}\n")

        # Parse the result
        cli_result = executor.parse_output(stdout, stderr, process.returncode)

        if cli_result.success:
            main_logger.info(
                "Execution completed successfully",
                {"returncode": process.returncode, "output_length": len(cli_result.output)},
            )
            return {
                "success": True,
                "output": cli_result.output,
                "exit_code": cli_result.exit_code,
            }
        else:
            main_logger.error(
                f"Execution failed with code {process.returncode}",
                {"returncode": process.returncode, "stderr": stderr[:500] if stderr else None},
            )
            return {
                "success": False,
                "error": cli_result.error or f"Exit code {process.returncode}",
                "exit_code": cli_result.exit_code,
            }

    except subprocess.TimeoutExpired:
        process.kill()
        main_logger.error(f"Execution timed out after {timeout}s")
        return {"success": False, "error": f"Timeout after {timeout} seconds", "exit_code": -1}
    except Exception as e:
        main_logger.error(f"Execution failed: {e}")
        return {"success": False, "error": str(e), "exit_code": -1}
