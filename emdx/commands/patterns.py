"""Pattern configurations for emdx run command.

Patterns are aliases for workflow configurations that enable quick access
to different workflow modes with sensible defaults.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class PatternConfig:
    """Configuration for a workflow pattern."""

    workflow_name: str
    description: str
    auto_worktree: bool = False
    auto_synthesize: bool = False


# Pattern aliases mapping pattern names to their configurations
PATTERN_ALIASES: Dict[str, PatternConfig] = {
    "parallel": PatternConfig(
        workflow_name="task_parallel",
        description="Run tasks in parallel (default)",
    ),
    "fix": PatternConfig(
        workflow_name="parallel_fix",
        description="Run fix tasks with worktree isolation",
        auto_worktree=True,
    ),
    "analyze": PatternConfig(
        workflow_name="parallel_analysis",
        description="Run analysis tasks with synthesis",
        auto_synthesize=True,
    ),
}


def get_pattern(name: str) -> Optional[PatternConfig]:
    """Get a pattern configuration by name.

    Args:
        name: Pattern name (case-insensitive)

    Returns:
        PatternConfig if found, None otherwise
    """
    return PATTERN_ALIASES.get(name.lower())


def list_patterns() -> Dict[str, PatternConfig]:
    """Get all available pattern configurations.

    Returns:
        Dictionary of pattern name to PatternConfig
    """
    return PATTERN_ALIASES.copy()
