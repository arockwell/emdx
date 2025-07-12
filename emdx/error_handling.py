"""
Centralized error handling system for emdx

This module provides standardized error handling with:
- Rich Console for user-facing error messages
- Structured logging for developer diagnostics
- Custom exception classes for different error types
- Consistent formatting and exit codes
"""

import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Global console instance for error display
console = Console(stderr=True, force_terminal=True, color_system="auto")

# Global logger for diagnostics
logger = logging.getLogger("emdx")


class ErrorSeverity(Enum):
    """Error severity levels for categorization"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better handling"""
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    NETWORK = "network"
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    CONFIGURATION = "configuration"
    EXTERNAL_TOOL = "external_tool"
    INTERNAL = "internal"


class EmdxError(Exception):
    """Base exception class for emdx-specific errors"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        exit_code: int = 1
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.suggestion = suggestion
        self.exit_code = exit_code


class DatabaseError(EmdxError):
    """Errors related to database operations"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.DATABASE,
            **kwargs
        )


class FileSystemError(EmdxError):
    """Errors related to file system operations"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.FILE_SYSTEM,
            **kwargs
        )


class ValidationError(EmdxError):
    """Errors related to input validation"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.VALIDATION,
            **kwargs
        )


class NetworkError(EmdxError):
    """Errors related to network operations"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.NETWORK,
            **kwargs
        )


class ExternalToolError(EmdxError):
    """Errors related to external tool execution"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.EXTERNAL_TOOL,
            **kwargs
        )


def setup_logging(
    verbose: bool = False,
    quiet: bool = False,
    log_file: Optional[Path] = None
) -> None:
    """
    Set up structured logging for emdx
    
    Args:
        verbose: Enable verbose (DEBUG) logging
        quiet: Disable INFO and WARNING logs to console
        log_file: Optional log file path (defaults to ~/.config/emdx/emdx.log)
    """
    # Determine log level
    if verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.ERROR
    else:
        console_level = logging.INFO
    
    # Set up formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s'
    )
    simple_formatter = logging.Formatter('%(levelname)s: %(message)s')
    
    # Clear any existing handlers
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    
    # Console handler for user feedback (only errors/warnings unless verbose)
    if not quiet:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(simple_formatter)
        logger.addHandler(console_handler)
    
    # File handler for detailed diagnostics
    if log_file is None:
        config_dir = Path.home() / ".config" / "emdx"
        config_dir.mkdir(parents=True, exist_ok=True)
        log_file = config_dir / "emdx.log"
    
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # If we can't create log file, continue without it
        if verbose:
            console.print(f"[yellow]Warning: Could not create log file {log_file}: {e}[/yellow]")


def log_context(operation: str, **context_data: Any) -> Dict[str, Any]:
    """
    Create structured context for logging
    
    Args:
        operation: The operation being performed
        **context_data: Additional context data
        
    Returns:
        Structured context dictionary
    """
    context = {
        "operation": operation,
        "timestamp": logger.handlers[0].formatter.formatTime(logging.LogRecord(
            name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
        )) if logger.handlers else None,
        **context_data
    }
    return context


def handle_error(
    error: Exception,
    operation: str = "unknown",
    context: Optional[Dict[str, Any]] = None,
    show_details: bool = False
) -> None:
    """
    Handle errors with consistent formatting and logging
    
    Args:
        error: The exception to handle
        operation: Description of the operation that failed
        context: Additional context for logging
        show_details: Whether to show technical details to user
    """
    context = context or {}
    
    if isinstance(error, EmdxError):
        # Handle our custom errors
        _handle_emdx_error(error, operation, context, show_details)
    else:
        # Handle generic exceptions
        _handle_generic_error(error, operation, context, show_details)


def _handle_emdx_error(
    error: EmdxError,
    operation: str,
    context: Dict[str, Any],
    show_details: bool
) -> None:
    """Handle EmdxError instances with rich formatting"""
    
    # Log the error with context
    log_data = log_context(operation, **context, **error.details)
    
    if error.severity == ErrorSeverity.CRITICAL:
        logger.critical(f"{error.category.value}: {error.message}", extra=log_data)
    elif error.severity == ErrorSeverity.ERROR:
        logger.error(f"{error.category.value}: {error.message}", extra=log_data)
    elif error.severity == ErrorSeverity.WARNING:
        logger.warning(f"{error.category.value}: {error.message}", extra=log_data)
    else:
        logger.info(f"{error.category.value}: {error.message}", extra=log_data)
    
    # Display user-friendly error
    _display_user_error(error, show_details)
    
    # Exit with appropriate code
    if error.severity in (ErrorSeverity.ERROR, ErrorSeverity.CRITICAL):
        raise typer.Exit(error.exit_code)


