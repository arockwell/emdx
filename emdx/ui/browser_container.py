#!/usr/bin/env python3
"""
Minimal browser container - just swaps browsers, no fancy shit.
"""

import logging

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widget import Widget

logger = logging.getLogger(__name__)


class BrowserContainerWidget(Widget):
    """Widget wrapper to avoid Screen padding issue."""

    DEFAULT_CSS = """
    BrowserContainerWidget {
        layout: vertical;
        height: 100%;
        offset: 0 -1;
    }

    #browser-mount {
        height: 1fr;
        padding: 0;
        margin: 0;
    }


    Container {
        padding: 0;
        margin: 0;
    }

    Vertical {
        padding: 0;
        margin: 0;
    }
    """

    def compose(self) -> ComposeResult:
        """Just a mount point - browsers handle their own status."""
        with Vertical():
            yield Container(id="browser-mount")


class BrowserContainer(App):
    """Dead simple container that swaps browser widgets."""

    # Note: 'q' key handling is done in on_key() method to support context-sensitive behavior

    # No CSS needed here - it's all in the widget

    current_browser = reactive("document")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.browsers = {}  # Will store browser instances
        self.browser_states = {}  # Quick and dirty state storage
        self.container_widget = None  # Will be set in compose

    def exit(self, *args, **kwargs):
        """Override exit to log when it's called."""
        import traceback
        logger.error("BrowserContainer.exit() called!")
        logger.error("".join(traceback.format_stack()))
        super().exit(*args, **kwargs)

    def _handle_exception(self, error: Exception) -> None:
        """Override exception handler to log exceptions."""
        import traceback
        logger.error(f"BrowserContainer._handle_exception called with: {error}")
        logger.error("".join(traceback.format_exception(type(error), error, error.__traceback__)))
        super()._handle_exception(error)

    def compose(self) -> ComposeResult:
        """Yield the widget wrapper."""
        self.container_widget = BrowserContainerWidget()
        yield self.container_widget

    async def on_mount(self) -> None:
        """Mount the default browser on startup."""
        from .document_browser import DocumentBrowser

        logger.info("=== BrowserContainer.on_mount START ===")
        logger.info(f"Screen size: {self.screen.size}")
        logger.info(f"Screen region: {self.screen.region}")

        # Log the container widget info
        logger.info(f"Container widget size: {self.container_widget.size}")
        logger.info(f"Container widget region: {self.container_widget.region}")

        # Create and mount document browser
        browser = DocumentBrowser()
        self.browsers["document"] = browser

        mount_point = self.container_widget.query_one("#browser-mount", Container)
        logger.info(f"Mount point size before mount: {mount_point.size}")
        logger.info(f"Mount point region before mount: {mount_point.region}")

        await mount_point.mount(browser)

        # Log after mounting
        logger.info(f"Mount point size after mount: {mount_point.size}")
        logger.info(f"Mount point region after mount: {mount_point.region}")
        logger.info("=== BrowserContainer.on_mount END ===")

        # Browser will have parent reference automatically after mounting

        # Don't set a default status - let the browser update it once it loads
        # The DocumentBrowser will call update_status() from its update_table() method

    def update_status(self, text: str) -> None:
        """Update the status bar - delegate to current browser."""
        current_browser = self.browsers.get(self.current_browser)
        if current_browser and hasattr(current_browser, 'update_status'):
            current_browser.update_status(text)

    async def switch_browser(self, browser_type: str) -> None:
        """Switch to a different browser."""
        logger.info(f"Switching to {browser_type} browser")

        # Save current browser state
        current = self.browsers.get(self.current_browser)
        if current and hasattr(current, "save_state"):
            self.browser_states[self.current_browser] = current.save_state()

        # Remove current browser
        mount_point = self.container_widget.query_one("#browser-mount", Container)
        await mount_point.remove_children()

        # Create or get the new browser
        if browser_type not in self.browsers:
            if browser_type == "file":
                from .file_browser import FileBrowser
                self.browsers[browser_type] = FileBrowser()
            elif browser_type == "git":
                from .git_browser_standalone import GitBrowser
                self.browsers[browser_type] = GitBrowser()
            elif browser_type == "log":
                from .log_browser import LogBrowser
                self.browsers[browser_type] = LogBrowser()
            elif browser_type == "agent":
                try:
                    from .agent_browser import AgentBrowser
                    self.browsers[browser_type] = AgentBrowser()
                    logger.info("AgentBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create AgentBrowser: {e}", exc_info=True)
                    # Create a simple error message widget instead
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Agent browser failed to load:\n{str(e)}\n\nCheck logs for details.")
                    logger.error(f"AgentBrowser creation failed, showing error message")
            elif browser_type == "control":
                from .pulse_browser import PulseBrowser
                self.browsers[browser_type] = PulseBrowser()
            elif browser_type == "workflow":
                try:
                    from .workflow_browser import WorkflowBrowser
                    self.browsers[browser_type] = WorkflowBrowser()
                    logger.info("WorkflowBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create WorkflowBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Workflow browser failed to load:\n{str(e)}\n\nCheck logs for details.")
            elif browser_type == "tasks":
                try:
                    from .task_browser import TaskBrowser
                    self.browsers[browser_type] = TaskBrowser()
                    logger.info("TaskBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create TaskBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Tasks browser failed to load:\n{str(e)}\n\nCheck logs for details.")
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

        # Let each browser handle its own status updates

    def action_quit(self) -> None:
        """Quit the application."""
        logger.info("action_quit called - exiting app")
        self.exit()

    async def on_key(self, event) -> None:
        """Global key routing - only handle browser switching keys."""
        key = event.key
        logger.info(f"BrowserContainer.on_key: {key}")

        # Debug key - dump widget tree
        if key == "ctrl+d":
            self._dump_widget_tree()
            event.stop()
            return

        # Only handle browser switching keys, let browsers handle their own keys
        if key == "q" and self.current_browser == "document":
            logger.info("Q key pressed in document browser - exiting app")
            self.exit()
            event.stop()
            return
        elif key == "f" and self.current_browser == "document":
            await self.switch_browser("file")
            event.stop()
            return
        elif key == "g" and self.current_browser == "document":
            await self.switch_browser("git")
            event.stop()
            return
        elif key == "l" and self.current_browser == "document":
            await self.switch_browser("log")
            event.stop()
            return
        elif key == "a" and self.current_browser == "document":
            await self.switch_browser("agent")
            event.stop()
            return
        elif key == "c" and self.current_browser == "document":
            await self.switch_browser("control")
            event.stop()
            return
        elif key == "w" and self.current_browser == "document":
            await self.switch_browser("workflow")
            event.stop()
            return
        elif key == "t" and self.current_browser == "document":
            await self.switch_browser("tasks")
            event.stop()
            return
        elif key == "q" and self.current_browser in ["file", "git", "log", "agent", "control", "workflow", "tasks"]:
            await self.switch_browser("document")
            event.stop()
            return

        # Don't handle any other keys - let them bubble to browsers

    def _dump_widget_tree(self) -> None:
        """Debug function to dump the widget tree and regions."""
        logger.info("=== WIDGET TREE DUMP ===")
        logger.info(f"Screen size: {self.screen.size}")
        logger.info(f"Screen region: {self.screen.region}")

        def dump_widget(widget, indent=0):
            prefix = "  " * indent
            logger.info(f"{prefix}{widget.__class__.__name__} id={widget.id}")
            logger.info(f"{prefix}  region: {widget.region}")
            logger.info(f"{prefix}  size: {widget.size}")
            logger.info(f"{prefix}  styles.padding: {widget.styles.padding}")
            logger.info(f"{prefix}  styles.margin: {widget.styles.margin}")

            # Check computed styles
            if hasattr(widget, 'styles') and hasattr(widget.styles, 'get_rule'):
                try:
                    computed_padding = widget.styles.get_rule('padding')
                    logger.info(f"{prefix}  computed padding: {computed_padding}")
                except Exception:
                    pass

            for child in widget.children:
                dump_widget(child, indent + 1)

        dump_widget(self.screen)
        logger.info("=== END WIDGET TREE DUMP ===")
