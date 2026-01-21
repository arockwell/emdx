"""Document execution service - executes EMDX documents with Claude.

This module provides document execution logic for use by UI components
and other service consumers. It breaks the bidirectional dependency
between UI and commands by providing a clean service interface.

The logic is adapted from commands/claude_execute.py but structured
for programmatic use rather than CLI invocation.
"""

import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from ..config.cli_config import DEFAULT_ALLOWED_TOOLS
from ..config.settings import DEFAULT_CLAUDE_MODEL
from ..models.documents import get_document
from ..models.executions import (
    create_execution,
    update_execution_pid,
    update_execution_working_dir,
)
from ..models.tags import get_document_tags
from ..prompts import build_prompt
from .claude_executor import execute_claude_detached


class ExecutionType(Enum):
    """Types of document execution based on tags."""
    NOTE = "note"
    ANALYSIS = "analysis"
    GAMEPLAN = "gameplan"
    GENERIC = "generic"


# Stage-specific tool restrictions
# DEFAULT_ALLOWED_TOOLS is imported from config.cli_config
STAGE_TOOLS = {
    ExecutionType.NOTE: [
        "Read", "Grep", "Glob", "LS",
        "Write",
        "Bash",
        "WebFetch", "WebSearch"
    ],
    ExecutionType.ANALYSIS: [
        "Read", "Grep", "Glob", "LS",
        "Write",
        "Bash",
        "WebFetch", "WebSearch"
    ],
    ExecutionType.GAMEPLAN: DEFAULT_ALLOWED_TOOLS,
    ExecutionType.GENERIC: DEFAULT_ALLOWED_TOOLS
}


def get_execution_context(doc_tags: list[str]) -> dict[str, Any]:
    """Determine execution behavior based on document tags.

    Args:
        doc_tags: List of tags on the document (normalized emojis)

    Returns:
        Context dictionary with execution type and configuration
    """
    tag_set = set(doc_tags)

    if '📝' in tag_set:
        return {
            'type': ExecutionType.NOTE,
            'prompt_template': 'analyze_note',
            'output_tags': ['analysis'],
            'output_title_prefix': 'Analysis: ',
            'description': 'Generate analysis from note'
        }
    elif '🔍' in tag_set:
        return {
            'type': ExecutionType.ANALYSIS,
            'prompt_template': 'create_gameplan',
            'output_tags': ['gameplan', 'active'],
            'output_title_prefix': 'Gameplan: ',
            'description': 'Generate gameplan from analysis'
        }
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


def generate_unique_execution_id(doc_id: str) -> str:
    """Generate a guaranteed unique execution ID.

    Args:
        doc_id: Document ID being executed

    Returns:
        Unique execution ID string
    """
    timestamp = int(time.time() * 1000000)
    pid = os.getpid()
    uuid_suffix = str(uuid.uuid4()).split('-')[0]
    return f"claude-{doc_id}-{timestamp}-{pid}-{uuid_suffix}"


def create_execution_worktree(execution_id: str, doc_title: str) -> Optional[Path]:
    """Create a dedicated temporary directory for Claude execution.

    Args:
        execution_id: Unique execution ID
        doc_title: Document title for directory naming

    Returns:
        Path to created directory or None if creation failed
    """
    try:
        exec_parts = execution_id.split('-')
        doc_id = exec_parts[1] if len(exec_parts) > 1 else "unknown"

        safe_title = re.sub(r'[^a-zA-Z0-9-]', '-', doc_title.lower())[:30]
        safe_title = re.sub(r'-+', '-', safe_title).strip('-')

        unique_suffix = execution_id.split('-', 2)[-1][-12:]

        temp_base = Path(tempfile.gettempdir())
        dir_name = f"emdx-exec-{doc_id}-{safe_title}-{unique_suffix}"
        worktree_path = temp_base / dir_name

        attempt = 0
        final_path = worktree_path
        while final_path.exists() and attempt < 10:
            attempt += 1
            final_path = temp_base / f"{dir_name}-{attempt}"

        if final_path.exists():
            final_path = temp_base / f"emdx-exec-{uuid.uuid4()}"

        final_path.mkdir(parents=True, exist_ok=True)
        return final_path

    except OSError as e:
        logger.warning("Failed to create worktree directory, using fallback: %s", e)
        try:
            fallback_dir = tempfile.mkdtemp(prefix="emdx-exec-")
            return Path(fallback_dir)
        except OSError as e:
            logger.warning("Failed to create fallback temp directory: %s", e)
            return None


def execute_document_background(
    doc_id: int,
    execution_id: str,
    log_file: Path,
    allowed_tools: Optional[List[str]] = None,
    use_stage_tools: bool = True,
    db_exec_id: Optional[int] = None
) -> dict[str, Any]:
    """Execute a document in background with context-aware behavior.

    This is the main entry point for UI components to execute documents.
    It starts execution in the background and returns immediately.

    Args:
        doc_id: Document ID to execute
        execution_id: Unique execution ID string
        log_file: Path to log file
        allowed_tools: Optional list of allowed tools (overrides stage tools)
        use_stage_tools: Whether to use stage-specific tools
        db_exec_id: Optional existing database execution ID to use

    Returns:
        Dictionary with execution details:
        - success: bool
        - execution_id: str
        - db_exec_id: int (database execution ID)
        - log_file: str
        - error: str (if success is False)

    Raises:
        ValueError: If document not found
    """
    doc = get_document(str(doc_id))
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    doc_tags = get_document_tags(str(doc_id))
    context = get_execution_context(doc_tags)
    prompt = build_prompt(context['prompt_template'], doc['content'])

    if use_stage_tools and allowed_tools is None:
        allowed_tools = STAGE_TOOLS.get(context['type'], DEFAULT_ALLOWED_TOOLS)
    elif allowed_tools is None:
        allowed_tools = DEFAULT_ALLOWED_TOOLS

    worktree_path = create_execution_worktree(execution_id, doc['title'])
    working_dir = str(worktree_path) if worktree_path else os.getcwd()

    if db_exec_id:
        db_execution_id = db_exec_id
        update_execution_working_dir(db_execution_id, working_dir)
    else:
        db_execution_id = create_execution(
            doc_id=doc_id,
            doc_title=doc['title'],
            log_file=str(log_file),
            working_dir=working_dir
        )

    try:
        pid = execute_claude_detached(
            task=prompt,
            execution_id=db_execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            working_dir=working_dir,
            doc_id=str(doc_id),
        )

        update_execution_pid(db_execution_id, pid)

        return {
            'success': True,
            'execution_id': execution_id,
            'db_exec_id': db_execution_id,
            'log_file': str(log_file),
            'pid': pid,
            'context': context,
        }
    except Exception as e:
        logger.warning("Failed to execute document %s: %s", doc_id, e, exc_info=True)
        return {
            'success': False,
            'execution_id': execution_id,
            'db_exec_id': db_execution_id,
            'log_file': str(log_file),
            'error': str(e),
        }
