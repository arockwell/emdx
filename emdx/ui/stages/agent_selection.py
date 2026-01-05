#!/usr/bin/env python3
"""
Agent selection stage for agent execution overlay.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, ListView, ListItem, Label
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from ...agents.registry import AgentRegistry
from .base import OverlayStage

logger = get_logger(__name__)

# Category emoji mapping
CATEGORY_EMOJI = {
    "research": "🔍",
    "generation": "✨",
    "analysis": "📊",
    "maintenance": "🔧"
}


def format_agent_display(agent: Dict[str, Any]) -> str:
    """Format agent for display in ListView."""
    # Get category emoji
    category = agent.get('category', 'research').lower()
    emoji = CATEGORY_EMOJI.get(category, "🤖")

    # Get usage stats
    usage_count = agent.get('usage_count', 0)
    success_count = agent.get('success_count', 0)

    # Calculate success rate
    success_rate = 0
    if usage_count > 0:
        success_rate = int((success_count / usage_count) * 100)

    # Format display name
    display_name = agent.get('display_name', agent.get('name', 'Unknown'))
    if len(display_name) > 40:
        display_name = display_name[:37] + "..."

    # Format category
    category_str = category.capitalize()[:10]

    # Build display string with stats
    stats_str = f"[{usage_count:3} runs, {success_rate:3}% success]"

    return f"{emoji} [{agent['id']:3}] {display_name:<40} {category_str:<12} {stats_str}"


class AgentSelectionStage(OverlayStage):
    """Agent selection stage with categorized agent list."""

    BINDINGS = [
        Binding("enter", "select_agent", "Select Agent"),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear Search"),
        Binding("1", "filter_research", "Research"),
        Binding("2", "filter_generation", "Generation"),
        Binding("3", "filter_analysis", "Analysis"),
        Binding("4", "filter_maintenance", "Maintenance"),
        Binding("0", "clear_filter", "All Categories"),
    ]

    DEFAULT_CSS = """
    AgentSelectionStage {
        height: 1fr;
        layout: vertical;
    }

    #agent-search-input {
        height: 3;
        margin: 0 0 1 0;
        border: solid $primary;
    }

    #agent-category-filter {
        height: 2;
        color: $text-muted;
        text-align: center;
    }

    #agent-list-view {
        height: 1fr;
        border: solid $primary;
    }

    #agent-help {
        height: 2;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }

    .agent-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 1 1;
    }
    """

    class AgentSelected(Message):
        """Message sent when an agent is selected."""
        def __init__(self, agent_id: int, agent_data: Dict[str, Any]) -> None:
            self.agent_id = agent_id
            self.agent_data = agent_data
            super().__init__()

    def __init__(self, host, **kwargs):
        super().__init__(host, "agent", **kwargs)
        self.agents: List[Dict[str, Any]] = []
        self.filtered_agents: List[Dict[str, Any]] = []
        self.selected_agent: Optional[Dict[str, Any]] = None
        self.search_query = ""
        self.category_filter: Optional[str] = None
        self.agent_registry = AgentRegistry()

    def compose(self) -> ComposeResult:
        """Create the agent selection UI."""
        yield Static("[bold yellow]🤖 Agent Selection[/bold yellow]", classes="agent-header")
        yield Static("All Categories | 1:Research 2:Generation 3:Analysis 4:Maintenance 0:All", id="agent-category-filter")
        yield Input(placeholder="Type to search agents... (Press / to focus)", id="agent-search-input")
        yield ListView(id="agent-list-view")
        yield Static("↑↓/jk: Navigate | Enter: Select | 1-4: Filter | Tab: Next Stage", id="agent-help")

    async def on_mount(self) -> None:
        """Load stage when mounted."""
        await super().on_mount()

    async def load_stage_data(self) -> None:
        """Load agents data."""
        try:
            logger.info("Loading agents from registry")
            self.agents = self.agent_registry.list_agents(include_inactive=False)
            self.filtered_agents = self.agents.copy()
            logger.info(f"Loaded {len(self.agents)} agents")

            # Ensure the UI is fully mounted before updating the list
            await asyncio.sleep(0.1)
            await self.update_agent_list()
        except Exception as e:
            logger.error(f"Failed to load agents: {e}")
            await self.show_error(f"Failed to load agents: {e}")

    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the search input so user can start typing."""
        try:
            # Focus the search input for immediate typing
            search_input = self.query_one("#agent-search-input", Input)
            search_input.focus()
        except Exception as e:
            logger.warning(f"Could not focus search input: {e}")

    def validate_selection(self) -> bool:
        """Check if an agent is selected."""
        return self.selected_agent is not None

    def get_selection_data(self) -> Dict[str, Any]:
        """Return selected agent data."""
        if self.selected_agent:
            return {
                "agent_id": self.selected_agent["id"],
                "agent_name": self.selected_agent.get("name", "unknown"),
                "agent_display_name": self.selected_agent.get("display_name", "Unknown Agent"),
                "agent_category": self.selected_agent.get("category", "research")
            }
        return {}

    async def update_agent_list(self) -> None:
        """Update the agent list display."""
        try:
            # Check if the ListView exists and is properly mounted
            list_view_query = self.query("#agent-list-view")
            if not list_view_query:
                logger.warning("ListView not found, waiting for UI to be ready")
                await asyncio.sleep(0.2)

            list_view = self.query_one("#agent-list-view", ListView)

            # Clear existing content
            list_view.clear()

            if not self.filtered_agents:
                if self.search_query or self.category_filter:
                    msg = f"No agents found"
                    if self.category_filter:
                        msg += f" in category '{self.category_filter}'"
                    if self.search_query:
                        msg += f" matching '{self.search_query}'"
                    list_view.append(ListItem(Static(msg)))
                else:
                    list_view.append(ListItem(Static("[yellow]No agents available. Press Ctrl+C to cancel and create agents first.[/yellow]")))
                return

            # Add agent items
            for agent in self.filtered_agents:
                display_text = format_agent_display(agent)
                list_view.append(ListItem(Static(display_text)))

        except Exception as e:
            logger.error(f"Failed to update agent list: {e}")
            try:
                await self.show_error(f"UI Error: {e}")
            except:
                logger.error(f"Could not show error in UI: {e}")

    async def update_category_filter_display(self) -> None:
        """Update the category filter display text."""
        try:
            filter_display = self.query_one("#agent-category-filter", Static)
            if self.category_filter:
                emoji = CATEGORY_EMOJI.get(self.category_filter, "🤖")
                cat_name = self.category_filter.capitalize()
                filter_display.update(f"{emoji} Showing: {cat_name} | 1:Research 2:Generation 3:Analysis 4:Maintenance 0:All")
            else:
                filter_display.update("All Categories | 1:Research 2:Generation 3:Analysis 4:Maintenance 0:All")
        except Exception as e:
            logger.error(f"Failed to update category filter display: {e}")

    async def show_error(self, message: str) -> None:
        """Show error message."""
        try:
            list_view = self.query_one("#agent-list-view", ListView)
            list_view.clear()
            list_view.append(ListItem(Static(f"[red]Error: {message}[/red]")))
        except Exception as e:
            logger.error(f"Could not show error in ListView: {e}")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in search input - select first filtered agent."""
        if event.input.id == "agent-search-input" and self.filtered_agents:
            # Get the currently highlighted item from ListView
            try:
                list_view = self.query_one("#agent-list-view", ListView)
                selected_index = list_view.index if list_view.index is not None else 0

                if 0 <= selected_index < len(self.filtered_agents):
                    agent = self.filtered_agents[selected_index]
                    self.selected_agent = agent

                    logger.info(f"Agent selected via search input Enter: {agent['id']}")

                    # Update host selection
                    self.host.set_agent_selection(agent["id"])

                    # Update selection data and mark as valid
                    self.update_selection(self.get_selection_data())
                    self._is_valid = True

                    # Post selection message
                    self.post_message(self.AgentSelected(agent["id"], agent))

                    # Request navigation to next stage
                    self.request_navigation("next")
            except Exception as e:
                logger.error(f"Error selecting agent from search: {e}")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle ListView selection (when user presses Enter on an item)."""
        if not self.filtered_agents:
            return

        # Get the selected index from the event
        selected_index = event.list_view.index

        if selected_index is not None and 0 <= selected_index < len(self.filtered_agents):
            agent = self.filtered_agents[selected_index]
            self.selected_agent = agent

            logger.info(f"Agent selected via ListView: {agent['id']} - {agent.get('display_name', agent.get('name', 'Unknown'))}")

            # Update host selection
            self.host.set_agent_selection(agent["id"])

            # Update selection data and mark as valid
            self.update_selection(self.get_selection_data())
            self._is_valid = True

            # Post selection message
            self.post_message(self.AgentSelected(agent["id"], agent))

            # Request navigation to next stage
            self.request_navigation("next")

    def action_select_agent(self) -> None:
        """Select the current agent (backup method for Enter key)."""
        logger.info("action_select_agent called")
        if not self.filtered_agents:
            logger.warning("No filtered agents available")
            return

        # Get currently highlighted item from ListView
        try:
            list_view = self.query_one("#agent-list-view", ListView)
            selected_index = list_view.index
            logger.info(f"ListView index: {selected_index}, filtered_agents count: {len(self.filtered_agents)}")

            if selected_index is not None and 0 <= selected_index < len(self.filtered_agents):
                agent = self.filtered_agents[selected_index]
                self.selected_agent = agent

                logger.info(f"Agent selected via action: {agent['id']} - {agent.get('display_name', agent.get('name', 'Unknown'))}")

                # Update host selection
                self.host.set_agent_selection(agent["id"])

                # Update selection data and mark as valid
                self.update_selection(self.get_selection_data())
                self._is_valid = True

                # Post selection message
                self.post_message(self.AgentSelected(agent["id"], agent))

                # Request navigation to next stage
                self.request_navigation("next")
            else:
                logger.warning(f"Invalid selection index: {selected_index}")
        except Exception as e:
            logger.error(f"Error in action_select_agent: {e}", exc_info=True)

    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        self.request_navigation("next")

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        self.request_navigation("prev")

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#agent-search-input", Input)
        search_input.focus()

    def action_clear_search(self) -> None:
        """Clear search and show all agents."""
        search_input = self.query_one("#agent-search-input", Input)
        search_input.value = ""
        self.search_query = ""
        self.apply_filters()

    def action_filter_research(self) -> None:
        """Filter to show only research agents."""
        self.category_filter = "research"
        self.apply_filters()

    def action_filter_generation(self) -> None:
        """Filter to show only generation agents."""
        self.category_filter = "generation"
        self.apply_filters()

    def action_filter_analysis(self) -> None:
        """Filter to show only analysis agents."""
        self.category_filter = "analysis"
        self.apply_filters()

    def action_filter_maintenance(self) -> None:
        """Filter to show only maintenance agents."""
        self.category_filter = "maintenance"
        self.apply_filters()

    def action_clear_filter(self) -> None:
        """Clear category filter and show all agents."""
        self.category_filter = None
        self.apply_filters()

    def apply_filters(self) -> None:
        """Apply current search and category filters."""
        # Start with all agents
        filtered = self.agents.copy()

        # Apply category filter
        if self.category_filter:
            filtered = [a for a in filtered if a.get('category', '').lower() == self.category_filter]

        # Apply search filter
        if self.search_query:
            query_lower = self.search_query.lower()
            filtered = [
                a for a in filtered
                if query_lower in a.get('name', '').lower()
                or query_lower in a.get('display_name', '').lower()
                or query_lower in a.get('description', '').lower()
            ]

        self.filtered_agents = filtered
        self.call_after_refresh(self.update_agent_list)
        self.call_after_refresh(self.update_category_filter_display)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "agent-search-input":
            self.search_query = event.value.strip()
            self.apply_filters()

    def get_help_text(self) -> str:
        """Get help text for this stage."""
        return "Select an agent to execute. Use ↑↓ or j/k to navigate, Enter to select, 1-4 to filter by category, / to search."
