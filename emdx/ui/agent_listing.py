#!/usr/bin/env python3
"""
Agent listing module - handles agent table display and navigation.

Extracted from AgentBrowser to improve maintainability.
"""

import logging
from typing import Optional

from textual.widgets import DataTable

logger = logging.getLogger(__name__)


class AgentListingMixin:
    """Mixin class providing agent listing and table navigation functionality.

    This mixin should be used with a Widget that has:
    - agents_list: list - List of agent dictionaries
    - current_agent_id: Optional[int] - Currently selected agent ID
    - An "#agent-table" DataTable widget
    """

    def update_table(self) -> None:
        """Refresh the agent table with current data from registry."""
        from ..agents.registry import agent_registry

        if not agent_registry:
            return

        try:
            agents = agent_registry.list_agents(include_inactive=True)
            self.agents_list = agents

            table = self.query_one("#agent-table", DataTable)
            table.clear()

            for agent in agents:
                table.add_row(
                    str(agent["id"]),
                    agent["display_name"],
                    "Active" if agent["is_active"] else "Inactive"
                )

            logger.info(f"Table updated with {len(agents)} agents")
        except Exception as e:
            logger.error(f"Failed to update table: {e}", exc_info=True)

    def load_agents_into_table(self, table: DataTable) -> None:
        """Load agents from registry into the provided table.

        Args:
            table: The DataTable widget to populate
        """
        from ..agents.registry import agent_registry

        if agent_registry:
            try:
                agents = agent_registry.list_agents(include_inactive=True)
                logger.info(f"Loaded {len(agents)} agents")
                self.agents_list = agents
                for agent in agents:
                    table.add_row(
                        str(agent["id"]),
                        agent["display_name"],
                        "Active" if agent["is_active"] else "Inactive"
                    )
                if agents:
                    table.cursor_coordinate = (0, 0)
                    self.on_data_table_row_highlighted(None)
                else:
                    self.show_welcome_screen()
            except Exception as e:
                logger.error(f"Failed to load agents: {e}", exc_info=True)
                table.add_row("1", "Error loading agents", str(e)[:20])
                self.show_welcome_screen()
        else:
            table.add_row("1", "Test Agent", "Active")
            table.add_row("2", "Another Agent", "Inactive")
            self.show_welcome_screen()

    def get_selected_agent(self) -> Optional[dict]:
        """Get the currently selected agent from the table.

        Returns:
            Agent dictionary or None if no agent is selected
        """
        table = self.query_one("#agent-table", DataTable)
        if table.cursor_coordinate and self.agents_list:
            row_index = table.cursor_coordinate[0]
            if 0 <= row_index < len(self.agents_list):
                return self.agents_list[row_index]
        return None

    def action_cursor_down(self) -> None:
        """Move cursor down in the agent table."""
        table = self.query_one("#agent-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the agent table."""
        table = self.query_one("#agent-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top of the agent table."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (0, 0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom of the agent table."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (len(table.rows) - 1, 0)

    def select_agent_by_id(self, agent_id: int) -> bool:
        """Select an agent in the table by its ID.

        Args:
            agent_id: The ID of the agent to select

        Returns:
            True if the agent was found and selected, False otherwise
        """
        table = self.query_one("#agent-table", DataTable)
        for i, agent in enumerate(self.agents_list):
            if agent["id"] == agent_id:
                table.cursor_coordinate = (i, 0)
                return True
        return False
