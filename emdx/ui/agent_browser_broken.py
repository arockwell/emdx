#!/usr/bin/env python3
"""
Agent browser for EMDX - view and manage AI agents.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, RichLog, Static, TextArea

from ..agents.executor import agent_executor
from ..database.connection import db_connection

# Import agent_registry after other imports to ensure database is ready
try:
    from ..agents.registry import agent_registry
except Exception as e:
    logger.error(f"Failed to import agent_registry: {e}", exc_info=True)
    agent_registry = None
# Temporarily disabled - mixing ModalScreen with overlays causes crashes
# from .agent_modals import (
#     RunAgentModal,
#     AgentHistoryModal,
#     EditAgentModal
# )

logger = logging.getLogger(__name__)
console = Console()


class AgentBrowser(Widget):
    """Browser for viewing and managing EMDX agents."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "select_agent", "Select"),
        Binding("r", "run_agent", "Run"),
        Binding("i", "agent_info", "Info"),
        Binding("e", "edit_agent", "Edit"),
        Binding("n", "new_agent", "New"),
        Binding("x", "execute_history", "History"),
        Binding("d", "delete_agent", "Delete"),
        Binding("q", "quit", "Back"),
        Binding("?", "help", "Help"),
    ]

    DEFAULT_CSS = """
    AgentBrowser {
        layout: vertical;
        height: 100%;
        padding: 0;
        margin: 0;
    }

    #agent-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
    }

    #agent-horizontal {
        height: 1fr;
    }

    #agent-sidebar {
        width: 2fr;
        min-width: 60;
        height: 100%;
    }

    #agent-table {
        height: 100%;
    }

    #agent-details {
        width: 1fr;
        min-width: 40;
        height: 100%;
        padding: 1;
    }

    .agent-details-log {
        height: 100%;
        border: solid $primary;
    }
    
    /* Overlay styles */
    .agent-overlay {
        /* layer: overlay; */  /* Temporarily disabled - might be causing crashes */
        position: absolute;
        background: $surface;
        border: thick $primary;
        padding: 2;
        top: 10%;
        left: 10%;
        width: 80%;
        height: auto;
        max-height: 80%;
        display: none;
        z-index: 1000;
    }
    
    .agent-overlay:not(.hidden) {
        display: block;
    }
    
    .agent-overlay Button {
        margin: 0 1;
    }
    
    .overlay-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    .overlay-content {
        padding: 1;
    }
    
    .button-row {
        margin-top: 2;
        align: center middle;
        height: 3;
    }
    """

    current_agent_id = reactive(None)
    agents_list = reactive([])
    current_overlay = reactive(None)

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        with Vertical():
            yield Static("EMDX Agent Browser - Press ? for help", id="agent-status")
            with Horizontal(id="agent-horizontal"):
                # Left side - agent list
                with ScrollableContainer(id="agent-sidebar"):
                    yield DataTable(id="agent-table", cursor_type="row")
                
                # Right side - agent details
                with ScrollableContainer(id="agent-details"):
                    yield RichLog(classes="agent-details-log")
            
            # Overlay containers temporarily disabled to debug crash
            # yield Container(id="run-agent-overlay", classes="agent-overlay hidden")
            # yield Container(id="create-agent-overlay", classes="agent-overlay hidden")
            # yield Container(id="edit-agent-overlay", classes="agent-overlay hidden")
            # yield Container(id="history-overlay", classes="agent-overlay hidden")
            # yield Container(id="delete-confirm-overlay", classes="agent-overlay hidden")

    def on_mount(self) -> None:
        """Set up the browser when mounted."""
        # Defer table setup to ensure widgets are mounted
        self.call_after_refresh(self._setup_table)
    
    def _setup_table(self) -> None:
        """Set up the table columns and initial data."""
        try:
            # Set up table columns
            table = self.query_one("#agent-table", DataTable)
            table.add_column("ID", key="id", width=6)
            table.add_column("Name", key="name", width=25)
            table.add_column("Category", key="category", width=12)
            table.add_column("Status", key="status", width=8)
            table.add_column("Usage", key="usage", width=8)
            table.add_column("Success", key="success", width=8)
            
            # Load initial data
            self.update_table()
            
            # Focus the table
            table.focus()
            
            self.update_status("Press 'r' to run an agent, 'i' for info, '?' for help")
        except Exception as e:
            logger.error(f"Error setting up table: {e}")
            self.update_status(f"Error: {e}")

    def update_table(self) -> None:
        """Update the agents table."""
        try:
            # Check if agent_registry is available
            if agent_registry is None:
                self.update_status("Agent system not initialized. Please restart.")
                return
                
            # Get all agents
            agents = agent_registry.list_agents(include_inactive=True)
            self.agents_list = agents
            
            # Update table - check if it exists first
            try:
                table = self.query_one("#agent-table", DataTable)
            except Exception:
                # Table not ready yet
                return
                
            table.clear()
            
            for agent in agents:
                # Format status
                status = "✓" if agent["is_active"] else "✗"
                if agent["is_builtin"]:
                    status += " 🏛️"
                
                # Calculate success rate
                usage = agent["usage_count"]
                success_rate = ""
                if usage > 0:
                    rate = (agent["success_count"] / usage) * 100
                    success_rate = f"{rate:.0f}%"
                
                table.add_row(
                    str(agent["id"]),
                    agent["display_name"],
                    agent["category"],
                    status,
                    str(usage),
                    success_rate
                )
            
            # Select first row if available
            if len(table.rows) > 0:
                table.cursor_coordinate = (0, 0)
                self.on_data_table_row_highlighted(None)
                
        except Exception as e:
            logger.error(f"Error updating agent table: {e}", exc_info=True)
            self.update_status(f"Error: {e}")
            # Try to show a helpful message if it's a database issue
            if "no such table: agents" in str(e):
                self.update_status("Database not initialized. Please restart the application.")

    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the table."""
        table = self.query_one("#agent-table", DataTable)
        if table.cursor_coordinate:
            row_index = table.cursor_coordinate[0]
            if 0 <= row_index < len(self.agents_list):
                agent = self.agents_list[row_index]
                self.current_agent_id = agent["id"]
                self.update_details(agent["id"])

    def update_details(self, agent_id: int) -> None:
        """Update the details panel for the selected agent."""
        try:
            if agent_registry is None:
                return
                
            agent = agent_registry.get_agent(agent_id)
            if not agent:
                return
            
            config = agent.config
            details = self.query_one(".agent-details-log", RichLog)
            details.clear()
            
            # Build rich console output
            output = Console(file=None, force_terminal=True)
            
            # Basic info
            output.print(f"[bold yellow]Agent: {config.display_name}[/bold yellow]")
            output.print(f"[dim]ID: {config.id} | Name: {config.name}[/dim]")
            output.print()
            
            output.print(f"[yellow]Category:[/yellow] {config.category}")
            output.print(f"[yellow]Description:[/yellow] {config.description}")
            output.print(f"[yellow]Status:[/yellow] {'Active' if config.is_active else 'Inactive'}")
            output.print(f"[yellow]Type:[/yellow] {'Built-in' if config.is_builtin else 'User-created'}")
            output.print()
            
            # Configuration
            output.print("[bold]Configuration:[/bold]")
            output.print(f"  [yellow]Allowed Tools:[/yellow] {', '.join(config.allowed_tools)}")
            output.print(f"  [yellow]Max Iterations:[/yellow] {config.max_iterations}")
            output.print(f"  [yellow]Timeout:[/yellow] {config.timeout_seconds}s")
            output.print(f"  [yellow]Max Context Docs:[/yellow] {config.max_context_docs}")
            output.print()
            
            # Usage statistics
            output.print("[bold]Usage Statistics:[/bold]")
            output.print(f"  [yellow]Total Runs:[/yellow] {config.usage_count}")
            output.print(f"  [yellow]Successful:[/yellow] {config.success_count}")
            output.print(f"  [yellow]Failed:[/yellow] {config.failure_count}")
            if config.usage_count > 0:
                success_rate = (config.success_count / config.usage_count) * 100
                output.print(f"  [yellow]Success Rate:[/yellow] {success_rate:.1f}%")
            if config.last_used_at:
                output.print(f"  [yellow]Last Used:[/yellow] {config.last_used_at}")
            output.print()
            
            # System prompt preview
            output.print("[bold]System Prompt:[/bold]")
            prompt_preview = config.system_prompt[:200] + "..." if len(config.system_prompt) > 200 else config.system_prompt
            output.print(f"[dim]{prompt_preview}[/dim]")
            
            # Write to details panel
            for line in output.file.getvalue().split('\n'):
                details.write(line)
                
        except Exception as e:
            logger.error(f"Error updating agent details: {e}")

    def update_status(self, text: str) -> None:
        """Update the status bar."""
        status = self.query_one("#agent-status", Static)
        status.update(text)

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#agent-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#agent-table", DataTable)
        table.action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (0, 0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (len(table.rows) - 1, 0)

    def action_select_agent(self) -> None:
        """Select current agent (same as info for now)."""
        self.action_agent_info()

    async def action_run_agent(self) -> None:
        """Run the selected agent."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
        
        # Get agent
        agent = agent_registry.get_agent(self.current_agent_id)
        if not agent:
            self.update_status("Agent not found")
            return
        
        # TODO: Convert RunAgentModal to overlay pattern
        self.update_status("Run agent not implemented yet (modal conversion in progress)")
        return
        
        if False:  # Disabled until overlay conversion
            # Execute the agent
            try:
                self.update_status(f"Executing {agent.config.display_name}...")
                
                execution_id = await agent_executor.execute_agent(
                    agent_id=result['agent_id'],
                    input_type=result.get('input_type', 'query'),
                    input_doc_id=result.get('doc_id'),
                    input_query=result.get('query'),
                    variables=result.get('variables', {}),
                    background=False
                )
                
                self.update_status(f"✅ Agent completed (execution #{execution_id})")
                
                # Refresh to update usage stats
                self.update_table()
                
            except Exception as e:
                self.update_status(f"❌ Error: {str(e)}")
                logger.error(f"Error running agent: {e}", exc_info=True)

    def action_agent_info(self) -> None:
        """Show detailed agent info."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
        
        # The details are already shown in the right panel
        self.update_status("Agent details shown in right panel")

    async def action_edit_agent(self) -> None:
        """Edit the selected agent."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
        
        agent = agent_registry.get_agent(self.current_agent_id)
        if not agent:
            self.update_status("Agent not found")
            return
        
        if agent.config.is_builtin:
            self.update_status("Cannot edit built-in agents")
            return
        
        # TODO: Convert EditAgentModal to overlay pattern
        self.update_status("Edit agent not implemented yet (modal conversion in progress)")
        return
        
        if False:  # Disabled until overlay conversion
            try:
                # Build update dict (only changed fields)
                updates = {}
                if config['display_name'] != agent.config.display_name:
                    updates['display_name'] = config['display_name']
                if config['description'] != agent.config.description:
                    updates['description'] = config['description']
                if config['category'] != agent.config.category:
                    updates['category'] = config['category']
                if config['system_prompt'] != agent.config.system_prompt:
                    updates['system_prompt'] = config['system_prompt']
                if config['user_prompt_template'] != agent.config.user_prompt_template:
                    updates['user_prompt_template'] = config['user_prompt_template']
                if config['allowed_tools'] != agent.config.allowed_tools:
                    updates['allowed_tools'] = config['allowed_tools']
                if config['max_context_docs'] != agent.config.max_context_docs:
                    updates['max_context_docs'] = config['max_context_docs']
                if config['timeout_seconds'] != agent.config.timeout_seconds:
                    updates['timeout_seconds'] = config['timeout_seconds']
                if config.get('output_tags') != agent.config.output_tags:
                    updates['output_tags'] = config.get('output_tags', [])
                    
                if updates:
                    # Update the agent
                    if agent_registry.update_agent(self.current_agent_id, updates):
                        self.update_status(f"✅ Updated agent '{agent.config.name}'")
                        # Refresh the table and details
                        self.update_table()
                        self.update_details(self.current_agent_id)
                    else:
                        self.update_status("❌ Failed to update agent")
                else:
                    self.update_status("No changes made")
                    
            except Exception as e:
                self.update_status(f"❌ Error updating agent: {str(e)}")
                logger.error(f"Error updating agent: {e}", exc_info=True)

    async def action_new_agent(self) -> None:
        """Create a new agent."""
        # Overlays temporarily disabled for debugging
        self.update_status("Create agent temporarily disabled (debugging crash)")
        return
        # await self.show_create_agent_overlay()

    async def action_execute_history(self) -> None:
        """Show execution history for the selected agent."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
        
        # TODO: Convert AgentHistoryModal to overlay pattern
        self.update_status("History view not implemented yet (modal conversion in progress)")

    # Overlay management methods
    async def show_overlay(self, overlay_id: str) -> None:
        """Show an overlay and hide others."""
        # Hide all overlays first
        for overlay in self.query(".agent-overlay"):
            overlay.add_class("hidden")
        
        # Show the requested overlay
        overlay = self.query_one(f"#{overlay_id}")
        overlay.remove_class("hidden")
        self.current_overlay = overlay_id
    
    async def hide_overlay(self, overlay_id: str) -> None:
        """Hide a specific overlay."""
        overlay = self.query_one(f"#{overlay_id}")
        overlay.add_class("hidden")
        
        # Clear any existing content
        await overlay.remove_children()
        
        if self.current_overlay == overlay_id:
            self.current_overlay = None
    
    async def hide_all_overlays(self) -> None:
        """Hide all overlays."""
        for overlay in self.query(".agent-overlay"):
            overlay.add_class("hidden")
            await overlay.remove_children()
        self.current_overlay = None
    
    async def show_delete_confirmation(self, agent) -> None:
        """Show delete confirmation overlay."""
        overlay = self.query_one("#delete-confirm-overlay")
        
        # Clear any existing content
        await overlay.remove_children()
        
        # Build the confirmation dialog
        with Vertical() as container:
            # Title
            title = Static("Delete Agent", classes="overlay-title")
            
            # Message
            message = Static(
                f"Are you sure you want to delete '{agent.config.display_name}'?\n"
                f"This agent has been used {agent.config.usage_count} times.",
                classes="overlay-content"
            )
            
            # Buttons
            button_row = Horizontal(classes="button-row")
            delete_btn = Button("Delete", variant="error", id="confirm-delete-btn")
            cancel_btn = Button("Cancel", variant="default", id="cancel-delete-btn")
            
        # Mount widgets
        await overlay.mount(container)
        await container.mount(title, message, button_row)
        await button_row.mount(delete_btn, cancel_btn)
        
        # Show the overlay
        await self.show_overlay("delete-confirm-overlay")
        
        # Focus the cancel button for safety
        cancel_btn.focus()
    
    async def show_create_agent_overlay(self) -> None:
        """Show create agent overlay with simplified form."""
        overlay = self.query_one("#create-agent-overlay")
        
        # Clear any existing content
        await overlay.remove_children()
        
        # Build the creation form
        main_container = Vertical()
        
        # Title
        title = Static("Create New Agent", classes="overlay-title")
        
        # Create scrollable form container
        form_container = ScrollableContainer()
        form_content = Vertical()
        
        # Basic info fields
        name_label = Label("Name (no spaces):")
        name_input = Input(placeholder="my-agent", id="create-name-input")
        
        display_label = Label("Display Name:")
        display_input = Input(placeholder="My Agent", id="create-display-input")
        
        desc_label = Label("Description:")
        desc_input = Input(placeholder="What this agent does...", id="create-desc-input")
        
        # Category selection
        cat_label = Label("Category:")
        cat_container = Horizontal()
        cat_research = Button("Research", id="cat-research", variant="primary")
        cat_generation = Button("Generation", id="cat-generation")
        cat_analysis = Button("Analysis", id="cat-analysis")
        cat_maintenance = Button("Maintenance", id="cat-maintenance")
        
        # Prompts
        system_label = Label("System Prompt:")
        system_input = TextArea(id="create-system-prompt", height=5)
        
        user_label = Label("User Prompt Template:")
        user_input = TextArea(
            "Analyze {{target}} and {{task}}. Variables can be used with {{name}} syntax.",
            id="create-user-prompt",
            height=5
        )
        
        # Tools
        tools_label = Label("Allowed Tools (comma-separated):")
        tools_input = Input(value="Read, Grep, Glob", id="create-tools-input")
        
        # Settings
        timeout_label = Label("Timeout (seconds):")
        timeout_input = Input(value="3600", id="create-timeout-input")
        
        # Buttons
        button_row = Horizontal(classes="button-row")
        create_btn = Button("Create", variant="primary", id="create-agent-btn")
        cancel_btn = Button("Cancel", variant="default", id="cancel-create-btn")
        
        # Mount all widgets
        await overlay.mount(main_container)
        await main_container.mount(title, form_container, button_row)
        await form_container.mount(form_content)
        
        # Mount form fields
        await form_content.mount(
            name_label, name_input,
            display_label, display_input,
            desc_label, desc_input,
            cat_label, cat_container,
            system_label, system_input,
            user_label, user_input,
            tools_label, tools_input,
            timeout_label, timeout_input
        )
        
        await cat_container.mount(cat_research, cat_generation, cat_analysis, cat_maintenance)
        await button_row.mount(create_btn, cancel_btn)
        
        # Store category state
        self.create_category = "research"
        
        # Show the overlay
        await self.show_overlay("create-agent-overlay")
        
        # Focus the first input
        name_input.focus()
    
    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        
        # If an overlay is open, escape closes it
        if key == "escape" and self.current_overlay:
            await self.hide_overlay(self.current_overlay)
            event.stop()
            event.prevent_default()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses from overlays."""
        button_id = event.button.id
        
        # Delete overlay buttons
        if button_id == "confirm-delete-btn":
            # Perform the deletion
            asyncio.create_task(self.perform_delete_agent())
        elif button_id == "cancel-delete-btn":
            # Hide the overlay
            asyncio.create_task(self.hide_overlay("delete-confirm-overlay"))
        
        # Create overlay buttons
        elif button_id == "create-agent-btn":
            asyncio.create_task(self.perform_create_agent())
        elif button_id == "cancel-create-btn":
            asyncio.create_task(self.hide_overlay("create-agent-overlay"))
        
        # Category buttons
        elif button_id.startswith("cat-"):
            self.handle_category_selection(button_id)
    
    def handle_category_selection(self, button_id: str) -> None:
        """Handle category button selection."""
        # Update button variants
        for cat in ["research", "generation", "analysis", "maintenance"]:
            btn = self.query_one(f"#cat-{cat}")
            btn.variant = "primary" if button_id == f"cat-{cat}" else "default"
        
        # Store selected category
        self.create_category = button_id.replace("cat-", "")
    
    async def perform_create_agent(self) -> None:
        """Create the agent with form data."""
        try:
            # Gather form data
            config = {
                "name": self.query_one("#create-name-input", Input).value.strip(),
                "display_name": self.query_one("#create-display-input", Input).value.strip(),
                "description": self.query_one("#create-desc-input", Input).value.strip(),
                "category": self.create_category,
                "system_prompt": self.query_one("#create-system-prompt", TextArea).text.strip(),
                "user_prompt_template": self.query_one("#create-user-prompt", TextArea).text.strip(),
                "allowed_tools": [t.strip() for t in self.query_one("#create-tools-input", Input).value.split(',')],
                "timeout_seconds": int(self.query_one("#create-timeout-input", Input).value or 3600),
                "created_by": "user"
            }
            
            # Validate required fields
            if not config['name']:
                self.update_status("❌ Agent name is required")
                return
            if ' ' in config['name']:
                self.update_status("❌ Agent name cannot contain spaces")
                return
            if not config['display_name']:
                self.update_status("❌ Display name is required")
                return
            if not config['description']:
                self.update_status("❌ Description is required")
                return
            if not config['system_prompt']:
                self.update_status("❌ System prompt is required")
                return
            if not config['user_prompt_template']:
                self.update_status("❌ User prompt template is required")
                return
            
            # Create the agent
            agent_id = agent_registry.create_agent(config)
            self.update_status(f"✅ Created agent '{config['name']}' (ID: {agent_id})")
            
            # Refresh the table
            self.update_table()
            
            # Select the new agent
            self.current_agent_id = agent_id
            
            # Hide the overlay
            await self.hide_overlay("create-agent-overlay")
            
        except Exception as e:
            self.update_status(f"❌ Error creating agent: {str(e)}")
            logger.error(f"Error creating agent: {e}", exc_info=True)
    
    async def perform_delete_agent(self) -> None:
        """Actually delete the agent after confirmation."""
        try:
            # Delete the agent (soft delete by default)
            if agent_registry.delete_agent(self.current_agent_id, hard_delete=False):
                agent = agent_registry.get_agent(self.current_agent_id)
                self.update_status(f"✅ Deactivated agent '{agent.config.name}'")
                # Clear current selection
                self.current_agent_id = None
                # Refresh the table
                self.update_table()
            else:
                self.update_status("❌ Failed to delete agent")
        except Exception as e:
            self.update_status(f"❌ Error deleting agent: {str(e)}")
            logger.error(f"Error deleting agent: {e}", exc_info=True)
        finally:
            # Hide the overlay
            await self.hide_overlay("delete-confirm-overlay")

    async def action_delete_agent(self) -> None:
        """Delete the selected agent."""
        # Overlays temporarily disabled for debugging
        self.update_status("Delete agent temporarily disabled (debugging crash)")
        return

    def action_quit(self) -> None:
        """Go back to document browser."""
        # The container will handle the actual switching
        pass

    def action_help(self) -> None:
        """Show help."""
        help_text = """
Agent Browser Help:
  j/k     - Navigate up/down
  g/G     - Go to top/bottom
  r       - Run selected agent
  i/Enter - Show agent info
  e       - Edit agent
  n       - Create new agent
  x       - Execution history
  d       - Delete agent
  q       - Back to documents
  ?       - This help
"""
        self.update_status("Help shown in details panel")
        details = self.query_one(".agent-details-log", RichLog)
        details.clear()
        details.write(help_text)

    def action_refresh(self) -> None:
        """Refresh the agent list."""
        self.update_table()
        self.update_status("Agent list refreshed")