"""Unified executor for Claude execution paths."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.executions import create_execution, update_execution_status
from ..utils.environment import ensure_claude_in_path
from .claude_executor import execute_claude_sync

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "MultiEdit", "Bash",
    "Glob", "Grep", "LS", "Task", "TodoWrite",
    "WebFetch", "WebSearch"
]


@dataclass
class ExecutionConfig:
    """Configuration for a Claude execution."""
    prompt: str
    working_dir: str = field(default_factory=lambda: str(Path.cwd()))
    title: str = "Claude Execution"
    doc_id: Optional[int] = None
    output_instruction: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy())
    timeout_seconds: int = 300


@dataclass
class ExecutionResult:
    """Result of a Claude execution."""
    success: bool
    execution_id: int
    log_file: Path
    output_doc_id: Optional[int] = None
    output_content: Optional[str] = None
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    exit_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
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
    """Unified executor for all Claude execution paths."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (Path.home() / ".config" / "emdx" / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, config: ExecutionConfig) -> ExecutionResult:
        """Execute Claude with the given configuration."""
        from ..workflows.output_parser import extract_output_doc_id, extract_token_usage_detailed

        ensure_claude_in_path()

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        log_file = self.log_dir / f"unified-{timestamp}.log"

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
            result_data = execute_claude_sync(
                task=full_prompt,
                execution_id=exec_id,
                log_file=log_file,
                allowed_tools=config.allowed_tools,
                working_dir=config.working_dir,
                doc_id=str(config.doc_id) if config.doc_id else None,
                timeout=config.timeout_seconds,
            )

            success = result_data.get('success', False)
            exit_code = result_data.get('exit_code', -1)
            status = 'completed' if success else 'failed'
            update_execution_status(exec_id, status, exit_code)

            result = ExecutionResult(
                success=success,
                execution_id=exec_id,
                log_file=log_file,
                exit_code=exit_code,
            )

            if success:
                result.output_doc_id = extract_output_doc_id(log_file)
                result.output_content = result_data.get('output')
            else:
                result.error_message = result_data.get('error', 'Unknown error')

            result.execution_time_ms = int((time.time() - start_time) * 1000)

            if log_file.exists():
                usage = extract_token_usage_detailed(log_file)
                result.tokens_used = usage.get('total', 0)
                result.input_tokens = usage.get('input', 0) + usage.get('cache_in', 0) + usage.get('cache_create', 0)
                result.output_tokens = usage.get('output', 0)
                result.cost_usd = usage.get('cost_usd', 0.0)

            return result

        except Exception as e:
            logger.exception("Execution failed: %s", e)
            update_execution_status(exec_id, 'failed', -1)
            return ExecutionResult(
                success=False,
                execution_id=exec_id,
                log_file=log_file,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
