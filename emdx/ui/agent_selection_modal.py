#!/usr/bin/env python3
"""
Modal dialog for selecting an agent and related widgets.
"""

from typing import Optional, Dict, Any, List

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, ListView, ListItem
from textual.message import Message

from ..agents.registry import agent_registry
from ..utils.logging import get_logger
from ..utils.text_formatting import truncate_description

# Set up logging for debugging
logger = get_logger(__name__)
key_logger = get_logger("key_events")


class AgentListItem(ListItem):
    """List item for displaying an agent."""

    def __init__(self, agent_data: Dict[str, Any]) -> None:
        self.agent_data = agent_data
        # Create display label with emoji for category
        category_emoji = {
            "analysis": "📋",
            "generation": "📝",
            "maintenance": "🔧",
            "research": "🔍",
        }.get(agent_data.get("category", ""), "🛠️")

        label = f"{category_emoji} {agent_data['display_name']}"
        super().__init__(Static(label))


class AgentListWidget(ListView):
    """Categorized list of available agents."""

    class AgentSelected(Message):
        """Message sent when an agent is selected."""

        def __init__(self, agent_id: int, agent_data: Dict[str, Any]) -> None:
            self.agent_id = agent_id
            self.agent_data = agent_data
            super().__init__()

    def __init__(self) -> None:
        super().__init__()
        self.agents: List[Dict[str, Any]] = []

    def load_agents(self) -> None:
        """Load agents from registry."""
        try:
            self.agents = agent_registry.list_agents(include_inactive=False)
            logger.info(f"Loaded {len(self.agents)} agents")

            # Group by category and add to list
            categories = {}
            for agent in self.agents:
                category = agent.get("category", "other")
                if category not in categories:
                    categories[category] = []
                categories[category].append(agent)

            # Add agents grouped by category
            for category in sorted(categories.keys()):
                # Add category header
                category_emoji = {
                    "analysis": "📋",
                    "generation": "📝",
                    "maintenance": "🔧",
                    "research": "🔍",
                }.get(category, "🛠️")

                header_item = ListItem(
                    Static(f"\n{category_emoji} {category.upper()}", classes="category-header")
                )
                self.append(header_item)

                # Add agents in this category
                for agent in categories[category]:
                    agent_item = AgentListItem(agent)
                    self.append(agent_item)

        except Exception as e:
            logger.error(f"Failed to load agents: {e}")
            # Add error message
            error_item = ListItem(Static("❌ Failed to load agents"))
            self.append(error_item)

    def on_mount(self) -> None:
        """Load agents when widget is mounted."""
        self.load_agents()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle agent selection."""
        if isinstance(event.item, AgentListItem):
            agent_data = event.item.agent_data
            self.post_message(self.AgentSelected(agent_data["id"], agent_data))
            logger.info(f"Agent selected: {agent_data['display_name']}")


class AgentDetailPanel(Static):
    """Panel showing details of selected agent."""

    def __init__(self) -> None:
        super().__init__("Select an agent to view details...")
        self.agent_data: Optional[Dict[str, Any]] = None

    def update_agent(self, agent_data: Dict[str, Any]) -> None:
        """Update the detail panel with agent information."""
        self.agent_data = agent_data

        # Format tools list
        try:
            import json

            tools = json.loads(agent_data.get("allowed_tools", "[]"))
            tools_str = ", ".join(tools[:3])
            if len(tools) > 3:
                tools_str += f" +{len(tools) - 3} more"
        except Exception:
            tools_str = "Unknown"

        # Format usage stats
        usage_count = agent_data.get("usage_count", 0)
        success_count = agent_data.get("success_count", 0)
        success_rate = (success_count / usage_count * 100) if usage_count > 0 else 0

        # Build detail text
        detail_text = f"""[bold]{agent_data['display_name']}[/bold]

{agent_data.get('description', 'No description available')}

[yellow]Tools:[/yellow] {tools_str}
[yellow]Usage:[/yellow] {usage_count} times
[yellow]Success Rate:[/yellow] {success_rate:.1f}%

[dim]Press [bold]Enter[/bold] to run this agent[/dim]"""

        self.update(detail_text)


class AgentSelectionModal(ModalScreen):
    """Modal screen for selecting and configuring agent execution."""

    DEFAULT_CSS = """
    AgentSelectionModal {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: auto 1fr auto;
        grid-columns: 1fr 1fr;
        padding: 1 2;
        width: 80;
        height: 25;
        border: thick $background 80%;
        background: $surface;
    }

    #title {
        column-span: 2;
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #agent-list {
        border: solid $primary;
        height: 100%;
    }

    #agent-detail {
        border: solid $secondary;
        height: 100%;
        padding: 1;
    }

    .category-header {
        text-style: bold;
        background: $primary 20%;
    }

    #buttons {
        column-span: 2;
        layout: horizontal;
        align: center middle;
        height: 3;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "run_agent", "Run Agent"),
    ]

    def __init__(self, document_id: int, document_title: str):
        super().__init__()
        self.document_id = document_id
        self.document_title = document_title
        self.selected_agent_id: Optional[int] = None
        self.selected_agent_data: Optional[Dict[str, Any]] = None
        logger.info(
            f"AgentSelectionModal initialized for doc #{document_id}: {document_title}"
        )

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            # Title
            yield Label(
                f'Select Agent for: "{truncate_description(self.document_title)}"',
                id="title",
            )

            # Agent list
            yield AgentListWidget()

            # Agent details
            self.detail_panel = AgentDetailPanel()
            yield self.detail_panel

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Run Agent", variant="primary", id="run", disabled=True)

    def on_agent_list_widget_agent_selected(
        self, event: AgentListWidget.AgentSelected
    ) -> None:
        """Handle agent selection from list."""
        self.selected_agent_id = event.agent_id
        self.selected_agent_data = event.agent_data

        # Update detail panel
        self.detail_panel.update_agent(event.agent_data)

        # Enable run button
        run_button = self.query_one("#run", Button)
        run_button.disabled = False

        logger.info(
            f"Agent selected: {event.agent_data['display_name']} (ID: {event.agent_id})"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        logger.info(f"Button pressed: {event.button.id}")
        if event.button.id == "run":
            self.action_run_agent()
        else:
            self.action_cancel()

    def action_run_agent(self) -> None:
        """Run the selected agent."""
        if self.selected_agent_id and self.selected_agent_data:
            logger.info(
                f"Running agent {self.selected_agent_id} on document {self.document_id}"
            )
            # Return the selected agent info
            self.dismiss(
                {
                    "action": "run",
                    "agent_id": self.selected_agent_id,
                    "agent_data": self.selected_agent_data,
                    "document_id": self.document_id,
                }
            )
        else:
            logger.warning("No agent selected for execution")

    def action_cancel(self) -> None:
        """Cancel agent selection."""
        logger.info("Agent selection cancelled")
        self.dismiss({"action": "cancel"})

    def on_mount(self) -> None:
        """Ensure modal has focus when mounted."""
        logger.info(f"AgentSelectionModal mounted for doc #{self.document_id}")
        # Focus the agent list for keyboard navigation
        agent_list = self.query_one(AgentListWidget)
        agent_list.focus()

    def on_key(self, event) -> None:
        """Log key events for debugging."""
        key_logger.info(
            f"AgentSelectionModal.on_key: key={event.key}, character={event.character}"
        )
