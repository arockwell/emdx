"""Claude execution service - handles spawning and managing Claude processes.

This module provides the core execution logic for running Claude Code processes.
It is used by both:
- commands/claude_execute.py (CLI interface)
- services/task_runner.py (programmatic task execution)

This separation breaks the bidirectional dependency between commands and services.
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

from ..config.settings import DEFAULT_CLAUDE_MODEL
from ..utils.environment import ensure_claude_in_path, validate_execution_environment
from ..utils.structured_logger import ProcessType, StructuredLogger


# Default allowed tools for Claude
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash",
    "Glob", "Grep", "LS", "Task", "TodoWrite"
]


def parse_task_content(task: str) -> str:
    """Parse task string, expanding @filename references.

    Args:
        task: Task description potentially containing @filename references

    Returns:
        Expanded task content with file contents included
    """
    # Find all @filename references
    pattern = r'@([^\s]+)'

    def replace_file_reference(match):
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
    allowed_tools: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> int:
    """Execute a task with Claude in a fully detached background process.

    This function starts Claude and returns immediately without waiting.
    The subprocess continues running independently of the parent process.

    Args:
        task: The task prompt to execute
        execution_id: Numeric database execution ID
        log_file: Path to the log file
        allowed_tools: List of allowed tools (defaults to DEFAULT_ALLOWED_TOOLS)
        working_dir: Working directory for execution
        doc_id: Document ID (for logging)

    Returns:
        The process ID of the started subprocess.

    Raises:
        RuntimeError: If environment validation fails.
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Validate environment first
    is_valid, env_info = validate_execution_environment(verbose=False)
    if not is_valid:
        error_msg = "; ".join(env_info.get('errors', ['Unknown error']))
        raise RuntimeError(f"Environment validation failed: {error_msg}")

    # Ensure claude is in PATH
    ensure_claude_in_path()

    # Expand @filename references
    expanded_task = parse_task_content(task)

    # Build Claude command
    cmd = [
        "claude",
        "--print", expanded_task,
        "--allowedTools", ",".join(allowed_tools),
        "--output-format", "stream-json",
        "--model", DEFAULT_CLAUDE_MODEL,
        "--verbose"
    ]

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize structured logger for main process
    main_logger = StructuredLogger(log_file, ProcessType.MAIN, os.getpid())
    main_logger.info(f"Preparing to execute document #{doc_id or 'unknown'}", {
        "doc_id": doc_id,
        "working_dir": working_dir,
        "allowed_tools": allowed_tools
    })

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
            str(log_file)
        ] + cmd

        # Use nohup for true detachment
        nohup_cmd = ["nohup"] + wrapper_cmd

        # Open log file for appending
        log_handle = open(log_file, 'a')

        # Ensure PATH contains the claude binary location
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        # Make sure PATH is preserved
        if 'PATH' not in env:
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin'

        process = subprocess.Popen(
            nohup_cmd,
            stdin=subprocess.DEVNULL,  # Critical: no stdin blocking
            stdout=log_handle,  # Direct to file, no pipe
            stderr=subprocess.STDOUT,
            cwd=working_dir,
            env=env,
            start_new_session=True,  # Better than preexec_fn
            close_fds=True  # Don't inherit file descriptors
        )

        # Close the file handle in parent process
        log_handle.close()

        # Return immediately - don't wait or read from pipes
        # Note: Don't use console.print here as stdout might be redirected
        # Print to stderr instead to avoid log pollution
        print(f"\033[32m✅ Claude started in background (PID: {process.pid})\033[0m", file=sys.stderr)
        print(f"Monitor with: emdx exec show {execution_id}", file=sys.stderr)

        return process.pid

    except FileNotFoundError as e:
        # Handle missing nohup
        if "nohup" in str(e):
            # Fallback without nohup
            log_handle = open(log_file, 'a')

            process = subprocess.Popen(
                wrapper_cmd,  # Use wrapper even without nohup
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=working_dir,
                env=env,  # Use same env as nohup version
                start_new_session=True,
                close_fds=True
            )

            log_handle.close()

            # Print to stderr to avoid log pollution
            print(f"\033[32m✅ Claude started in background (PID: {process.pid}) [no nohup]\033[0m", file=sys.stderr)
            return process.pid
        else:
            raise


def execute_claude_sync(
    task: str,
    execution_id: int,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    timeout: int = 300,
) -> dict:
    """Execute a task with Claude synchronously, waiting for completion.

    Args:
        task: The task prompt to execute
        execution_id: Numeric database execution ID
        log_file: Path to the log file
        allowed_tools: List of allowed tools (defaults to DEFAULT_ALLOWED_TOOLS)
        working_dir: Working directory for execution
        doc_id: Document ID (for logging)
        timeout: Maximum seconds to wait (default 300 = 5 minutes)

    Returns:
        Dict with 'success' (bool) and 'output' (str) or 'error' (str)
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Validate environment first
    is_valid, env_info = validate_execution_environment(verbose=False)
    if not is_valid:
        error_msg = "; ".join(env_info.get('errors', ['Unknown error']))
        return {"success": False, "error": f"Environment validation failed: {error_msg}"}

    # Ensure claude is in PATH
    ensure_claude_in_path()

    # Expand @filename references
    expanded_task = parse_task_content(task)

    # Build Claude command - simpler for sync execution
    cmd = [
        "claude",
        "--print", expanded_task,
        "--allowedTools", ",".join(allowed_tools),
        "--output-format", "text",
        "--model", DEFAULT_CLAUDE_MODEL,
    ]

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialize structured logger
    main_logger = StructuredLogger(log_file, ProcessType.MAIN, os.getpid())
    main_logger.info(f"Preparing to execute document #{doc_id or 'unknown'} (synchronous)", {
        "doc_id": doc_id,
        "working_dir": working_dir,
        "allowed_tools": allowed_tools,
        "mode": "synchronous"
    })

    try:
        # Run synchronously with timeout
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=working_dir,
        )

        # Log the output
        with open(log_file, 'a') as f:
            f.write(f"\n--- STDOUT ---\n{result.stdout}\n")
            if result.stderr:
                f.write(f"\n--- STDERR ---\n{result.stderr}\n")

        if result.returncode == 0:
            main_logger.info("Execution completed successfully", {
                "returncode": result.returncode,
                "output_length": len(result.stdout)
            })
            return {"success": True, "output": result.stdout}
        else:
            main_logger.error(f"Execution failed with code {result.returncode}", {
                "returncode": result.returncode,
                "stderr": result.stderr[:500] if result.stderr else None
            })
            return {"success": False, "error": result.stderr or f"Exit code {result.returncode}"}

    except subprocess.TimeoutExpired:
        main_logger.error(f"Execution timed out after {timeout}s")
        return {"success": False, "error": f"Timeout after {timeout} seconds"}
    except Exception as e:
        main_logger.error(f"Execution failed: {e}")
        return {"success": False, "error": str(e)}
