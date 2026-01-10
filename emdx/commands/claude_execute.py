"""Execute EMDX documents with Claude Code."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console

from ..models.documents import get_document
from ..utils.constants import DEFAULT_CLAUDE_MODEL
from ..models.executions import (
    Execution,
    create_execution,
    update_execution_pid,
    update_execution_status,
)
from ..models.tags import add_tags_to_document
from ..prompts import build_prompt
from ..utils.environment import ensure_claude_in_path, validate_execution_environment
from ..utils.structured_logger import ProcessType, StructuredLogger

app = typer.Typer(name="claude", help="Execute documents with Claude")
console = Console()


class ExecutionType(Enum):
    """Types of document execution based on tags."""
    NOTE = "note"
    ANALYSIS = "analysis"
    GAMEPLAN = "gameplan"
    GENERIC = "generic"


# Default allowed tools for Claude
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash",
    "Glob", "Grep", "LS", "Task", "TodoWrite"
]

# Stage-specific tool restrictions
STAGE_TOOLS = {
    ExecutionType.NOTE: [
        "Read", "Grep", "Glob", "LS",  # Analysis needs to read/search
        "Write",  # For creating temporary files to pipe to emdx save
        "Bash",  # For piping to emdx save
        "WebFetch", "WebSearch"  # For research during analysis
    ],
    ExecutionType.ANALYSIS: [
        "Read", "Grep", "Glob", "LS",  # Gameplan creation needs to read
        "Write",  # For creating temporary files to pipe to emdx save
        "Bash",  # For piping to emdx save
        "WebFetch", "WebSearch"  # For research during gameplan creation
    ],
    ExecutionType.GAMEPLAN: DEFAULT_ALLOWED_TOOLS,  # Full tools for implementation
    ExecutionType.GENERIC: DEFAULT_ALLOWED_TOOLS  # Legacy behavior
}

# Emoji mappings for tool usage
TOOL_EMOJIS = {
    "Read": "📖",
    "Write": "📝",
    "Edit": "✏️",
    "MultiEdit": "✏️",
    "Bash": "💻",
    "Glob": "🔍",
    "Grep": "🔍",
    "LS": "📁",
    "Task": "📋",
    "TodoWrite": "📋",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
}

# Emoji mappings for execution types
EXECUTION_TYPE_EMOJIS = {
    ExecutionType.NOTE: "📝",
    ExecutionType.ANALYSIS: "🔍",
    ExecutionType.GAMEPLAN: "🎯",
    ExecutionType.GENERIC: "⚡"
}


def generate_unique_execution_id(doc_id: str) -> str:
    """Generate a guaranteed unique execution ID.
    
    Uses multiple sources of entropy to ensure uniqueness:
    - Document ID
    - Microsecond timestamp
    - Process ID
    - Random UUID component
    
    Args:
        doc_id: Document ID being executed
        
    Returns:
        Unique execution ID string
    """
    timestamp = int(time.time() * 1000000)  # Microsecond precision
    pid = os.getpid()
    # Use last 8 chars of UUID for additional entropy
    uuid_suffix = str(uuid.uuid4()).split('-')[0]
    return f"claude-{doc_id}-{timestamp}-{pid}-{uuid_suffix}"


def get_execution_context(doc_tags: list[str]) -> dict[str, Any]:
    """Determine execution behavior based on document tags."""
    tag_set = set(doc_tags)

    # Check for note tags (get_document_tags returns normalized emojis)
    if '📝' in tag_set:
        return {
            'type': ExecutionType.NOTE,
            'prompt_template': 'analyze_note',
            'output_tags': ['analysis'],
            'output_title_prefix': 'Analysis: ',
            'description': 'Generate analysis from note'
        }
    # Check for analysis tags
    elif '🔍' in tag_set:
        return {
            'type': ExecutionType.ANALYSIS,
            'prompt_template': 'create_gameplan',
            'output_tags': ['gameplan', 'active'],
            'output_title_prefix': 'Gameplan: ',
            'description': 'Generate gameplan from analysis'
        }
    # Check for gameplan tags
    elif '🎯' in tag_set:
        return {
            'type': ExecutionType.GAMEPLAN,
            'prompt_template': 'implement_gameplan',
            'output_tags': [],
            'create_pr': True,
            'description': 'Implement gameplan and create PR'
        }
    else:
        return {
            'type': ExecutionType.GENERIC,
            'prompt_template': None,
            'output_tags': [],
            'description': 'Execute with document content'
        }


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
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {filename}: {e}[/yellow]")
                return f"[File not found: {filename}]"
        else:
            console.print(f"[yellow]Warning: File {filename} not found[/yellow]")
            return f"[File not found: {filename}]"

    # Replace all @filename references
    expanded = re.sub(pattern, replace_file_reference, task)
    return expanded


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """Get formatted timestamp for log output.

    Args:
        timestamp: Optional epoch timestamp. If None, uses current time.

    Returns:
        Formatted timestamp string in [HH:MM:SS] format
    """
    if timestamp is None:
        return datetime.now().strftime("[%H:%M:%S]")
    else:
        return datetime.fromtimestamp(timestamp).strftime("[%H:%M:%S]")


def parse_log_timestamp(line: str) -> Optional[float]:
    """Parse timestamp from a log line.

    Args:
        line: Log line that may contain a timestamp in format [HH:MM:SS]

    Returns:
        Epoch timestamp as float if found, None otherwise
    """
    if not line:
        return None

    # Look for timestamp pattern at the beginning of the line
    timestamp_match = re.match(r'^\[(\d{2}):(\d{2}):(\d{2})\]', line.strip())
    if timestamp_match:
        hour = int(timestamp_match.group(1))
        minute = int(timestamp_match.group(2))
        second = int(timestamp_match.group(3))

        # Validate time components
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            return None

        # Create datetime for today with the parsed time
        now = datetime.now()
        timestamp_dt = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

        # If the timestamp appears to be in the future (log from before midnight)
        # adjust the date accordingly
        if timestamp_dt > now:
            # Timestamp is in the future, likely from yesterday
            from datetime import timedelta
            timestamp_dt = timestamp_dt - timedelta(days=1)

        return timestamp_dt.timestamp()

    return None


def format_claude_output(line: str, timestamp: float) -> Optional[str]:
    """Format Claude's JSON output into readable log entries.

    Args:
        line: Raw output line from Claude
        timestamp: Timestamp to use for this log entry

    Returns:
        Formatted log entry or None if line should be skipped
    """
    line = line.strip()
    if not line:
        return None

    # Check if line already has a timestamp - if so, return as-is
    import re
    timestamp_pattern = r'^\[\d{2}:\d{2}:\d{2}\]'
    if re.match(timestamp_pattern, line):
        return line

    try:
        # Try to parse as JSON (Claude's stream-json format)
        data = json.loads(line)

        # Handle different event types
        if data.get("type") == "system":
            # Handle system initialization messages
            if data.get("subtype") == "init":
                return f"{format_timestamp(timestamp)} 🚀 Claude Code session started"
            # Skip other system messages for now
            return None

        elif data.get("type") == "assistant" and "message" in data:
            # Extract text content from assistant messages
            msg = data.get("message", {})
            content = msg.get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        return f"{format_timestamp(timestamp)} 🤖 Claude: {text}"
                elif item.get("type") == "tool_use":
                    tool_name = item.get("name", "Unknown")
                    emoji = TOOL_EMOJIS.get(tool_name, "🛠️")
                    return f"{format_timestamp(timestamp)} {emoji} Using tool: {tool_name}"

        elif data.get("type") == "user" and data.get("message", {}).get("role") == "user":
            # Tool result - extract key info
            content = data.get("message", {}).get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                result = content[0].get("content", "")
                if len(result) > 100:
                    result = result[:100] + "..."
                return f"{format_timestamp(timestamp)} 📄 Tool result: {result}"

        elif data.get("type") == "text":
            text = data.get("text", "").strip()
            if text:
                return f"{format_timestamp(timestamp)} 🤖 Claude: {text}"

        elif data.get("type") == "error":
            error = data.get("error", {}).get("message", "Unknown error")
            return f"{format_timestamp(timestamp)} ❌ Error: {error}"

        elif data.get("type") == "result":
            # Handle the final result message
            if data.get("subtype") == "success":
                # Duration calculation isn't possible here without tracking start time
                return f"{format_timestamp(timestamp)} ✅ Task completed successfully!"
            else:
                result = data.get('result', 'Unknown error')
                return f"{format_timestamp(timestamp)} ❌ Task failed: {result}"

        # For debugging: show unhandled JSON types (this was the source of "JSON shit")
        debug_info = f"{data.get('type', 'unknown')} - {str(data)[:100]}..."
        return f"{format_timestamp(timestamp)} 🔧 Debug: {debug_info}"

    except json.JSONDecodeError:
        # Not JSON - return as plain text if it's not empty
        if line and not line.startswith("{"):
            return f"{format_timestamp(timestamp)} 💬 {line}"
        else:
            # Malformed JSON - show for debugging
            return f"{format_timestamp(timestamp)} ⚠️  Malformed JSON: {line[:100]}..."

    return None


def validate_environment() -> tuple[bool, str]:
    """Validate that the execution environment is properly configured.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    import shutil
    
    # Check if claude is available
    if not shutil.which("claude"):
        return False, "Claude Code not found. Please install Claude Code: https://github.com/anthropics/claude-code"
    
    # Check if Python is available (should always be true since we're running Python)
    if not shutil.which("python3") and not shutil.which("python"):
        return False, "Python not found in PATH"
    
    # Check if git is available (needed for many operations)
    if not shutil.which("git"):
        return False, "Git not found. Please install Git: https://git-scm.com/"
    
    # Check if emdx is available in PATH (for piping operations)
    if not shutil.which("emdx"):
        # Try to find it in the current environment
        python_path = sys.executable
        emdx_path = Path(python_path).parent / "emdx"
        if not emdx_path.exists():
            return False, "EMDX not found in PATH. This may cause issues with document creation."
    
    return True, ""


