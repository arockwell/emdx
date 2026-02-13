"""Service modules for EMDX."""

from .auto_tagger import AutoTagger
from .duplicate_detector import DuplicateDetector
from .claude_executor import (
    execute_claude_detached,
)
from .similarity import IndexStats, SimilarDocument, SimilarityService

__all__ = [
    'AutoTagger',
    'DuplicateDetector',
    'IndexStats',
    'SimilarDocument',
    'SimilarityService',
    'execute_claude_detached',
]
