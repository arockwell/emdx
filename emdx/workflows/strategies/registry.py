"""Registry for execution strategies."""

from typing import Dict, Optional, Type

from .base import ExecutionStrategy
from .single import SingleExecutionStrategy
from .parallel import ParallelExecutionStrategy
from .iterative import IterativeExecutionStrategy
from .adversarial import AdversarialExecutionStrategy
from .dynamic import DynamicExecutionStrategy
from ..base import ExecutionMode


class StrategyRegistry:
    """Registry mapping execution modes to strategy classes."""

    def __init__(self):
        self._strategies: Dict[ExecutionMode, Type[ExecutionStrategy]] = {
            ExecutionMode.SINGLE: SingleExecutionStrategy,
            ExecutionMode.PARALLEL: ParallelExecutionStrategy,
            ExecutionMode.ITERATIVE: IterativeExecutionStrategy,
            ExecutionMode.ADVERSARIAL: AdversarialExecutionStrategy,
            ExecutionMode.DYNAMIC: DynamicExecutionStrategy,
        }
        self._instances: Dict[ExecutionMode, ExecutionStrategy] = {}

    def get_strategy(
        self,
        mode: ExecutionMode,
        max_concurrent: int = 10,
    ) -> ExecutionStrategy:
        """Get strategy instance for the given execution mode.

        Args:
            mode: Execution mode
            max_concurrent: Maximum concurrent runs (for parallel/dynamic modes)

        Returns:
            ExecutionStrategy instance
        """
        if mode not in self._strategies:
            raise ValueError(f"Unknown execution mode: {mode}")

        strategy_class = self._strategies[mode]

        # For parallel mode, create new instance with specific concurrency limit
        if mode == ExecutionMode.PARALLEL:
            return ParallelExecutionStrategy(max_concurrent=max_concurrent)

        # For other modes, reuse cached instance
        if mode not in self._instances:
            self._instances[mode] = strategy_class()

        return self._instances[mode]

    def register(self, mode: ExecutionMode, strategy_class: Type[ExecutionStrategy]) -> None:
        """Register a custom strategy for an execution mode.

        Args:
            mode: Execution mode
            strategy_class: Strategy class to use
        """
        self._strategies[mode] = strategy_class
        # Clear cached instance if exists
        if mode in self._instances:
            del self._instances[mode]


# Global registry instance
strategy_registry = StrategyRegistry()


def get_strategy(mode: ExecutionMode, max_concurrent: int = 10) -> ExecutionStrategy:
    """Get strategy instance for the given execution mode.

    Args:
        mode: Execution mode
        max_concurrent: Maximum concurrent runs (for parallel/dynamic modes)

    Returns:
        ExecutionStrategy instance
    """
    return strategy_registry.get_strategy(mode, max_concurrent)