def execute_with_claude_detached(
    task: str,
    execution_id: int,  # Now expects numeric database ID
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    context: Optional[dict] = None
) -> int:
    """Execute a task with Claude in a fully detached background process.

    This function starts Claude and returns immediately without waiting.
    The subprocess continues running independently of the parent process.

    Returns:
        The process ID of the started subprocess.
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Validate environment first
    is_valid, env_info = validate_execution_environment(verbose=False)
    if not is_valid:
        error_msg = "; ".join(env_info.get('errors', ['Unknown error']))
        console.print(f"[red]Environment validation failed: {error_msg}[/red]")
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

        # Don't write to log - let wrapper handle all logging

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


def execute_with_claude(
    task: str,
    execution_id: int,  # Now expects numeric database ID
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    verbose: bool = True,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    context: Optional[dict] = None
) -> int:
    """Execute a task with Claude, streaming output to log file.

    Args:
        task: Task description to execute
        execution_id: Unique execution ID
        log_file: Path to log file
        allowed_tools: List of allowed tools (defaults to DEFAULT_ALLOWED_TOOLS)
        verbose: Whether to show output in console

    Returns:
        Exit code from Claude process
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Validate environment first
    is_valid, env_info = validate_execution_environment(verbose=False)
    if not is_valid:
        error_msg = "; ".join(env_info.get('errors', ['Unknown error']))
        console.print(f"[red]Environment validation failed: {error_msg}[/red]")
        with open(log_file, 'a') as log:
            log.write(f"\n{format_timestamp()} ❌ Environment validation failed: {error_msg}\n")
        return 1
    
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
    main_logger.info(f"Preparing to execute document #{doc_id or 'unknown'} (synchronous)", {
        "doc_id": doc_id,
        "working_dir": working_dir,
        "allowed_tools": allowed_tools,
        "mode": "synchronous"
    })

    # Start subprocess
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,  # Unbuffered
            universal_newlines=True,
            cwd=working_dir,  # Run in specified working directory
            # Force unbuffered for any Python subprocesses
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            # Detach from parent process group so it survives parent exit
            preexec_fn=os.setsid if os.name != 'nt' else None
        )

        exec_start_time = time.time()

        # Stream output
        last_timestamp = None
        with open(log_file, 'a') as log:
            for line in process.stdout:
                # Parse timestamp from log line if available
                parsed_timestamp = parse_log_timestamp(line)
                if parsed_timestamp:
                    last_timestamp = parsed_timestamp
                # Use parsed timestamp or last known timestamp, fallback to current time
                timestamp_to_use = parsed_timestamp or last_timestamp or time.time()
                formatted = format_claude_output(line, timestamp_to_use)
                if formatted:
                    log.write(formatted + "\n")
                    log.flush()
                    if verbose:
                        console.print(formatted)

        # Wait for completion
        exit_code = process.wait()

        # Write completion status
        with open(log_file, 'a') as log:
            duration = time.time() - exec_start_time
            end_time = datetime.now()
            if exit_code == 0:
                if context and context.get('type'):
                    exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
                    exec_type = context['type'].value.upper()
                    log.write(f"\n{format_timestamp()} ✅ {exec_type} execution completed successfully!\n")
                    log.write(f"{format_timestamp()} {exec_emoji} All tasks finished\n")
                else:
                    log.write(f"\n{format_timestamp()} ✅ Execution completed successfully\n")
            else:
                log.write(f"\n{format_timestamp()} ❌ Process exited with code {exit_code}\n")
            log.write(f"{format_timestamp()} ⏱️  Duration: {duration:.1f}s\n")
            log.write(f"{format_timestamp()} 🏁 Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")

        return exit_code

    except FileNotFoundError:
        error_msg = ("Error: claude command not found. "
                    "Make sure Claude Code is installed and in your PATH.")
        with open(log_file, 'a') as log:
            log.write(f"\n{format_timestamp()} ❌ {error_msg}\n")
        if verbose:
            console.print(f"[red]{error_msg}[/red]")
        return 1
    except Exception as e:
        error_msg = f"Error executing Claude: {e}"
        with open(log_file, 'a') as log:
            log.write(f"\n{format_timestamp()} ❌ {error_msg}\n")
        if verbose:
            console.print(f"[red]{error_msg}[/red]")
        return 1


