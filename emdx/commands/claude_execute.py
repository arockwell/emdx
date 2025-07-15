"""Execute EMDX documents with Claude Code."""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console

from ..models.documents import get_document
from ..models.executions import Execution, save_execution, update_execution_status, update_execution_pid
from ..models.tags import add_tags_to_document
from ..prompts import build_prompt

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
        if data.get("type") == "system":
            # Handle system initialization messages
            if data.get("subtype") == "init":
                return f"{format_timestamp()} 🚀 Claude Code session started"
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
                return f"{format_timestamp()} ✅ Task completed successfully! Duration: {duration:.2f}s"
            else:
                return f"{format_timestamp()} ❌ Task failed: {data.get('result', 'Unknown error')}"

        # For debugging: show unhandled JSON types (this was the source of "JSON shit")
        return f"{format_timestamp()} 🔧 Debug: {data.get('type', 'unknown')} - {str(data)[:100]}..."

    except json.JSONDecodeError:
        # Not JSON - return as plain text if it's not empty
        if line and not line.startswith("{"):
            return f"{format_timestamp()} 💬 {line}"
        else:
            # Malformed JSON - show for debugging
            return f"{format_timestamp()} ⚠️  Malformed JSON: {line[:100]}..."

    return None


def execute_with_claude_detached(
    task: str,
    execution_id: str,
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
    from emdx import __version__, __build_id__
    start_time = datetime.now()
    with open(log_file, 'w') as f:
        f.write("=== EMDX Claude Execution ===\n")
        f.write(f"Version: {__version__}\n")
        f.write(f"Build ID: {__build_id__}\n")
        f.write(f"Doc ID: {doc_id or 'unknown'}\n")
        f.write(f"Execution ID: {execution_id}\n")
        if working_dir:
            f.write(f"Worktree: {working_dir}\n")
        f.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        f.write(f"{'=' * 50}\n\n")
        # Get execution type emoji and description
        if context and context.get('type'):
            exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
            exec_type = context['type'].value.upper()
            exec_desc = context.get('description', 'Executing document')
            f.write(f"{format_timestamp()} 🚀 Claude Code session started (detached)\n")
            f.write(f"{format_timestamp()} {exec_emoji} Execution type: {exec_type} - {exec_desc}\n")
        else:
            f.write(f"{format_timestamp()} 🚀 Claude Code session started (detached)\n")
        f.write(f"{format_timestamp()} 📋 Available tools: {', '.join(allowed_tools)}\n")
        f.write(f"{format_timestamp()} 📝 Prompt being sent to Claude:\n")
        f.write(f"{'─' * 60}\n")
        f.write(f"{expanded_task}\n")
        f.write(f"{'─' * 60}\n\n")
    
    # Start subprocess in detached mode using wrapper
    try:
        # Get the wrapper script path
        wrapper_path = Path(__file__).parent.parent / "utils" / "claude_wrapper.py"
        
        # Build wrapper command: wrapper.py exec_id log_file claude_command...
        wrapper_cmd = [
            sys.executable,  # Use current Python interpreter
            str(wrapper_path),
            execution_id,
            str(log_file)
        ] + cmd
        
        # Use nohup for true detachment
        nohup_cmd = ["nohup"] + wrapper_cmd
        
        # Open log file for appending
        log_handle = open(log_file, 'a')
        
        process = subprocess.Popen(
            nohup_cmd,
            stdin=subprocess.DEVNULL,  # Critical: no stdin blocking
            stdout=log_handle,  # Direct to file, no pipe
            stderr=subprocess.STDOUT,
            cwd=working_dir,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'},
            start_new_session=True,  # Better than preexec_fn
            close_fds=True  # Don't inherit file descriptors
        )
        
        # Close the file handle in parent process
        log_handle.close()
        
        # Log the PID for tracking
        with open(log_file, 'a') as f:
            f.write(f"\n{format_timestamp()} 🔧 Background process started with PID: {process.pid}\n")
            f.write(f"{format_timestamp()} 📄 Output is being written to this log file\n")
            f.write(f"{format_timestamp()} 🔄 Wrapper will update status on completion\n")
        
        # Return immediately - don't wait or read from pipes
        console.print(f"[green]✅ Claude started in background (PID: {process.pid})[/green]")
        
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
                env={**os.environ, 'PYTHONUNBUFFERED': '1'},
                start_new_session=True,
                close_fds=True
            )
            
            log_handle.close()
            
            console.print(f"[green]✅ Claude started in background (PID: {process.pid}) [no nohup][/green]")
            return process.pid
        else:
            raise


