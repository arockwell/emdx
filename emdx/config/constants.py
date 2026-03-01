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
# BACKUP CONFIGURATION
# =============================================================================

# =============================================================================
# LINKING DEFAULTS
# =============================================================================

# Whether to allow auto-linking across projects by default.
# When False (default), title-match and entity-match wikification
# only link documents within the same project.
DEFAULT_CROSS_PROJECT_LINKING = False

# =============================================================================
# BACKUP CONFIGURATION
# =============================================================================

EMDX_BACKUP_DIR = EMDX_CONFIG_DIR / "backups"
# Logarithmic retention tiers (days)
BACKUP_DAILY_DAYS = 7  # Keep all from last 7 days
BACKUP_WEEKLY_DAYS = 28  # Keep 1/week for weeks 2-4
BACKUP_MONTHLY_DAYS = 180  # Keep 1/month for months 2-6
BACKUP_YEARLY_DAYS = 730  # Keep 1/year for last 2 years
