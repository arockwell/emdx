"""
Centralized constants for EMDX.

This module contains all magic numbers and configuration values that were
previously scattered throughout the codebase. Organizing them here makes
it easier to understand, modify, and maintain the system's behavior.
"""

# =============================================================================
# DATABASE & QUERY LIMITS
# =============================================================================

# Default limits for list operations
DEFAULT_LIST_LIMIT = 10  # Standard search results, tag suggestions
DEFAULT_RECENT_LIMIT = 20  # Recent executions, recent tag results
DEFAULT_BROWSE_LIMIT = 50  # Document/task browser, workflow runs
DEFAULT_BATCH_LIMIT = 100  # Large batch operations, document loading

# =============================================================================
# TIMEOUT & STALE DETECTION (in seconds unless noted)
# =============================================================================

# Agent/workflow execution timeouts
EXECUTION_TIMEOUT_SECONDS = 3600  # 1 hour - max time for agent/workflow execution
STALE_EXECUTION_TIMEOUT_SECONDS = 1800  # 30 minutes - when to consider execution stale

# Process monitoring
MAX_PROCESS_RUNTIME_HOURS = 2  # Hours before a process is considered stuck
EXECUTION_STALE_TIMEOUT_MINUTES = 30  # Minutes before execution marked stale

# UI refresh intervals
DEFAULT_REFRESH_INTERVAL_SECONDS = 5  # UI auto-refresh interval

# =============================================================================
# CONCURRENCY & POOL SIZES
# =============================================================================

DEFAULT_MAX_CONCURRENT_WORKFLOWS = 5  # Workflow executor default
DEFAULT_MAX_CONCURRENT_STAGES = 5  # Stage config, worktree pool
DEFAULT_MAX_AGENT_ITERATIONS = 10  # Max iterations for agent loops

# =============================================================================
# CONTENT CONTEXT LIMITS
# =============================================================================

DEFAULT_MAX_CONTEXT_DOCS = 5  # Max documents to include in agent context
DEFAULT_MAX_TAGS_PER_DOC = 3  # Max tags to auto-assign per document
DEFAULT_MAX_SUGGESTIONS = 5  # Max suggestions for auto-tagging, recommendations

# =============================================================================
# FILE SIZE LIMITS
# =============================================================================

MAX_FILE_PREVIEW_SIZE_BYTES = 1024 * 1024  # 1MB - max file size for preview
MAX_PREVIEW_ITEMS = 20  # Max items to show in file preview

# =============================================================================
# SIMILARITY & CONFIDENCE THRESHOLDS
# =============================================================================

# Document similarity
DEFAULT_SIMILARITY_THRESHOLD = 0.7  # Document merger similarity threshold
NEAR_DUPLICATE_THRESHOLD = 0.85  # Near-duplicate detection threshold

# Tagging confidence levels
DEFAULT_TAGGING_CONFIDENCE = 0.75  # Default confidence for auto-tagging
MIN_TAGGING_CONFIDENCE = 0.7  # Minimum confidence for pattern matching
PATTERN_CONFIDENCE_REDUCTION = 0.75  # Reduced confidence for certain patterns

# Confidence level presets (for reference)
CONFIDENCE_LOW = 0.7
CONFIDENCE_MEDIUM = 0.75
CONFIDENCE_HIGH = 0.8
CONFIDENCE_VERY_HIGH = 0.85
CONFIDENCE_HIGHEST = 0.9

# =============================================================================
# HEALTH MONITORING THRESHOLDS
# =============================================================================

HEALTH_CRITICAL_THRESHOLD = 0.4  # Below this = critical status
HEALTH_WARNING_THRESHOLD = 0.7  # Below this = warning status

# Health metric weights (should sum to 1.0)
HEALTH_WEIGHT_PERFORMANCE = 0.25
HEALTH_WEIGHT_RELIABILITY = 0.20
HEALTH_WEIGHT_AVAILABILITY = 0.20
HEALTH_WEIGHT_QUALITY = 0.15
HEALTH_WEIGHT_FRESHNESS = 0.20

# Health score blend factors
HEALTH_PRIMARY_FACTOR = 0.7
HEALTH_SECONDARY_FACTOR = 0.3

# =============================================================================
# GARBAGE COLLECTION & CLEANUP (in days unless noted)
# =============================================================================

# Trash and cleanup policies
TRASH_CLEANUP_DAYS = 30  # Days before emptying trash
STALE_DOCUMENT_ARCHIVAL_DAYS = 180  # Days before considering document stale
STALE_DOCUMENT_MIN_VIEWS = 5  # Min views to avoid archival