def execute_document_smart_background(
    doc_id: int,
    execution_id: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    use_stage_tools: bool = True,
    db_exec_id: Optional[int] = None
) -> None:
    """Execute a document in background with context-aware behavior.

    This function starts execution and returns immediately.
    """
    # Get document
    doc = get_document(str(doc_id))
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    # Get document tags
    from ..models.tags import get_document_tags
    doc_tags = get_document_tags(str(doc_id))

    # Get execution context based on tags
    context = get_execution_context(doc_tags)

    # Build prompt with template
    prompt = build_prompt(context['prompt_template'], doc['content'])

    # Use stage-specific tools if enabled and no custom tools provided
    if use_stage_tools and allowed_tools is None:
        allowed_tools = STAGE_TOOLS.get(context['type'], DEFAULT_ALLOWED_TOOLS)
    elif allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Create worktree
    worktree_path = create_execution_worktree(execution_id, doc['title'])
    working_dir = str(worktree_path) if worktree_path else os.getcwd()

    # Create or use existing execution record
    if db_exec_id:
        # Use existing execution ID
        db_execution_id = db_exec_id
        # Update the working directory in the existing execution
        from ..models.executions import update_execution_working_dir
        update_execution_working_dir(db_execution_id, working_dir)
    else:
        # Create new execution record in database
        db_execution_id = create_execution(
            doc_id=doc_id,
            doc_title=doc['title'],
            log_file=str(log_file),
            working_dir=working_dir
        )


    # Execute with Claude in detached mode
    pid = execute_with_claude_detached(
        task=prompt,
        execution_id=db_execution_id,  # Pass numeric ID
        log_file=log_file,
        allowed_tools=allowed_tools,
        working_dir=working_dir,
        doc_id=str(doc_id),
        context=context
    )

    # Update execution with PID
    update_execution_pid(db_execution_id, pid)


