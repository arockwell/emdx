"""CLI tool configuration for EMDX execution system.

This module defines configurations for different CLI tools (Claude, Cursor)
that can be used to execute agent tasks.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from .models import CLAUDE_OPUS, CLAUDE_SONNET


# Default tools allowed for Claude CLI execution
# These are the standard tools that most agents need for basic operations
DEFAULT_ALLOWED_TOOLS: List[str] = [
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
    CURSOR = "cursor"


@dataclass
class CliConfig:
    """Configuration for a CLI tool."""

    # Command structure
    binary: List[str]  # e.g., ["claude"] or ["cursor", "agent"]
    prompt_flag: str  # e.g., "--print" or "-p"
    prompt_is_positional: bool  # True if prompt goes at end (Cursor)

    # Output format
    output_format_flag: str  # "--output-format"
    default_output_format: str  # "stream-json" or "text"
    requires_verbose_for_stream: bool  # Claude needs --verbose for stream-json

    # Model configuration
    model_flag: str  # "--model"
    default_model: str  # Default model for this CLI

    # Tool control
    supports_allowed_tools: bool  # Claude has --allowedTools
    allowed_tools_flag: Optional[str]  # "--allowedTools"
    force_flag: Optional[str]  # Cursor uses "--force"

    # Workspace
    workspace_flag: Optional[str]  # Cursor has "--workspace"

    # Environment
    config_path: Optional[str]  # Path to CLI config file
    api_key_env: Optional[str]  # Environment variable for API key


# CLI configurations
CLI_CONFIGS: Dict[CliTool, CliConfig] = {
    CliTool.CLAUDE: CliConfig(
        binary=["claude"],
        prompt_flag="--print",
        prompt_is_positional=False,
        output_format_flag="--output-format",
        default_output_format="stream-json",
        requires_verbose_for_stream=True,
        model_flag="--model",
        default_model=CLAUDE_OPUS,
        supports_allowed_tools=True,
        allowed_tools_flag="--allowedTools",
        force_flag=None,
        workspace_flag=None,
        config_path="~/.claude/claude_cli.json",
        api_key_env="ANTHROPIC_API_KEY",
    ),
    CliTool.CURSOR: CliConfig(
        binary=["cursor", "agent"],
        prompt_flag="-p",
        prompt_is_positional=True,
        output_format_flag="--output-format",
        default_output_format="stream-json",
        requires_verbose_for_stream=False,
        model_flag="--model",
        default_model="auto",
        supports_allowed_tools=False,
        allowed_tools_flag=None,
        force_flag="--force",
        workspace_flag="--workspace",
        config_path=None,
        api_key_env="CURSOR_API_KEY",
    ),
}

# Model aliases for cross-CLI compatibility
# Use these aliases for portable commands that work with either CLI
MODEL_ALIASES: Dict[str, Dict[str, str]] = {
    "opus": {
        "claude": CLAUDE_OPUS,
        "cursor": "opus-4.5",
    },
    "sonnet": {
        "claude": CLAUDE_SONNET,
        "cursor": "sonnet-4.5",
    },
    "auto": {
        "claude": CLAUDE_SONNET,
        "cursor": "auto",
    },
    "fast": {
        "claude": CLAUDE_SONNET,
        "cursor": "auto",
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


def get_cli_config(cli_tool: Optional[CliTool] = None) -> CliConfig:
    """Get configuration for a CLI tool.

    Args:
        cli_tool: The CLI tool to get config for. If None, uses default.

    Returns:
        CliConfig for the specified tool.
    """
    if cli_tool is None:
        cli_tool = get_default_cli_tool()
    return CLI_CONFIGS[cli_tool]


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


def get_available_models(cli_tool: CliTool) -> List[str]:
    """Get list of known models for a CLI tool.

    Returns:
        List of model names/aliases available for the CLI.
    """
    if cli_tool == CliTool.CLAUDE:
        return [
            CLAUDE_OPUS,
            CLAUDE_SONNET,
            "opus",
            "sonnet",
        ]
    elif cli_tool == CliTool.CURSOR:
        return [
            "auto",
            "opus-4.5",
            "opus-4.5-thinking",
            "sonnet-4.5",
            "sonnet-4.5-thinking",
            "gpt-5.2",
            "gemini-3-pro",
        ]
    return []
