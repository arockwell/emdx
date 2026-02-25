"""Delegate configuration for EMDX.

Manages user-configurable settings for the delegate command,
including default allowed tools for Claude CLI subprocesses.
"""

import json
import logging

from .constants import EMDX_CONFIG_DIR

logger = logging.getLogger(__name__)

DELEGATE_CONFIG_PATH = EMDX_CONFIG_DIR / "delegate.json"

# Base tools always granted to delegates (Bash subcommand patterns).
# These are the minimum set needed for Python dev workflows.
BASE_ALLOWED_TOOLS: list[str] = [
    "Bash(git:*)",
    "Bash(poetry:*)",
    "Bash(ruff:*)",
    "Bash(mypy:*)",
    "Bash(pytest:*)",
    "Bash(emdx:*)",
]


def load_delegate_config() -> dict[str, list[str]]:
    """Load delegate config from ~/.config/emdx/delegate.json.

    Returns a dict with at least an "allowed_tools" key (list of tool patterns).
    If no config file exists, returns an empty list (base tools are added separately).
    """
    if not DELEGATE_CONFIG_PATH.exists():
        return {"allowed_tools": []}

    try:
        with open(DELEGATE_CONFIG_PATH) as f:
            data = json.load(f)
        tools = data.get("allowed_tools", [])
        if not isinstance(tools, list):
            logger.warning("delegate config: allowed_tools must be a list, ignoring")
            return {"allowed_tools": []}
        return {"allowed_tools": [str(t) for t in tools]}
    except Exception as e:
        logger.warning("delegate config: failed to load %s: %s", DELEGATE_CONFIG_PATH, e)
        return {"allowed_tools": []}


def build_allowed_tools(
    pr: bool = False,
    branch: bool = False,
    extra_tools: list[str] | None = None,
) -> list[str]:
    """Build the full allowed tools list for a delegate subprocess.

    Combines:
    1. BASE_ALLOWED_TOOLS (always included)
    2. Bash(gh:*) if --pr or --branch
    3. User defaults from ~/.config/emdx/delegate.json
    4. Per-invocation --tool flags (extra_tools)

    Deduplicates while preserving order.
    """
    tools: list[str] = list(BASE_ALLOWED_TOOLS)

    if pr or branch:
        tools.append("Bash(gh:*)")

    # Add user defaults from config file
    config = load_delegate_config()
    for tool in config["allowed_tools"]:
        if tool not in tools:
            tools.append(tool)

    # Add per-invocation extras
    if extra_tools:
        for tool in extra_tools:
            if tool not in tools:
                tools.append(tool)

    return tools
