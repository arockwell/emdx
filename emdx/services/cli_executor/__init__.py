"""CLI executor package for EMDX.

This package provides a strategy pattern implementation for different CLI tools
(Claude, Cursor) that can execute agent tasks.
"""

from .base import CliCommand, CliExecutor, CliResult
from .factory import get_cli_executor

__all__ = [
    "CliCommand",
    "CliExecutor",
    "CliResult",
    "get_cli_executor",
]
