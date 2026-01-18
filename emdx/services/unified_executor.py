"""Unified executor service for all Claude execution paths.

This module consolidates the common execution logic shared across:
- emdx agent (commands/agent.py)
- workflow agent runner (workflows/agent_runner.py)
- cascade processing (commands/cascade.py)

The goal is to have one place where:
1. Claude processes are spawned
2. Logs are captured
3. Output document IDs are extracted
4. Token usage is tracked
5. Execution records are managed

Each caller can customize behavior via ExecutionConfig while sharing
the core execution infrastructure.
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..models.executions import create_execution, update_execution_status
from ..utils.environment import ensure_claude_in_path
from .claude_executor import execute_claude_sync

# Lazy import to avoid circular dependency with workflows
def _get_output_parser():
    """Lazily import output_parser to avoid circular imports."""
    from ..workflows.output_parser import extract_output_doc_id, extract_token_usage_detailed
    return extract_output_doc_id, extract_token_usage_detailed

logger = logging.getLogger(__name__)

# Default allowed tools for Claude executions
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash",
    "Glob", "Grep", "LS", "Task", "TodoWrite",
    "WebFetch", "WebSearch"
]


@dataclass
class ExecutionConfig:
    """Configuration for a Claude execution.

    This dataclass captures all the options that can vary between
    different execution contexts (agent, workflow, cascade).
    """
    # Core prompt
    prompt: str

    # Execution context
    working_dir: str = field(default_factory=lambda: str(Path.cwd()))

    # Metadata for tracking
    title: str = "Claude Execution"
    doc_id: Optional[int] = None

    # Output handling
    output_instruction: Optional[str] = None  # Appended to prompt

    # Claude configuration
    allowed_tools: List[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy())
    timeout_seconds: int = 300  # 5 minutes default
    model: Optional[str] = None  # Use default if None

    # Execution mode
    sync: bool = True  # Wait for completion vs detached
    verbose: bool = False  # Stream output to console

    # Callbacks for custom handling
    on_start: Optional[Callable[[int], None]] = None  # Called with exec_id
    on_complete: Optional[Callable[[Dict[str, Any]], None]] = None
    on_error: Optional[Callable[[str], None]] = None


@dataclass
class ExecutionResult:
    """Result of a Claude execution."""
    success: bool
    execution_id: int
    log_file: Path

    # On success
    output_doc_id: Optional[int] = None
    output_content: Optional[str] = None

    # Token tracking
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    # Timing
    execution_time_ms: int = 0

    # On failure
    error_message: Optional[str] = None
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for easy consumption."""
        return {
            'success': self.success,
            'execution_id': self.execution_id,
            'log_file': str(self.log_file),
            'output_doc_id': self.output_doc_id,
            'output_content': self.output_content,
            'tokens_used': self.tokens_used,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cost_usd': self.cost_usd,
            'execution_time_ms': self.execution_time_ms,
            'error_message': self.error_message,
            'exit_code': self.exit_code,
        }


