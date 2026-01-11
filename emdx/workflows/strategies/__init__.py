"""Execution strategies for workflow stages."""

from .base import ExecutionStrategy, StageResult
from .single import SingleExecutionStrategy
from .parallel import ParallelExecutionStrategy
from .iterative import IterativeExecutionStrategy
from .adversarial import AdversarialExecutionStrategy
from .dynamic import DynamicExecutionStrategy
from .registry import strategy_registry, get_strategy

__all__ = [
    "ExecutionStrategy",
    "StageResult",
    "SingleExecutionStrategy",
    "ParallelExecutionStrategy",
    "IterativeExecutionStrategy",
    "AdversarialExecutionStrategy",
    "DynamicExecutionStrategy",
    "strategy_registry",
    "get_strategy",
]
