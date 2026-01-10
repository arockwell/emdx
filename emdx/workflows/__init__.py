"""
EMDX Workflow Orchestration System

Workflows allow composing multiple agent runs with different execution modes:
- single: Run once
- parallel: Run N times simultaneously, synthesize results
- iterative: Run N times sequentially, each building on previous
- adversarial: Advocate -> Critic -> Synthesizer pattern
"""

from .base import (
    WorkflowConfig,
    WorkflowRun,
    WorkflowStageRun,
    WorkflowIndividualRun,
    IterationStrategy,
    StageConfig,
    ExecutionMode,
)
from .registry import workflow_registry
from .executor import WorkflowExecutor, workflow_executor

__all__ = [
    # Data classes
    "WorkflowConfig",
    "WorkflowRun",
    "WorkflowStageRun",
    "WorkflowIndividualRun",
    "IterationStrategy",
    "StageConfig",
    "ExecutionMode",
    # Registry
    "workflow_registry",
    # Executor
    "WorkflowExecutor",
    "workflow_executor",
]