def execute_document_smart(
    doc_id: int,
    execution_id: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    verbose: bool = True,
    background: bool = False,
    use_stage_tools: bool = True
) -> Optional[int]:
    """Execute a document with context-aware behavior.

    Args:
        doc_id: Document ID to execute
        execution_id: Unique execution ID
        log_file: Path to log file
        allowed_tools: List of allowed tools
        verbose: Whether to show output
        background: Whether running in background

    Returns:
        ID of created output document (if any)
    """
    # Get document
    doc = get_document(str(doc_id))
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    # Get document tags
    from ..models.tags import get_document_tags
    doc_tags = get_document_tags(str(doc_id))

    # Get execution context based on tags
    context = get_execution_context(doc_tags)

    # Build prompt with template
    prompt = build_prompt(context['prompt_template'], doc['content'])

    # Use stage-specific tools if enabled and no custom tools provided
    if use_stage_tools and allowed_tools is None:
        allowed_tools = STAGE_TOOLS.get(context['type'], DEFAULT_ALLOWED_TOOLS)
        console.print(f"[dim]Using stage-specific tools for {context['type'].value}[/dim]")
    elif allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS
        console.print("[dim]Using default tools (stage-specific disabled)[/dim]")

    # Log execution type
    exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
    exec_type = context['type'].value.upper()
    console.print(f"[bold cyan]{exec_emoji} {exec_type} EXECUTION[/bold cyan]")
    console.print(f"[cyan]📋 {context['description']}[/cyan]")
    if verbose and allowed_tools:
        console.print(f"[dim]Allowed tools: {', '.join(allowed_tools)}[/dim]")

    # Create worktree
    worktree_path = create_execution_worktree(execution_id, doc['title'])
    working_dir = str(worktree_path) if worktree_path else os.getcwd()

    # Create execution record in database and get numeric ID
    db_execution_id = create_execution(
        doc_id=doc_id,
        doc_title=doc['title'],
        log_file=str(log_file),
        working_dir=working_dir
    )

    # Execute with Claude
    if verbose:
        console.print(f"[dim]Passing {len(allowed_tools)} tools to Claude: {', '.join(allowed_tools)}[/dim]")

    exit_code = execute_with_claude(
        task=prompt,
        execution_id=db_execution_id,  # Pass database ID
        log_file=log_file,
        allowed_tools=allowed_tools,
        verbose=verbose,
        working_dir=working_dir,
        doc_id=str(doc_id),
        context=context
    )

    # Don't update status here - the wrapper already handled it

    # Handle output based on context
    if exit_code == 0:
        if context['type'] == ExecutionType.GAMEPLAN:
            # Update original gameplan tags
            add_tags_to_document(str(doc_id), ['done', 'success'])
            console.print(f"[green]{EXECUTION_TYPE_EMOJIS[ExecutionType.GAMEPLAN]} Gameplan implemented successfully![/green]")
        elif context['type'] == ExecutionType.ANALYSIS:
            console.print(f"[green]{EXECUTION_TYPE_EMOJIS[ExecutionType.ANALYSIS]} Analysis completed successfully![/green]")
        elif context['type'] == ExecutionType.NOTE:
            console.print(f"[green]{EXECUTION_TYPE_EMOJIS[ExecutionType.NOTE]} Note analysis completed successfully![/green]")
        else:
            console.print("[green]✅ Execution completed successfully![/green]")
    else:
        console.print(f"[red]❌ Execution failed with exit code {exit_code}[/red]")

    return None


