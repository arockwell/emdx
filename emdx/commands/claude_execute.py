"""Execute EMDX documents with Claude Code."""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console

from ..models.documents import get_document
from ..models.executions import save_execution, update_execution_status, Execution

app = typer.Typer(name="claude", help="Execute documents with Claude")
console = Console()

# Default allowed tools for Claude
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash", 
    "Glob", "Grep", "LS", "Task", "TodoWrite"
]

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


def format_timestamp() -> str:
    """Get formatted timestamp for log output."""
    return datetime.now().strftime("[%H:%M:%S]")


def format_claude_output(line: str, start_time: float) -> Optional[str]:
    """Format Claude's JSON output into readable log entries.
    
    Args:
        line: Raw output line from Claude
        start_time: Timestamp when execution started
        
    Returns:
        Formatted log entry or None if line should be skipped
    """
    line = line.strip()
    if not line:
        return None
        
    try:
        # Try to parse as JSON (Claude's stream-json format)
        data = json.loads(line)
        
        # Handle different event types
        if data.get("type") == "assistant" and "message" in data:
            # Extract text content from assistant messages
            msg = data.get("message", {})
            content = msg.get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        return f"{format_timestamp()} 🤖 Claude: {text}"
                elif item.get("type") == "tool_use":
                    tool_name = item.get("name", "Unknown")
                    emoji = TOOL_EMOJIS.get(tool_name, "🛠️")
                    return f"{format_timestamp()} {emoji} Using tool: {tool_name}"
            
        elif data.get("type") == "user" and data.get("message", {}).get("role") == "user":
            # Tool result - extract key info
            content = data.get("message", {}).get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                result = content[0].get("content", "")
                if len(result) > 100:
                    result = result[:100] + "..."
                return f"{format_timestamp()} 📄 Tool result: {result}"
            
        elif data.get("type") == "text":
            text = data.get("text", "").strip()
            if text:
                return f"{format_timestamp()} 🤖 Claude: {text}"
                
        elif data.get("type") == "error":
            error = data.get("error", {}).get("message", "Unknown error")
            return f"{format_timestamp()} ❌ Error: {error}"
            
        elif data.get("type") == "result":
            # Handle the final result message
            if data.get("subtype") == "success":
                duration = time.time() - start_time
                return f"{format_timestamp()} ✅ Task completed!\n{format_timestamp()} ⏱️  Duration: {duration:.2f}s"
            else:
                return f"{format_timestamp()} ❌ Task failed: {data.get('result', 'Unknown error')}"
            
        # Return raw JSON for unhandled types (for debugging)
        return None
        
    except json.JSONDecodeError:
        # Not JSON - return as plain text if it's not empty
        if line and not line.startswith("{"):
            return f"{format_timestamp()} 💬 {line}"
    
    return None


def execute_with_claude(
    task: str,
    execution_id: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    verbose: bool = True
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
    
    # Expand @filename references
    expanded_task = parse_task_content(task)
    
    # Build Claude command
    cmd = [
        "claude",
        "--print", expanded_task,
        "--allowedTools", ",".join(allowed_tools),
        "--output-format", "stream-json",
        "--verbose"
    ]
    
    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Write initial log header
    with open(log_file, 'w') as f:
        f.write(f"=== EMDX Claude Execution ===\n")
        f.write(f"ID: {execution_id}\n")
        f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 50}\n\n")
        f.write(f"{format_timestamp()} 🚀 Claude Code session started\n")
        f.write(f"{format_timestamp()} 📋 Available tools: {', '.join(allowed_tools)}\n")
    
    # Start subprocess
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,  # Unbuffered
            universal_newlines=True,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}  # Force unbuffered for any Python subprocesses
        )
        
        start_time = time.time()
        
        # Stream output
        with open(log_file, 'a') as log:
            for line in process.stdout:
                formatted = format_claude_output(line, start_time)
                if formatted:
                    log.write(formatted + "\n")
                    log.flush()
                    if verbose:
                        console.print(formatted)
        
        # Wait for completion
        exit_code = process.wait()
        
        # Write completion status
        with open(log_file, 'a') as log:
            duration = time.time() - start_time
            if exit_code == 0:
                log.write(f"\n{format_timestamp()} ✅ Using Max subscription (no API charges)\n")
            else:
                log.write(f"\n{format_timestamp()} ❌ Process exited with code {exit_code}\n")
            log.write(f"{format_timestamp()} ⏱️  Total duration: {duration:.2f}s\n")
        
        return exit_code
        
    except FileNotFoundError:
        error_msg = "Error: claude command not found. Make sure Claude Code is installed and in your PATH."
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
        # Create and save initial execution record
        execution = Execution(
            id=execution_id,
            doc_id=int(doc_id),
            doc_title=doc_title,
            status="running",
            started_at=datetime.now(),
            log_file=str(log_file),
            working_dir=os.getcwd()
        )
        save_execution(execution)
        
        # Execute with Claude
        exit_code = execute_with_claude(
            task=task,
            execution_id=execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            verbose=False  # Don't show output when running in background
        )
        
        # Update execution status
        status = "completed" if exit_code == 0 else "failed"
        update_execution_status(execution_id, status, exit_code)
    except Exception as e:
        # Log error and update status
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(f"\n❌ Error in monitor_execution: {e}\n")
            update_execution_status(execution_id, "failed", 1)
        except:
            pass  # Silent fail if we can't even log the error


@app.command()
def execute(
    doc_id: str = typer.Argument(..., help="Document ID to execute"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Comma-separated list of allowed tools")
):
    """Execute a document with Claude Code."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)
    
    # Parse allowed tools
    allowed_tools = tools.split(",") if tools else DEFAULT_ALLOWED_TOOLS
    
    # Generate execution ID
    timestamp = int(time.time())
    execution_id = f"claude-{doc['id']}-{timestamp}"
    
    # Set up log file
    log_dir = Path.home() / ".config" / "emdx" / "logs"
    log_file = log_dir / f"{execution_id}.log"
    
    if background:
        # Run in background thread
        console.print(f"[green]Starting execution in background...[/green]")
        console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
        console.print(f"Log file: [dim]{log_file}[/dim]")
        
        thread = threading.Thread(
            target=monitor_execution,
            args=(execution_id, doc['content'], str(doc['id']), doc['title'], log_file, allowed_tools),
            daemon=True
        )
        thread.start()
        
        console.print("\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
    else:
        # Run in foreground
        console.print(f"[green]Executing document #{doc_id}: {doc['title']}[/green]")
        console.print(f"Execution ID: [cyan]{execution_id}[/cyan]")
        console.print(f"Log file: [dim]{log_file}[/dim]")
        console.print()
        
        # Create execution record
        execution = Execution(
            id=execution_id,
            doc_id=int(doc_id),
            doc_title=doc['title'],
            status="running",
            started_at=datetime.now(),
            log_file=str(log_file),
            working_dir=os.getcwd()
        )
        save_execution(execution)
        
        # Execute
        exit_code = execute_with_claude(
            task=doc['content'],
            execution_id=execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            verbose=True
        )
        
        # Update status
        status = "completed" if exit_code == 0 else "failed"
        update_execution_status(execution_id, status, exit_code)
        
        if exit_code != 0:
            raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()