# Branch and execution cleanup
BRANCH_CLEANUP_DAYS = 7  # Days before cleaning up old branches
EXECUTION_HISTORY_DAYS = 7  # Days of agent execution history to keep
CLEANUP_DIRECTORY_AGE_HOURS = 24  # Hours before cleaning temp directories

# =============================================================================
# TASK & PRIORITY DEFAULTS
# =============================================================================

DEFAULT_TASK_PRIORITY = 3  # Default priority for new tasks (1-5 scale)

# =============================================================================
# LIFECYCLE DURATION ESTIMATES (in days)
# =============================================================================

# Average duration estimates for lifecycle stages
LIFECYCLE_PLANNING_AVG_DAYS = 3
LIFECYCLE_PLANNING_MIN_DAYS = 1
LIFECYCLE_PLANNING_MAX_DAYS = 7

LIFECYCLE_ACTIVE_AVG_DAYS = 14
LIFECYCLE_ACTIVE_MIN_DAYS = 3
LIFECYCLE_ACTIVE_MAX_DAYS = 60

LIFECYCLE_BLOCKED_AVG_DAYS = 7
LIFECYCLE_BLOCKED_MIN_DAYS = 1
LIFECYCLE_BLOCKED_MAX_DAYS = 30

LIFECYCLE_COMPLETED_AVG_DAYS = 1
LIFECYCLE_COMPLETED_MIN_DAYS = 0
LIFECYCLE_COMPLETED_MAX_DAYS = 3

# =============================================================================
# TEXT FORMATTING & TRUNCATION
# =============================================================================

DEFAULT_TRUNCATE_LENGTH = 30  # Generic text truncation
PATH_TRUNCATE_LENGTH = 35  # Path truncation
DESCRIPTION_TRUNCATE_LENGTH = 40  # Description truncation
TITLE_TRUNCATE_LENGTH = 50  # Title truncation

# =============================================================================
# UI LAYOUT CONSTANTS
# =============================================================================

# Panel widths (as percentages or character counts)
UI_PANEL_WIDTH_PERCENT = "50%"
UI_GIT_BROWSER_WIDTH_PERCENT = "60%"
UI_SIDEBAR_MIN_WIDTH = 50
UI_LOG_CONTAINER_MIN_HEIGHT = 15
UI_SMALL_CONTAINER_MIN_HEIGHT = 8

# Common table column widths
TABLE_COL_ID_WIDTH = 5
TABLE_COL_NAME_WIDTH = 20
TABLE_COL_STATUS_WIDTH = 15
TABLE_COL_DATE_WIDTH = 10
TABLE_COL_DESCRIPTION_WIDTH = 50

# =============================================================================
# DATE GROUPING THRESHOLDS (in days)
# =============================================================================

DATE_GROUP_YESTERDAY = 1
DATE_GROUP_THIS_WEEK = 7
DATE_GROUP_THIS_MONTH = 30
DATE_GROUP_THIS_YEAR = 365

# Time threshold for "today" grouping (in seconds)
DATE_GROUP_TODAY_SECONDS = 3600  # Show as "today" if within 1 hour

# =============================================================================
# WORKFLOW DEFAULTS
# =============================================================================

DEFAULT_STAGE_RUNS = 1  # Default number of runs per stage
RECOMMENDED_WORKFLOW_RUNS = 5  # Recommended runs for workflow stats

# =============================================================================
# CLAUDE MODEL CONFIGURATION
# =============================================================================

DEFAULT_CLAUDE_MODEL = "claude-opus-4-5-20251101"

# =============================================================================
# CASCADE PROGRESS TRACKING
# =============================================================================

# Stuck detection threshold multiplier
# A document is considered stuck if time_at_stage > expected_time * multiplier
CASCADE_STUCK_THRESHOLD_MULTIPLIER = 2.0

# Rolling window for timing statistics (days)
CASCADE_TIMING_WINDOW_DAYS = 30

# Default stage timing thresholds (seconds) when no historical data available
CASCADE_DEFAULT_TIMINGS = {
    "idea→prompt": 30,
    "prompt→analyzed": 60,
    "analyzed→planned": 120,
    "planned→done": 300,
}

# Maximum time before a document is definitely considered stuck (seconds)
CASCADE_STAGE_MAX_TIMEOUTS = {
    "idea": 300,  # 5 minutes
    "prompt": 600,  # 10 minutes
    "analyzed": 1800,  # 30 minutes
    "planned": 3600,  # 1 hour
}
