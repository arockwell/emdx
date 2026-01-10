"""Service modules for EMDX."""

from .auto_tagger import AutoTagger
from .duplicate_detector import DuplicateDetector
from .claude_executor import (
    ExecutionType,
    execute_with_claude,
    execute_with_claude_detached,
    execute_document_smart,
    execute_document_smart_background,
)

__all__ = [
    'DuplicateDetector',
    'AutoTagger',
    'ExecutionType',
    'execute_with_claude',
    'execute_with_claude_detached',
    'execute_document_smart',
    'execute_document_smart_background',
]
