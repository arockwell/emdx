"""Shared command helpers to reduce duplication across commands.

This module provides:
- require_document(): Fetch a document or exit with error
- @handle_command_error: Consistent error handling decorator
- @ensure_schema: Ensures database schema before command execution
"""

from functools import wraps
from typing import Any, Callable, TypeVar

import typer

from emdx.database import db
from emdx.models.documents import get_document
from emdx.utils.output import console

F = TypeVar("F", bound=Callable[..., Any])


class DocumentNotFoundError(Exception):
    """Raised when a document cannot be found."""

    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"Document '{identifier}' not found")


def require_document(identifier: str | int) -> dict[str, Any]:
    """Fetch a document by ID or title, or exit with error if not found.

    Args:
        identifier: Document ID (int or str) or title string

    Returns:
        Document dict with all fields

    Raises:
        typer.Exit: If document is not found (exits with code 1)

    Example:
        doc = require_document(42)
        doc = require_document("My Document Title")
    """
    doc = get_document(str(identifier))
    if not doc:
        console.print(f"[red]Error: Document '{identifier}' not found[/red]")
        raise typer.Exit(1)
    return doc


def require_document_or_raise(identifier: str | int) -> dict[str, Any]:
    """Fetch a document by ID or title, or raise DocumentNotFoundError.

    Use this variant when you want to handle the error yourself or when
    using inside @handle_command_error decorated functions.

    Args:
        identifier: Document ID (int or str) or title string

    Returns:
        Document dict with all fields

    Raises:
        DocumentNotFoundError: If document is not found
    """
    doc = get_document(str(identifier))
    if not doc:
        raise DocumentNotFoundError(str(identifier))
    return doc


def handle_command_error(
    operation: str | None = None,
    *,
    exit_code: int = 1,
    reraise_abort: bool = True,
) -> Callable[[F], F]:
    """Decorator for consistent error handling in CLI commands.

    Catches exceptions and displays a formatted error message before exiting.
    Handles typer.Abort specially to show "Cancelled" message.

    Args:
        operation: Description of the operation for error messages (e.g., "viewing document")
                  If not provided, extracts from function name.
        exit_code: Exit code to use on error (default: 1)
        reraise_abort: Whether to let typer.Abort propagate (default: True)

    Example:
        @app.command()
        @handle_command_error("viewing document")
        def view(doc_id: int):
            doc = require_document(doc_id)
            ...

        @app.command()
        @handle_command_error()  # Auto-detects operation from function name
        def delete(doc_id: int):
            ...
    """

    def decorator(func: F) -> F:
        # Auto-detect operation from function name if not provided
        op = operation
        if op is None:
            # Convert function name: "list_tags" -> "listing tags"
            name = func.__name__.replace("_", " ")
            if name.endswith("s"):
                op = f"{name}ing"[:-1]  # "tags" -> "tagging"
            else:
                op = f"{name}ing"

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except typer.Exit:
                # Let explicit exits pass through
                raise
            except typer.Abort:
                console.print("[yellow]Cancelled[/yellow]")
                if reraise_abort:
                    raise typer.Exit(0) from None
                raise
            except DocumentNotFoundError as e:
                console.print(f"[red]Error: Document '{e.identifier}' not found[/red]")
                raise typer.Exit(exit_code) from e
            except Exception as e:
                console.print(f"[red]Error {op}: {e}[/red]")
                raise typer.Exit(exit_code) from e

        return wrapper  # type: ignore[return-value]

    return decorator


def ensure_schema(func: F) -> F:
    """Decorator to ensure database schema exists before command execution.

    This should be applied to command functions that interact with the database.
    It calls db.ensure_schema() before executing the function.

    Example:
        @app.command()
        @ensure_schema
        def view(doc_id: int):
            doc = require_document(doc_id)
            ...

    Can be combined with handle_command_error (order matters - ensure_schema should be inner):
        @app.command()
        @handle_command_error("viewing document")
        @ensure_schema
        def view(doc_id: int):
            ...
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        db.ensure_schema()
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def combined_decorator(operation: str | None = None) -> Callable[[F], F]:
    """Convenience decorator combining @handle_command_error and @ensure_schema.

    This is the most common pattern for commands - ensure schema and handle errors.

    Args:
        operation: Description of the operation for error messages

    Example:
        @app.command()
        @combined_decorator("viewing document")
        def view(doc_id: int):
            doc = require_document(doc_id)
            ...
    """

    def decorator(func: F) -> F:
        # Apply decorators in correct order: error handling wraps schema check
        return handle_command_error(operation)(ensure_schema(func))

    return decorator
