"""Execution strategies for workflow stages.

This module provides the Strategy pattern implementation for different
execution modes in the workflow system.
"""

from .base import ExecutionStrategy, StageResult
from .single import SingleStrategy
from .parallel import ParallelStrategy
from .iterative import IterativeStrategy
from .adversarial import AdversarialStrategy
from .dynamic import DynamicStrategy
from .registry import StrategyRegistry, get_strategy

__all__ = [
    "ExecutionStrategy",
    "StageResult",
    "SingleStrategy",
    "ParallelStrategy",
    "IterativeStrategy",
    "AdversarialStrategy",
    "DynamicStrategy",
    "StrategyRegistry",
    "get_strategy",
]
