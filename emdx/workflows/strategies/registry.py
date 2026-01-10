"""Strategy registry for mapping execution modes to strategies."""

from typing import TYPE_CHECKING

from ..base import ExecutionMode
from .base import ExecutionStrategy
from .single import SingleStrategy
from .parallel import ParallelStrategy
from .iterative import IterativeStrategy
from .adversarial import AdversarialStrategy
from .dynamic import DynamicStrategy

if TYPE_CHECKING:
    from .base import WorkflowExecutorProtocol


class StrategyRegistry:
    """Registry mapping execution modes to their strategy implementations."""

    _strategies = {
        ExecutionMode.SINGLE: SingleStrategy,
        ExecutionMode.PARALLEL: ParallelStrategy,
        ExecutionMode.ITERATIVE: IterativeStrategy,
        ExecutionMode.ADVERSARIAL: AdversarialStrategy,
        ExecutionMode.DYNAMIC: DynamicStrategy,
    }

    @classmethod
    def get_strategy(
        cls, mode: ExecutionMode, executor: "WorkflowExecutorProtocol"
    ) -> ExecutionStrategy:
        """Get the strategy instance for the given execution mode.

        Args:
            mode: The execution mode
            executor: The parent workflow executor

        Returns:
            An ExecutionStrategy instance

        Raises:
            ValueError: If the mode is not supported
        """
        strategy_class = cls._strategies.get(mode)
        if not strategy_class:
            raise ValueError(f"Unknown execution mode: {mode}")
        return strategy_class(executor)

    @classmethod
    def register(
        cls, mode: ExecutionMode, strategy_class: type[ExecutionStrategy]
    ) -> None:
        """Register a new strategy for an execution mode.

        Args:
            mode: The execution mode
            strategy_class: The strategy class to register
        """
        cls._strategies[mode] = strategy_class


def get_strategy(
    mode: ExecutionMode, executor: "WorkflowExecutorProtocol"
) -> ExecutionStrategy:
    """Convenience function to get a strategy for the given mode.

    Args:
        mode: The execution mode
        executor: The parent workflow executor

    Returns:
        An ExecutionStrategy instance
    """
    return StrategyRegistry.get_strategy(mode, executor)
