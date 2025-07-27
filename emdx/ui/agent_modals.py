#!/usr/bin/env python3
"""
Modal dialogs for agent operations.
"""

import json
from typing import Optional, Dict, Any, List

from textual.app import ComposeResult
from textual.containers import Grid, Vertical, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Static, TextArea
from textual.binding import Binding

from ..agents.registry import agent_registry
from ..models.documents import get_recent_documents


class RunAgentModal(ModalScreen):
    """Modal for running an agent."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Run Agent"),
    ]
    
    DEFAULT_CSS = """
    RunAgentModal {
        align: center middle;
    }
    
    #run-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 80;
        height: auto;
        max-height: 40;
    }
    
    #run-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    .field-label {
        margin-top: 1;
        color: $text-muted;
    }
    
    Input, TextArea {
        margin-bottom: 1;
    }
    
    #button-container {
        margin-top: 2;
        align: center middle;
        height: 3;
    }
    
    Button {
        margin: 0 1;
    }
    
    .radio-option {
        margin: 0 1;
    }
    """
    
    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        self.input_type = "document"
        
    def compose(self) -> ComposeResult:
        """Create the run agent dialog."""
        with Vertical(id="run-dialog"):
            yield Static(f"Run Agent: {self.agent.config.display_name}", id="run-title")
            
            # Input type selection
            yield Label("Input Type:", classes="field-label")
            with Horizontal():
                yield Button("Document", id="type-document", variant="primary", classes="radio-option")
                yield Button("Query", id="type-query", variant="default", classes="radio-option")
            
            # Document ID input
            yield Label("Document ID (or leave empty to use most recent):", classes="field-label", id="doc-label")
            yield Input(placeholder="123", id="doc-input")
            
            # Recent documents hint
            recent_docs = get_recent_documents(limit=5)
            if recent_docs:
                hints = []
                for doc in recent_docs:
                    hints.append(f"#{doc['id']}: {doc['title'][:40]}...")
                yield Static("Recent: " + " | ".join(hints), classes="field-label", id="recent-hint")
            
            # Query input (hidden by default)
            yield Label("Query:", classes="field-label query-field")
            yield TextArea(id="query-input", classes="query-field")
            
            # Variables input (optional)
            yield Label("Variables (key=value, one per line):", classes="field-label")
            yield TextArea(id="vars-input", height=3)
            
            # Buttons
            with Horizontal(id="button-container"):
                yield Button("Run", variant="primary", id="run-button")
                yield Button("Cancel", variant="default", id="cancel-button")
                
    async def on_mount(self) -> None:
        """Set up initial state."""
        # Hide query fields initially
        for widget in self.query(".query-field"):
            widget.display = False
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        if button_id == "type-document":
            self.input_type = "document"
            self.query_one("#type-document").variant = "primary"
            self.query_one("#type-query").variant = "default"
            
            # Show document fields, hide query fields
            self.query_one("#doc-label").display = True
            self.query_one("#doc-input").display = True
            if self.query_one("#recent-hint", Static):
                self.query_one("#recent-hint").display = True
            
            for widget in self.query(".query-field"):
                widget.display = False
                
        elif button_id == "type-query":
            self.input_type = "query"
            self.query_one("#type-document").variant = "default"
            self.query_one("#type-query").variant = "primary"
            
            # Hide document fields, show query fields
            self.query_one("#doc-label").display = False
            self.query_one("#doc-input").display = False
            if self.query_one("#recent-hint", Static):
                self.query_one("#recent-hint").display = False
                
            for widget in self.query(".query-field"):
                widget.display = True
                
        elif button_id == "run-button":
            self.action_submit()
        elif button_id == "cancel-button":
            self.action_cancel()
            
    def action_submit(self) -> None:
        """Submit the form."""
        result = {
            "agent_id": self.agent_id,
            "input_type": self.input_type,
        }
        
        if self.input_type == "document":
            doc_id_str = self.query_one("#doc-input", Input).value.strip()
            if doc_id_str:
                try:
                    result["doc_id"] = int(doc_id_str)
                except ValueError:
                    pass
            else:
                # Use most recent document
                recent_docs = get_recent_documents(limit=1)
                if recent_docs:
                    result["doc_id"] = recent_docs[0]["id"]
        else:
            result["query"] = self.query_one("#query-input", TextArea).text
            
        # Parse variables
        vars_text = self.query_one("#vars-input", TextArea).text
        if vars_text.strip():
            variables = {}
            for line in vars_text.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    variables[key.strip()] = value.strip()
            if variables:
                result["variables"] = variables
                
        self.dismiss(result)
        
    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class AgentHistoryModal(ModalScreen):
    """Modal for viewing agent execution history."""
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
    ]
    
    DEFAULT_CSS = """
    AgentHistoryModal {
        align: center middle;
    }
    
    #history-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
        height: 80%;
    }
    
    #history-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    #history-log {
        height: 1fr;
        border: solid $primary;
        margin: 1 0;
    }
    """
    
    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        
    def compose(self) -> ComposeResult:
        """Create the history dialog."""
        with Vertical(id="history-dialog"):
            yield Static(f"Execution History: {self.agent.config.display_name}", id="history-title")
            yield RichLog(id="history-log")
            yield Button("Close", id="close-button")
            
    async def on_mount(self) -> None:
        """Load execution history."""
        log = self.query_one("#history-log", RichLog)
        
        try:
            from ..database.connection import db_connection
            
            with db_connection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        ae.id,
                        ae.status,
                        ae.started_at,
                        ae.completed_at,
                        ae.input_type,
                        ae.input_query,
                        ae.error_message,
                        ae.execution_time_ms,
                        ae.iterations_used,
                        ae.output_doc_ids,
                        d.title as input_doc_title
                    FROM agent_executions ae
                    LEFT JOIN documents d ON ae.input_doc_id = d.id
                    WHERE ae.agent_id = ?
                    ORDER BY ae.started_at DESC
                    LIMIT 50
                """, (self.agent_id,))
                
                rows = cursor.fetchall()
                
                if not rows:
                    log.write("[yellow]No execution history found[/yellow]")
                    return
                    
                for row in rows:
                    # Format execution entry
                    status_icon = {
                        'completed': '✅',
                        'failed': '❌',
                        'running': '🔄',
                        'cancelled': '⚠️'
                    }.get(row['status'], '❓')
                    
                    log.write(f"\n[bold]{status_icon} Execution #{row['id']}[/bold]")
                    log.write(f"Started: {row['started_at']}")
                    
                    if row['input_type'] == 'document':
                        log.write(f"Input: Document - {row['input_doc_title'] or 'Unknown'}")
                    else:
                        log.write(f"Input: Query - {row['input_query'][:100]}...")
                        
                    if row['status'] == 'completed':
                        log.write(f"Completed: {row['completed_at']}")
                        if row['execution_time_ms']:
                            log.write(f"Duration: {row['execution_time_ms']/1000:.1f}s")
                        if row['iterations_used']:
                            log.write(f"Iterations: {row['iterations_used']}")
                        if row['output_doc_ids']:
                            doc_ids = json.loads(row['output_doc_ids'])
                            log.write(f"Output Docs: {', '.join(f'#{id}' for id in doc_ids)}")
                    elif row['status'] == 'failed':
                        log.write(f"[red]Failed: {row['error_message']}[/red]")
                        
                    log.write("-" * 60)
                    
        except Exception as e:
            log.write(f"[red]Error loading history: {e}[/red]")
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-button":
            self.action_close()
            
    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss()


