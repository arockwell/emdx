#!/usr/bin/env python3
"""
Agent form widget for creating and editing agents.
Based on the document form pattern with tabbed navigation and vim editors.
"""

import logging
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input
from textual.widget import Widget

from .vim_editor import VimEditor
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AgentFormInput(Input):
    """Custom Input that handles Tab navigation for agent forms."""
    
    def __init__(self, app_instance, field_name: str, next_field: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance
        self.field_name = field_name
        self.next_field = next_field
        self._saved_cursor_position = 0
    
    def on_focus(self) -> None:
        """Handle focus event."""
        self.call_after_refresh(self._restore_cursor_position)
        self.set_timer(0.05, self._restore_cursor_position)
        
        # Update status to show current field
        self.app_instance.update_status(f"Editing {self.field_name} | Tab=next field | Ctrl+S=save | ESC=cancel")
    
    def _restore_cursor_position(self) -> None:
        """Restore the saved cursor position."""
        try:
            self.action_end()
            if self._saved_cursor_position < len(self.value):
                for _ in range(len(self.value) - self._saved_cursor_position):
                    self.action_cursor_left()
        except Exception as e:
            logger.debug(f"Error restoring cursor: {e}")
    
    def on_blur(self) -> None:
        """Save cursor position when losing focus."""
        self._saved_cursor_position = self.cursor_position
    
    async def on_key(self, event) -> None:
        """Handle Tab to navigate and Ctrl+S to save."""
        logger.debug(f"AgentFormInput.on_key: field={self.field_name}, key={event.key}")
        
        if event.key == "ctrl+s":
            # Save the agent form
            if hasattr(self.app_instance, 'save_agent_form'):
                await self.app_instance.save_agent_form()
            event.stop()
            event.prevent_default()
            return
        
        if event.key == "tab":
            # Move to next field
            try:
                next_widget = self.app_instance.query_one(f"#{self.next_field}")
                if hasattr(next_widget, 'focus_editor'):
                    next_widget.focus_editor()
                else:
                    next_widget.focus()
                event.stop()
                event.prevent_default()
                return
            except Exception as e:
                logger.debug(f"Could not switch to {self.next_field}: {e}")
        
        if event.key == "escape":
            # Cancel agent form
            if hasattr(self.app_instance, 'cancel_agent_form'):
                await self.app_instance.cancel_agent_form()
            event.stop()
            event.prevent_default()
            return
        
        # For all other keys (typing, backspace, arrows, etc.), don't stop the event
        # Let the Input widget handle them normally


class AgentFormVimEditor(VimEditor):
    """VimEditor that handles Tab navigation for agent forms."""
    
    def __init__(self, app_instance, field_name: str, next_field: str, content="", **kwargs):
        super().__init__(app_instance, content, **kwargs)
        self.field_name = field_name
        self.next_field = next_field
    
    def focus_editor(self) -> None:
        """Focus the vim editor and update status."""
        super().focus_editor()
        # Update status to show current field
        mode_name = getattr(self.text_area, 'vim_mode', 'NORMAL')
        self.app_instance.update_status(f"Editing {self.field_name} ({mode_name}) | Tab=next field | Ctrl+S=save | ESC=cancel")
    
    def on_key(self, event) -> None:
        """Handle Tab navigation and save."""
        if event.key == "ctrl+s":
            # Save the agent form
            if hasattr(self.app_instance, 'save_agent_form'):
                self.app_instance.save_agent_form()
            event.stop()
            event.prevent_default()
            return
        
        if event.key == "tab" and getattr(self.text_area, 'vim_mode', 'NORMAL') == 'NORMAL':
            # Only allow tab navigation in NORMAL mode (not while typing)
            try:
                next_widget = self.app_instance.query_one(f"#{self.next_field}")
                if hasattr(next_widget, 'focus_editor'):
                    next_widget.focus_editor()
                else:
                    next_widget.focus()
                event.stop()
                event.prevent_default()
                return
            except Exception as e:
                logger.debug(f"Could not switch to {self.next_field}: {e}")
        
        # Let VimEditor handle other keys
        super().on_key(event)


class AgentFormTabbed(Widget):
    """Complete agent form with tabbed navigation."""
    
    DEFAULT_CSS = """
    AgentFormTabbed {
        layout: vertical;
        height: 100%;
        padding: 1;
    }
    
    .form-section {
        margin-bottom: 1;
        border: solid $primary;
        padding: 1;
    }
    
    .form-label {
        color: $text;
        background: $primary;
        padding: 0 1;
        text-align: center;
        height: 1;
    }
    
    .form-input {
        height: 3;
    }
    
    .form-vim {
        height: 8;
    }
    
    #agent-name-input, #agent-display-name-input, #agent-category-input {
        height: 1;
    }
    """
    
    def __init__(self, parent_browser, agent_registry, edit_mode=False, agent_data=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_browser = parent_browser
        self.agent_registry = agent_registry
        self.edit_mode = edit_mode
        self.agent_data = agent_data or {}
        
    def compose(self):
        """Create the agent form layout."""
        # Form title
        title = "Edit Agent" if self.edit_mode else "Create New Agent"
        yield Static(f"[bold green]{title}[/bold green]", classes="form-label")
        
        # Basic fields section
        with Vertical(classes="form-section"):
            yield Static("[bold]Basic Information[/bold]", classes="form-label")
            
            # Agent name (required, no spaces)
            yield Static("Agent Name (no spaces):", classes="form-label")
            yield AgentFormInput(
                self.parent_browser,
                "name",
                "agent-display-name-input",
                placeholder="my-agent-name",
                value=self.agent_data.get("name", ""),
                id="agent-name-input"
            )
            
            # Display name
            yield Static("Display Name:", classes="form-label") 
            yield AgentFormInput(
                self.parent_browser,
                "display_name", 
                "agent-category-input",
                placeholder="My Agent",
                value=self.agent_data.get("display_name", ""),
                id="agent-display-name-input"
            )
            
            # Category
            yield Static("Category:", classes="form-label")
            yield AgentFormInput(
                self.parent_browser,
                "category",
                "agent-description-editor",
                placeholder="research/generation/analysis/maintenance",
                value=self.agent_data.get("category", "research"),
                id="agent-category-input"
            )
        
        # Multi-line fields section
        with Vertical(classes="form-section"):
            yield Static("[bold]Content (Use vim editing)[/bold]", classes="form-label")
            
            # Description
            yield Static("Description:", classes="form-label")
            yield AgentFormVimEditor(
                self.parent_browser,
                "description",
                "agent-system-prompt-editor", 
                content=self.agent_data.get("description", ""),
                id="agent-description-editor"
            )
            
            # System prompt
            yield Static("System Prompt:", classes="form-label")
            yield AgentFormVimEditor(
                self.parent_browser,
                "system_prompt",
                "agent-user-prompt-editor",
                content=self.agent_data.get("system_prompt", "You are a helpful assistant."),
                id="agent-system-prompt-editor"
            )
            
            # User prompt template
            yield Static("User Prompt Template:", classes="form-label")
            yield AgentFormVimEditor(
                self.parent_browser,
                "user_prompt_template", 
                "agent-name-input",  # Loop back to first field
                content=self.agent_data.get("user_prompt_template", "Help with: {{task}}"),
                id="agent-user-prompt-editor"
            )
        
        # Instructions
        yield Static(
            "[green]Tab[/green] to navigate | [yellow]Ctrl+S[/yellow] to save | [red]ESC[/red] to cancel",
            classes="form-label"
        )
    
    def on_mount(self) -> None:
        """Focus first field when mounted."""
        self.call_after_refresh(self._focus_first_field)
    
    def _focus_first_field(self) -> None:
        """Focus the first input field."""
        try:
            first_input = self.query_one("#agent-name-input")
            first_input.focus()
        except Exception as e:
            logger.error(f"Could not focus first field: {e}")
    
    def get_form_data(self) -> dict:
        """Extract all form data."""
        try:
            data = {}
            
            # Get simple input values
            data["name"] = self.query_one("#agent-name-input").value.strip()
            data["display_name"] = self.query_one("#agent-display-name-input").value.strip()
            data["category"] = self.query_one("#agent-category-input").value.strip()
            
            # Get vim editor content
            data["description"] = str(self.query_one("#agent-description-editor").text_area.text).strip()
            data["system_prompt"] = str(self.query_one("#agent-system-prompt-editor").text_area.text).strip()
            data["user_prompt_template"] = str(self.query_one("#agent-user-prompt-editor").text_area.text).strip()
            
            return data
        except Exception as e:
            logger.error(f"Error getting form data: {e}", exc_info=True)
            return {}