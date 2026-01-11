#!/usr/bin/env python3
"""
Agent execution module - handles running agents from the browser.

Extracted from AgentBrowser to improve maintainability.
"""

import logging
from typing import Optional

from textual.widgets import Static

logger = logging.getLogger(__name__)


class AgentExecutionMixin:
    """Mixin class providing agent execution functionality.

    This mixin should be used with a Widget that has:
    - agents_list: list - List of agent dictionaries
    - current_agent_id: Optional[int] - Currently selected agent ID
    - update_status(text: str) - Method to update status bar
    - An "#agent-content" Static widget
    """

    def action_run_agent(self) -> None:
        """Run the currently selected agent.

        Since the TUI can't run agents interactively, this displays
        CLI instructions for running the agent.
        """
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return

        agent = self.find_agent_by_id(self.current_agent_id)
        if not agent:
            self.update_status("Agent not found")
            return

        self.update_status(
            f"Use CLI to run: emdx agent run {agent['name']} --query 'your query'"
        )
        self.show_run_instructions(agent)

    def find_agent_by_id(self, agent_id: int) -> Optional[dict]:
        """Find an agent in the list by its ID.

        Args:
            agent_id: The ID of the agent to find

        Returns:
            Agent dictionary or None if not found
        """
        return next(
            (a for a in self.agents_list if a["id"] == agent_id),
            None
        )

    def show_run_instructions(self, agent: dict) -> None:
        """Display CLI run instructions for an agent.

        Args:
            agent: The agent dictionary
        """
        content = self.query_one("#agent-content", Static)
        instructions = (
            f"To run agent '{agent['display_name']}':\n\n"
            f"CLI command:\n  emdx agent run {agent['name']} --query 'your task'\n\n"
            f"Or with document:\n  emdx agent run {agent['name']} --doc 123"
        )
        content.update(instructions)

    def can_execute_agent(self, agent: dict) -> tuple[bool, str]:
        """Check if an agent can be executed.

        Args:
            agent: The agent dictionary

        Returns:
            Tuple of (can_execute, reason_if_not)
        """
        if not agent.get("is_active", False):
            return False, "Agent is inactive"
        return True, ""

    def get_execution_command(self, agent: dict, query: Optional[str] = None,
                               doc_id: Optional[int] = None) -> str:
        """Generate the CLI command to execute an agent.

        Args:
            agent: The agent dictionary
            query: Optional query string
            doc_id: Optional document ID

        Returns:
            CLI command string
        """
        base_cmd = f"emdx agent run {agent['name']}"

        if doc_id:
            return f"{base_cmd} --doc {doc_id}"
        elif query:
            return f'{base_cmd} --query "{query}"'
        else:
            return f"{base_cmd} --query 'your task here'"