def create_execution_worktree(execution_id: str, doc_title: str) -> Optional[Path]:
    """Create a dedicated temporary directory for Claude execution.
    
    NOTE: We do NOT create git worktrees anymore to avoid Claude editing
    the source code of the system it's running in!

    Args:
        execution_id: Unique execution ID
        doc_title: Document title for branch naming

    Returns:
        Path to created worktree or None if creation failed
    """
    try:
        # Extract components from execution ID
        # Format: "claude-{doc_id}-{timestamp}-{pid}-{uuid}"
        exec_parts = execution_id.split('-')
        doc_id = exec_parts[1] if len(exec_parts) > 1 else "unknown"
        
        # Sanitize doc title for directory name
        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', doc_title.lower())[:30]
        safe_title = re.sub(r'-+', '-', safe_title).strip('-')  # Clean up multiple dashes
        
        # Use last 12 chars of execution ID for uniqueness
        # This includes part of timestamp, PID, and UUID
        unique_suffix = execution_id.split('-', 2)[-1][-12:]
        
        # Create temp directory
        import tempfile
        temp_base = Path(tempfile.gettempdir())
        dir_name = f"emdx-exec-{doc_id}-{safe_title}-{unique_suffix}"
        worktree_path = temp_base / dir_name

        # Handle existing directory (shouldn't happen with unique IDs, but be safe)
        attempt = 0
        final_path = worktree_path
        while final_path.exists() and attempt < 10:
            attempt += 1
            final_path = temp_base / f"{dir_name}-{attempt}"
        
        if final_path.exists():
            # Very unlikely, but use a completely random directory
            import uuid
            final_path = temp_base / f"emdx-exec-{uuid.uuid4()}"
        
        # Create the directory
        final_path.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[green]✅ Created execution directory: {final_path}[/green]")
        return final_path

    except Exception as e:
        console.print(f"[yellow]Warning: Directory creation failed: {e}[/yellow]")
        # Fallback to a simple temp directory
        import tempfile
        try:
            fallback_dir = tempfile.mkdtemp(prefix="emdx-exec-")
            console.print(f"[yellow]Using fallback directory: {fallback_dir}[/yellow]")
            return Path(fallback_dir)
        except Exception:
            console.print("[red]Failed to create any execution directory[/red]")
            return None


