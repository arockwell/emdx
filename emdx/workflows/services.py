"""Service layer for workflow operations.

This module provides a clean abstraction over document and execution operations,
reducing direct imports from models and commands in the executor. This helps
break bidirectional dependencies and improves testability.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class DocumentService:
    """Service for document operations used by workflows."""

    @staticmethod
    def get_document(doc_id: int) -> Optional[Dict[str, Any]]:
        """Get a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict with 'content', 'title', etc. or None if not found
        """
        from emdx.models.documents import get_document
        return get_document(doc_id)

    @staticmethod
    def save_document(
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Save a new document.

        Args:
            title: Document title
            content: Document content
            tags: Optional list of tags

        Returns:
            Created document ID
        """
        from emdx.models.documents import save_document
        return save_document(title=title, content=content, tags=tags)


class ExecutionService:
    """Service for execution operations used by workflows."""

    @staticmethod
    def create_execution(
        doc_id: int,
        doc_title: str,
        log_file: str,
        working_dir: Optional[str] = None,
    ) -> int:
        """Create a new execution record.

        Args:
            doc_id: Document ID being executed
            doc_title: Document title
            log_file: Path to log file
            working_dir: Working directory for execution

        Returns:
            Created execution ID
        """
        from emdx.models.executions import create_execution
        return create_execution(
            doc_id=doc_id,
            doc_title=doc_title,
            log_file=log_file,
            working_dir=working_dir,
        )

    @staticmethod
    def get_execution(exec_id: int) -> Optional[Any]:
        """Get an execution by ID.

        Args:
            exec_id: Execution ID (int)

        Returns:
            Execution object or None if not found
        """
        from emdx.models.executions import get_execution
        return get_execution(exec_id)

    @staticmethod
    def update_execution_status(
        exec_id: int,
        status: str,
        exit_code: Optional[int] = None,
    ) -> None:
        """Update execution status.

        Args:
            exec_id: Execution ID
            status: New status ('completed', 'failed', etc.)
            exit_code: Optional exit code
        """
        from emdx.models.executions import update_execution_status
        update_execution_status(exec_id, status, exit_code)


class ClaudeService:
    """Service for Claude execution operations."""

    @staticmethod
    def execute_with_claude(
        task: str,
        execution_id: int,
        log_file: Path,
        allowed_tools: List[str],
        verbose: bool = False,
        working_dir: Optional[str] = None,
        doc_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Execute a task with Claude synchronously.

        Args:
            task: The task/prompt to execute
            execution_id: Execution ID for tracking
            log_file: Path to log file
            allowed_tools: List of allowed Claude tools
            verbose: Whether to show verbose output
            working_dir: Working directory for execution
            doc_id: Associated document ID (for logging)
            context: Optional execution context

        Returns:
            Exit code from Claude process
        """
        from emdx.commands.claude_execute import execute_with_claude
        return execute_with_claude(
            task=task,
            execution_id=execution_id,
            log_file=log_file,
            allowed_tools=allowed_tools,
            verbose=verbose,
            working_dir=working_dir,
            doc_id=doc_id,
            context=context,
        )


# Singleton instances for convenience
document_service = DocumentService()
execution_service = ExecutionService()
claude_service = ClaudeService()
