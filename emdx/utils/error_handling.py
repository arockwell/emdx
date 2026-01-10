"""Error handling utilities and decorators for consistent error patterns.

This module provides:
- Custom exception classes for EMDX-specific errors
- Decorators for CLI command error handling
- Context managers for safe resource access
- Logging utilities for consistent error reporting
"""

import functools
import logging
from contextlib import contextmanager
from typing import Any, Callable, Optional, TypeVar

import typer
from rich.console import Console

logger = logging.getLogger(__name__)

# Type variables for generic decorators
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Custom Exception Classes
# =============================================================================


class EmdxError(Exception):
    """Base exception for all EMDX-specific errors."""

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(message)


class EmdxDatabaseError(EmdxError):
    """Exception for database-related failures."""

    pass


class EmdxValidationError(EmdxError):
    """Exception for input validation failures."""

    pass


class EmdxIOError(EmdxError):
    """Exception for file/directory operation failures."""

    pass


class EmdxNotFoundError(EmdxError):
    """Exception for resource not found errors."""

    def __init__(self, resource_type: str, identifier: Any):
        self.resource_type = resource_type
        self.identifier = identifier
        super().__init__(f"{resource_type} '{identifier}' not found")


class EmdxExecutionError(EmdxError):
    """Exception for execution/agent failures."""

    pass


# =============================================================================
# CLI Error Handling Decorator
# =============================================================================


