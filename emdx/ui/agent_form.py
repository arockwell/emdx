#!/usr/bin/env python3
"""
Agent form widget for creating and editing agents.
"""

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input, TextArea, Button, Select
from textual.widget import Widget
from textual.screen import ModalScreen
from textual.reactive import reactive
from textual.validation import Validator, ValidationResult
from typing import Optional, Dict, Any


class AgentNameValidator(Validator):
    """Validator for agent names (no spaces, alphanumeric + hyphens/underscores)."""
    
    def validate(self, value: str) -> ValidationResult:
        if not value.strip():
            return self.failure("Agent name is required")
        
        name = value.strip()
        if " " in name:
            return self.failure("Agent name cannot contain spaces")
        
        if not name.replace("-", "").replace("_", "").isalnum():
            return self.failure("Agent name can only contain letters, numbers, hyphens, and underscores")
        
        return self.success()


class AgentNameInput(Input):
    """Custom input for agent names with validation."""
    
    def __init__(self, **kwargs):
        super().__init__(
            placeholder="my-agent-name",
            validators=[AgentNameValidator()],
            **kwargs
        )


class CategorySelect(Select):
    """Custom select widget for agent categories."""

    def __init__(self, initial_value="research", **kwargs):
        self._initial_value = initial_value
        # Pass options directly to Select constructor
        super().__init__(
            options=[
                ("research", "🔍 Research"),
                ("generation", "📝 Generation"),
                ("analysis", "📊 Analysis"),
                ("maintenance", "🔧 Maintenance")
            ],
            value=initial_value,
            **kwargs
        )


class AgentDisplayNameInput(Input):
    """Custom input for agent display names."""
    
    def __init__(self, **kwargs):
        super().__init__(
            placeholder="My Agent",
            **kwargs
        )


class AgentDescriptionArea(TextArea):
    """Custom text area for agent descriptions."""
    
    def __init__(self, **kwargs):
        super().__init__(
            **kwargs
        )


