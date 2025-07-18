"""
Minimal Browser Container for EMDX.

This demonstrates the correct architecture: a lightweight container that just
swaps browser components, with each browser being self-contained.
"""

import logging
from typing import Dict, Optional, Type
from abc import ABC, abstractmethod

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Label
from textual.binding import Binding
from textual import events

logger = logging.getLogger(__name__)


class BrowserComponent(ABC):
    """Base class for all browser components."""
    
    @abstractmethod
    def compose(self) -> ComposeResult:
        """Compose the browser UI."""
        pass
    
    @abstractmethod
    def on_mount(self) -> None:
        """Called when browser is mounted."""
        pass
    
    @abstractmethod
    def on_unmount(self) -> None:
        """Called when browser is unmounted."""
        pass
    
    @abstractmethod
    def handle_key(self, event: events.Key) -> bool:
        """
        Handle key events. Return True if handled, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_status_text(self) -> str:
        """Get status bar text for this browser."""
        pass


class MinimalEMDXContainer(App):
    """
    Minimal container app that manages browser switching.
    
    This is what the architecture SHOULD be:
    - Container handles ONLY browser switching
    - Each browser is completely self-contained
    - No mode switching within browsers
    - Clean separation of concerns
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("d", "switch_to_documents", "Documents"),
        Binding("f", "switch_to_files", "Files"),
        Binding("g", "switch_to_git", "Git"),
        Binding("l", "switch_to_logs", "Logs"),
        Binding("?", "help", "Help"),
    ]
    
    CSS = """
    #browser-container {
        height: 1fr;
        background: $surface;
    }
    
    #status-bar {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    
    /* Smooth transitions between browsers */
    .browser-entering {
        offset-x: 100%;
        transition: offset 300ms ease-out;
    }
    
    .browser-active {
        offset-x: 0;
    }
    
    .browser-exiting {
        offset-x: -100%;
        transition: offset 300ms ease-in;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.browser_registry: Dict[str, Type[BrowserComponent]] = {}
        self.current_browser: Optional[BrowserComponent] = None
        self.current_browser_name: str = "documents"
        self._register_browsers()
    
    def _register_browsers(self):
        """Register available browsers."""
        # Import browser components lazily to avoid circular imports
        try:
            from .browsers.document_browser_v2 import DocumentBrowserV2
            self.browser_registry["documents"] = DocumentBrowserV2
        except ImportError:
            logger.warning("DocumentBrowserV2 not available")
        
        try:
            from .browsers.file_browser_v2 import FileBrowserV2
            self.browser_registry["files"] = FileBrowserV2
        except ImportError:
            logger.warning("FileBrowserV2 not available")
        
        try:
            from .browsers.git_browser_v2 import GitBrowserV2
            self.browser_registry["git"] = GitBrowserV2
        except ImportError:
            logger.warning("GitBrowserV2 not available")
        
        try:
            from .browsers.log_browser_v2 import LogBrowserV2
            self.browser_registry["logs"] = LogBrowserV2
        except ImportError:
            logger.warning("LogBrowserV2 not available")
    
    def compose(self) -> ComposeResult:
        """Compose the container UI."""
        with Vertical():
            # Browser container
            yield Container(id="browser-container")
            
            # Status bar
            yield Label("EMDX Browser - Press ? for help", id="status-bar")
            
            # Footer with keybindings
            yield Footer()
    
    async def on_mount(self):
        """Initialize with default browser."""
        await self.switch_browser("documents")
    
    async def switch_browser(self, browser_name: str):
        """Switch to a different browser."""
        if browser_name == self.current_browser_name:
            return
        
        if browser_name not in self.browser_registry:
            self.notify(f"Browser '{browser_name}' not available", severity="error")
            return
        
        container = self.query_one("#browser-container")
        
        # Unmount current browser
        if self.current_browser:
            try:
                self.current_browser.on_unmount()
            except Exception as e:
                logger.error(f"Error unmounting {self.current_browser_name}: {e}")
            
            # Clear container
            await container.remove_children()
        
        # Create and mount new browser
        try:
            browser_class = self.browser_registry[browser_name]
            self.current_browser = browser_class()
            
            # Mount the browser
            await container.mount(self.current_browser)
            
            # Call on_mount
            self.current_browser.on_mount()
            
            # Update state
            self.current_browser_name = browser_name
            
            # Update status
            self.update_status()
            
        except Exception as e:
            logger.error(f"Error switching to {browser_name}: {e}")
            self.notify(f"Failed to switch to {browser_name}", severity="error")
    
    def on_key(self, event: events.Key):
        """Route key events."""
        # Let current browser handle first
        if self.current_browser and self.current_browser.handle_key(event):
            event.prevent_default()
            return
        
        # Container handles browser switching keys
        # Other keys are handled by the binding system
    
    def update_status(self):
        """Update status bar."""
        if self.current_browser:
            status_text = self.current_browser.get_status_text()
        else:
            status_text = "No browser loaded"
        
        status_label = self.query_one("#status-bar", Label)
        status_label.update(f"{self.current_browser_name.upper()} - {status_text}")
    
    # Actions for browser switching
    
    def action_quit(self):
        """Quit the application."""
        self.exit()
    
    def action_switch_to_documents(self):
        """Switch to documents browser."""
        self.switch_browser("documents")
    
    def action_switch_to_files(self):
        """Switch to file browser."""
        self.switch_browser("files")
    
    def action_switch_to_git(self):
        """Switch to git browser."""
        self.switch_browser("git")
    
    def action_switch_to_logs(self):
        """Switch to log browser."""
        self.switch_browser("logs")
    
    def action_help(self):
        """Show help."""
        help_text = """
EMDX Browser Help

Global Keys:
  q         - Quit
  d         - Documents browser
  f         - File browser
  g         - Git browser
  l         - Log browser
  ?         - This help

Each browser has its own keys. Press ? within a browser for specific help.
        """
        self.notify(help_text, title="Help", timeout=10)


# Example of what a proper browser component looks like:

class DocumentBrowserV2(Container):
    """
    Self-contained document browser component.
    
    This is what each browser should look like:
    - Extends Container (a widget)
    - Implements BrowserComponent interface
    - Completely self-contained
    - No mode switching - just one focused purpose
    """
    
    def compose(self) -> ComposeResult:
        """Compose the document browser UI."""
        # This would have the document table, preview, etc.
        yield Label("Document Browser V2 - Self-contained component")
    
    def on_mount(self):
        """Initialize the browser."""
        logger.info("Document browser mounted")
        # Load documents, setup table, etc.
    
    def on_unmount(self):
        """Cleanup when switching away."""
        logger.info("Document browser unmounted")
        # Save state, cleanup resources, etc.
    
    def handle_key(self, event: events.Key) -> bool:
        """Handle document browser specific keys."""
        if event.key == "j":
            # Move down in document list
            return True
        elif event.key == "k":
            # Move up in document list
            return True
        elif event.key == "/":
            # Search documents
            return True
        elif event.key == "e":
            # Edit document
            return True
        
        return False
    
    def get_status_text(self) -> str:
        """Get status text."""
        return "j/k: navigate, /: search, e: edit"


def run_minimal_container():
    """Run the minimal container app."""
    app = MinimalEMDXContainer()
    app.run()


if __name__ == "__main__":
    run_minimal_container()