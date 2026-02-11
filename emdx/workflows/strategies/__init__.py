"""Execution mode strategies for workflow stages.

Each execution mode (single, parallel, iterative, adversarial, dynamic)
is implemented as a separate strategy class.
"""

from .base import ExecutionStrategy
from .single import SingleStrategy
from .parallel import ParallelStrategy
from .iterative import IterativeStrategy
from .adversarial import AdversarialStrategy
from .dynamic import DynamicStrategy
from ..base import ExecutionMode

_strategies = {
    ExecutionMode.SINGLE: SingleStrategy(),
    ExecutionMode.PARALLEL: ParallelStrategy(),
    ExecutionMode.ITERATIVE: IterativeStrategy(),
    ExecutionMode.ADVERSARIAL: AdversarialStrategy(),
    ExecutionMode.DYNAMIC: DynamicStrategy(),
}


def get_strategy(mode: ExecutionMode) -> ExecutionStrategy:
    """Get the strategy instance for an execution mode."""
    strategy = _strategies.get(mode)
    if not strategy:
        raise ValueError(f"Unknown execution mode: {mode}")
    return strategy
