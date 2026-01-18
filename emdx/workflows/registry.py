"""Workflow registry for managing workflow definitions."""

from typing import Dict, List, Optional

from .base import WorkflowConfig
from . import database as db


class WorkflowRegistry:
    """Registry for workflow definitions.

    Provides a high-level interface for managing workflows, with caching
    for frequently accessed workflows.
    """

    def __init__(self):
        self._cache: Dict[str, WorkflowConfig] = {}

    def get_workflow(self, name_or_id: str | int) -> Optional[WorkflowConfig]:
        """Get a workflow by name or ID.

        Args:
            name_or_id: Workflow name (string) or ID (int)

        Returns:
            WorkflowConfig if found, None otherwise
        """
        # Check cache first (by name)
        if isinstance(name_or_id, str) and name_or_id in self._cache:
            return self._cache[name_or_id]

        # Fetch from database
        if isinstance(name_or_id, int):
            row = db.get_workflow(name_or_id)
        else:
            row = db.get_workflow_by_name(name_or_id)

        if row:
            config = WorkflowConfig.from_db_row(row)
            self._cache[config.name] = config
            return config

        return None

    def list_workflows(
        self,
        category: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[WorkflowConfig]:
        """List all workflows with optional filtering.

        Args:
            category: Filter by category (analysis, planning, etc.)
            include_inactive: Include soft-deleted workflows

        Returns:
            List of WorkflowConfig objects
        """
        rows = db.list_workflows(category=category, include_inactive=include_inactive)
        return [WorkflowConfig.from_db_row(row) for row in rows]

    def create_workflow(
        self,
        name: str,
        display_name: str,
        stages: List[dict],
        variables: Optional[Dict] = None,
        description: Optional[str] = None,
        category: str = 'custom',
        created_by: Optional[str] = None,
    ) -> WorkflowConfig:
        """Create a new workflow.

        Args:
            name: Unique workflow name
            display_name: Human-readable display name
            stages: List of stage configurations
            variables: Default variables for the workflow
            description: Workflow description
            category: Workflow category
            created_by: Creator identifier

        Returns:
            Created WorkflowConfig
        """
        import json

        definition = {
            'stages': stages,
            'variables': variables or {},
        }

        workflow_id = db.create_workflow(
            name=name,
            display_name=display_name,
            definition_json=json.dumps(definition),
            description=description,
            category=category,
            created_by=created_by,
        )

        # Fetch and cache
        return self.get_workflow(workflow_id)

    def update_workflow(
        self,
        name_or_id: str | int,
        display_name: Optional[str] = None,
        stages: Optional[List[dict]] = None,
        variables: Optional[Dict] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[WorkflowConfig]:
        """Update an existing workflow.

        Args:
            name_or_id: Workflow name or ID
            display_name: New display name
            stages: New stage configurations
            variables: New variables
            description: New description
            category: New category

        Returns:
            Updated WorkflowConfig if successful, None otherwise
        """
        import json

        workflow = self.get_workflow(name_or_id)
        if not workflow:
            return None

        # Build new definition if stages or variables changed
        definition_json = None
        if stages is not None or variables is not None:
            new_stages = stages if stages is not None else [s.to_dict() for s in workflow.stages]
            new_variables = variables if variables is not None else workflow.variables
            definition = {'stages': new_stages, 'variables': new_variables}
            definition_json = json.dumps(definition)

        success = db.update_workflow(
            workflow_id=workflow.id,
            display_name=display_name,
            description=description,
            definition_json=definition_json,
            category=category,
        )

        if success:
            # Invalidate cache
            if workflow.name in self._cache:
                del self._cache[workflow.name]
            return self.get_workflow(workflow.id)

        return None

    def delete_workflow(self, name_or_id: str | int, hard_delete: bool = False) -> bool:
        """Delete a workflow.

        Args:
            name_or_id: Workflow name or ID
            hard_delete: If True, permanently delete; otherwise soft delete

        Returns:
            True if deleted, False otherwise
        """
        workflow = self.get_workflow(name_or_id)
        if not workflow:
            return False

        success = db.delete_workflow(workflow.id, hard_delete=hard_delete)

        if success and workflow.name in self._cache:
            del self._cache[workflow.name]

        return success

    def clear_cache(self) -> None:
        """Clear the workflow cache."""
        self._cache.clear()


# Global singleton instance
workflow_registry = WorkflowRegistry()
