#!/usr/bin/env python3
"""
Execution data manager - manages selection state for agent execution overlay.

Extracted from AgentExecutionOverlay to separate state management from UI logic.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

from ..utils.logging import get_logger

logger = get_logger(__name__)


class StageType(Enum):
    """Available overlay stages."""
    DOCUMENT = "document"
    AGENT = "agent"
    PROJECT = "project"
    WORKTREE = "worktree"
    CONFIG = "config"


@dataclass
class ExecutionData:
    """Data class holding all execution selection state."""

    # Primary IDs
    document_id: Optional[int] = None
    agent_id: Optional[int] = None
    project_index: Optional[int] = None
    project_path: Optional[str] = None
    worktree_index: Optional[int] = None

    # Additional data from stages
    project_worktrees: List[Any] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    document_data: Dict[str, Any] = field(default_factory=dict)
    agent_data: Dict[str, Any] = field(default_factory=dict)
    project_data: Dict[str, Any] = field(default_factory=dict)
    worktree_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
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


class ExecutionDataManager:
    """
    Manages selection state and stage completion for agent execution.

    This class encapsulates all data management logic previously in AgentExecutionOverlay,
    making the overlay class focused on UI orchestration.
    """

    def __init__(self, initial_document_id: Optional[int] = None):
        """
        Initialize the data manager.

        Args:
            initial_document_id: Optional pre-selected document ID
        """
        self.data = ExecutionData(document_id=initial_document_id)
        self.stages = [
            StageType.DOCUMENT,
            StageType.AGENT,
            StageType.PROJECT,
            StageType.WORKTREE,
            StageType.CONFIG
        ]
        self.stage_completed: Dict[StageType, bool] = {
            stage: False for stage in self.stages
        }

        # If we have an initial document, mark document stage as completed
        if initial_document_id:
            self.stage_completed[StageType.DOCUMENT] = True
            self._load_initial_document(initial_document_id)

    def _load_initial_document(self, document_id: int) -> None:
        """Load document data for pre-selected document."""
        try:
            from ..database.documents import get_document
            doc = get_document(str(document_id))
            if doc:
                self.data.document_data = {
                    'document_id': doc['id'],
                    'document_title': doc.get('title', 'Untitled'),
                    'document_project': doc.get('project', 'Default')
                }
                logger.info(f"Pre-selected document data: {self.data.document_data}")
            else:
                logger.warning(f"Could not fetch document {document_id}")
        except Exception as e:
            logger.error(f"Failed to fetch pre-selected document data: {e}", exc_info=True)

    def set_document_selection(self, document_id: int) -> None:
        """Set selected document ID."""
        self.data.document_id = document_id
        self.stage_completed[StageType.DOCUMENT] = True
        logger.info(f"Document selected: {document_id}")

    def set_agent_selection(self, agent_id: int) -> None:
        """Set selected agent ID."""
        self.data.agent_id = agent_id
        self.stage_completed[StageType.AGENT] = True
        logger.info(f"Agent selected: {agent_id}")

    def set_project_selection(
        self,
        project_index: int,
        project_path: str,
        worktrees: Optional[List[Any]] = None
    ) -> None:
        """Set selected project and its worktrees."""
        self.data.project_index = project_index
        self.data.project_path = project_path
        self.data.project_worktrees = worktrees or []
        self.stage_completed[StageType.PROJECT] = True
        logger.info(
            f"Project selected: index={project_index}, "
            f"path={project_path}, worktrees={len(worktrees or [])}"
        )

    def set_worktree_selection(self, worktree_index: int) -> None:
        """Set selected worktree index."""
        self.data.worktree_index = worktree_index
        self.stage_completed[StageType.WORKTREE] = True
        logger.info(f"Worktree selected: {worktree_index}")

    def set_execution_config(self, config: Dict[str, Any]) -> None:
        """Set execution configuration."""
        self.data.config.update(config)
        self.stage_completed[StageType.CONFIG] = True
        logger.info(f"Config updated: {config}")

    def update_stage_data(self, stage_name: str, selection_data: Dict[str, Any]) -> None:
        """Update selection data for a specific stage."""
        if stage_name == "document":
            self.data.document_data = selection_data
        elif stage_name == "agent":
            self.data.agent_data = selection_data
        elif stage_name == "project":
            self.data.project_data = selection_data
        elif stage_name == "worktree":
            self.data.worktree_data = selection_data
        elif stage_name == "config":
            self.data.config.update(selection_data)

    def mark_stage_completed(self, stage_name: str) -> None:
        """Mark a stage as completed by name."""
        stage_map = {
            "document": StageType.DOCUMENT,
            "agent": StageType.AGENT,
            "project": StageType.PROJECT,
            "worktree": StageType.WORKTREE,
            "config": StageType.CONFIG,
        }
        if stage_name in stage_map:
            self.stage_completed[stage_map[stage_name]] = True

    def can_execute(self) -> bool:
        """Check if minimum required selections are made for execution."""
        return (
            self.data.document_id is not None and
            self.data.agent_id is not None
        )

    def get_execution_data(self) -> Dict[str, Any]:
        """Get data needed to start execution."""
        return {
            "document_id": self.data.document_id,
            "agent_id": self.data.agent_id,
            "worktree_index": self.data.worktree_index,
            "config": self.data.config.copy()
        }

    def get_selection_summary(self, current_stage: StageType, stage_index: int) -> Dict[str, Any]:
        """Get summary of current selections - flatten all nested data."""
        summary = {}

        # Add base data (IDs and paths)
        summary.update({
            'document_id': self.data.document_id,
            'agent_id': self.data.agent_id,
            'project_index': self.data.project_index,
            'project_path': self.data.project_path,
            'worktree_index': self.data.worktree_index,
        })

        # Flatten nested data dicts
        for key, value in [
            ('document_data', self.data.document_data),
            ('agent_data', self.data.agent_data),
            ('project_data', self.data.project_data),
            ('worktree_data', self.data.worktree_data),
            ('config', self.data.config),
        ]:
            if value:
                logger.debug(f"Flattening {key}: {value}")
                summary.update(value)

        logger.debug(f"Final summary: {summary}")

        # Add metadata
        summary['current_stage'] = current_stage.value
        summary['stage_index'] = stage_index
        summary['completed_stages'] = [
            stage.value for stage, completed in self.stage_completed.items()
            if completed
        ]
        return summary

    # Property accessors for backward compatibility with host.data dict access
    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access for backward compatibility."""
        data_dict = self.data.to_dict()
        return data_dict.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-like assignment for backward compatibility."""
        if hasattr(self.data, key):
            setattr(self.data, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """Allow dict-like get for backward compatibility."""
        data_dict = self.data.to_dict()
        return data_dict.get(key, default)
