"""Modal dialogs for file browser operations."""

import time
from pathlib import Path
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Static

from emdx.models.documents import save_document
from emdx.models.tags import add_tags_to_document
from emdx.utils.emoji_aliases import expand_aliases
from emdx.commands.claude_execute import (
    execute_document_smart_background,
    ExecutionType,
    STAGE_TOOLS
)


class SaveFileModal(ModalScreen[Optional[dict]]):
    """Modal for saving file to EMDX with tags."""
    
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "save", "Save"),
    ]
    
    def __init__(self, file_path: Path, **kwargs):
        """Initialize save modal.
        
        Args:
            file_path: Path to file being saved
        """
        super().__init__(**kwargs)
        self.file_path = file_path
        self.add_class("save-file-modal")
    
    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container(id="save-modal-container"):
            yield Label(f"Save to EMDX: {self.file_path.name}", id="modal-title")
            
            with Vertical(id="modal-content"):
                # Title input
                yield Label("Title:")
                yield Input(
                    value=self.file_path.stem,  # Default to filename without extension
                    placeholder="Document title",
                    id="title-input"
                )
                
                # Tags input
                yield Label("Tags (comma-separated, emoji aliases supported):")
                yield Input(
                    placeholder="e.g., notes, python, refactor",
                    id="tags-input"
                )
                
                # File preview
                yield Label("Preview:", classes="preview-label")
                with Container(id="file-preview-container"):
                    yield RichLog(id="preview-log", wrap=True, highlight=True)
                
                # Buttons
                with Horizontal(id="button-container"):
                    yield Button("Save", variant="primary", id="save-btn")
                    yield Button("Cancel", variant="default", id="cancel-btn")
    
    def on_mount(self) -> None:
        """Set up the modal when mounted."""
        # Focus title input
        self.query_one("#title-input", Input).focus()
        
        # Load file preview
        self._load_preview()
    
    def _load_preview(self) -> None:
        """Load file content preview."""
        log = self.query_one("#preview-log", RichLog)
        
        try:
            # Read first 20 lines
            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 20:
                        lines.append("... (truncated)")
                        break
                    lines.append(line.rstrip())
            
            content = '\n'.join(lines)
            
            # Use syntax highlighting if possible
            from .file_preview import FilePreview
            preview = FilePreview()
            lexer = preview._get_lexer(self.file_path)
            
            if lexer:
                from rich.syntax import Syntax
                syntax = Syntax(
                    content,
                    lexer,
                    theme="monokai",
                    line_numbers=True
                )
                log.write(syntax)
            else:
                log.write(content)
                
        except Exception as e:
            log.write(f"Error loading preview: {e}")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
    
    def on_key(self, event: events.Key) -> None:
        """Handle key presses."""
        # Enter in tags input should save
        if event.key == "enter":
            focused = self.focused
            if focused and focused.id == "tags-input":
                self.action_save()
    
    def action_save(self) -> None:
        """Save the file to EMDX."""
        title_input = self.query_one("#title-input", Input)
        tags_input = self.query_one("#tags-input", Input)
        
        title = title_input.value.strip()
        if not title:
            title = self.file_path.name
        
        # Parse and expand tags
        tags_raw = tags_input.value.strip()
        tags = []
        if tags_raw:
            # Split by comma and expand aliases
            for tag in tags_raw.split(','):
                tag = tag.strip()
                if tag:
                    expanded = expand_aliases(tag)
                    tags.extend(expanded.split(','))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_tags = []
        for tag in tags:
            tag = tag.strip()
            if tag and tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        
        try:
            # Read file content
            content = self.file_path.read_text(encoding='utf-8', errors='replace')
            
            # Add file metadata to content
            metadata = f"<!-- Source: {self.file_path} -->\n\n"
            content = metadata + content
            
            # Save to EMDX
            doc_id = save_document(
                title=title,
                content=content,
                project=None  # Will be auto-detected
            )
            
            # Add tags if any
            if unique_tags:
                add_tags_to_document(str(doc_id), unique_tags)
            
            # Return success
            self.dismiss({
                'success': True,
                'doc_id': doc_id,
                'title': title,
                'tags': unique_tags
            })
            
        except Exception as e:
            # Show error (in real app, would show error modal)
            self.dismiss({
                'success': False,
                'error': str(e)
            })
    
    def action_cancel(self) -> None:
        """Cancel without saving."""
        self.dismiss(None)


class ExecuteFileModal(ModalScreen[Optional[dict]]):
    """Modal for executing file with Claude."""
    
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "execute", "Execute"),
    ]
    
    def __init__(self, file_path: Path, doc_id: Optional[int] = None, **kwargs):
        """Initialize execute modal.
        
        Args:
            file_path: Path to file being executed
            doc_id: EMDX document ID if file is already saved
        """
        super().__init__(**kwargs)
        self.file_path = file_path
        self.doc_id = doc_id
        self.add_class("execute-file-modal")
    
    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container(id="execute-modal-container"):
            yield Label(f"Execute with Claude: {self.file_path.name}", id="modal-title")
            
            with Vertical(id="modal-content"):
                # Execution options
                yield Label("This will execute the file with Claude Code.")
                yield Static("")
                
                if self.doc_id:
                    yield Static(f"✅ File is saved in EMDX (#{self.doc_id})", classes="success-text")
                else:
                    yield Static("⚠️ File not saved to EMDX. Save first for better tracking.", classes="warning-text")
                
                yield Static("")
                yield Label("Execution will run in background with appropriate tools.")
                
                # Buttons
                with Horizontal(id="button-container"):
                    yield Button("Execute", variant="primary", id="execute-btn")
                    yield Button("Cancel", variant="default", id="cancel-btn")
    
    def on_mount(self) -> None:
        """Focus execute button."""
        self.query_one("#execute-btn", Button).focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "execute-btn":
            self.action_execute()
        elif event.button.id == "cancel-btn":
            self.action_cancel()
    
    def action_execute(self) -> None:
        """Execute the file."""
        if self.doc_id:
            # Use smart execution for saved documents
            timestamp = int(time.time())
            execution_id = f"claude-{self.doc_id}-{timestamp}"
            log_dir = Path.home() / ".config" / "emdx" / "logs"
            log_file = log_dir / f"{execution_id}.log"
            
            try:
                execute_document_smart_background(
                    doc_id=self.doc_id,
                    execution_id=execution_id,
                    log_file=log_file,
                    use_stage_tools=True
                )
                
                self.dismiss({
                    'success': True,
                    'execution_id': execution_id,
                    'log_file': str(log_file)
                })
            except Exception as e:
                self.dismiss({
                    'success': False,
                    'error': str(e)
                })
        else:
            # For unsaved files, we need to save first
            self.dismiss({
                'success': False,
                'error': 'Please save the file to EMDX first'
            })
    
    def action_cancel(self) -> None:
        """Cancel without executing."""
        self.dismiss(None)