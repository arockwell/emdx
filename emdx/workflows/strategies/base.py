"""Base class for execution strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import asyncio
import re

if TYPE_CHECKING:
    from ..base import StageConfig


@dataclass
class StageResult:
    """Result of executing a stage."""

    success: bool
    output_doc_id: Optional[int] = None
    synthesis_doc_id: Optional[int] = None
    individual_outputs: List[int] = field(default_factory=list)
    tokens_used: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None


class ExecutionStrategy(ABC):
    """Base class for stage execution strategies.

    Each strategy implements a different execution pattern:
    - single: Run agent once
    - parallel: Run agent N times simultaneously, synthesize results
    - iterative: Run agent N times sequentially, each building on previous
    - adversarial: Advocate -> Critic -> Synthesizer pattern
    - dynamic: Discover items at runtime, process each in parallel
    """

    def __init__(self, executor: "WorkflowExecutorProtocol"):
        """Initialize strategy with reference to the executor.

        Args:
            executor: The parent workflow executor providing shared services
        """
        self._executor = executor

    @abstractmethod
    async def execute(
        self,
        stage_run_id: int,
        stage: "StageConfig",
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute the stage using this strategy.

        Args:
            stage_run_id: Stage run ID for tracking
            stage: Stage configuration
            context: Execution context with variables
            stage_input: Resolved input for this stage

        Returns:
            StageResult with execution results
        """
        pass

    # Shared helper methods delegating to executor

    def _resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
        """Resolve {{variable}} templates in a string."""
        return self._executor.resolve_template(template, context)

    async def _run_agent(
        self,
        individual_run_id: int,
        agent_id: Optional[int],
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run an agent with the given prompt."""
        return await self._executor.run_agent(
            individual_run_id=individual_run_id,
            agent_id=agent_id,
            prompt=prompt,
            context=context,
        )

    async def _synthesize_outputs(
        self,
        stage_run_id: int,
        output_doc_ids: List[int],
        synthesis_prompt: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize multiple outputs into one."""
        return await self._executor.synthesize_outputs(
            stage_run_id=stage_run_id,
            output_doc_ids=output_doc_ids,
            synthesis_prompt=synthesis_prompt,
            context=context,
        )

    def _get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        return self._executor.get_document(doc_id)

    def _create_individual_run(
        self,
        stage_run_id: int,
        run_number: int,
        prompt_used: Optional[str] = None,
        input_context: Optional[str] = None,
    ) -> int:
        """Create an individual run record."""
        return self._executor.create_individual_run(
            stage_run_id=stage_run_id,
            run_number=run_number,
            prompt_used=prompt_used,
            input_context=input_context,
        )

    def _update_stage_run(self, stage_run_id: int, **kwargs) -> None:
        """Update stage run record."""
        self._executor.update_stage_run(stage_run_id, **kwargs)

    def _get_iteration_strategy(self, name: str):
        """Get an iteration strategy by name."""
        return self._executor.get_iteration_strategy(name)


class WorkflowExecutorProtocol:
    """Protocol defining the interface that strategies expect from the executor.

    This defines the methods that the WorkflowExecutor must provide for
    strategies to function correctly.
    """

    def resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
        """Resolve {{variable}} templates in a string."""
        raise NotImplementedError

    async def run_agent(
        self,
        individual_run_id: int,
        agent_id: Optional[int],
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run an agent with the given prompt."""
        raise NotImplementedError

    async def synthesize_outputs(
        self,
        stage_run_id: int,
        output_doc_ids: List[int],
        synthesis_prompt: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize multiple outputs into one."""
        raise NotImplementedError

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        raise NotImplementedError

    def create_individual_run(
        self,
        stage_run_id: int,
        run_number: int,
        prompt_used: Optional[str] = None,
        input_context: Optional[str] = None,
    ) -> int:
        """Create an individual run record."""
        raise NotImplementedError

    def update_stage_run(self, stage_run_id: int, **kwargs) -> None:
        """Update stage run record."""
        raise NotImplementedError

    def get_iteration_strategy(self, name: str):
        """Get an iteration strategy by name."""
        raise NotImplementedError
