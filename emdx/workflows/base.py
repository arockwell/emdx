"""Base classes for EMDX workflow orchestration system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class ExecutionMode(Enum):
    """Execution modes for workflow stages."""
    SINGLE = "single"           # Run once
    PARALLEL = "parallel"       # Run N times simultaneously, synthesize
    ITERATIVE = "iterative"     # Run N times sequentially, building on previous
    ADVERSARIAL = "adversarial" # Advocate -> Critic -> Synthesizer
    DYNAMIC = "dynamic"         # Discover items at runtime, process each in parallel


@dataclass
class StageConfig:
    """Configuration for a single workflow stage."""
    name: str
    mode: ExecutionMode
    runs: int = 1
    agent_id: Optional[int] = None
    prompt: Optional[str] = None  # Custom prompt for this stage
    prompts: Optional[List[str]] = None  # For iterative/adversarial: per-run prompts
    iteration_strategy: Optional[str] = None  # Name of builtin strategy to use
    synthesis_prompt: Optional[str] = None  # For parallel/dynamic mode
    input: Optional[str] = None  # Template reference like "{{prev_stage.output}}"
    timeout_seconds: int = 3600
    # Dynamic mode fields
    discovery_command: Optional[str] = None  # Shell command that outputs items (one per line)
    item_variable: str = "item"  # Variable name for each discovered item in prompt
    max_concurrent: int = 5  # Max parallel executions for dynamic mode
    continue_on_failure: bool = True  # Continue processing other items if one fails

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StageConfig':
        """Create StageConfig from dictionary."""
        mode = ExecutionMode(data.get('mode', 'single'))
        return cls(
            name=data['name'],
            mode=mode,
            runs=data.get('runs', 1),
            agent_id=data.get('agent_id'),
            prompt=data.get('prompt'),
            prompts=data.get('prompts'),
            iteration_strategy=data.get('iteration_strategy'),
            synthesis_prompt=data.get('synthesis_prompt'),
            input=data.get('input'),
            timeout_seconds=data.get('timeout_seconds', 3600),
            discovery_command=data.get('discovery_command'),
            item_variable=data.get('item_variable', 'item'),
            max_concurrent=data.get('max_concurrent', 5),
            continue_on_failure=data.get('continue_on_failure', True),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'mode': self.mode.value,
            'runs': self.runs,
            'agent_id': self.agent_id,
            'prompt': self.prompt,
            'prompts': self.prompts,
            'iteration_strategy': self.iteration_strategy,
            'synthesis_prompt': self.synthesis_prompt,
            'input': self.input,
            'timeout_seconds': self.timeout_seconds,
            'discovery_command': self.discovery_command,
            'item_variable': self.item_variable,
            'max_concurrent': self.max_concurrent,
            'continue_on_failure': self.continue_on_failure,
        }


@dataclass
class WorkflowConfig:
    """Configuration for a workflow."""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    stages: List[StageConfig]
    variables: Dict[str, Any] = field(default_factory=dict)
    category: str = 'custom'
    is_builtin: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'WorkflowConfig':
        """Create WorkflowConfig from database row."""
        definition = json.loads(row['definition_json']) if row['definition_json'] else {}
        stages = [StageConfig.from_dict(s) for s in definition.get('stages', [])]
        variables = definition.get('variables', {})

        return cls(
            id=row['id'],
            name=row['name'],
            display_name=row['display_name'],
            description=row.get('description'),
            stages=stages,
            variables=variables,
            category=row.get('category', 'custom'),
            is_builtin=bool(row.get('is_builtin', False)),
            is_active=bool(row.get('is_active', True)),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
            created_by=row.get('created_by'),
            usage_count=row.get('usage_count', 0),
            last_used_at=row.get('last_used_at'),
            success_count=row.get('success_count', 0),
            failure_count=row.get('failure_count', 0),
        )

    def to_definition_json(self) -> str:
        """Convert stages and variables to JSON definition."""
        definition = {
            'stages': [s.to_dict() for s in self.stages],
            'variables': self.variables,
        }
        return json.dumps(definition)


@dataclass
class WorkflowRun:
    """Tracks execution of a workflow."""
    id: int
    workflow_id: int
    status: str  # pending, running, paused, completed, failed, cancelled
    current_stage: Optional[str] = None
    current_stage_run: int = 0
    input_doc_id: Optional[int] = None
    input_variables: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)  # Accumulated outputs
    gameplan_id: Optional[int] = None
    task_id: Optional[int] = None
    parent_run_id: Optional[int] = None
    output_doc_ids: List[int] = field(default_factory=list)
    error_message: Optional[str] = None
    total_tokens_used: int = 0
    total_execution_time_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'WorkflowRun':
        """Create WorkflowRun from database row."""
        input_vars = json.loads(row['input_variables']) if row.get('input_variables') else {}
        context = json.loads(row['context_json']) if row.get('context_json') else {}
        output_ids = json.loads(row['output_doc_ids']) if row.get('output_doc_ids') else []

        return cls(
            id=row['id'],
            workflow_id=row['workflow_id'],
            status=row['status'],
            current_stage=row.get('current_stage'),
            current_stage_run=row.get('current_stage_run', 0),
            input_doc_id=row.get('input_doc_id'),
            input_variables=input_vars,
            context=context,
            gameplan_id=row.get('gameplan_id'),
            task_id=row.get('task_id'),
            parent_run_id=row.get('parent_run_id'),
            output_doc_ids=output_ids,
            error_message=row.get('error_message'),
            total_tokens_used=row.get('total_tokens_used', 0),
            total_execution_time_ms=row.get('total_execution_time_ms', 0),
            started_at=row.get('started_at'),
            completed_at=row.get('completed_at'),
        )


@dataclass
class WorkflowStageRun:
    """Tracks execution of a single stage within a workflow run."""
    id: int
    workflow_run_id: int
    stage_name: str
    mode: str
    target_runs: int
    status: str  # pending, running, completed, failed, cancelled
    runs_completed: int = 0
    output_doc_id: Optional[int] = None
    synthesis_doc_id: Optional[int] = None
    error_message: Optional[str] = None
    tokens_used: int = 0
    execution_time_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'WorkflowStageRun':
        """Create WorkflowStageRun from database row."""
        return cls(
            id=row['id'],
            workflow_run_id=row['workflow_run_id'],
            stage_name=row['stage_name'],
            mode=row['mode'],
            target_runs=row['target_runs'],
            status=row['status'],
            runs_completed=row.get('runs_completed', 0),
            output_doc_id=row.get('output_doc_id'),
            synthesis_doc_id=row.get('synthesis_doc_id'),
            error_message=row.get('error_message'),
            tokens_used=row.get('tokens_used', 0),
            execution_time_ms=row.get('execution_time_ms', 0),
            started_at=row.get('started_at'),
            completed_at=row.get('completed_at'),
        )


@dataclass
class WorkflowIndividualRun:
    """Tracks a single run within a stage (one of N in parallel/iterative)."""
    id: int
    stage_run_id: int
    run_number: int
    status: str  # pending, running, completed, failed, cancelled
    agent_execution_id: Optional[int] = None
    prompt_used: Optional[str] = None
    input_context: Optional[str] = None
    output_doc_id: Optional[int] = None
    error_message: Optional[str] = None
    tokens_used: int = 0
    execution_time_ms: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'WorkflowIndividualRun':
        """Create WorkflowIndividualRun from database row."""
        return cls(
            id=row['id'],
            stage_run_id=row['stage_run_id'],
            run_number=row['run_number'],
            status=row['status'],
            agent_execution_id=row.get('agent_execution_id'),
            prompt_used=row.get('prompt_used'),
            input_context=row.get('input_context'),
            output_doc_id=row.get('output_doc_id'),
            error_message=row.get('error_message'),
            tokens_used=row.get('tokens_used', 0),
            execution_time_ms=row.get('execution_time_ms', 0),
            started_at=row.get('started_at'),
            completed_at=row.get('completed_at'),
        )


@dataclass
class IterationStrategy:
    """Predefined prompt sequences for iterative mode."""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    prompts: List[str]  # Prompts for each iteration
    recommended_runs: int = 5
    category: str = 'general'
    is_builtin: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'IterationStrategy':
        """Create IterationStrategy from database row."""
        prompts = json.loads(row['prompts_json']) if row['prompts_json'] else []

        return cls(
            id=row['id'],
            name=row['name'],
            display_name=row['display_name'],
            description=row.get('description'),
            prompts=prompts,
            recommended_runs=row.get('recommended_runs', 5),
            category=row.get('category', 'general'),
            is_builtin=bool(row.get('is_builtin', False)),
            created_at=row.get('created_at'),
        )

    def get_prompt_for_run(self, run_number: int) -> str:
        """Get the prompt for a specific run number (1-indexed)."""
        if not self.prompts:
            return ""
        # Clamp to available prompts (reuse last if more runs than prompts)
        index = min(run_number - 1, len(self.prompts) - 1)
        return self.prompts[index]