def monitor_execution_detached(
    execution_id: str,
    task: str,
    doc_id: str,
    doc_title: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None
) -> None:
    """Start Claude execution in detached mode and return immediately."""
    try:
        # Create dedicated worktree for this execution
        worktree_path = create_execution_worktree(execution_id, doc_title)
        working_dir = str(worktree_path) if worktree_path else os.getcwd()

        # Create and save initial execution record
        execution = Execution(
            id=execution_id,
            doc_id=int(doc_id),
            doc_title=doc_title,
            status="running",
            started_at=datetime.now(timezone.utc),
            log_file=str(log_file),
            working_dir=working_dir
        )

        # Execute with Claude in detached mode
        pid = execute_with_claude_detached(
            task=task,
            execution_id=execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            working_dir=working_dir,
            doc_id=doc_id,
            context=None  # Context not available in these functions yet
        )

        # Update execution with PID
        update_execution_pid(execution_id, pid)
    except Exception as e:
        # Log error but don't update status - let the wrapper handle it
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(f"\n❌ Error starting execution: {e}\n")
            # Don't update status here - wrapper will handle it
        except Exception:
            pass  # Silent fail if we can't even log the error


def monitor_execution(
    execution_id: str,
    task: str,
    doc_id: str,
    doc_title: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None
) -> None:
    """Monitor Claude execution and update status in database.

    Args:
        execution_id: Unique execution ID
        task: Task to execute
        doc_id: Document ID
        doc_title: Document title
        log_file: Path to log file
        allowed_tools: List of allowed tools
    """
    try:
        # Create dedicated worktree for this execution
        worktree_path = create_execution_worktree(execution_id, doc_title)
        working_dir = str(worktree_path) if worktree_path else os.getcwd()

        # Create and save initial execution record
        execution = Execution(
            id=execution_id,
            doc_id=int(doc_id),
            doc_title=doc_title,
            status="running",
            started_at=datetime.now(timezone.utc),
            log_file=str(log_file),
            working_dir=working_dir
        )

        # Execute with Claude in the worktree
        exit_code = execute_with_claude(
            task=task,
            execution_id=execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            verbose=False,  # Don't show output when running in background
            working_dir=working_dir,
            doc_id=doc_id,
            context=None  # Context not available in these functions yet
        )

        # Don't update status here - the wrapper already did it
        pass
    except Exception as e:
        # Log error but don't update status - wrapper handles it
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(f"\n❌ Error in execution: {e}\n")
            # Don't update status - wrapper handles it
        except Exception:
            pass  # Silent fail if we can't even log the error


@app.command(name="check-env")
def check_environment(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed environment info")
):
    """Check if the execution environment is properly configured."""
    console.print("[bold]Checking EMDX execution environment...[/bold]\n")
    
    # Use the comprehensive validation
    is_valid, env_info = validate_execution_environment(verbose=True)
    
    # Additional quick checks
    console.print("\n[bold]Quick Status:[/bold]")
    checks = [
        ("Python", lambda: sys.version.split()[0]),
        ("Claude Code", lambda: "✓" if shutil.which("claude") else "✗"),
        ("Git", lambda: "✓" if shutil.which("git") else "✗"),
        ("EMDX", lambda: "✓" if shutil.which("emdx") else "✗"),
    ]
    
    for name, check_func in checks:
        try:
            result = check_func()
            if result and result != "✗":
                console.print(f"  {name}: [green]{result}[/green]")
            else:
                console.print(f"  {name}: [red]Not found[/red]")
        except Exception:
            console.print(f"  {name}: [red]Error[/red]")
    
    # Show PATH info if verbose
    if verbose:
        console.print(f"\n[dim]PATH entries: {len(os.environ.get('PATH', '').split(os.pathsep))}[/dim]")
        console.print(f"[dim]Installation: {env_info.get('info', {}).get('installation', 'unknown')}[/dim]")
    
    # Overall result
    if is_valid:
        console.print("\n[bold green]✅ Environment is properly configured![/bold green]")
        console.print("[dim]You can run executions without issues.[/dim]")
    else:
        console.print("\n[bold red]❌ Environment issues detected[/bold red]")
        console.print("[dim]Please fix the issues above before running executions.[/dim]")
        
        # Suggest fixes
        if env_info and env_info.get('errors'):
            console.print("\n[yellow]Suggested fixes:[/yellow]")
            for error in env_info['errors']:
                if "claude" in error.lower():
                    console.print("  • Install Claude Code: https://github.com/anthropics/claude-code")
                elif "git" in error.lower():
                    console.print("  • Install Git: https://git-scm.com/")
                elif "python" in error.lower():
                    console.print("  • Upgrade Python to 3.8 or later")