class CreateAgentModal(ModalScreen):
    """Modal for creating a new agent."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Create Agent"),
    ]
    
    DEFAULT_CSS = """
    CreateAgentModal {
        align: center middle;
    }
    
    #create-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
        height: auto;
        max-height: 90%;
    }
    
    #create-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    .field-label {
        margin-top: 1;
        color: $text-muted;
    }
    
    Input, TextArea {
        margin-bottom: 1;
    }
    
    #button-container {
        margin-top: 2;
        align: center middle;
        height: 3;
    }
    
    Button {
        margin: 0 1;
    }
    
    .category-buttons {
        margin-bottom: 1;
    }
    
    .category-button {
        margin-right: 1;
    }
    
    ScrollableContainer {
        height: 1fr;
    }
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = "research"
        
    def compose(self) -> ComposeResult:
        """Create the agent creation form."""
        with Vertical(id="create-dialog"):
            yield Static("Create New Agent", id="create-title")
            
            with ScrollableContainer():
                # Basic info
                yield Label("Name (no spaces):", classes="field-label")
                yield Input(placeholder="my-agent", id="name-input")
                
                yield Label("Display Name:", classes="field-label")
                yield Input(placeholder="My Agent", id="display-name-input")
                
                yield Label("Description:", classes="field-label")
                yield Input(placeholder="What this agent does...", id="description-input")
                
                yield Label("Category:", classes="field-label")
                with Horizontal(classes="category-buttons"):
                    yield Button("Research", id="cat-research", variant="primary", classes="category-button")
                    yield Button("Generation", id="cat-generation", variant="default", classes="category-button")
                    yield Button("Analysis", id="cat-analysis", variant="default", classes="category-button")
                    yield Button("Maintenance", id="cat-maintenance", variant="default", classes="category-button")
                
                # Prompts
                yield Label("System Prompt:", classes="field-label")
                yield TextArea(id="system-prompt", height=5)
                
                yield Label("User Prompt Template:", classes="field-label")
                yield TextArea(
                    id="user-prompt",
                    height=5,
                    text="Analyze {{target}} and {{task}}. Variables can be used with {{name}} syntax."
                )
                
                # Tools
                yield Label("Allowed Tools (comma-separated):", classes="field-label")
                yield Input(
                    placeholder="Read, Grep, Glob, Write",
                    value="Read, Grep, Glob",
                    id="tools-input"
                )
                
                # Settings
                yield Label("Max Context Docs:", classes="field-label")
                yield Input(value="5", id="max-context-input")
                
                yield Label("Timeout (seconds):", classes="field-label")
                yield Input(value="3600", id="timeout-input")
            
                yield Label("Output Tags (comma-separated, optional):", classes="field-label")
                yield Input(placeholder="analysis, report", id="tags-input")
            
            # Buttons outside scrollable area
            with Horizontal(id="button-container"):
                yield Button("Create", variant="primary", id="create-button")
                yield Button("Cancel", variant="default", id="cancel-button")
                
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id
        
        # Handle category selection
        if button_id.startswith("cat-"):
            # Reset all category buttons
            for cat in ["research", "generation", "analysis", "maintenance"]:
                self.query_one(f"#cat-{cat}").variant = "default"
            # Set selected category
            event.button.variant = "primary"
            self.category = button_id.replace("cat-", "")
            
        elif button_id == "create-button":
            self.action_submit()
        elif button_id == "cancel-button":
            self.action_cancel()
            
    def action_submit(self) -> None:
        """Submit the form."""
        import os
        
        # Gather form data
        config = {
            "name": self.query_one("#name-input", Input).value.strip(),
            "display_name": self.query_one("#display-name-input", Input).value.strip(),
            "description": self.query_one("#description-input", Input).value.strip(),
            "category": self.category,
            "system_prompt": self.query_one("#system-prompt", TextArea).text.strip(),
            "user_prompt_template": self.query_one("#user-prompt", TextArea).text.strip(),
            "allowed_tools": [t.strip() for t in self.query_one("#tools-input", Input).value.split(',')],
            "max_context_docs": int(self.query_one("#max-context-input", Input).value or 5),
            "timeout_seconds": int(self.query_one("#timeout-input", Input).value or 3600),
            "created_by": os.environ.get('USER', 'unknown')
        }
        
        # Add tags if provided
        tags_input = self.query_one("#tags-input", Input).value.strip()
        if tags_input:
            from ..utils.emoji_aliases import EMOJI_ALIASES
            tags = []
            for tag in tags_input.split(','):
                tag = tag.strip()
                # Convert text aliases to emojis
                if tag in EMOJI_ALIASES:
                    tags.append(EMOJI_ALIASES[tag])
                else:
                    tags.append(tag)
            config["output_tags"] = tags
            
        self.dismiss(config)
        
    def action_cancel(self) -> None:
        """Cancel the dialog."""
        self.dismiss(None)


