#!/usr/bin/env python3
"""
Agent form widget for creating and editing agents.
"""

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, TextArea, Button
from textual.widget import Widget


class AgentForm(Widget):
    """Agent form with basic inputs."""
    
    def __init__(self, parent_browser, agent_registry, edit_mode=False, agent_data=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_browser = parent_browser
        self.agent_registry = agent_registry
        self.edit_mode = edit_mode
        self.agent_data = agent_data or {}
        
    def compose(self):
        """Create simple form layout."""
        yield Static("[bold green]Create New Agent[/bold green]")
        yield Static("")
        
        yield Static("Agent Name:")
        yield Input(
            placeholder="my-agent-name",
            value=self.agent_data.get("name", ""),
            id="agent-name"
        )
        yield Static("")
        
        yield Static("Display Name:")
        yield Input(
            placeholder="My Agent",
            value=self.agent_data.get("display_name", ""),
            id="agent-display-name"
        )
        yield Static("")
        
        yield Static("Description:")
        yield TextArea(
            text=self.agent_data.get("description", ""),
            id="agent-description"
        )
        yield Static("")
        
        yield Static("System Prompt:")
        yield TextArea(
            text=self.agent_data.get("system_prompt", "You are a helpful assistant."),
            id="agent-system-prompt"
        )
        yield Static("")
        
        yield Static("User Prompt Template:")
        yield TextArea(
            text=self.agent_data.get("user_prompt_template", "Help with: {{task}}"),
            id="agent-user-prompt"
        )
        yield Static("")
        
        with Horizontal():
            yield Button("Save Agent", variant="primary", id="save-btn")
            yield Button("Cancel", id="cancel-btn")
        
        yield Static("")
        yield Static("[green]Click Save[/green] or [red]Cancel[/red] | [yellow]Ctrl+S[/yellow] = save | [red]ESC[/red] = cancel")
    
    def on_mount(self):
        """Focus first input."""
        self.query_one("#agent-name").focus()
    
    async def on_button_pressed(self, event):
        """Handle button clicks."""
        if event.button.id == "save-btn":
            await self.save_form()
        elif event.button.id == "cancel-btn":
            await self.cancel_form()
    
    async def on_key(self, event):
        """Handle save and cancel."""
        print(f"SimpleAgentForm.on_key: {event.key}")  # Debug logging
        if event.key == "ctrl+s":
            print("Saving form...")  # Debug logging
            await self.save_form()
            event.stop()
        elif event.key == "escape":
            print("Cancelling form...")  # Debug logging
            await self.cancel_form()
            event.stop()
    
    async def save_form(self):
        """Save the agent."""
        try:
            name = self.query_one("#agent-name").value.strip()
            display_name = self.query_one("#agent-display-name").value.strip()
            description = self.query_one("#agent-description").text.strip()
            system_prompt = self.query_one("#agent-system-prompt").text.strip()
            user_prompt = self.query_one("#agent-user-prompt").text.strip()
            
            if not name:
                self.parent_browser.update_status("❌ Name required")
                return
            if not display_name:
                self.parent_browser.update_status("❌ Display name required")
                return
            
            config = {
                "name": name,
                "display_name": display_name,
                "description": description or "An AI agent",
                "category": "research",
                "system_prompt": system_prompt or "You are a helpful assistant.",
                "user_prompt_template": user_prompt or "Help with: {{task}}",
                "allowed_tools": ["Read", "Grep", "Glob"],
                "timeout_seconds": 3600,
                "created_by": "user"
            }
            
            agent_id = self.agent_registry.create_agent(config)
            self.parent_browser.update_status(f"✅ Created agent '{display_name}' (ID: {agent_id})")
            self.parent_browser.current_agent_id = agent_id
            await self.parent_browser.exit_agent_form_mode()
            
        except Exception as e:
            self.parent_browser.update_status(f"❌ Error: {str(e)}")
    
    async def cancel_form(self):
        """Cancel the form."""
        self.parent_browser.update_status("Agent creation cancelled")
        await self.parent_browser.exit_agent_form_mode()