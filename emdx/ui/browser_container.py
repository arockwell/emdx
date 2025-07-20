#!/usr/bin/env python3
"""
Minimal browser container - just swaps browsers, no fancy shit.
"""

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, Static
from textual.reactive import reactive
from textual.binding import Binding

import logging
logger = logging.getLogger(__name__)


class BrowserContainer(App):
    """Dead simple container that swaps browser widgets."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]
    
    CSS = """
    #browser-mount {
        height: 1fr;
    }
    
    #status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    """
    
    current_browser = reactive("document")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.browsers = {}  # Will store browser instances
        self.browser_states = {}  # Quick and dirty state storage
        
    def compose(self) -> ComposeResult:
        """Just a mount point and status bar."""
        with Vertical():
            yield Static(id="browser-mount")
            yield Label("Loading...", id="status")
            
    async def on_mount(self) -> None:
        """Mount the default browser on startup."""
        from .document_browser import DocumentBrowser
        
        # Create and mount document browser
        browser = DocumentBrowser()
        self.browsers["document"] = browser
        
        mount_point = self.query_one("#browser-mount", Static)
        await mount_point.mount(browser)
        
        # Browser will have parent reference automatically after mounting
        
        # Don't set a default status - let the browser update it once it loads
        # The DocumentBrowser will call update_status() from its update_table() method
        
    def update_status(self, text: str) -> None:
        """Update the status bar."""
        status = self.query_one("#status", Label)
        status.update(text)
        
    async def switch_browser(self, browser_type: str) -> None:
        """Switch to a different browser."""
        logger.info(f"Switching to {browser_type} browser")
        
        # Save current browser state
        current = self.browsers.get(self.current_browser)
        if current and hasattr(current, "save_state"):
            self.browser_states[self.current_browser] = current.save_state()
            
        # Remove current browser
        mount_point = self.query_one("#browser-mount", Static)
        await mount_point.remove_children()
        
        # Create or get the new browser
        if browser_type not in self.browsers:
            if browser_type == "file":
                from .file_browser import FileBrowser
                self.browsers[browser_type] = FileBrowser()
            elif browser_type == "git":
                from .git_browser_standalone import GitBrowser
                self.browsers[browser_type] = GitBrowser()
            else:
                # Fallback to document
                browser_type = "document"
                
        # Mount the new browser
        browser = self.browsers[browser_type]
        await mount_point.mount(browser)
        
        # Set focus to the new browser
        if hasattr(browser, 'focus'):
            browser.focus()
        
        # Parent reference is set automatically by Textual during mount
        
        # Restore state if we have it
        if browser_type in self.browser_states and hasattr(browser, "restore_state"):
            browser.restore_state(self.browser_states[browser_type])
            
        self.current_browser = browser_type
        
    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()
        
    async def on_key(self, event) -> None:
        """Global key routing - only handle browser switching keys."""
        key = event.key
        logger.info(f"BrowserContainer.on_key: {key}")
        
        # Only handle browser switching keys, let browsers handle their own keys
        if key == "q" and self.current_browser == "document":
            self.exit()
            event.stop()
            return
        elif key == "f" and self.current_browser == "document":
            await self.switch_browser("file")
            event.stop()
            return
        elif key == "d" and self.current_browser == "document":
            await self.switch_browser("git")
            event.stop()
            return
        elif key == "q" and self.current_browser in ["file", "git"]:
            await self.switch_browser("document")
            event.stop()
            return
        
        # Don't handle any other keys - let them bubble to browsers