@app.command()
def execute(
    doc_id: str = typer.Argument(..., help="Document ID to execute"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t",
                                        help="Comma-separated list of allowed tools"),
    smart: bool = typer.Option(True, "--smart/--no-smart",
                              help="Use smart context-aware execution"),
    exec_id: Optional[int] = typer.Option(None, "--exec-id",
                                          help="Use existing execution ID from database")
):
    """Execute a document with Claude Code."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Parse allowed tools
    allowed_tools = tools.split(",") if tools else None

    # Handle execution ID and log file
    import os
    
    if exec_id:
        # Use provided execution ID from database
        from ..models.executions import get_execution
        existing_exec = get_execution(exec_id)
        if not existing_exec:
            console.print(f"[red]Execution #{exec_id} not found[/red]")
            raise typer.Exit(1)
        
        # Use the existing log file path
        log_file = Path(existing_exec.log_file)
        execution_id = f"claude-{doc['id']}-{exec_id}"  # Keep simple for backward compat
        console.print(f"[yellow]Using existing execution #{exec_id}[/yellow]")
    else:
        # Generate new execution ID with guaranteed uniqueness
        execution_id = generate_unique_execution_id(doc['id'])
        
        # Set up log file
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_file = log_dir / f"{execution_id}.log"



    if smart:
        # Get document tags
        from ..models.tags import get_document_tags
        doc_tags = get_document_tags(doc_id)

        # Use smart execution
        if background:
            console.print("[green]Starting smart execution in background...[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")

            # Get execution context to show what will happen
            context = get_execution_context(doc_tags)
            exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
            exec_type = context['type'].value.upper()
            console.print(f"[bold cyan]{exec_emoji} {exec_type} EXECUTION[/bold cyan]")
            console.print(f"[cyan]📋 {context['description']}[/cyan]")

            # Execute in background without blocking
            execute_document_smart_background(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                use_stage_tools=True,
                db_exec_id=exec_id
            )

            console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
        else:
            # Run smart execution in foreground
            execute_document_smart(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                verbose=True,
                background=False
            )
    else:
        # Legacy execution mode - use default tools if none specified
        if allowed_tools is None:
            allowed_tools = DEFAULT_ALLOWED_TOOLS

        if background:
            # Run in background thread
            console.print("[green]Starting execution in background...[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")

            # Execute in background without blocking
            monitor_execution_detached(
                execution_id=execution_id,
                task=doc['content'],
                doc_id=str(doc['id']),
                doc_title=doc['title'],
                log_file=log_file,
                allowed_tools=allowed_tools
            )

            console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
        else:
            # Run in foreground
            console.print(f"[green]Executing document #{doc_id}: {doc['title']}[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")
            console.print()

            # Create worktree for execution
            worktree_path = create_execution_worktree(execution_id, doc['title'])
            working_dir = str(worktree_path) if worktree_path else os.getcwd()

            # Create execution record
            execution = Execution(
                id=execution_id,
                doc_id=int(doc_id),
                doc_title=doc['title'],
                status="running",
                started_at=datetime.now(timezone.utc),
                log_file=str(log_file),
                working_dir=working_dir
            )

            # Execute in worktree
            exit_code = execute_with_claude(
                task=doc['content'],
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                verbose=True,
                working_dir=working_dir,
                doc_id=doc_id,
                context=None  # Direct execution - no context analysis
            )

            # Update status
            status = "completed" if exit_code == 0 else "failed"
            update_execution_status(execution_id, status, exit_code)

            if exit_code != 0:
                raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
