"""Service modules for EMDX."""

from .auto_tagger import AutoTagger
from .duplicate_detector import DuplicateDetector
from .execution_service import Execution, get_agent_executions, get_recent_executions
from .log_stream import LogStream, LogStreamSubscriber
from .similarity import IndexStats, SimilarDocument, SimilarityService
from .unified_executor import ExecutionConfig, ExecutionResult, UnifiedExecutor

__all__ = [
    "AutoTagger",
    "DuplicateDetector",
    "Execution",
    "ExecutionConfig",
    "ExecutionResult",
    "IndexStats",
    "LogStream",
    "LogStreamSubscriber",
    "SimilarDocument",
    "SimilarityService",
    "UnifiedExecutor",
    "get_agent_executions",
    "get_recent_executions",
]
