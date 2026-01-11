"""Service modules for EMDX."""

from .auto_tagger import AutoTagger
from .duplicate_detector import DuplicateDetector
from .claude_executor import (
    execute_claude_detached,
)
from .document_executor import (
    ExecutionType,
    execute_document_background,
    generate_unique_execution_id,
)

__all__ = [
    'DuplicateDetector',
    'AutoTagger',
    'ExecutionType',
    'execute_claude_detached',
    'execute_document_background',
    'generate_unique_execution_id',
]
