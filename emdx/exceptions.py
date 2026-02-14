"""Custom exception hierarchy for EMDX.

This module provides a structured exception hierarchy for categorizing errors
across the EMDX codebase. Using specific exception types enables:

1. Better error handling at call sites (catch specific errors, not broad Exception)
2. Improved debugging with contextual error information
3. Appropriate retry behavior for transient vs permanent failures
4. Consistent error logging and user feedback

Exception Hierarchy:
    EmdxError (base)
    ├── DatabaseError - SQLite/database operations
    │   ├── DatabaseConnectionError
    │   └── DatabaseQueryError
    ├── ExecutionError - Claude/CLI execution issues
    │   ├── ExecutionTimeoutError
    │   └── ExecutionSubprocessError
    ├── GitError - Git operations
    │   ├── GitLockError (retryable)
    │   └── GitCommandError
    ├── FileOperationError - File I/O
    │   ├── FileNotFoundError (shadows builtin intentionally)
    │   └── FileReadError
    ├── ApiError - External API calls
    │   ├── ApiConnectionError (retryable)
    │   ├── ApiRateLimitError (retryable)
    │   └── ApiAuthenticationError
    └── ConfigurationError - Settings/configuration issues

Usage:
    from emdx.exceptions import DatabaseError, GitLockError

    try:
        # database operation
    except sqlite3.Error as e:
        raise DatabaseQueryError("Failed to fetch document", document_id=42) from e
"""

from typing import Any, Optional


class EmdxError(Exception):
    """Base exception for all EMDX errors.

    All EMDX-specific exceptions should inherit from this class.
    This allows catching all EMDX errors with a single except clause
    when needed, while still enabling specific error handling.

    Attributes:
        message: Human-readable error description
        context: Additional context about the error (e.g., IDs, paths)
        retryable: Whether this error might succeed on retry
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        **context: Any,
    ) -> None:
        self.message = message
        self.context = context
        self.retryable = retryable
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message with context."""
        if self.context:
            context_str = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(EmdxError):
    """Base exception for database operations."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to or access the database."""

    def __init__(self, message: str = "Database connection failed", **context: Any) -> None:
        super().__init__(message, **context)


class DatabaseQueryError(DatabaseError):
    """A database query failed."""

    def __init__(
        self,
        message: str = "Database query failed",
        *,
        query: Optional[str] = None,
        **context: Any,
    ) -> None:
        if query:
            context["query"] = query[:100] + "..." if len(query) > 100 else query
        super().__init__(message, **context)


# =============================================================================
# Execution Errors
# =============================================================================


class ExecutionError(EmdxError):
    """Base exception for CLI/agent execution errors."""

    pass


class ExecutionTimeoutError(ExecutionError):
    """An execution timed out."""

    def __init__(
        self,
        message: str = "Execution timed out",
        *,
        timeout_seconds: Optional[float] = None,
        **context: Any,
    ) -> None:
        if timeout_seconds is not None:
            context["timeout_seconds"] = timeout_seconds
        super().__init__(message, **context)


class ExecutionSubprocessError(ExecutionError):
    """A subprocess execution failed."""

    def __init__(
        self,
        message: str = "Subprocess execution failed",
        *,
        command: Optional[str] = None,
        exit_code: Optional[int] = None,
        stderr: Optional[str] = None,
        **context: Any,
    ) -> None:
        if command:
            context["command"] = command[:100] + "..." if len(command) > 100 else command
        if exit_code is not None:
            context["exit_code"] = exit_code
        if stderr:
            context["stderr"] = stderr[:200] + "..." if len(stderr) > 200 else stderr
        super().__init__(message, **context)


# =============================================================================
# Git Errors
# =============================================================================


class GitError(EmdxError):
    """Base exception for git operations."""

    pass


class GitLockError(GitError):
    """Git lock file contention - retryable."""

    def __init__(
        self,
        message: str = "Git lock contention",
        *,
        lock_file: Optional[str] = None,
        **context: Any,
    ) -> None:
        if lock_file:
            context["lock_file"] = lock_file
        super().__init__(message, retryable=True, **context)