class UnifiedExecutor:
    """Unified executor for all Claude execution paths.

    Usage:
        executor = UnifiedExecutor()

        config = ExecutionConfig(
            prompt="Analyze the auth module",
            title="Auth Analysis",
            output_instruction="Save output with: emdx save --title '...'",
        )

        result = executor.execute(config)

        if result.success:
            print(f"Output doc: #{result.output_doc_id}")
        else:
            print(f"Failed: {result.error_message}")
    """

    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize the executor.

        Args:
            log_dir: Directory for log files. Defaults to ~/.config/emdx/logs
        """
        self.log_dir = log_dir or (Path.home() / ".config" / "emdx" / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, config: ExecutionConfig) -> ExecutionResult:
        """Execute Claude with the given configuration.

        Args:
            config: Execution configuration

        Returns:
            ExecutionResult with success/failure details
        """
        ensure_claude_in_path()

        # Set up log file
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        log_file = self.log_dir / f"unified-{timestamp}.log"

        # Create execution record
        exec_id = create_execution(
            doc_id=config.doc_id,
            doc_title=config.title,
            log_file=str(log_file),
            working_dir=config.working_dir,
        )

        # Notify start callback
        if config.on_start:
            config.on_start(exec_id)

        # Build full prompt
        full_prompt = config.prompt
        if config.output_instruction:
            full_prompt = config.prompt + config.output_instruction

        start_time = time.time()

        try:
            if config.sync:
                result = self._execute_sync(
                    exec_id=exec_id,
                    prompt=full_prompt,
                    config=config,
                    log_file=log_file,
                )
            else:
                result = self._execute_detached(
                    exec_id=exec_id,
                    prompt=full_prompt,
                    config=config,
                    log_file=log_file,
                )

            # Calculate execution time
            result.execution_time_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from log
            if log_file.exists():
                _, extract_token_usage_detailed = _get_output_parser()
                usage = extract_token_usage_detailed(log_file)
                result.tokens_used = usage.get('total', 0)
                result.input_tokens = usage.get('input', 0) + usage.get('cache_in', 0) + usage.get('cache_create', 0)
                result.output_tokens = usage.get('output', 0)
                result.cost_usd = usage.get('cost_usd', 0.0)

            # Notify complete callback
            if config.on_complete:
                config.on_complete(result.to_dict())

            return result

        except Exception as e:
            error_msg = str(e)
            logger.exception("Execution failed: %s", error_msg)

            update_execution_status(exec_id, 'failed', -1)

            if config.on_error:
                config.on_error(error_msg)

            return ExecutionResult(
                success=False,
                execution_id=exec_id,
                log_file=log_file,
                error_message=error_msg,
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

    def _execute_sync(
        self,
        exec_id: int,
        prompt: str,
        config: ExecutionConfig,
        log_file: Path,
    ) -> ExecutionResult:
        """Execute Claude synchronously and wait for completion."""

        result_data = execute_claude_sync(
            task=prompt,
            execution_id=exec_id,
            log_file=log_file,
            allowed_tools=config.allowed_tools,
            working_dir=config.working_dir,
            doc_id=str(config.doc_id) if config.doc_id else None,
            timeout=config.timeout_seconds,
        )

        success = result_data.get('success', False)
        exit_code = result_data.get('exit_code', -1)

        # Update execution status
        status = 'completed' if success else 'failed'
        update_execution_status(exec_id, status, exit_code)

        if success:
            # Try to extract output document ID from log
            extract_output_doc_id, _ = _get_output_parser()
            output_doc_id = extract_output_doc_id(log_file)

            return ExecutionResult(
                success=True,
                execution_id=exec_id,
                log_file=log_file,
                output_doc_id=output_doc_id,
                output_content=result_data.get('output'),
                exit_code=exit_code,
            )
        else:
            return ExecutionResult(
                success=False,
                execution_id=exec_id,
                log_file=log_file,
                error_message=result_data.get('error', 'Unknown error'),
                exit_code=exit_code,
            )

    def _execute_detached(
        self,
        exec_id: int,
        prompt: str,
        config: ExecutionConfig,
        log_file: Path,
    ) -> ExecutionResult:
        """Execute Claude in detached mode (returns immediately)."""
        from .claude_executor import execute_claude_detached

        pid = execute_claude_detached(
            task=prompt,
            execution_id=exec_id,
            log_file=log_file,
            allowed_tools=config.allowed_tools,
            working_dir=config.working_dir,
            doc_id=str(config.doc_id) if config.doc_id else None,
        )

        # Note: For detached execution, we can't know the result yet
        # The caller is responsible for checking later
        return ExecutionResult(
            success=True,  # Started successfully
            execution_id=exec_id,
            log_file=log_file,
        )


# Convenience functions for common patterns

def execute_with_output_tracking(
    prompt: str,
    title: str = "Agent Output",
    tags: Optional[List[str]] = None,
    group_id: Optional[int] = None,
    group_role: str = "member",
    create_pr: bool = False,
    working_dir: Optional[str] = None,
    timeout: int = 300,
    verbose: bool = False,
) -> ExecutionResult:
    """Execute a task with output tracking instructions injected.

    This is the main entry point for the 'emdx agent' command pattern.
    It appends instructions telling Claude how to save its output.

    Args:
        prompt: The task for Claude to perform
        title: Title for the output document
        tags: Tags to apply to output
        group_id: Optional group to add output to
        group_role: Role in group (primary, exploration, synthesis, variant, member)
        create_pr: Whether to instruct Claude to create a PR
        working_dir: Working directory for execution
        timeout: Timeout in seconds
        verbose: Whether to stream output

    Returns:
        ExecutionResult with output_doc_id populated if Claude saved output
    """
    # Build the output instruction
    cmd_parts = [f'emdx save --title "{title}"']

    if tags:
        tag_str = ",".join(tags)
        cmd_parts.append(f'--tags "{tag_str}"')

    if group_id is not None:
        cmd_parts.append(f'--group {group_id}')
        if group_role != "member":
            cmd_parts.append(f'--group-role {group_role}')

    save_cmd = " ".join(cmd_parts)

    output_instruction = f'''

IMPORTANT: When you complete this task, save your final output/analysis using:
echo "YOUR OUTPUT HERE" | {save_cmd}

Report the document ID that was created.'''

    if create_pr:
        output_instruction += '''

After saving your output, if you made any code changes, create a pull request:
1. Create a new branch with a descriptive name
2. Commit your changes with a clear message
3. Push and create a PR using: gh pr create --title "..." --body "..."
4. Report the PR URL that was created.'''

    config = ExecutionConfig(
        prompt=prompt,
        title=title,
        output_instruction=output_instruction,
        working_dir=working_dir or str(Path.cwd()),
        timeout_seconds=timeout,
        verbose=verbose,
        sync=True,
    )

    executor = UnifiedExecutor()
    return executor.execute(config)


def execute_for_cascade(
    prompt: str,
    doc_id: int,
    title: str,
    is_implementation: bool = False,
    timeout: int = 300,
) -> ExecutionResult:
    """Execute a cascade stage transformation.

    This is the entry point for cascade processing.
    Implementation stage gets special handling (longer timeout, PR extraction).

    Args:
        prompt: The transformation prompt
        doc_id: Source document ID
        title: Title for execution record
        is_implementation: Whether this is the planned→done stage
        timeout: Timeout in seconds (default 5min, implementation gets 30min)

    Returns:
        ExecutionResult with output_content containing Claude's response
    """
    if is_implementation:
        timeout = 1800  # 30 minutes for implementation

    config = ExecutionConfig(
        prompt=prompt,
        doc_id=doc_id,
        title=title,
        timeout_seconds=timeout,
        sync=True,
    )

    executor = UnifiedExecutor()
    return executor.execute(config)


def execute_for_workflow(
    prompt: str,
    doc_id: Optional[int] = None,
    title: str = "Workflow Agent",
    working_dir: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
) -> ExecutionResult:
    """Execute an agent as part of a workflow.

    This is the entry point for workflow agent execution.
    Includes the standard workflow output instruction.

    Args:
        prompt: The agent task
        doc_id: Optional input document ID
        title: Title for execution record
        working_dir: Working directory
        allowed_tools: Tools to allow (defaults to standard set)

    Returns:
        ExecutionResult with output_doc_id if agent saved output
    """
    output_instruction = """

IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"

Report the document ID that was created."""

    config = ExecutionConfig(
        prompt=prompt,
        doc_id=doc_id,
        title=title,
        output_instruction=output_instruction,
        working_dir=working_dir or str(Path.cwd()),
        allowed_tools=allowed_tools or DEFAULT_ALLOWED_TOOLS,
        sync=True,
    )

    executor = UnifiedExecutor()
    return executor.execute(config)
