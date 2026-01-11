"""Execute EMDX documents with Claude Code.

CLI commands for document execution. The core execution logic has been
extracted to services/claude_executor.py to break bidirectional dependencies.
"""

import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..models.documents import get_document
from ..models.executions import (
    Execution,
    update_execution_status,
)
from ..models.tags import add_tags_to_document
from ..prompts import build_prompt
from ..config.settings import DEFAULT_CLAUDE_MODEL
from ..utils.environment import ensure_claude_in_path, validate_execution_environment
from ..utils.structured_logger import ProcessType, StructuredLogger
from ..services.claude_executor import execute_claude_detached as _execute_claude_detached

# Import from document_executor for backward compatibility
from ..services.document_executor import (
    ExecutionType,
    DEFAULT_ALLOWED_TOOLS,
    STAGE_TOOLS,
    get_execution_context,
    generate_unique_execution_id,
    create_execution_worktree,
    execute_document_background,
)

# Re-export TOOL_EMOJIS and EXECUTION_TYPE_EMOJIS for backward compatibility
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

EXECUTION_TYPE_EMOJIS = {
    ExecutionType.NOTE: "📝",
    ExecutionType.ANALYSIS: "🔍",
    ExecutionType.GAMEPLAN: "🎯",
    ExecutionType.GENERIC: "⚡"
}


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

        # For debugging: show unhandled JSON types
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
            except Exception:
                return f"[File not found: {filename}]"
        else:
            return f"[File not found: {filename}]"

    # Replace all @filename references
    expanded = re.sub(pattern, replace_file_reference, task)
    return expanded


def execute_with_claude_detached(
    task: str,
    execution_id: int,
    log_file: Path,
    allowed_tools: Optional[list] = None,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    context: Optional[dict] = None
) -> int:
    """Execute a task with Claude in a fully detached background process.

    This is a thin wrapper around the service layer implementation.
    The context parameter is ignored (kept for backwards compatibility).

    Returns:
        The process ID of the started subprocess.
    """
    if allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    # Delegate to service layer
    return _execute_claude_detached(
        task=task,
        execution_id=execution_id,
        log_file=log_file,
        allowed_tools=allowed_tools,
        working_dir=working_dir,
        doc_id=doc_id,
    )


def execute_with_claude(
    task: str,
    execution_id: int,
    log_file: Path,
    allowed_tools: Optional[list] = None,
    verbose: bool = True,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    context: Optional[dict] = None
) -> int:
    """Execute a task with Claude, streaming output to log file.

    Args:
        task: Task description to execute
        execution_id: Execution ID
        log_file: Path to log file
        allowed_tools: List of allowed tools
        verbose: Whether to show output in console
        working_dir: Working directory for execution
        doc_id: Document ID
        context: Optional execution context

    Returns:
        Exit code from Claude process
    """
    import subprocess
    import time

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
            bufsize=0,
            universal_newlines=True,
            cwd=working_dir,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
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


app = typer.Typer(name="claude", help="Execute documents with Claude")
console = Console()


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

        # Get execution context to show what will happen
        context = get_execution_context(doc_tags)
        exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
        exec_type = context['type'].value.upper()

        console.print(f"[bold cyan]{exec_emoji} {exec_type} EXECUTION[/bold cyan]")
        console.print(f"[cyan]📋 {context['description']}[/cyan]")

        if background:
            console.print("[green]Starting smart execution in background...[/green]")
            console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
            console.print(f"Log file: [dim]{log_file}[/dim]")

            # Execute in background using the service layer
            result = execute_document_background(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                use_stage_tools=True,
                db_exec_id=exec_id
            )

            if result['success']:
                console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
            else:
                console.print(f"[red]Failed to start execution: {result.get('error', 'Unknown error')}[/red]")
                raise typer.Exit(1)
        else:
            # Run in foreground - not yet implemented in service layer
            console.print("[yellow]Foreground execution not yet migrated to service layer[/yellow]")
            raise typer.Exit(1)
    else:
        # Legacy execution mode - use default tools if none specified
        if allowed_tools is None:
            allowed_tools = DEFAULT_ALLOWED_TOOLS

        console.print("[yellow]Legacy (non-smart) execution mode[/yellow]")
        console.print(f"[green]Executing document #{doc_id}: {doc['title']}[/green]")
        console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
        console.print(f"Log file: [dim]{log_file}[/dim]")

        if background:
            # Use the service layer for background execution
            result = execute_document_background(
                doc_id=int(doc_id),
                execution_id=execution_id,
                log_file=log_file,
                allowed_tools=allowed_tools,
                use_stage_tools=False,
                db_exec_id=exec_id
            )

            if result['success']:
                console.print(f"\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
            else:
                console.print(f"[red]Failed to start execution: {result.get('error', 'Unknown error')}[/red]")
                raise typer.Exit(1)
        else:
            console.print("[yellow]Foreground execution not yet migrated to service layer[/yellow]")
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