class AgentForm(Widget):
    """Agent form with custom inputs and validation."""

    # Make the form focusable so it receives key events
    can_focus = True

    DEFAULT_CSS = """
    AgentForm {
        height: 100%;
        padding: 1;
        overflow-y: auto;
    }

    #form-title {
        text-align: center;
        margin: 0 0 1 0;
    }

    #form-container {
        height: auto;
        overflow-y: auto;
    }
    
    #basic-info-row {
        height: auto;
        margin: 0 0 1 0;
    }
    
    #name-column, #display-name-column, #category-column {
        width: 1fr;
        margin: 0 1 0 0;
    }
    
    .field-label {
        height: 1;
        margin: 0 0 0 0;
        text-style: bold;
    }
    
    AgentNameInput, AgentDisplayNameInput {
        height: 3;
        margin: 0 0 1 0;
    }
    
    CategorySelect {
        height: 3;
        margin: 0 0 1 0;
    }
    
    AgentDescriptionArea {
        height: 5;
        margin: 0 0 1 0;
    }
    
    #agent-system-prompt, #agent-user-prompt {
        height: 6;
        margin: 0 0 1 0;
    }
    
    .validation-area {
        height: 2;
        color: $error;
    }
    
    #button-row {
        height: 3;
        margin: 1 0 0 0;
    }
    
    #form-instructions {
        height: 1;
        text-align: center;
        margin: 1 0 0 0;
        color: $text-muted;
    }
    """
    
    def __init__(self, parent_browser, agent_registry, edit_mode=False, agent_data=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_browser = parent_browser
        self.agent_registry = agent_registry
        self.edit_mode = edit_mode
        self.agent_data = agent_data or {}
        self.field_order = [
            "agent-name",
            "agent-display-name", 
            "agent-category",
            "agent-description",
            "agent-system-prompt",
            "agent-user-prompt"
        ]
        
    def compose(self):
        """Create comprehensive form layout with all fields visible."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info("AgentForm.compose() called - START")

        # Form header
        title = "Edit Agent" if self.edit_mode else "Create New Agent"
        logger.info(f"Creating title: {title}")
        yield Static(f"[bold green]{title}[/bold green]", id="form-title")
        logger.info("Title created")
        
        # Main form container with grid layout
        logger.info("Creating form container")
        with Vertical(id="form-container"):
            # Row 1: Basic Info
            logger.info("Creating basic info row")
            with Horizontal(id="basic-info-row"):
                with Vertical(id="name-column"):
                    yield Static("Agent Name:", classes="field-label")
                    logger.info("Creating AgentNameInput")
                    yield AgentNameInput(
                        value=self.agent_data.get("name", ""),
                        id="agent-name"
                    )
                    logger.info("AgentNameInput created")

                with Vertical(id="display-name-column"):
                    yield Static("Display Name:", classes="field-label")
                    logger.info("Creating AgentDisplayNameInput")
                    yield AgentDisplayNameInput(
                        value=self.agent_data.get("display_name", ""),
                        id="agent-display-name"
                    )
                    logger.info("AgentDisplayNameInput created")

                with Vertical(id="category-column"):
                    yield Static("Category:", classes="field-label")
                    logger.info("Creating CategorySelect")
                    yield CategorySelect(
                        current_value=self.agent_data.get("category", "research"),
                        id="agent-category"
                    )
                    logger.info("Category input created")
            
            # Row 2: Description
            yield Static("Description:", classes="field-label")
            yield AgentDescriptionArea(
                text=self.agent_data.get("description", ""),
                id="agent-description"
            )
            
            # Row 3: System Prompt
            yield Static("System Prompt:", classes="field-label")
            yield TextArea(
                text=self.agent_data.get("system_prompt", "You are a helpful assistant."),
                id="agent-system-prompt"
            )
            
            # Row 4: User Prompt Template
            yield Static("User Prompt Template:", classes="field-label")
            yield TextArea(
                text=self.agent_data.get("user_prompt_template", "Help with: {{task}}"),
                id="agent-user-prompt"
            )
            
            # Validation messages area
            yield Static("", id="validation-messages", classes="validation-area")
            
            # Action buttons
            with Horizontal(id="button-row"):
                save_text = "Update Agent" if self.edit_mode else "Create Agent"
                yield Button(save_text, variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")
        
        # Footer instructions
        yield Static(
            "[green]Tab[/green] = next field | [yellow]Ctrl+S[/yellow] = save | [red]ESC[/red] = cancel",
            id="form-instructions"
        )
    
    def on_mount(self):
        """Focus first input and set up tab navigation."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info("AgentForm.on_mount called - START")
            # Focus the form itself so it receives key events
            self.focus()
            logger.info("AgentForm focused")
            logger.info("AgentForm.on_mount completed successfully")
        except Exception as e:
            logger.error(f"ERROR in AgentForm.on_mount: {e}", exc_info=True)
            raise

    def focus_first_input(self):
        """Focus the first input field."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info("focus_first_input called - attempting to focus #agent-name")
            input_widget = self.query_one("#agent-name")
            logger.info(f"Found input widget: {input_widget}")
            input_widget.focus()
            logger.info("First input focused successfully")
        except Exception as e:
            logger.error(f"ERROR focusing first input: {e}", exc_info=True)
            # Don't raise - just log the error so app doesn't crash
    
    async def on_button_pressed(self, event):
        """Handle button clicks."""
        if event.button.id == "save-btn":
            await self.save_form()
        elif event.button.id == "cancel-btn":
            await self.cancel_form()
    
    async def on_key(self, event):
        """Handle form keyboard shortcuts."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"AgentForm.on_key: {event.key}")

        # Stop j/k from bubbling to parent
        if event.key in ("j", "k", "up", "down"):
            logger.info(f"Stopping {event.key} from bubbling to parent")
            event.stop()
            event.prevent_default()
            return

        if event.key == "ctrl+s":
            logger.info("Ctrl+S pressed - saving form")
            await self.save_form()
            event.stop()
        elif event.key == "escape":
            logger.info("Escape pressed - cancelling form")
            await self.cancel_form()
            event.stop()
        elif event.key == "tab":
            self.focus_next_field()
            event.stop()
        elif event.key == "shift+tab":
            self.focus_previous_field()
            event.stop()
    
    def focus_next_field(self):
        """Move focus to the next field in tab order."""
        try:
            # Get currently focused widget
            focused = self.screen.focused
            if focused and hasattr(focused, 'id') and focused.id:
                current_index = self.field_order.index(focused.id)
                next_index = (current_index + 1) % len(self.field_order)
                next_field_id = self.field_order[next_index]
                self.query_one(f"#{next_field_id}").focus()
        except (ValueError, Exception):
            # If current field not found, focus first field
            self.query_one("#agent-name").focus()
    
    def focus_previous_field(self):
        """Move focus to the previous field in tab order."""
        try:
            # Get currently focused widget
            focused = self.screen.focused
            if focused and hasattr(focused, 'id') and focused.id:
                current_index = self.field_order.index(focused.id)
                prev_index = (current_index - 1) % len(self.field_order)
                prev_field_id = self.field_order[prev_index]
                self.query_one(f"#{prev_field_id}").focus()
        except (ValueError, Exception):
            # If current field not found, focus last field
            self.query_one("#agent-user-prompt").focus()
    
    def show_validation_error(self, message: str):
        """Show validation error message."""
        validation_area = self.query_one("#validation-messages")
        validation_area.update(f"[red]❌ {message}[/red]")
    
    def clear_validation_errors(self):
        """Clear validation error messages."""
        validation_area = self.query_one("#validation-messages")
        validation_area.update("")
    
    def validate_form(self) -> tuple[bool, str]:
        """Validate all form fields."""
        # Clear previous errors
        self.clear_validation_errors()
        
        # Get form values
        name = self.query_one("#agent-name").value.strip()
        display_name = self.query_one("#agent-display-name").value.strip()
        description = self.query_one("#agent-description").text.strip()
        system_prompt = self.query_one("#agent-system-prompt").text.strip()
        user_prompt = self.query_one("#agent-user-prompt").text.strip()
        
        # Validate required fields
        if not name:
            return False, "Agent name is required"
        if not display_name:
            return False, "Display name is required"
        if not description:
            return False, "Description is required"
        if not system_prompt:
            return False, "System prompt is required"
        if not user_prompt:
            return False, "User prompt template is required"
        
        # Validate agent name format (handled by validator, but double-check)
        if " " in name:
            return False, "Agent name cannot contain spaces"
        
        return True, ""
    
    async def save_form(self):
        """Save the agent with validation."""
        try:
            # Validate form
            is_valid, error_message = self.validate_form()
            if not is_valid:
                self.show_validation_error(error_message)
                self.parent_browser.update_status(f"❌ {error_message}")
                return
            
            # Get form values
            name = self.query_one("#agent-name").value.strip()
            display_name = self.query_one("#agent-display-name").value.strip()
            description = self.query_one("#agent-description").text.strip()
            category = self.query_one("#agent-category").value
            system_prompt = self.query_one("#agent-system-prompt").text.strip()
            user_prompt = self.query_one("#agent-user-prompt").text.strip()
            
            # Build config
            config = {
                "name": name,
                "display_name": display_name,
                "description": description,
                "category": category,
                "system_prompt": system_prompt,
                "user_prompt_template": user_prompt,
                "allowed_tools": ["Read", "Grep", "Glob"],
                "timeout_seconds": 3600,
                "created_by": "user"
            }
            
            if self.edit_mode:
                # Update existing agent
                agent_id = self.agent_data.get("id")
                if self.agent_registry.update_agent(agent_id, config):
                    self.parent_browser.update_status(f"✅ Updated agent '{display_name}'")
                    self.parent_browser.current_agent_id = agent_id
                    await self.parent_browser.exit_agent_form_mode()
                else:
                    self.show_validation_error("Failed to update agent")
                    self.parent_browser.update_status("❌ Failed to update agent")
            else:
                # Create new agent
                agent_id = self.agent_registry.create_agent(config)
                self.parent_browser.update_status(f"✅ Created agent '{display_name}' (ID: {agent_id})")
                self.parent_browser.current_agent_id = agent_id
                await self.parent_browser.exit_agent_form_mode()
            
        except Exception as e:
            error_msg = str(e)
            self.show_validation_error(f"Error: {error_msg}")
            self.parent_browser.update_status(f"❌ Error: {error_msg}")
    
    async def cancel_form(self):
        """Cancel the form."""
        self.parent_browser.update_status("Agent creation cancelled")
        await self.parent_browser.exit_agent_form_mode()


class DeleteConfirmationDialog(ModalScreen[bool]):
    """Modal dialog for confirming agent deletion."""
    
    DEFAULT_CSS = """
    DeleteConfirmationDialog {
        align: center middle;
    }
    
    #delete-dialog {
        width: 60;
        height: 15;
        border: thick $error;
        background: $surface;
        padding: 1;
    }
    
    #delete-title {
        text-align: center;
        margin: 0 0 1 0;
        color: $error;
    }
    
    #delete-details {
        margin: 0 0 1 0;
    }
    
    #delete-warning {
        text-align: center;
        margin: 0 0 1 0;
        color: $error;
    }
    
    #name-input {
        margin: 0 0 1 0;
    }
    
    #delete-buttons {
        height: 3;
        margin: 1 0 0 0;
    }
    
    #delete-instructions {
        text-align: center;
        margin: 1 0 0 0;
        color: $text-muted;
    }
    """
    
    def __init__(self, agent_name: str, agent_display_name: str, usage_count: int, **kwargs):
        super().__init__(**kwargs)
        self.agent_name = agent_name
        self.agent_display_name = agent_display_name
        self.usage_count = usage_count
    
    def compose(self):
        """Create the delete confirmation dialog."""
        with Vertical(id="delete-dialog"):
            yield Static("⚠️  Delete Agent", id="delete-title")
            
            yield Static(
                f"Agent: {self.agent_display_name}\n"
                f"Name: {self.agent_name}\n"
                f"Usage: {self.usage_count} times",
                id="delete-details"
            )
            
            yield Static("This action cannot be undone!", id="delete-warning")
            
            yield Static(f"Type '{self.agent_name}' to confirm:")
            yield Input(
                placeholder=self.agent_name,
                id="name-input"
            )
            
            with Horizontal(id="delete-buttons"):
                yield Button("Delete", variant="error", id="delete-btn")
                yield Button("Cancel", id="cancel-btn")
            
            yield Static(
                "[red]Enter[/red] or click Delete | [green]ESC[/green] or click Cancel",
                id="delete-instructions"
            )
    
    def on_mount(self):
        """Focus the input field."""
        self.query_one("#name-input").focus()
    
    async def on_button_pressed(self, event):
        """Handle button clicks."""
        if event.button.id == "delete-btn":
            await self.confirm_deletion()
        elif event.button.id == "cancel-btn":
            self.dismiss(False)
    
    async def on_key(self, event):
        """Handle keyboard shortcuts."""
        if event.key == "enter":
            await self.confirm_deletion()
            event.stop()
        elif event.key == "escape":
            self.dismiss(False)
            event.stop()
    
    async def confirm_deletion(self):
        """Check input and confirm deletion."""
        name_input = self.query_one("#name-input")
        if name_input.value.strip() == self.agent_name:
            self.dismiss(True)
        else:
            # Show error by updating the input to show what's wrong
            name_input.value = ""
            name_input.placeholder = f"Must type: {self.agent_name}"