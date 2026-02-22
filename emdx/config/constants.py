"""
Centralized constants for EMDX.

This module contains all magic numbers and configuration values that were
previously scattered throughout the codebase. Organizing them here makes
it easier to understand, modify, and maintain the system's behavior.
"""

from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

EMDX_CONFIG_DIR = Path.home() / ".config" / "emdx"
EMDX_LOG_DIR = EMDX_CONFIG_DIR / "logs"

# =============================================================================
# DATABASE & QUERY LIMITS
# =============================================================================

DEFAULT_RECENT_LIMIT = 20  # Recent executions, recent tag results
DEFAULT_BROWSE_LIMIT = 50  # Document/task browser

# =============================================================================
# CONTENT CONTEXT LIMITS
# =============================================================================

DEFAULT_MAX_TAGS_PER_DOC = 3  # Max tags to auto-assign per document
DEFAULT_MAX_SUGGESTIONS = 5  # Max suggestions for auto-tagging, recommendations

# =============================================================================
# SIMILARITY & CONFIDENCE THRESHOLDS
# =============================================================================

DEFAULT_TAGGING_CONFIDENCE = 0.75  # Default confidence for auto-tagging

# =============================================================================
# TASK & PRIORITY DEFAULTS
# =============================================================================

DEFAULT_TASK_PRIORITY = 3  # Default priority for new tasks (1-5 scale)

# =============================================================================
# SUBPROCESS & NETWORK TIMEOUTS (in seconds)
# =============================================================================

DELEGATE_EXECUTION_TIMEOUT = 1800  # 30 min - delegates need time for complex tasks
