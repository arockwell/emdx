#!/usr/bin/env python3
"""
Selection state management for agent execution overlay.

This module provides a dataclass for managing selection state during
multi-stage agent execution workflows.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class SelectionState:
    """
    Manages selection state for the agent execution overlay.

    This dataclass holds all selection data across stages:
    - Document selection
    - Agent selection
    - Project selection
    - Worktree selection
    - Execution configuration
    """

    # Primary selection IDs
    document_id: Optional[int] = None
    agent_id: Optional[int] = None
    project_index: Optional[int] = None
    project_path: Optional[str] = None
    worktree_index: Optional[int] = None

    # Pre-loaded data for stages
    project_worktrees: List[Any] = field(default_factory=list)

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Additional data from stages (metadata)
    document_data: Dict[str, Any] = field(default_factory=dict)
    agent_data: Dict[str, Any] = field(default_factory=dict)
    project_data: Dict[str, Any] = field(default_factory=dict)
    worktree_data: Dict[str, Any] = field(default_factory=dict)

    def set_document(self, document_id: int, data: Optional[Dict[str, Any]] = None) -> None:
        """Set document selection."""
        self.document_id = document_id
        if data:
            self.document_data = data

    def set_agent(self, agent_id: int, data: Optional[Dict[str, Any]] = None) -> None:
        """Set agent selection."""
        self.agent_id = agent_id
        if data:
            self.agent_data = data

    def set_project(
        self,
        project_index: int,
        project_path: str,
        worktrees: Optional[List[Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Set project selection with optional worktrees."""
        self.project_index = project_index
        self.project_path = project_path
        self.project_worktrees = worktrees or []
        if data:
            self.project_data = data

    def set_worktree(self, worktree_index: int, data: Optional[Dict[str, Any]] = None) -> None:
        """Set worktree selection."""
        self.worktree_index = worktree_index
        if data:
            self.worktree_data = data

    def update_config(self, config: Dict[str, Any]) -> None:
        """Update execution configuration."""
        self.config.update(config)

    def can_execute(self) -> bool:
        """Check if minimum required selections are made for execution."""
        return self.document_id is not None and self.agent_id is not None

    def to_execution_data(self) -> Dict[str, Any]:
        """Convert to execution data dictionary."""
        return {
            "document_id": self.document_id,
            "agent_id": self.agent_id,
            "worktree_index": self.worktree_index,
            "config": self.config.copy(),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for backward compatibility with self.data access)."""
        return {
            'document_id': self.document_id,
            'agent_id': self.agent_id,
            'project_index': self.project_index,
            'project_path': self.project_path,
            'project_worktrees': self.project_worktrees,
            'worktree_index': self.worktree_index,
            'config': self.config,
            'document_data': self.document_data,
            'agent_data': self.agent_data,
            'project_data': self.project_data,
            'worktree_data': self.worktree_data,
        }

    def get_summary(self, current_stage: str, stage_index: int, completed_stages: List[str]) -> Dict[str, Any]:
        """
        Get a flattened summary of all selections.

        Args:
            current_stage: Current stage name
            stage_index: Current stage index
            completed_stages: List of completed stage names

        Returns:
            Flattened dictionary with all selection data and metadata
        """
        summary = {
            'document_id': self.document_id,
            'agent_id': self.agent_id,
            'project_index': self.project_index,
            'project_path': self.project_path,
            'worktree_index': self.worktree_index,
        }

        # Flatten nested data dicts
        for data_dict in [self.document_data, self.agent_data, self.project_data,
                          self.worktree_data, self.config]:
            if data_dict:
                summary.update(data_dict)

        # Add metadata
        summary['current_stage'] = current_stage
        summary['stage_index'] = stage_index
        summary['completed_stages'] = completed_stages

        return summary