def _handle_generic_error(
    error: Exception,
    operation: str,
    context: Dict[str, Any],
    show_details: bool
) -> None:
    """Handle generic Python exceptions"""
    
    # Log the error
    log_data = log_context(operation, **context, error_type=type(error).__name__)
    logger.error(f"Unexpected error during {operation}: {error}", extra=log_data, exc_info=True)
    
    # Create an EmdxError wrapper for consistent display
    wrapped_error = EmdxError(
        message=f"An unexpected error occurred during {operation}",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.ERROR,
        details={"original_error": str(error), "error_type": type(error).__name__},
        suggestion="Please check the logs for more details or contact support if this persists."
    )
    
    _display_user_error(wrapped_error, show_details or isinstance(error, KeyboardInterrupt))
    
    # Exit with error code
    raise typer.Exit(1)


def _display_user_error(error: EmdxError, show_details: bool) -> None:
    """Display error to user with Rich formatting"""
    
    # Choose color based on severity
    color_map = {
        ErrorSeverity.INFO: "blue",
        ErrorSeverity.WARNING: "yellow",
        ErrorSeverity.ERROR: "red",
        ErrorSeverity.CRITICAL: "red"
    }
    color = color_map.get(error.severity, "red")
    
    # Choose icon based on severity
    icon_map = {
        ErrorSeverity.INFO: "ℹ️",
        ErrorSeverity.WARNING: "⚠️",
        ErrorSeverity.ERROR: "❌",
        ErrorSeverity.CRITICAL: "💥"
    }
    icon = icon_map.get(error.severity, "❌")
    
    # Create error message
    message = Text()
    message.append(f"{icon} ", style="bold")
    message.append(error.message, style=f"bold {color}")
    
    # Add details if requested
    if show_details and error.details:
        details_text = "\n".join(f"• {k}: {v}" for k, v in error.details.items())
        message.append(f"\n\nDetails:\n{details_text}", style=f"dim {color}")
    
    # Add suggestion if available
    if error.suggestion:
        message.append(f"\n\n💡 Suggestion: {error.suggestion}", style="cyan")
    
    # Display in panel for better visibility
    panel = Panel(
        message,
        title=f"[bold]{error.category.value.replace('_', ' ').title()} Error[/bold]",
        title_align="left",
        border_style=color,
        padding=(0, 1)
    )
    
    console.print(panel)


def safe_operation(operation_name: str, show_details: bool = False):
    """
    Decorator for safe operation execution with standardized error handling
    
    Args:
        operation_name: Name of the operation for logging
        show_details: Whether to show technical details on error
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_error(e, operation_name, show_details=show_details)
        return wrapper
    return decorator


def warn_user(message: str, suggestion: Optional[str] = None) -> None:
    """Display a warning message to the user"""
    warning = EmdxError(
        message=message,
        severity=ErrorSeverity.WARNING,
        suggestion=suggestion
    )
    _display_user_error(warning, show_details=False)


def info_user(message: str, suggestion: Optional[str] = None) -> None:
    """Display an info message to the user"""
    info = EmdxError(
        message=message,
        severity=ErrorSeverity.INFO,
        suggestion=suggestion
    )
    _display_user_error(info, show_details=False)


# Convenience functions for common error scenarios
def database_connection_error(db_path: Path, original_error: Exception) -> DatabaseError:
    """Create a standardized database connection error"""
    return DatabaseError(
        message=f"Cannot connect to database at {db_path}",
        details={"db_path": str(db_path), "original_error": str(original_error)},
        suggestion="Check if the database file exists and you have proper permissions."
    )


def file_not_found_error(file_path: Path) -> FileSystemError:
    """Create a standardized file not found error"""
    return FileSystemError(
        message=f"File not found: {file_path}",
        details={"file_path": str(file_path)},
        suggestion="Check if the file path is correct and the file exists."
    )


def permission_denied_error(path: Path, operation: str) -> FileSystemError:
    """Create a standardized permission denied error"""
    return FileSystemError(
        message=f"Permission denied: Cannot {operation} {path}",
        details={"path": str(path), "operation": operation},
        suggestion="Check file permissions or run with appropriate privileges."
    )


def invalid_input_error(field: str, value: Any, expected: str) -> ValidationError:
    """Create a standardized input validation error"""
    return ValidationError(
        message=f"Invalid {field}: {value}",
        details={"field": field, "value": str(value), "expected": expected},
        suggestion=f"Please provide a valid {expected} for {field}."
    )