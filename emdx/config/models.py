"""Centralized Claude model configuration for EMDX.

Single source of truth for all Claude model identifiers. When models are
updated, only this file needs to change.

Usage:
    from ..config.models import CLAUDE_OPUS, CLAUDE_SONNET, DEFAULT_MODEL
"""

# =============================================================================
# CLAUDE MODEL IDENTIFIERS
# =============================================================================

# Primary models - these are the canonical identifiers
CLAUDE_OPUS = "claude-opus-4-5-20251101"
CLAUDE_SONNET = "claude-sonnet-4-5-20250929"

# Default model for most operations
DEFAULT_MODEL = CLAUDE_OPUS

# Lighter model for cheaper operations (API Q&A, quick tasks)
FAST_MODEL = CLAUDE_SONNET

# =============================================================================
# MODEL ALIASES
# =============================================================================

# User-friendly aliases that map to canonical model IDs
MODEL_ALIASES = {
    "opus": CLAUDE_OPUS,
    "sonnet": CLAUDE_SONNET,
    "fast": CLAUDE_SONNET,
    "default": DEFAULT_MODEL,
}


def resolve_model(model_or_alias: str) -> str:
    """Resolve a model name or alias to the canonical model ID.

    Args:
        model_or_alias: Model ID or alias (e.g., "opus", "sonnet", "claude-opus-4-5-20251101")

    Returns:
        Canonical model ID string.
    """
    return MODEL_ALIASES.get(model_or_alias.lower(), model_or_alias)
