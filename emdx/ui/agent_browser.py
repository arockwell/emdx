#!/usr/bin/env python3
"""
Minimal agent browser - copied from log browser structure to debug crash.
"""

import logging
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, RichLog, Static, TextArea
from rich.console import Console
from rich.text import Text

logger = logging.getLogger(__name__)

# Test adding agent imports one by one
try:
    from ..agents.registry import agent_registry
    logger.info("Successfully imported agent_registry")
    
    # Quick test to see if the database is ready
    try:
        test_agents = agent_registry.list_agents()
        logger.info(f"Database check: Found {len(test_agents)} agents")
    except Exception as e:
        logger.warning(f"Database may not be initialized: {e}")
        # Try to trigger migrations
        from ..database.connection import db_connection
        from ..database.migrations import run_migrations
        logger.info("Running database migrations...")
        with db_connection.get_connection() as conn:
            run_migrations()
        logger.info("Migrations complete")
        
except Exception as e:
    logger.error(f"Failed to import agent_registry: {e}", exc_info=True)
    agent_registry = None


class AgentBrowser(Widget):
    """Minimal agent browser for testing."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("r", "run_agent", "Run"),
        Binding("a", "new_agent", "Add Agent"),
        Binding("n", "new_agent", "New"),
        Binding("e", "edit_agent", "Edit"),
        Binding("d", "delete_agent", "Delete"),
    ]
    
    # Add some state tracking
    def __init__(self):
        super().__init__()
        self.agents_list = []
        self.current_agent_id = None
        self.create_mode = False
        self.create_form_visible = False
        self.input_mode = None  # Track what we're inputting
        self.input_buffer = ""  # Current input
        self.form_data = {}  # Collected form data
        self.form_fields = [
            ("name", "Agent name (no spaces)", "my-agent"),
            ("display_name", "Display name", "My Agent"), 
            ("description", "Description", "What this agent does"),
            ("category", "Category (research/generation/analysis/maintenance)", "research"),
            ("system_prompt", "System prompt", "You are a helpful assistant."),
            ("user_prompt_template", "User prompt template", "Help with: {{task}}"),
        ]
        self.current_field_index = 0
        
        # Form mode state (following document browser pattern)
        self.form_mode = False
        self.editing_agent_id = None

    DEFAULT_CSS = """
    AgentBrowser {
        layout: vertical;
        height: 100%;
    }
    
    .agent-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
    }
    
    .agent-content {
        height: 1fr;
    }
    
    #agent-sidebar {
        width: 50%;
        height: 100%;
    }
    
    #agent-table {
        height: 66%;
    }
    
    #agent-details {
        height: 34%;
        border: solid $primary;
        padding: 1;
    }
    
    #agent-preview-container {
        width: 50%;
        height: 100%;
    }
    
    #agent-preview {
        height: 100%;
        padding: 1;
    }
    
    #agent-content {
        height: 100%;
        border: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        """Create minimal UI layout."""
        # Status bar
        yield Static("Agent Browser - Minimal Test", classes="agent-status")
        
        # Main content
        with Horizontal(classes="agent-content"):
            # Left sidebar
            with Vertical(id="agent-sidebar"):
                yield DataTable(id="agent-table", cursor_type="row")
                yield Static("", id="agent-details", markup=True)
            
            # Right preview
            with Vertical(id="agent-preview-container"):
                with ScrollableContainer(id="agent-preview"):
                    yield Static("", id="agent-content", markup=True)
        

    def on_mount(self) -> None:
        """Set up when mounted."""
        self.update_status("Agent browser mounted - minimal version")
        
        # Set up table
        table = self.query_one("#agent-table", DataTable)
        table.add_column("ID", width=8)
        table.add_column("Name", width=30)
        table.add_column("Status", width=10)
        
        # Try to load real agents
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
                # Select first row if available
                if agents:
                    table.cursor_coordinate = (0, 0)
                    self.on_data_table_row_highlighted(None)
                else:
                    # No agents available, show welcome screen
                    self.show_welcome_screen()
            except Exception as e:
                logger.error(f"Failed to load agents: {e}", exc_info=True)
                # Fall back to test data
                table.add_row("1", "Error loading agents", str(e)[:20])
                self.show_welcome_screen()
        else:
            # Add test data
            table.add_row("1", "Test Agent", "Active")
            table.add_row("2", "Another Agent", "Inactive")
            self.show_welcome_screen()
        
        # Focus the table
        table.focus()
        
        # Initialize content areas properly - no clearing since they should be empty
        # The key is to prevent logs from appearing in the first place

    def update_status(self, text: str) -> None:
        """Update status bar."""
        logger.info(f"Agent status: {text}")
        status = self.query_one(".agent-status", Static)
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
        """Move to top."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (0, 0)

    def action_cursor_bottom(self) -> None:
        """Move to bottom."""
        table = self.query_one("#agent-table", DataTable)
        if len(table.rows) > 0:
            table.cursor_coordinate = (len(table.rows) - 1, 0)
    
    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the table."""
        table = self.query_one("#agent-table", DataTable)
        if table.cursor_coordinate and self.agents_list:
            row_index = table.cursor_coordinate[0]
            if 0 <= row_index < len(self.agents_list):
                agent = self.agents_list[row_index]
                self.current_agent_id = agent["id"]
                self.update_details(agent)
            else:
                # Invalid row, show welcome screen
                self.current_agent_id = None
                self.show_welcome_screen()
        else:
            # No selection or no agents, show welcome screen
            self.current_agent_id = None
            self.show_welcome_screen()
    
    def update_details(self, agent_info: dict) -> None:
        """Update the details panel."""
        details = self.query_one("#agent-details", Static)
        
        # Build the content as a single string
        content_lines = [
            f"[bold yellow]Agent: {agent_info['display_name']}[/bold yellow]",
            f"ID: {agent_info['id']}",
            f"Category: {agent_info['category']}",
            f"Active: {agent_info['is_active']}",
            f"Usage: {agent_info['usage_count']} times"
        ]
        
        if agent_info['description']:
            content_lines.append(f"\n[dim]{agent_info['description']}[/dim]")
        
        details.update("\n".join(content_lines))
        
        # Also update the main content area
        self.update_agent_content(agent_info)
    
    def update_agent_content(self, agent_info: dict) -> None:
        """Update the main RHS content area with full agent details."""
        content = self.query_one("#agent-content", Static)
        
        # Get full agent configuration if available
        full_agent = None
        if agent_registry and agent_info['id']:
            try:
                full_agent = agent_registry.get_agent(agent_info['id'])
            except Exception as e:
                logger.error(f"Failed to load full agent: {e}")
        
        # Build the content string
        lines = []
        
        # Header
        lines.append(f"[bold cyan]🤖 {agent_info['display_name']}[/bold cyan]")
        lines.append("=" * 60)
        lines.append("")
        
        # Basic info
        lines.append(f"[bold]Name:[/bold] {agent_info.get('name', 'N/A')}")
        lines.append(f"[bold]Category:[/bold] {agent_info['category']}")
        lines.append(f"[bold]Status:[/bold] {'Active' if agent_info['is_active'] else 'Inactive'}")
        lines.append(f"[bold]Usage:[/bold] {agent_info['usage_count']} executions")
        lines.append("")
        
        # Description
        if agent_info.get('description'):
            lines.append(f"[bold]Description:[/bold]")
            lines.append(f"[dim]{agent_info['description']}[/dim]")
            lines.append("")
        
        # Full configuration if available
        if full_agent and hasattr(full_agent, 'config'):
            config = full_agent.config
            
            # System prompt
            lines.append(f"[bold]System Prompt:[/bold]")
            lines.append("[green]" + "─" * 50 + "[/green]")
            system_prompt = getattr(config, 'system_prompt', 'N/A')
            if len(system_prompt) > 200:
                lines.append(f"{system_prompt[:200]}...")
                lines.append(f"[dim](truncated - {len(system_prompt)} chars total)[/dim]")
            else:
                lines.append(system_prompt)
            lines.append("")
            
            # User prompt template
            lines.append(f"[bold]User Prompt Template:[/bold]")
            lines.append("[blue]" + "─" * 50 + "[/blue]")
            user_prompt = getattr(config, 'user_prompt_template', 'N/A')
            lines.append(user_prompt)
            lines.append("")
            
            # Tools and settings
            lines.append(f"[bold]Configuration:[/bold]")
            lines.append(f"• [bold]Allowed Tools:[/bold] {', '.join(getattr(config, 'allowed_tools', []))}")
            lines.append(f"• [bold]Timeout:[/bold] {getattr(config, 'timeout_seconds', 3600)} seconds")
            lines.append(f"• [bold]Created By:[/bold] {getattr(config, 'created_by', 'Unknown')}")
            
            if hasattr(config, 'created_at'):
                lines.append(f"• [bold]Created:[/bold] {config.created_at}")
        else:
            lines.append("[dim]Full configuration not available[/dim]")
        
        lines.append("")
        lines.append("─" * 60)
        lines.append("[dim]Press 'e' to edit • 'd' to delete • 'r' to run[/dim]")
        
        # Update the content
        content.update("\n".join(lines))
    
    def show_welcome_screen(self) -> None:
        """Show welcome screen when no agent is selected."""
        logger.info("Showing welcome screen")
        content = self.query_one("#agent-content", Static)
        
        # Build the welcome content
        lines = []
        
        # Header
        lines.append("[bold cyan]🤖 EMDX Agent System[/bold cyan]")
        lines.append("=" * 60)
        lines.append("")
        
        # Overview
        lines.append("[bold]Welcome to the Agent Management Interface[/bold]")
        lines.append("")
        lines.append("Agents are specialized AI assistants that can help with:")
        lines.append("• [green]Research[/green] - Information gathering and analysis")
        lines.append("• [blue]Generation[/blue] - Creating content and code")
        lines.append("• [yellow]Analysis[/yellow] - Code review and examination")
        lines.append("• [magenta]Maintenance[/magenta] - System upkeep and optimization")
        lines.append("")
        
        # Quick stats
        agent_count = len(self.agents_list) if self.agents_list else 0
        active_count = sum(1 for a in self.agents_list if a.get('is_active', False)) if self.agents_list else 0
        
        lines.append(f"[bold]System Status:[/bold]")
        lines.append(f"• Total Agents: {agent_count}")
        lines.append(f"• Active Agents: {active_count}")
        lines.append(f"• Built-in Agents: {sum(1 for a in self.agents_list if a.get('is_builtin', False)) if self.agents_list else 0}")
        lines.append("")
        
        # Getting started
        lines.append("[bold]Getting Started:[/bold]")
        lines.append("")
        if agent_count == 0:
            lines.append("🚀 [bold yellow]No agents found - Create your first agent![/bold yellow]")
            lines.append("")
            lines.append("1. Press [bold green]'n'[/bold green] to create a new agent")
            lines.append("2. Fill in the agent details")
            lines.append("3. Press [bold green]Ctrl+S[/bold green] or click Create")
        else:
            lines.append("📋 [bold green]Select an agent[/bold green] from the table to view details")
            lines.append("")
            lines.append("• Use [bold]j/k[/bold] or arrow keys to navigate")
            lines.append("• Press [bold green]'n'[/bold green] to create a new agent")
            lines.append("• Press [bold blue]'e'[/bold blue] to edit the selected agent")
            lines.append("• Press [bold red]'d'[/bold red] to delete the selected agent")
            lines.append("• Press [bold yellow]'r'[/bold yellow] to run the selected agent")
        
        lines.append("")
        lines.append("─" * 60)
        
        # Key bindings reminder
        lines.append("[bold]Key Bindings:[/bold]")
        lines.append("• [green]n[/green] - New agent")
        lines.append("• [blue]e[/blue] - Edit agent")
        lines.append("• [red]d[/red] - Delete agent")
        lines.append("• [yellow]r[/yellow] - Run agent")
        lines.append("• [cyan]j/k[/cyan] - Navigate")
        lines.append("• [magenta]g/G[/magenta] - Go to top/bottom")
        
        lines.append("")
        lines.append("─" * 60)
        lines.append("[dim]Select an agent to see its configuration and details[/dim]")
        
        # Update the content
        content.update("\n".join(lines))
    
    def update_table(self) -> None:
        """Refresh the agent table with current data."""
        if not agent_registry:
            return
            
        try:
            # Get updated agent list
            agents = agent_registry.list_agents(include_inactive=True)
            self.agents_list = agents
            
            # Clear and repopulate table
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
    
    def action_run_agent(self) -> None:
        """Run agent - stub for now."""
        self.update_status("Run agent - not implemented in minimal version")
    
    async def action_edit_agent(self) -> None:
        """Start editing the selected agent using form."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
            
        # Get agent info
        agent = next((a for a in self.agents_list if a["id"] == self.current_agent_id), None)
        if not agent:
            self.update_status("Agent not found")
            return
            
        if agent["is_builtin"]:
            self.update_status("Cannot edit built-in agents")
            return
            
        # Load full agent config
        full_agent = agent_registry.get_agent(self.current_agent_id)
        if not full_agent:
            self.update_status("Failed to load agent")
            return
            
        # Prepare agent data for form
        agent_data = {
            "id": self.current_agent_id,
            "name": full_agent.config.name,
            "display_name": full_agent.config.display_name,
            "description": full_agent.config.description,
            "category": full_agent.config.category,
            "system_prompt": full_agent.config.system_prompt,
            "user_prompt_template": full_agent.config.user_prompt_template,
        }
        
        # Enter form mode for editing
        await self.enter_agent_form_mode(edit_mode=True, agent_data=agent_data)
    
    async def action_new_agent(self) -> None:
        """Start interactive agent creation using form."""
        logger.info("action_new_agent called")
        
        if not agent_registry:
            self.update_status("❌ Agent registry not available - database may not be initialized")
            logger.error("agent_registry is None")
            return
        
        # Try the form approach
        logger.info("Calling enter_agent_form_mode...")
        try:
            await self.enter_agent_form_mode(edit_mode=False)
            logger.info("enter_agent_form_mode completed")
        except Exception as e:
            logger.error(f"Error in action_new_agent: {e}", exc_info=True)
            self.update_status(f"❌ Error creating form: {str(e)}")
    
    def action_delete_agent(self) -> None:
        """Start agent deletion with confirmation."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return
            
        # Get agent info
        agent = next((a for a in self.agents_list if a["id"] == self.current_agent_id), None)
        if not agent:
            self.update_status("Agent not found")
            return
            
        if agent["is_builtin"]:
            self.update_status("Cannot delete built-in agents")
            return
            
        # Enter delete confirmation mode
        self.input_mode = "delete"
        self.input_buffer = ""
        
        # Show confirmation prompt
        content = self.query_one("#agent-content", RichLog)
        content.clear()
        
        content.write("[bold red]⚠️  Delete Agent[/bold red]")
        content.write("─" * 50)
        content.write("")
        content.write(f"[yellow]Agent:[/yellow] {agent['display_name']}")
        content.write(f"[yellow]ID:[/yellow] {agent['id']}")
        content.write(f"[yellow]Usage:[/yellow] Used {agent['usage_count']} times")
        content.write("")
        content.write("[bold red]This action cannot be undone![/bold red]")
        content.write("")
        content.write(f"Type [bold]{agent['name']}[/bold] to confirm deletion:")
        content.write("")
        content.write(f"> {self.input_buffer}▋")
        content.write("")
        content.write("─" * 50)
        content.write("[red]Enter[/red] to confirm | [green]ESC[/green] to cancel")
        
        self.update_status(f"Confirm deletion of '{agent['display_name']}'")
    
    def show_edit_field(self) -> None:
        """Show the current field being edited in edit mode."""
        if self.current_field_index >= len(self.form_fields):
            # All fields reviewed, save changes
            self.save_agent_edits()
            return
            
        field_name, prompt, _ = self.form_fields[self.current_field_index]
        current_value = self.form_data[field_name]
        
        # Use the right panel for the form
        content = self.query_one("#agent-content", RichLog)
        content.clear()
        
        content.write("[bold yellow]✏️  Edit Agent[/bold yellow]")
        content.write("─" * 50)
        content.write("")
        
        # Show all fields with current values
        for i, (fn, fp, _) in enumerate(self.form_fields):
            value = self.form_data[fn]
            if i < self.current_field_index:
                # Already edited
                if value != self.original_data[fn]:
                    content.write(f"✓ [green]{fn}:[/green] {value} [yellow](changed)[/yellow]")
                else:
                    content.write(f"✓ [green]{fn}:[/green] {value}")
            elif i == self.current_field_index:
                # Currently editing
                content.write(f"[bold yellow]→ {fp}:[/bold yellow]")
                content.write(f"  [dim]Current: {current_value}[/dim]")
                content.write(f"  > {self.input_buffer}▋")
            else:
                # Not yet edited
                content.write(f"  [dim]{fn}: {value}[/dim]")
        
        content.write("")
        content.write("─" * 50)
        content.write("[green]Enter[/green] to keep/update | [yellow]Tab[/yellow] to skip | [red]ESC[/red] to cancel all")
        
        self.update_status(f"Editing: {prompt}")
    
    def save_agent_edits(self) -> None:
        """Save the edited agent data."""
        try:
            # Check what changed
            updates = {}
            for field_name in self.form_data:
                if self.form_data[field_name] != self.original_data[field_name]:
                    updates[field_name] = self.form_data[field_name]
            
            if updates:
                # Save changes
                if agent_registry.update_agent(self.current_agent_id, updates):
                    self.update_status(f"✅ Updated agent successfully")
                else:
                    self.update_status("❌ Failed to update agent")
            else:
                self.update_status("No changes made")
            
            # Exit edit mode
            self.input_mode = None
            content = self.query_one("#agent-content", RichLog)
            content.clear()
            self.update_table()
            self.update_details(self.current_agent_id)
            
        except Exception as e:
            logger.error(f"Failed to save agent edits: {e}", exc_info=True)
            self.update_status(f"❌ Error: {str(e)}")
    
    def show_current_field(self) -> None:
        """Show the current field being edited."""
        if self.current_field_index >= len(self.form_fields):
            # All fields collected, create the agent
            self.create_agent_from_form()
            return
            
        field_name, prompt, default = self.form_fields[self.current_field_index]
        
        # Use the right panel for the form
        content = self.query_one("#agent-content", RichLog)
        content.clear()
        
        content.write("[bold yellow]🤖 Create New Agent[/bold yellow]")
        content.write("─" * 50)
        content.write("")
        
        # Show previously entered fields
        for i in range(self.current_field_index):
            fn, _, _ = self.form_fields[i]
            value = self.form_data.get(fn, "")
            content.write(f"✓ [green]{fn}:[/green] {value}")
        
        content.write("")
        content.write(f"[bold yellow]{prompt}:[/bold yellow]")
        content.write(f"[dim]Default: {default}[/dim]")
        content.write("")
        content.write(f"> {self.input_buffer}▋")
        content.write("")
        content.write("─" * 50)
        content.write("[green]Enter[/green] to accept | [yellow]Tab[/yellow] to use default | [red]ESC[/red] to cancel")
        
        self.update_status(f"Creating agent: {prompt}")
    
    def create_agent_from_form(self) -> None:
        """Create agent with collected form data."""
        try:
            # Fill in any missing fields with defaults
            for field_name, _, default in self.form_fields:
                if field_name not in self.form_data:
                    self.form_data[field_name] = default
            
            # Create config
            config = {
                "name": self.form_data["name"],
                "display_name": self.form_data["display_name"],
                "description": self.form_data["description"],
                "category": self.form_data["category"],
                "system_prompt": self.form_data["system_prompt"],
                "user_prompt_template": self.form_data["user_prompt_template"],
                "allowed_tools": ["Read", "Grep", "Glob"],
                "timeout_seconds": 3600,
                "created_by": "user"
            }
            
            # Create the agent
            agent_id = agent_registry.create_agent(config)
            self.update_status(f"✅ Created agent '{config['display_name']}' (ID: {agent_id})")
            
            # Exit create mode
            self.create_mode = False
            self.input_mode = None
            
            # Clear content and refresh
            content = self.query_one("#agent-content", RichLog)
            content.clear()
            self.update_table()
            
        except Exception as e:
            logger.error(f"Failed to create agent: {e}", exc_info=True)
            self.update_status(f"❌ Error: {str(e)}")
    
    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        
        # Skip old key handling if we're in form mode
        if getattr(self, 'form_mode', False):
            return
        
        # Handle create mode keys
        if self.create_mode and self.input_mode == "create":
            if key == "escape":
                # Cancel creation
                self.create_mode = False
                self.input_mode = None
                self.update_status("Agent creation cancelled")
                # Clear the content panel
                content = self.query_one("#agent-content", Static)
                content.update("")
                event.stop()
            elif key == "enter":
                # Accept current input
                if self.input_buffer.strip():
                    field_name, _, _ = self.form_fields[self.current_field_index]
                    self.form_data[field_name] = self.input_buffer.strip()
                    self.input_buffer = ""
                    self.current_field_index += 1
                    self.show_current_field()
                event.stop()
            elif key == "tab":
                # Use default value
                field_name, _, default = self.form_fields[self.current_field_index]
                self.form_data[field_name] = default
                self.input_buffer = ""
                self.current_field_index += 1
                self.show_current_field()
                event.stop()
            elif key == "backspace":
                # Remove last character
                if self.input_buffer:
                    self.input_buffer = self.input_buffer[:-1]
                    self.show_current_field()
                event.stop()
            elif len(key) == 1 and key.isprintable():
                # Add character to buffer
                self.input_buffer += key
                self.show_current_field()
                event.stop()
            else:
                event.stop()  # Consume all other keys in create mode
        
        # Handle delete confirmation mode
        elif self.input_mode == "delete":
            if key == "escape":
                # Cancel deletion
                self.input_mode = None
                self.input_buffer = ""
                self.update_status("Deletion cancelled")
                content = self.query_one("#agent-content", Static)
                content.update("")
                event.stop()
            elif key == "enter":
                # Check if confirmation matches
                agent = next((a for a in self.agents_list if a["id"] == self.current_agent_id), None)
                if agent and self.input_buffer == agent["name"]:
                    # Perform deletion
                    try:
                        if agent_registry.delete_agent(self.current_agent_id, hard_delete=False):
                            self.update_status(f"✅ Deleted agent '{agent['display_name']}'")
                            self.current_agent_id = None
                            self.input_mode = None
                            self.input_buffer = ""
                            content = self.query_one("#agent-content", RichLog)
                            content.clear()
                            self.update_table()
                        else:
                            self.update_status("❌ Failed to delete agent")
                    except Exception as e:
                        logger.error(f"Failed to delete agent: {e}", exc_info=True)
                        self.update_status(f"❌ Error: {str(e)}")
                else:
                    self.update_status("❌ Name doesn't match - deletion cancelled")
                    self.input_mode = None
                    self.input_buffer = ""
                    content = self.query_one("#agent-content", RichLog)
                    content.clear()
                event.stop()
            elif key == "backspace":
                if self.input_buffer:
                    self.input_buffer = self.input_buffer[:-1]
                    self.action_delete_agent()  # Refresh display
                event.stop()
            elif len(key) == 1 and key.isprintable():
                self.input_buffer += key
                self.action_delete_agent()  # Refresh display
                event.stop()
            else:
                event.stop()
        
        # Handle edit mode
        elif self.input_mode == "edit":
            if key == "escape":
                # Cancel editing
                self.input_mode = None
                self.update_status("Edit cancelled")
                content = self.query_one("#agent-content", Static)
                content.update("")
                event.stop()
            elif key == "enter":
                # Save current field value if changed
                field_name, _, _ = self.form_fields[self.current_field_index]
                if self.input_buffer.strip() and self.input_buffer != self.form_data[field_name]:
                    self.form_data[field_name] = self.input_buffer.strip()
                # Move to next field
                self.current_field_index += 1
                if self.current_field_index < len(self.form_fields):
                    field_name, _, _ = self.form_fields[self.current_field_index]
                    self.input_buffer = self.form_data[field_name]
                self.show_edit_field()
                event.stop()
            elif key == "tab":
                # Skip to next field without changing
                self.current_field_index += 1
                if self.current_field_index < len(self.form_fields):
                    field_name, _, _ = self.form_fields[self.current_field_index]
                    self.input_buffer = self.form_data[field_name]
                self.show_edit_field()
                event.stop()
            elif key == "backspace":
                if self.input_buffer:
                    self.input_buffer = self.input_buffer[:-1]
                    self.show_edit_field()
                event.stop()
            elif len(key) == 1 and key.isprintable():
                self.input_buffer += key
                self.show_edit_field()
                event.stop()
            else:
                event.stop()
    
    async def enter_agent_form_mode(self, edit_mode=False, agent_data=None) -> None:
        """Enter agent form mode (following document browser pattern)."""
        logger.info(f"Entering agent form mode: edit_mode={edit_mode}, agent_data={agent_data}")
        
        # Store that we're in form mode
        self.editing_agent_id = agent_data.get("id") if agent_data and isinstance(agent_data, dict) else None
        self.form_mode = True
        self.edit_mode = edit_mode
        
        # Replace content with form
        from textual.containers import Vertical
        try:
            content_container = self.query_one("#agent-preview-container", Vertical)
            logger.info(f"Found content container: {content_container}")
        except Exception as e:
            logger.error(f"Could not find content container: {e}")
            return
        
        try:
            # Remove the existing content container completely to prevent log bleeding
            content_scroll = self.query_one("#agent-preview", ScrollableContainer)
            await content_scroll.remove()
            logger.info("Removed existing content")
        except Exception as e:
            logger.error(f"Error removing content: {e}")
        
        # Create the agent form
        try:
            from .agent_form import AgentForm
            logger.info("Creating AgentForm...")
            agent_form = AgentForm(
                self, 
                agent_registry,
                edit_mode=edit_mode,
                agent_data=agent_data,
                id="agent-form"
            )
            logger.info(f"Created form: {agent_form}")
            
            # Mount the form directly to the container
            logger.info("Mounting form...")
            await content_container.mount(agent_form)
            logger.info("Form mounted successfully")
            
            # Focus the form to ensure it's active
            agent_form.focus()
            
        except Exception as e:
            logger.error(f"Error creating/mounting form: {e}", exc_info=True)
            # Show error in status instead of letting logs bleed through
            self.update_status(f"❌ Failed to create form: {str(e)}")
        
        # Update status
        action = "editing" if edit_mode else "creating"
        self.update_status(f"Agent {action} mode | Ctrl+S=save | ESC=cancel")
    
    async def exit_agent_form_mode(self) -> None:
        """Exit agent form mode and restore normal view."""
        # Clean up form mode state
        self.form_mode = False
        self.edit_mode = False
        self.editing_agent_id = None
        
        # Remove the form
        from textual.containers import Vertical
        content_container = self.query_one("#agent-preview-container", Vertical)
        
        try:
            agent_form = self.query_one("#agent-form")
            await agent_form.remove()
        except Exception as e:
            logger.error(f"Error removing agent form: {e}")
        
        # Recreate the content area since we removed it
        try:
            from textual.containers import ScrollableContainer
            content_scroll = ScrollableContainer(id="agent-preview")
            content_log = Static("", id="agent-content", markup=True)
            
            await content_container.mount(content_scroll)
            await content_scroll.mount(content_log)
            logger.info("Recreated content area")
        except Exception as e:
            logger.error(f"Error recreating content: {e}")
        
        # Refresh the table and details
        self.update_table()
        
        # Select the current agent in the table if we have one
        if self.current_agent_id:
            # Find the row for this agent
            table = self.query_one("#agent-table", DataTable)
            selected_agent = None
            for i, agent in enumerate(self.agents_list):
                if agent["id"] == self.current_agent_id:
                    table.cursor_coordinate = (i, 0)  # Use cursor_coordinate instead of cursor_row
                    selected_agent = agent
                    break
            # Update details for selected agent
            if selected_agent:
                self.update_details(selected_agent)
            else:
                # Agent not found, show welcome screen
                self.show_welcome_screen()
        else:
            # No current agent, show welcome screen
            self.show_welcome_screen()
        
        # Focus back to table and trigger selection event to refresh content
        table = self.query_one("#agent-table", DataTable)
        table.focus()
        
        # Force a selection event to refresh the content properly
        if self.current_agent_id:
            # Trigger the row highlighted event manually
            self.on_data_table_row_highlighted(None)