class EditAgentModal(CreateAgentModal):
    """Modal for editing an existing agent."""
    
    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        self.category = self.agent.config.category
        
    def compose(self) -> ComposeResult:
        """Create the edit form with pre-filled values."""
        for widget in super().compose():
            if widget.id == "create-title":
                widget.update(f"Edit Agent: {self.agent.config.display_name}")
            elif widget.id == "create-button":
                widget.label = "Save"
            yield widget
            
    async def on_mount(self) -> None:
        """Pre-fill form with current values."""
        config = self.agent.config
        
        self.query_one("#name-input", Input).value = config.name
        self.query_one("#display-name-input", Input).value = config.display_name
        self.query_one("#description-input", Input).value = config.description
        
        # Set category button
        for cat in ["research", "generation", "analysis", "maintenance"]:
            button = self.query_one(f"#cat-{cat}")
            button.variant = "primary" if cat == config.category else "default"
        
        self.query_one("#system-prompt", TextArea).text = config.system_prompt
        self.query_one("#user-prompt", TextArea).text = config.user_prompt_template
        self.query_one("#tools-input", Input).value = ", ".join(config.allowed_tools)
        self.query_one("#max-context-input", Input).value = str(config.max_context_docs)
        self.query_one("#timeout-input", Input).value = str(config.timeout_seconds)
        
        if config.output_tags:
            self.query_one("#tags-input", Input).value = ", ".join(config.output_tags)
            
        # Disable name field for editing
        self.query_one("#name-input", Input).disabled = True


class DeleteAgentModal(ModalScreen):
    """Modal for confirming agent deletion."""
    
    DEFAULT_CSS = """
    DeleteAgentModal {
        align: center middle;
    }
    
    #delete-dialog {
        background: $surface;
        border: thick $error;
        padding: 2;
        width: 60;
        height: auto;
    }
    
    #delete-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    
    #delete-message {
        margin: 1 0;
        text-align: center;
    }
    
    #button-container {
        margin-top: 2;
        align: center middle;
        height: 3;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)
        
    def compose(self) -> ComposeResult:
        """Create the deletion confirmation dialog."""
        with Vertical(id="delete-dialog"):
            yield Static("Delete Agent", id="delete-title")
            yield Static(
                f"Are you sure you want to delete '{self.agent.config.display_name}'?\n"
                f"This agent has been used {self.agent.config.usage_count} times.",
                id="delete-message"
            )
            
            with Horizontal(id="button-container"):
                yield Button("Delete", variant="error", id="delete-button")
                yield Button("Cancel", variant="default", id="cancel-button")
                
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "delete-button":
            self.dismiss(True)
        else:
            self.dismiss(False)