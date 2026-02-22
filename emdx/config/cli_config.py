"""CLI tool configuration for EMDX execution system.

This module defines configurations for the Claude CLI tool
used to execute agent tasks.
"""

import os
from dataclasses import dataclass
from enum import Enum

# Default tools allowed for Claude CLI execution
# These are the standard tools that most agents need for basic operations
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "LS",
    "MultiEdit",
    "Read",
    "Task",
    "TodoRead",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
]


class CliTool(str, Enum):
    """Supported CLI tools."""

    CLAUDE = "claude"


@dataclass
class CliConfig:
    """Configuration for a CLI tool."""

    # Command structure
    binary: list[str]  # e.g., ["claude"]
    prompt_flag: str  # e.g., "--print"
    prompt_is_positional: bool  # True if prompt is a positional argument

    # Output format
    output_format_flag: str  # "--output-format"
    default_output_format: str  # "stream-json" or "text"
    requires_verbose_for_stream: bool  # Claude needs --verbose for stream-json

    # Model configuration
    model_flag: str  # "--model"
    default_model: str  # Default model for this CLI

    # Tool control
    supports_allowed_tools: bool  # Claude has --allowedTools
    allowed_tools_flag: str | None  # "--allowedTools"
    force_flag: str | None  # "--force" flag (unused for Claude)

    # Workspace
    workspace_flag: str | None  # "--workspace" flag (unused for Claude)

    # Environment
    config_path: str | None  # Path to CLI config file
    api_key_env: str | None  # Environment variable for API key


# CLI configurations
CLI_CONFIGS: dict[CliTool, CliConfig] = {
    CliTool.CLAUDE: CliConfig(
        binary=["claude"],
        prompt_flag="--print",
        prompt_is_positional=False,
        output_format_flag="--output-format",
        default_output_format="stream-json",
        requires_verbose_for_stream=True,
        model_flag="--model",
        default_model="claude-opus-4-6",
        supports_allowed_tools=True,
        allowed_tools_flag="--allowedTools",
        force_flag=None,
        workspace_flag=None,
        config_path="~/.claude/claude_cli.json",
        api_key_env="ANTHROPIC_API_KEY",
    ),
}

# Model aliases for convenience
MODEL_ALIASES: dict[str, dict[str, str]] = {
    "opus": {
        "claude": "claude-opus-4-6",
    },
    "sonnet": {
        "claude": "claude-sonnet-4-5-20250929",
    },
    "auto": {
        "claude": "claude-sonnet-4-5-20250929",
    },
    "fast": {
        "claude": "claude-sonnet-4-5-20250929",
    },
}


def get_default_cli_tool() -> CliTool:
    """Get the default CLI tool from environment or fallback to Claude.

    Checks EMDX_CLI_TOOL environment variable first.
    """
    env_value = os.environ.get("EMDX_CLI_TOOL", "claude").lower()
    try:
        return CliTool(env_value)
    except ValueError:
        return CliTool.CLAUDE


def resolve_model_alias(alias: str, cli_tool: CliTool) -> str:
    """Resolve a model alias to the actual model name for a CLI.

    Args:
        alias: Model alias (e.g., "opus", "sonnet", "auto")
        cli_tool: Target CLI tool

    Returns:
        Actual model name for the CLI, or the alias if not found.
    """
    if alias in MODEL_ALIASES:
        return MODEL_ALIASES[alias].get(cli_tool.value, alias)
    return alias


def get_model_display_name(model: str | None, cli_tool: CliTool | None = None) -> str:
    """Get a short display name for a model.

    Reverse-resolves full model names to short aliases (e.g. "claude-opus-4-6" → "opus").
    Falls back to the full model string if no alias matches.

    Args:
        model: Model name or alias (None uses default).
        cli_tool: CLI tool context (defaults to Claude).

    Returns:
        Short display name like "opus" or "sonnet".
    """
    if cli_tool is None:
        cli_tool = get_default_cli_tool()
    config = CLI_CONFIGS[cli_tool]

    if model is None:
        model = config.default_model

    # If it's already a known alias, return it
    if model in MODEL_ALIASES:
        return model

    # Reverse lookup: find alias whose resolved name matches
    for alias, cli_map in MODEL_ALIASES.items():
        if cli_map.get(cli_tool.value) == model:
            return alias

    return model


def resolve_model_version(model: str | None, cli_tool: CliTool | None = None) -> str:
    """Resolve a model spec to its full version ID.

    Handles aliases, full names, and None (default). Always returns the
    concrete model identifier (e.g. "claude-opus-4-6").

    Args:
        model: Model name, alias, or None (uses default).
        cli_tool: CLI tool context (defaults to Claude).
    """
    if cli_tool is None:
        cli_tool = get_default_cli_tool()
    config = CLI_CONFIGS[cli_tool]

    if model is None:
        model = config.default_model

    return resolve_model_alias(model, cli_tool) if model in MODEL_ALIASES else model
