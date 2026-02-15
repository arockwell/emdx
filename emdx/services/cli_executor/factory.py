"""Factory for creating CLI executors."""

import os
from typing import Union

from ...config.cli_config import CliTool
from ...config.constants import ENV_CLI_TOOL
from .base import CliExecutor
from .claude import ClaudeCliExecutor
from .cursor import CursorCliExecutor

# Registry of executor classes
_EXECUTORS = {
    CliTool.CLAUDE: ClaudeCliExecutor,
    CliTool.CURSOR: CursorCliExecutor,
}


def get_cli_executor(cli_tool: Union[str, CliTool] | None = None) -> CliExecutor:
    """Get the appropriate CLI executor.

    Args:
        cli_tool: "claude", "cursor", CliTool enum, or None (uses default/env var)

    Returns:
        CliExecutor instance for the specified tool

    Raises:
        ValueError: If cli_tool is not recognized

    Examples:
        >>> executor = get_cli_executor()  # Uses EMDX_CLI_TOOL env var or "claude"
        >>> executor = get_cli_executor("cursor")
        >>> executor = get_cli_executor(CliTool.CLAUDE)
    """
    # Determine which CLI to use
    if cli_tool is None:
        # Check environment variable, default to Claude
        env_value = os.environ.get(ENV_CLI_TOOL, "claude").lower()
        cli_tool = env_value

    # Convert string to enum if needed
    if isinstance(cli_tool, str):
        try:
            cli_tool = CliTool(cli_tool.lower())
        except ValueError:
            valid = ", ".join(t.value for t in CliTool)
            raise ValueError(
                f"Unknown CLI tool: {cli_tool}. Valid options: {valid}"
            )

    # Get executor class and instantiate
    executor_class = _EXECUTORS.get(cli_tool)
    if executor_class is None:
        raise ValueError(f"No executor registered for CLI tool: {cli_tool}")

    return executor_class()


def get_available_cli_tools() -> list[str]:
    """Get list of available CLI tools.

    Returns:
        List of CLI tool names that have executors registered
    """
    return [tool.value for tool in _EXECUTORS.keys()]


def detect_available_cli() -> CliTool | None:
    """Detect which CLI tools are available on the system.

    Checks for installed CLIs in order of preference (Claude first).

    Returns:
        The first available CliTool, or None if none found
    """
    for tool in [CliTool.CLAUDE, CliTool.CURSOR]:
        executor = _EXECUTORS[tool]()
        if executor.get_binary_path() is not None:
            return tool
    return None
