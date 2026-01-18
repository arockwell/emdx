#!/usr/bin/env python3
"""
Minimal browser container - just swaps browsers, no fancy shit.
"""

import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widget import Widget

from emdx.config.ui_config import get_theme, set_theme
from emdx.ui.themes import register_all_themes, get_theme_names

logger = logging.getLogger(__name__)

# Global keybinding registry instance
_keybinding_registry = None


def get_keybinding_registry():
    """Get the global keybinding registry instance."""
    return _keybinding_registry


class BrowserContainerWidget(Widget):
    """Widget wrapper to avoid Screen padding issue."""

    DEFAULT_CSS = """
    BrowserContainerWidget {
        layout: vertical;
        height: 100%;
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

    BINDINGS = [
        Binding("backslash", "cycle_theme", "Theme", show=True),
    ]

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
        global _keybinding_registry
        logger.info("=== BrowserContainer.on_mount START ===")

        # Initialize keybinding registry and check for conflicts
        await self._init_keybinding_registry()

        # Register and apply theme
        register_all_themes(self)
        saved_theme = get_theme()
        if saved_theme in get_theme_names() or saved_theme in self.available_themes:
            self.theme = saved_theme
            logger.info(f"Applied theme: {saved_theme}")
        else:
            # Fallback to default
            self.theme = "emdx-dark"
            logger.warning(f"Unknown theme '{saved_theme}', using emdx-dark")

        logger.info(f"Screen size: {self.screen.size}")
        logger.info(f"Screen region: {self.screen.region}")

        # Log the container widget info
        logger.info(f"Container widget size: {self.container_widget.size}")
        logger.info(f"Container widget region: {self.container_widget.region}")

        # Create and mount Activity browser as the default (Mission Control)
        try:
            from .browsers.activity_browser import ActivityBrowser
            browser = ActivityBrowser()
            self.browsers["activity"] = browser
            self.current_browser = "activity"
            logger.info("ActivityBrowser created successfully as default")
        except Exception as e:
            # Fallback to document browser if activity fails
            logger.error(f"Failed to create ActivityBrowser: {e}", exc_info=True)
            from .browsers.document_browser import DocumentBrowser
            browser = DocumentBrowser()
            self.browsers["document"] = browser
            self.current_browser = "document"

        mount_point = self.container_widget.query_one("#browser-mount", Container)
        logger.info(f"Mount point size before mount: {mount_point.size}")
        logger.info(f"Mount point region before mount: {mount_point.region}")

        await mount_point.mount(browser)

        # Log after mounting
        logger.info(f"Mount point size after mount: {mount_point.size}")
        logger.info(f"Mount point region after mount: {mount_point.region}")
        logger.info("=== BrowserContainer.on_mount END ===")

    async def _init_keybinding_registry(self) -> None:
        """Initialize the keybinding registry and check for conflicts."""
        global _keybinding_registry

        try:
            from emdx.ui.keybindings import KeybindingRegistry, ConflictSeverity
            from emdx.ui.keybindings.extractor import extract_all_keybindings

            # Extract all keybindings from widgets
            entries = extract_all_keybindings()
            logger.info(f"Extracted {len(entries)} keybindings from widgets")

            # Create and populate registry
            registry = KeybindingRegistry()
            registry.register_many(entries)

            # Detect conflicts
            conflicts = registry.detect_conflicts()
            _keybinding_registry = registry

            # Log summary
            logger.info(registry.summary())

            # Warn about critical conflicts
            critical = registry.get_conflicts_by_severity(ConflictSeverity.CRITICAL)
            if critical:
                logger.warning(f"Found {len(critical)} critical keybinding conflicts!")
                for conflict in critical[:5]:  # Log first 5
                    logger.warning(conflict.to_string())
                if len(critical) > 5:
                    logger.warning(f"... and {len(critical) - 5} more conflicts")

        except Exception as e:
            logger.error(f"Failed to initialize keybinding registry: {e}", exc_info=True)

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
            if browser_type == "activity":
                try:
                    from .browsers.activity_browser import ActivityBrowser
                    self.browsers[browser_type] = ActivityBrowser()
                    logger.info("ActivityBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create ActivityBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Activity browser failed to load:\n{str(e)}")
            elif browser_type == "file":
                try:
                    from .browsers.file_browser import FileBrowser
                    self.browsers[browser_type] = FileBrowser()
                    logger.info("FileBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create FileBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"File browser failed to load:\n{str(e)}")
            elif browser_type == "git":
                try:
                    from .browsers.git_browser import GitBrowser
                    self.browsers[browser_type] = GitBrowser()
                    logger.info("GitBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create GitBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Git browser failed to load:\n{str(e)}")
            elif browser_type == "log":
                try:
                    from .browsers.log_browser import LogBrowser
                    self.browsers[browser_type] = LogBrowser()
                    logger.info("LogBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create LogBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Log browser failed to load:\n{str(e)}")
            elif browser_type == "control":
                from .pulse_browser import PulseBrowser
                self.browsers[browser_type] = PulseBrowser()
            elif browser_type == "workflow":
                try:
                    from .browsers.workflow_browser import WorkflowBrowser
                    self.browsers[browser_type] = WorkflowBrowser()
                    logger.info("WorkflowBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create WorkflowBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Workflow browser failed to load:\n{str(e)}\n\nCheck logs for details.")
            elif browser_type == "tasks":
                try:
                    from .browsers.task_browser import TaskBrowser
                    self.browsers[browser_type] = TaskBrowser()
                    logger.info("TaskBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create TaskBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Tasks browser failed to load:\n{str(e)}\n\nCheck logs for details.")
            elif browser_type == "document":
                try:
                    from .browsers.document_browser import DocumentBrowser
                    self.browsers[browser_type] = DocumentBrowser()
                    logger.info("DocumentBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create DocumentBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Document browser failed to load:\n{str(e)}\n\nCheck logs for details.")
            elif browser_type == "example":
                try:
                    from .browsers.example_browser import ExampleBrowser
                    self.browsers[browser_type] = ExampleBrowser()
                    logger.info("ExampleBrowser created successfully")
                except Exception as e:
                    logger.error(f"Failed to create ExampleBrowser: {e}", exc_info=True)
                    from textual.widgets import Static
                    self.browsers[browser_type] = Static(f"Example browser failed to load:\n{str(e)}\n\nCheck logs for details.")
            else:
                # Unknown browser type - fallback to document
                logger.warning(f"Unknown browser type: {browser_type}, falling back to document")
                from .browsers.document_browser import DocumentBrowser
                self.browsers["document"] = DocumentBrowser()
                browser_type = "document"

        # Mount the new browser
        browser = self.browsers[browser_type]
        await mount_point.mount(browser)

        # Set focus to the new browser after mount is complete
        def do_focus():
            if hasattr(browser, 'focus'):
                browser.focus()

        self.call_after_refresh(do_focus)

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

    async def on_pulse_view_view_document(self, event) -> None:
        """Handle ViewDocument message from PulseView - switch to document browser."""
        await self._view_document(event.doc_id)

    async def on_activity_browser_view_document(self, event) -> None:
        """Handle ViewDocument message from ActivityBrowser - switch to document browser."""
        await self._view_document(event.doc_id)

    async def _view_document(self, doc_id: int) -> None:
        """Switch to document browser and view a specific document."""
        logger.info(f"Switching to document browser to view doc #{doc_id}")

        # Switch to document browser
        await self.switch_browser("document")

        # Try to select the document in the browser
        doc_browser = self.browsers.get("document")
        if doc_browser and hasattr(doc_browser, 'select_document_by_id'):
            await doc_browser.select_document_by_id(doc_id)
        elif doc_browser:
            # Fallback: search for the document
            if hasattr(doc_browser, 'search'):
                await doc_browser.search(f"#{doc_id}")

    async def on_key(self, event) -> None:
        """Global key routing - handle screen switching and browser-specific keys."""
        key = event.key
        logger.info(f"BrowserContainer.on_key: {key}")

        # Debug key - dump widget tree
        if key == "ctrl+d":
            self._dump_widget_tree()
            event.stop()
            return

        # Global number keys for screen switching (1=Activity, 2=Workflows, 3=Documents)
        if key == "1":
            await self.switch_browser("activity")
            event.stop()
            return
        elif key == "2":
            await self.switch_browser("workflow")
            event.stop()
            return
        elif key == "3":
            await self.switch_browser("document")
            event.stop()
            return

        # Q to quit from activity or document browser
        if key == "q" and self.current_browser in ["activity", "document"]:
            logger.info(f"Q key pressed in {self.current_browser} browser - exiting app")
            self.exit()
            event.stop()
            return

        # Browser-specific keys from document browser
        if self.current_browser == "document":
            if key == "f":
                await self.switch_browser("file")
                event.stop()
                return
            elif key == "g":
                await self.switch_browser("git")
                event.stop()
                return
            elif key == "l":
                await self.switch_browser("log")
                event.stop()
                return
            elif key == "c":
                await self.switch_browser("control")
                event.stop()
                return
            elif key == "w":
                await self.switch_browser("workflow")
                event.stop()
                return
            elif key == "t":
                await self.switch_browser("tasks")
                event.stop()
                return
            elif key == "e":
                await self.switch_browser("example")
                event.stop()
                return

        # Q from sub-browsers goes back to activity
        if key == "q" and self.current_browser in ["file", "git", "log", "control", "workflow", "tasks", "example"]:
            await self.switch_browser("activity")
            event.stop()
            return

        # Don't handle any other keys - let them bubble to browsers

    async def view_document_fullscreen(self, doc_id: int) -> None:
        """View a document fullscreen - switch to document browser and open it."""
        await self._view_document(doc_id)

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
                except Exception as e:
                    logger.debug("Could not get computed padding for widget: %s", e)

            for child in widget.children:
                dump_widget(child, indent + 1)

        dump_widget(self.screen)
        logger.info("=== END WIDGET TREE DUMP ===")

    def action_cycle_theme(self) -> None:
        """Open theme selector modal."""
        from emdx.ui.theme_selector import ThemeSelectorScreen

        def on_theme_selected(theme_name: str | None) -> None:
            if theme_name:
                logger.info(f"Theme selected: {theme_name}")
                self.notify(f"Theme: {theme_name}", timeout=2)

        self.push_screen(ThemeSelectorScreen(), on_theme_selected)
