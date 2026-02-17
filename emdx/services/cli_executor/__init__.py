"""CLI executor package for EMDX.

This package provides a strategy pattern implementation for the Claude CLI tool
that executes agent tasks.
"""

from .base import CliCommand, CliExecutor, CliResult
from .factory import get_cli_executor
from .types import (
    AssistantMessage,
    ContentItem,
    EnvironmentInfo,
    ErrorMessage,
    ResultMessage,
    StreamMessage,
    SystemMessage,
    ThinkingMessage,
    ToolCallMessage,
)

__all__ = [
    "AssistantMessage",
    "CliCommand",
    "CliExecutor",
    "CliResult",
    "ContentItem",
    "EnvironmentInfo",
    "ErrorMessage",
    "ResultMessage",
    "StreamMessage",
    "SystemMessage",
    "ThinkingMessage",
    "ToolCallMessage",
    "get_cli_executor",
]