class GitCommandError(GitError):
    """A git command failed."""

    def __init__(
        self,
        message: str = "Git command failed",
        *,
        command: Optional[str] = None,
        exit_code: Optional[int] = None,
        **context: Any,
    ) -> None:
        if command:
            context["command"] = command
        if exit_code is not None:
            context["exit_code"] = exit_code
        super().__init__(message, **context)


# =============================================================================
# File Operation Errors
# =============================================================================


class FileOperationError(EmdxError):
    """Base exception for file operations."""

    pass


class FileNotFoundError(FileOperationError):  # noqa: A001 - intentionally shadows builtin
    """A required file was not found.

    Note: This shadows the builtin FileNotFoundError intentionally.
    Import explicitly if you need both:
        from emdx.exceptions import FileNotFoundError as EmdxFileNotFoundError
    """

    def __init__(
        self,
        message: str = "File not found",
        *,
        path: Optional[str] = None,
        **context: Any,
    ) -> None:
        if path:
            context["path"] = path
        super().__init__(message, **context)


class FileReadError(FileOperationError):
    """Failed to read a file."""

    def __init__(
        self,
        message: str = "Failed to read file",
        *,
        path: Optional[str] = None,
        **context: Any,
    ) -> None:
        if path:
            context["path"] = path
        super().__init__(message, **context)


class FileWriteError(FileOperationError):
    """Failed to write to a file."""

    def __init__(
        self,
        message: str = "Failed to write file",
        *,
        path: Optional[str] = None,
        **context: Any,
    ) -> None:
        if path:
            context["path"] = path
        super().__init__(message, **context)


# =============================================================================
# API Errors
# =============================================================================


class ApiError(EmdxError):
    """Base exception for external API calls."""

    pass


class ApiConnectionError(ApiError):
    """Failed to connect to an external API - typically retryable."""

    def __init__(
        self,
        message: str = "API connection failed",
        *,
        service: Optional[str] = None,
        **context: Any,
    ) -> None:
        if service:
            context["service"] = service
        super().__init__(message, retryable=True, **context)


class ApiRateLimitError(ApiError):
    """Hit rate limit on an external API - retryable with backoff."""

    def __init__(
        self,
        message: str = "API rate limit exceeded",
        *,
        service: Optional[str] = None,
        retry_after: Optional[float] = None,
        **context: Any,
    ) -> None:
        if service:
            context["service"] = service
        if retry_after is not None:
            context["retry_after"] = retry_after
        super().__init__(message, retryable=True, **context)


class ApiAuthenticationError(ApiError):
    """Authentication with an external API failed."""

    def __init__(
        self,
        message: str = "API authentication failed",
        *,
        service: Optional[str] = None,
        **context: Any,
    ) -> None:
        if service:
            context["service"] = service
        super().__init__(message, retryable=False, **context)


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(EmdxError):
    """Configuration or settings error."""

    def __init__(
        self,
        message: str = "Configuration error",
        *,
        setting: Optional[str] = None,
        **context: Any,
    ) -> None:
        if setting:
            context["setting"] = setting
        super().__init__(message, **context)


# =============================================================================
# Task/Workflow Errors
# =============================================================================


class TaskError(EmdxError):
    """Base exception for task-related errors."""

    pass


class TaskUpdateError(TaskError):
    """Failed to update task status."""

    def __init__(
        self,
        message: str = "Task update failed",
        *,
        task_id: Optional[int] = None,
        **context: Any,
    ) -> None:
        if task_id is not None:
            context["task_id"] = task_id
        super().__init__(message, **context)


class ExecutionTrackingError(TaskError):
    """Failed to track execution status."""

    def __init__(
        self,
        message: str = "Execution tracking failed",
        *,
        execution_id: Optional[int] = None,
        **context: Any,
    ) -> None:
        if execution_id is not None:
            context["execution_id"] = execution_id
        super().__init__(message, **context)