def execute_with_claude(
    task: str,
    execution_id: str,
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
    from emdx import __version__, __build_id__
    start_time = datetime.now()
    with open(log_file, 'w') as f:
        f.write("=== EMDX Claude Execution ===\n")
        f.write(f"Version: {__version__}\n")
        f.write(f"Build ID: {__build_id__}\n")
        f.write(f"Doc ID: {doc_id or 'unknown'}\n")
        f.write(f"Execution ID: {execution_id}\n")
        if working_dir:
            f.write(f"Worktree: {working_dir}\n")
        f.write(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        f.write(f"{'=' * 50}\n\n")
        # Get execution type emoji and description
        if context and context.get('type'):
            exec_emoji = EXECUTION_TYPE_EMOJIS.get(context['type'], "⚡")
            exec_type = context['type'].value.upper()
            exec_desc = context.get('description', 'Executing document')
            f.write(f"{format_timestamp()} 🚀 Claude Code session started\n")
            f.write(f"{format_timestamp()} {exec_emoji} Execution type: {exec_type} - {exec_desc}\n")
        else:
            f.write(f"{format_timestamp()} 🚀 Claude Code session started\n")
        f.write(f"{format_timestamp()} 📋 Available tools: {', '.join(allowed_tools)}\n")
        f.write(f"{format_timestamp()} 📝 Prompt being sent to Claude:\n")
        f.write(f"{'─' * 60}\n")
        f.write(f"{expanded_task}\n")
        f.write(f"{'─' * 60}\n\n")

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
        with open(log_file, 'a') as log:
            for line in process.stdout:
                formatted = format_claude_output(line, exec_start_time)
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
    use_stage_tools: bool = True
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

    # Create execution record
    execution = Execution(
        id=execution_id,
        doc_id=doc_id,
        doc_title=doc['title'],
        status="running",
        started_at=datetime.now(),
        log_file=str(log_file),
        working_dir=working_dir
    )
    save_execution(execution)

    # Execute with Claude in detached mode
    pid = execute_with_claude_detached(
        task=prompt,
        execution_id=execution_id,
        log_file=log_file,
        allowed_tools=allowed_tools,
        working_dir=working_dir,
        doc_id=str(doc_id),
        context=context
    )
    
    # Update execution with PID
    update_execution_pid(execution_id, pid)


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
        console.print(f"[dim]Using default tools (stage-specific disabled)[/dim]")

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

    # Create execution record
    execution = Execution(
        id=execution_id,
        doc_id=doc_id,
        doc_title=doc['title'],
        status="running",
        started_at=datetime.now(),
        log_file=str(log_file),
        working_dir=working_dir
    )
    save_execution(execution)

    # Execute with Claude
    if verbose:
        console.print(f"[dim]Passing {len(allowed_tools)} tools to Claude: {', '.join(allowed_tools)}[/dim]")
    
    exit_code = execute_with_claude(
        task=prompt,
        execution_id=execution_id,
        log_file=log_file,
        allowed_tools=allowed_tools,
        verbose=verbose,
        working_dir=working_dir,
        doc_id=str(doc_id),
        context=context
    )

    # Update execution status
    status = "completed" if exit_code == 0 else "failed"
    update_execution_status(execution_id, status, exit_code)

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
    """Create a dedicated git worktree for Claude execution.

    Args:
        execution_id: Unique execution ID
        doc_title: Document title for branch naming

    Returns:
        Path to created worktree or None if creation failed
    """
    try:
        # Get project name from git remote
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )

        if result.returncode == 0:
            remote_url = result.stdout.strip()
            # Extract project name from URL
            import re
            match = re.search(r'([^/]+)(\.git)?$', remote_url)
            if match:
                project_name = match.group(1).replace('.git', '')
            else:
                project_name = Path.cwd().name
        else:
            project_name = Path.cwd().name

        # Create branch name from execution ID and doc title
        # Extract doc ID from execution_id (format: "claude-{doc_id}-{timestamp}")
        exec_parts = execution_id.split('-')
        doc_id = exec_parts[1] if len(exec_parts) > 1 else "unknown"

        # Sanitize doc title for git branch name
        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', doc_title.lower())[:20]
        branch_name = f"exec-{doc_id}-{safe_title}"

        # Worktree directory
        worktrees_dir = Path.home() / "dev" / "worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        worktree_name = f"{project_name}-{branch_name}"
        worktree_path = worktrees_dir / worktree_name

        # Create branch from current HEAD
        subprocess.run(
            ["git", "branch", branch_name],
            check=True,
            capture_output=True
        )

        # Create worktree
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch_name],
            check=True,
            capture_output=True
        )

        console.print(f"[green]✅ Created execution worktree: {worktree_path}[/green]")
        return worktree_path

    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Could not create worktree: {e}[/yellow]")
        console.print("[yellow]Execution will run in current directory[/yellow]")
        return None
    except Exception as e:
        console.print(f"[yellow]Warning: Worktree creation failed: {e}[/yellow]")
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
            started_at=datetime.now(),
            log_file=str(log_file),
            working_dir=working_dir
        )
        save_execution(execution)

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
        # Log error
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a') as f:
                f.write(f"\n❌ Error in monitor_execution_detached: {e}\n")
            update_execution_status(execution_id, "failed", 1)
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
            started_at=datetime.now(),
            log_file=str(log_file),
            working_dir=working_dir
        )
        save_execution(execution)

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
        except Exception:
            pass  # Silent fail if we can't even log the error


@app.command()
def execute(
    doc_id: str = typer.Argument(..., help="Document ID to execute"),
    background: bool = typer.Option(False, "--background", "-b", help="Run in background"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t",
                                        help="Comma-separated list of allowed tools"),
    smart: bool = typer.Option(True, "--smart/--no-smart",
                              help="Use smart context-aware execution")
):
    """Execute a document with Claude Code."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Parse allowed tools
    allowed_tools = tools.split(",") if tools else None

    # Generate execution ID
    timestamp = int(time.time())
    execution_id = f"claude-{doc['id']}-{timestamp}"

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
                use_stage_tools=True
            )

            console.print("\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
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

            console.print("\n[dim]Monitor with:[/dim] [cyan]emdx exec show {execution_id}[/cyan]")
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
                started_at=datetime.now(),
                log_file=str(log_file),
                working_dir=working_dir
            )
            save_execution(execution)

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
