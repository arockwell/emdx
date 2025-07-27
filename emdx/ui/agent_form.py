#!/usr/bin/env python3
"""
Agent form widget for creating and editing agents.
Follows the document browser pattern with real Input/TextArea widgets.
"""

import logging
from typing import Dict, Any, Optional

from textual import events
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Label, Select, TextArea

logger = logging.getLogger(__name__)


class AgentNameInput(Input):
    """Custom input for agent names - validates no spaces and uniqueness."""
    
    def __init__(self, agent_registry, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_registry = agent_registry
        self.error_label: Optional[Label] = None
    
    def on_blur(self) -> None:
        """Validate agent name when losing focus."""
        self.validate_name()
    
    def validate_name(self) -> bool:
        """Validate the agent name and show errors."""
        name = self.value.strip()
        
        if not name:
            self.set_error("Name is required")
            return False
        
        if " " in name:
            self.set_error("Name cannot contain spaces")
            return False
        
        # Check if name exists (for create mode)
        if hasattr(self, 'edit_mode') and not self.edit_mode:
            existing_agents = self.agent_registry.list_agents()
            if any(agent['name'] == name for agent in existing_agents):
                self.set_error("Agent name already exists")
                return False
        
        self.clear_error()
        return True
    
    def set_error(self, message: str) -> None:
        """Set error message."""
        if self.error_label:
            self.error_label.update(f"[red]❌ {message}[/red]")
    
    def clear_error(self) -> None:
        """Clear error message."""
        if self.error_label:
            self.error_label.update("")


class AgentForm(Vertical):
    """Agent creation/edit form using real widgets."""
    
    DEFAULT_CSS = """
    AgentForm {
        padding: 2;
        background: $surface;
        border: thick $primary;
    }
    
    .form-field {
        margin-bottom: 1;
    }
    
    .form-label {
        margin-bottom: 0;
        color: $text-muted;
    }
    
    .form-input {
        margin-bottom: 1;
    }
    
    .form-textarea {
        height: 4;
        margin-bottom: 1;
    }
    
    .form-buttons {
        margin-top: 2;
        align: center middle;
    }
    
    .form-buttons Button {
        margin: 0 1;
    }
    
    .error-text {
        color: $error;
        margin-bottom: 1;
    }
    """
    
    def __init__(self, app_instance, agent_registry, edit_mode=False, agent_data=None, **kwargs):
        """Initialize the agent form.
        
        Args:
            app_instance: The browser instance for callbacks
            agent_registry: Agent registry for validation and creation
            edit_mode: Whether this is editing an existing agent
            agent_data: Existing agent data for edit mode
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.agent_registry = agent_registry
        self.edit_mode = edit_mode
        self.agent_data = agent_data or {}
        
        # Form widgets
        self.name_input: Optional[AgentNameInput] = None
        self.display_name_input: Optional[Input] = None
        self.description_textarea: Optional[TextArea] = None
        self.category_select: Optional[Select] = None
        self.system_prompt_textarea: Optional[TextArea] = None
        self.user_prompt_textarea: Optional[TextArea] = None
        
        # Error labels
        self.name_error_label: Optional[Label] = None
        self.display_name_error_label: Optional[Label] = None
    
    def compose(self):
        """Compose the form layout."""
        # Form title
        title = "✏️ Edit Agent" if self.edit_mode else "🤖 Create New Agent"
        yield Label(f"[bold yellow]{title}[/bold yellow]", classes="form-field")
        
        with ScrollableContainer():
            with Vertical():
                # Agent name
                yield Label("Name (no spaces):", classes="form-label")
                self.name_input = AgentNameInput(
                    self.agent_registry,
                    placeholder="my-agent",
                    value=self.agent_data.get("name", ""),
                    id="agent-name-input",
                    classes="form-input"
                )
                self.name_input.edit_mode = self.edit_mode
                yield self.name_input
                self.name_error_label = Label("", classes="error-text")
                self.name_input.error_label = self.name_error_label
                yield self.name_error_label
                
                # Display name
                yield Label("Display Name:", classes="form-label")
                self.display_name_input = Input(
                    placeholder="My Agent",
                    value=self.agent_data.get("display_name", ""),
                    id="agent-display-name-input",
                    classes="form-input"
                )
                yield self.display_name_input
                self.display_name_error_label = Label("", classes="error-text")
                yield self.display_name_error_label
                
                # Category
                yield Label("Category:", classes="form-label")
                categories = [
                    ("Research", "research"),
                    ("Generation", "generation"), 
                    ("Analysis", "analysis"),
                    ("Maintenance", "maintenance")
                ]
                current_category = self.agent_data.get("category", "research")
                self.category_select = Select(
                    categories,
                    value=current_category,
                    id="agent-category-select",
                    classes="form-input"
                )
                yield self.category_select
                
                # Description
                yield Label("Description:", classes="form-label")
                self.description_textarea = TextArea(
                    text=self.agent_data.get("description", ""),
                    id="agent-description-textarea",
                    classes="form-textarea"
                )
                yield self.description_textarea
                
                # System prompt
                yield Label("System Prompt:", classes="form-label")
                self.system_prompt_textarea = TextArea(
                    text=self.agent_data.get("system_prompt", "You are a helpful assistant."),
                    id="agent-system-prompt-textarea",
                    classes="form-textarea"
                )
                self.system_prompt_textarea.styles.height = 6
                yield self.system_prompt_textarea
                
                # User prompt template
                yield Label("User Prompt Template:", classes="form-label")
                self.user_prompt_textarea = TextArea(
                    text=self.agent_data.get("user_prompt_template", "Help with: {{task}}"),
                    id="agent-user-prompt-textarea", 
                    classes="form-textarea"
                )
                yield self.user_prompt_textarea
        
        # Buttons
        with Horizontal(classes="form-buttons"):
            button_text = "Update" if self.edit_mode else "Create"
            yield Button(button_text, variant="primary", id="form-submit-btn")
            yield Button("Cancel", id="form-cancel-btn")
    
    def on_mount(self) -> None:
        """Focus the first input when mounted."""
        if self.name_input:
            self.name_input.focus()
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "form-submit-btn":
            await self.submit_form()
        elif event.button.id == "form-cancel-btn":
            await self.cancel_form()
    
    async def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "ctrl+s":
            await self.submit_form()
            event.stop()
        elif event.key == "escape":
            await self.cancel_form()
            event.stop()
    
    def validate_form(self) -> bool:
        """Validate all form fields."""
        valid = True
        
        # Validate name
        if not self.name_input.validate_name():
            valid = False
        
        # Validate display name
        if not self.display_name_input.value.strip():
            self.display_name_error_label.update("[red]❌ Display name is required[/red]")
            valid = False
        else:
            self.display_name_error_label.update("")
        
        return valid
    
    def get_form_data(self) -> Dict[str, Any]:
        """Get all form data."""
        return {
            "name": self.name_input.value.strip(),
            "display_name": self.display_name_input.value.strip(),
            "description": self.description_textarea.text.strip(),
            "category": self.category_select.value,
            "system_prompt": self.system_prompt_textarea.text.strip(),
            "user_prompt_template": self.user_prompt_textarea.text.strip(),
            "allowed_tools": ["Read", "Grep", "Glob"],  # Default for now
            "timeout_seconds": 3600,
            "created_by": "user"
        }
    
    async def submit_form(self) -> None:
        """Submit the form."""
        if not self.validate_form():
            return
        
        try:
            form_data = self.get_form_data()
            
            if self.edit_mode:
                # Update existing agent
                agent_id = self.agent_data.get("id")
                if self.agent_registry.update_agent(agent_id, form_data):
                    self.app_instance.update_status(f"✅ Updated agent '{form_data['display_name']}'")
                    # Set the current agent to the updated one
                    self.app_instance.current_agent_id = agent_id
                    await self.app_instance.exit_agent_form_mode()
                else:
                    self.app_instance.update_status("❌ Failed to update agent")
            else:
                # Create new agent
                agent_id = self.agent_registry.create_agent(form_data)
                self.app_instance.update_status(f"✅ Created agent '{form_data['display_name']}' (ID: {agent_id})")
                # Set the current agent to the newly created one
                self.app_instance.current_agent_id = agent_id
                await self.app_instance.exit_agent_form_mode()
                
        except Exception as e:
            logger.error(f"Form submission error: {e}", exc_info=True)
            self.app_instance.update_status(f"❌ Error: {str(e)}")
    
    async def cancel_form(self) -> None:
        """Cancel form and exit."""
        action = "edit" if self.edit_mode else "creation"
        self.app_instance.update_status(f"Agent {action} cancelled")
        await self.app_instance.exit_agent_form_mode()