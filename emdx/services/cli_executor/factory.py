"""Factory for creating CLI executors."""

import os
from typing import Union

from ...config.cli_config import CliTool
from .base import CliExecutor
from .claude import ClaudeCliExecutor

# Registry of executor classes
_EXECUTORS = {
    CliTool.CLAUDE: ClaudeCliExecutor,
}


def get_cli_executor(cli_tool: Union[str, CliTool] | None = None) -> CliExecutor:
    """Get the appropriate CLI executor.

    Args:
        cli_tool: "claude", CliTool enum, or None (uses default/env var)

    Returns:
        CliExecutor instance for the specified tool

    Raises:
        ValueError: If cli_tool is not recognized

    Examples:
        >>> executor = get_cli_executor()  # Uses EMDX_CLI_TOOL env var or "claude"
        >>> executor = get_cli_executor(CliTool.CLAUDE)
    """
    # Determine which CLI to use
    if cli_tool is None:
        # Check environment variable, default to Claude
        env_value = os.environ.get("EMDX_CLI_TOOL", "claude").lower()
        cli_tool = env_value

    # Convert string to enum if needed
    if isinstance(cli_tool, str):
        try:
            cli_tool = CliTool(cli_tool.lower())
        except ValueError:
            valid = ", ".join(t.value for t in CliTool)
            raise ValueError(f"Unknown CLI tool: {cli_tool}. Valid options: {valid}") from None

    # Get executor class and instantiate
    executor_class = _EXECUTORS.get(cli_tool)
    if executor_class is None:
        raise ValueError(f"No executor registered for CLI tool: {cli_tool}") from None

    return executor_class()
