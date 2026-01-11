"""CLI utilities for error handling."""

import functools
from typing import Callable, TypeVar

import typer

from emdx.utils.output import console

F = TypeVar('F', bound=Callable)


def handle_cli_errors(action: str) -> Callable[[F], F]:
    """Decorator that catches exceptions and prints user-friendly errors.

    Args:
        action: Description of the action being performed (e.g., "saving document")

    Returns:
        Decorator function that wraps the target function with error handling.

    Example:
        @handle_cli_errors("saving document")
        def save(doc_id: int):
            # code that might raise exceptions
            pass
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except typer.Exit:
                raise
            except Exception as e:
                console.print(f"[red]Error {action}: {e}[/red]")
                raise typer.Exit(1) from e
        return wrapper
    return decorator
