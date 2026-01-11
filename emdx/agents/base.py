"""Base classes for EMDX agent system."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from emdx.config.constants import (
    DEFAULT_MAX_AGENT_ITERATIONS,
    DEFAULT_MAX_CONTEXT_DOCS,
    EXECUTION_TIMEOUT_SECONDS,
)


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    id: int
    name: str
    display_name: str
    description: str
    category: str
    system_prompt: str
    user_prompt_template: str
    allowed_tools: List[str]
    tool_restrictions: Optional[Dict[str, Any]] = None
    max_iterations: int = DEFAULT_MAX_AGENT_ITERATIONS
    timeout_seconds: int = EXECUTION_TIMEOUT_SECONDS
    requires_confirmation: bool = False
    max_context_docs: int = DEFAULT_MAX_CONTEXT_DOCS
    context_search_query: Optional[str] = None
    include_doc_content: bool = True
    output_format: str = 'markdown'
    save_outputs: bool = True
    output_tags: Optional[List[str]] = None
    version: int = 1
    is_active: bool = True
    is_builtin: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> 'AgentConfig':
        """Create AgentConfig from database row."""
        # Parse JSON fields
        allowed_tools = json.loads(row['allowed_tools']) if row['allowed_tools'] else []
        tool_restrictions = json.loads(row['tool_restrictions']) if row.get('tool_restrictions') else None
        output_tags = json.loads(row['output_tags']) if row.get('output_tags') else None
        
        return cls(
            id=row['id'],
            name=row['name'],
            display_name=row['display_name'],
            description=row['description'],
            category=row['category'],
            system_prompt=row['system_prompt'],
            user_prompt_template=row['user_prompt_template'],
            allowed_tools=allowed_tools,
            tool_restrictions=tool_restrictions,
            max_iterations=row.get('max_iterations', DEFAULT_MAX_AGENT_ITERATIONS),
            timeout_seconds=row.get('timeout_seconds', EXECUTION_TIMEOUT_SECONDS),
            requires_confirmation=bool(row.get('requires_confirmation', False)),
            max_context_docs=row.get('max_context_docs', DEFAULT_MAX_CONTEXT_DOCS),
            context_search_query=row.get('context_search_query'),
            include_doc_content=bool(row.get('include_doc_content', True)),
            output_format=row.get('output_format', 'markdown'),
            save_outputs=bool(row.get('save_outputs', True)),
            output_tags=output_tags,
            version=row.get('version', 1),
            is_active=bool(row.get('is_active', True)),
            is_builtin=bool(row.get('is_builtin', False)),
            created_at=row.get('created_at'),
            updated_at=row.get('updated_at'),
            created_by=row.get('created_by'),
            usage_count=row.get('usage_count', 0),
            last_used_at=row.get('last_used_at'),
            success_count=row.get('success_count', 0),
            failure_count=row.get('failure_count', 0)
        )


@dataclass
class AgentContext:
    """Runtime context for agent execution."""
    execution_id: int
    working_dir: str
    input_type: str  # 'document', 'query', 'pipeline'
    input_doc_id: Optional[int] = None
    input_query: Optional[str] = None
    context_docs: List[int] = field(default_factory=list)
    parent_execution_id: Optional[int] = None  # For pipeline executions
    variables: Dict[str, Any] = field(default_factory=dict)  # For template variables
    log_file: Optional[str] = None  # Path to log file for this execution


@dataclass
class AgentResult:
    """Result of agent execution."""
    status: str  # 'completed', 'failed', 'cancelled'
    output_doc_ids: List[int] = field(default_factory=list)
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    total_tokens_used: int = 0
    iterations_used: int = 0
    tools_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Agent(ABC):
    """Base class for all agents."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        
    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent with given context."""
        pass
        
    def validate_tools(self, requested_tools: List[str]) -> List[str]:
        """Validate and filter requested tools against allowed tools."""
        return [tool for tool in requested_tools if tool in self.config.allowed_tools]
        
    def format_prompt(self, **kwargs) -> str:
        """Format the user prompt template with provided variables."""
        prompt = self.config.user_prompt_template
        
        # Replace {{variable}} patterns with values
        for key, value in kwargs.items():
            pattern = f"{{{{{key}}}}}"
            prompt = prompt.replace(pattern, str(value))
            
        return prompt
    
    def apply_tool_restrictions(self, tools: List[str]) -> Dict[str, Any]:
        """Apply any tool-specific restrictions from config."""
        if not self.config.tool_restrictions:
            return {}
            
        restrictions = {}
        for tool in tools:
            if tool in self.config.tool_restrictions:
                restrictions[tool] = self.config.tool_restrictions[tool]
                
        return restrictions