def handle_cli_error(
    operation: str,
    console: Optional[Console] = None,
    exit_code: int = 1,
    log_traceback: bool = True,
) -> Callable[[F], F]:
    """Decorator for consistent CLI command error handling.

    Args:
        operation: Description of the operation for error messages
        console: Rich Console instance for output (creates one if not provided)
        exit_code: Exit code to use on error (default: 1)
        log_traceback: Whether to log the full traceback (default: True)

    Usage:
        @app.command()
        @handle_cli_error("saving document")
        def save(title: str):
            # Command implementation
            ...
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            _console = console or Console()
            try:
                return func(*args, **kwargs)
            except typer.Exit:
                # Re-raise typer exits (already handled)
                raise
            except typer.Abort:
                # User cancelled operation
                _console.print(f"[yellow]{operation.capitalize()} cancelled[/yellow]")
                raise typer.Exit(0) from None
            except EmdxNotFoundError as e:
                _console.print(f"[red]Error: {e.message}[/red]")
                raise typer.Exit(exit_code) from e
            except EmdxValidationError as e:
                _console.print(f"[red]Validation error: {e.message}[/red]")
                if e.details:
                    _console.print(f"[dim]{e.details}[/dim]")
                raise typer.Exit(exit_code) from e
            except EmdxDatabaseError as e:
                _console.print(f"[red]Database error: {e.message}[/red]")
                if log_traceback:
                    logger.error(f"Database error during {operation}: {e}", exc_info=True)
                raise typer.Exit(exit_code) from e
            except EmdxError as e:
                _console.print(f"[red]Error {operation}: {e.message}[/red]")
                if e.details:
                    _console.print(f"[dim]{e.details}[/dim]")
                if log_traceback:
                    logger.error(f"Error during {operation}: {e}", exc_info=True)
                raise typer.Exit(exit_code) from e
            except Exception as e:
                _console.print(f"[red]Error {operation}: {e}[/red]")
                if log_traceback:
                    logger.error(f"Unexpected error during {operation}: {e}", exc_info=True)
                raise typer.Exit(exit_code) from e

        return wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# Database Error Handling
# =============================================================================


def ensure_database(console: Optional[Console] = None) -> None:
    """Ensure database schema exists with proper error handling.

    Args:
        console: Rich Console instance for output

    Raises:
        EmdxDatabaseError: If database initialization fails
    """
    from emdx.database import db

    try:
        db.ensure_schema()
    except Exception as e:
        if console:
            console.print(f"[red]Database error: {e}[/red]")
        raise EmdxDatabaseError(f"Failed to initialize database: {e}") from e


@contextmanager
def database_operation(operation: str, console: Optional[Console] = None):
    """Context manager for database operations with consistent error handling.

    Args:
        operation: Description of the database operation
        console: Rich Console instance for output

    Usage:
        with database_operation("saving document", console):
            save_document(...)
    """
    try:
        yield
    except EmdxDatabaseError:
        raise
    except Exception as e:
        if console:
            console.print(f"[red]Database error during {operation}: {e}[/red]")
        raise EmdxDatabaseError(f"Failed during {operation}: {e}") from e


# =============================================================================
# Resource Validation Utilities
# =============================================================================


def require_document(doc_id: Any, console: Optional[Console] = None) -> dict:
    """Get a document or raise EmdxNotFoundError if not found.

    Args:
        doc_id: Document ID to look up
        console: Rich Console instance for output

    Returns:
        Document dict if found

    Raises:
        EmdxNotFoundError: If document is not found
    """
    from emdx.models.documents import get_document

    doc = get_document(str(doc_id))
    if not doc:
        if console:
            console.print(f"[red]Error: Document #{doc_id} not found[/red]")
        raise EmdxNotFoundError("Document", doc_id)
    return doc


def validate_exists(path: str, resource_type: str = "Path") -> None:
    """Validate that a file or directory exists.

    Args:
        path: Path to validate
        resource_type: Type of resource for error messages

    Raises:
        EmdxNotFoundError: If path does not exist
    """
    from pathlib import Path as PathLib

    if not PathLib(path).exists():
        raise EmdxNotFoundError(resource_type, path)


# =============================================================================
# Logging Utilities
# =============================================================================


def log_and_raise(
    error: Exception,
    message: str,
    error_class: type[EmdxError] = EmdxError,
    log_level: int = logging.ERROR,
) -> None:
    """Log an error and raise a wrapped exception.

    Args:
        error: Original exception
        message: Error message
        error_class: EmdxError subclass to raise
        log_level: Logging level (default: ERROR)

    Raises:
        error_class: Wrapped exception with the provided message
    """
    logger.log(log_level, f"{message}: {error}", exc_info=True)
    raise error_class(message, details=str(error)) from error


@contextmanager
def log_errors(operation: str, reraise: bool = True):
    """Context manager that logs any exceptions.

    Args:
        operation: Description of the operation for logging
        reraise: Whether to re-raise the exception (default: True)

    Usage:
        with log_errors("processing file"):
            process_file()
    """
    try:
        yield
    except Exception as e:
        logger.error(f"Error during {operation}: {e}", exc_info=True)
        if reraise:
            raise


# =============================================================================
# Fallback/Retry Utilities
# =============================================================================


def with_fallback(
    primary_func: Callable[[], Any],
    fallback_func: Callable[[], Any],
    exception_types: tuple[type[Exception], ...] = (Exception,),
    log_warning: bool = True,
) -> Any:
    """Execute primary function with fallback on failure.

    Args:
        primary_func: Primary function to execute
        fallback_func: Fallback function if primary fails
        exception_types: Exception types to catch (default: all)
        log_warning: Whether to log a warning on fallback

    Returns:
        Result from primary or fallback function
    """
    try:
        return primary_func()
    except exception_types as e:
        if log_warning:
            logger.warning(f"Primary operation failed, using fallback: {e}")
        return fallback_func()


def retry_on_error(
    max_attempts: int = 3,
    exception_types: tuple[type[Exception], ...] = (Exception,),
    delay_seconds: float = 0,
) -> Callable[[F], F]:
    """Decorator for retrying operations on failure.

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        exception_types: Exception types to retry on (default: all)
        delay_seconds: Delay between retries in seconds (default: 0)

    Usage:
        @retry_on_error(max_attempts=3, exception_types=(IOError,))
        def flaky_operation():
            ...
    """
    import time

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Optional[Exception] = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed: {e}, retrying..."
                        )
                        if delay_seconds > 0:
                            time.sleep(delay_seconds)
                    else:
                        logger.error(f"All {max_attempts} attempts failed: {e}")
            raise last_error  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


# =============================================================================
# Safe UI Access Utilities
# =============================================================================


def safe_query_one(
    app: Any,
    selector: str,
    widget_class: type,
    default: Any = None,
) -> Any:
    """Safely query a single widget from a Textual app.

    Args:
        app: Textual app instance
        selector: CSS selector for the widget
        widget_class: Expected widget class
        default: Default value if query fails

    Returns:
        Widget instance or default value
    """
    try:
        return app.query_one(selector, widget_class)
    except Exception as e:
        logger.debug(f"Widget query failed for '{selector}': {e}")
        return default


def safe_widget_call(
    widget: Any,
    method_name: str,
    *args: Any,
    default: Any = None,
    **kwargs: Any,
) -> Any:
    """Safely call a method on a widget.

    Args:
        widget: Widget instance
        method_name: Method name to call
        *args: Positional arguments for the method
        default: Default value if call fails
        **kwargs: Keyword arguments for the method

    Returns:
        Method result or default value
    """
    try:
        method = getattr(widget, method_name, None)
        if method is None:
            logger.debug(f"Widget method '{method_name}' not found")
            return default
        return method(*args, **kwargs)
    except Exception as e:
        logger.debug(f"Widget method call failed: {method_name}: {e}")
        return default
