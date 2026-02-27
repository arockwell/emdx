#!/usr/bin/env python3
"""
Minimal browser container - just swaps browsers, no fancy shit.
"""

import logging
from typing import Any

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.reactive import reactive
from textual.widget import Widget

from emdx.config.ui_config import get_theme, set_theme
from emdx.ui.themes import get_opposite_theme, get_theme_names, is_dark_theme, register_all_themes

logger = logging.getLogger(__name__)

# Global keybinding registry instance
_keybinding_registry = None


def get_keybinding_registry() -> Any:
    """Get the global keybinding registry instance."""
    return _keybinding_registry


class BrowserContainerWidget(Widget):
    """Widget wrapper to avoid Screen padding issue."""

    DEFAULT_CSS = """
    BrowserContainerWidget {
        layout: vertical;
        height: 100%;
        padding: 0;
        margin: 0;
    }

    #browser-mount {
        height: 100%;
        padding: 0;
        margin: 0;
    }

    BrowserContainerWidget Container {
        padding: 0;
        margin: 0;
        height: 100%;
    }

    BrowserContainerWidget Vertical {
        padding: 0;
        margin: 0;
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        """Just a mount point - browsers handle their own status."""
        yield Container(id="browser-mount")


class BrowserContainer(App[None]):
    """Dead simple container that swaps browser widgets."""

    # Note: 'q' key handling is done in on_key() method to support context-sensitive behavior

    BINDINGS = [
        Binding("1", "switch_activity", "Docs", show=True),
        Binding("2", "switch_tasks", "Tasks", show=True),
        Binding("3", "switch_delegates", "Delegates", show=True),
        Binding("backslash", "cycle_theme", "Theme", show=True),
        Binding("ctrl+k", "open_command_palette", "Search", show=True),
        Binding("ctrl+p", "open_command_palette", "Search", show=False),
        Binding("ctrl+t", "toggle_theme", "Toggle Dark/Light", show=True),
    ]

    # No CSS needed here - it's all in the widget

    current_browser = reactive("document")

    def __init__(self, initial_theme: str | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.browsers: dict[str, Widget] = {}  # Will store browser instances
        self.browser_states: dict[str, Any] = {}  # Quick and dirty state storage
        self.container_widget: BrowserContainerWidget | None = None  # Will be set in compose
        self._initial_theme = initial_theme  # Theme override from CLI
        self._pending_doc_id: int | None = None  # For deferred doc navigation

    def exit(self, *args: Any, **kwargs: Any) -> None:
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
        widget = BrowserContainerWidget()
        self.container_widget = widget
        yield widget

    async def on_mount(self) -> None:
        """Mount the default browser on startup."""
        global _keybinding_registry

        # Initialize keybinding registry and check for conflicts
        await self._init_keybinding_registry()

        # Register and apply theme
        register_all_themes(self)

        # Use CLI theme if provided, otherwise load from config
        if self._initial_theme and (
            self._initial_theme in get_theme_names() or self._initial_theme in self.available_themes
        ):  # noqa: E501
            self.theme = self._initial_theme
        else:
            saved_theme = get_theme()
            if saved_theme in get_theme_names() or saved_theme in self.available_themes:
                self.theme = saved_theme
            else:
                self.theme = "emdx-dark"
                logger.warning(f"Unknown theme '{saved_theme}', using emdx-dark")

        # Create and mount Activity browser as the default (Mission Control)
        browser: Widget
        try:
            from .activity_browser import ActivityBrowser

            browser = ActivityBrowser()
            self.browsers["activity"] = browser
            self.current_browser = "activity"
        except Exception as e:
            logger.error(f"Failed to create ActivityBrowser: {e}", exc_info=True)
            from .task_browser import TaskBrowser

            browser = TaskBrowser()
            self.browsers["task"] = browser
            self.current_browser = "task"

        assert self.container_widget is not None
        mount_point = self.container_widget.query_one("#browser-mount", Container)
        await mount_point.mount(browser)

    async def _init_keybinding_registry(self) -> None:
        """Initialize the keybinding registry and check for conflicts."""
        global _keybinding_registry

        try:
            from emdx.ui.keybindings import ConflictSeverity, KeybindingRegistry
            from emdx.ui.keybindings.extractor import extract_all_keybindings

            # Extract all keybindings from widgets
            entries = extract_all_keybindings()
            # Create and populate registry
            registry = KeybindingRegistry()
            registry.register_many(entries)

            # Detect conflicts
            registry.detect_conflicts()
            _keybinding_registry = registry

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
        if current_browser and hasattr(current_browser, "update_status"):
            current_browser.update_status(text)

    async def switch_browser(self, browser_type: str) -> None:
        """Switch to a different browser."""
        logger.debug(f"Switching to {browser_type} browser")

        # Save current browser state
        current = self.browsers.get(self.current_browser)
        if current and hasattr(current, "save_state"):
            self.browser_states[self.current_browser] = current.save_state()

        # Remove current browser
        assert self.container_widget is not None
        mount_point = self.container_widget.query_one("#browser-mount", Container)
        await mount_point.remove_children()

        # Create or get the new browser
        if browser_type not in self.browsers:
            if browser_type == "activity":
                try:
                    from .activity_browser import ActivityBrowser

                    self.browsers[browser_type] = ActivityBrowser()
                    logger.debug("ActivityBrowser created")
                except Exception as e:
                    logger.error(f"Failed to create ActivityBrowser: {e}", exc_info=True)
                    from textual.widgets import Static

                    self.browsers[browser_type] = Static(
                        f"Activity browser failed to load:\n{escape(str(e))}"
                    )  # noqa: E501
            elif browser_type == "log":
                from .log_browser import LogBrowser

                self.browsers[browser_type] = LogBrowser()
            elif browser_type == "task":
                try:
                    from .task_browser import TaskBrowser

                    self.browsers[browser_type] = TaskBrowser()
                    logger.debug("TaskBrowser created")
                except Exception as e:
                    logger.error(f"Failed to create TaskBrowser: {e}", exc_info=True)
                    from textual.widgets import Static

                    self.browsers[browser_type] = Static(
                        f"Task browser failed to load:\n{escape(str(e))}\n\nCheck logs for details."
                    )  # noqa: E501
            elif browser_type == "delegate":
                try:
                    from .delegate_browser import DelegateBrowser

                    self.browsers[browser_type] = DelegateBrowser()
                    logger.debug("DelegateBrowser created")
                except Exception as e:
                    logger.error(f"Failed to create DelegateBrowser: {e}", exc_info=True)
                    from textual.widgets import Static

                    msg = f"Delegate browser failed to load:\n{escape(str(e))}"
                    self.browsers[browser_type] = Static(msg)
            else:
                # Unknown browser type - fallback to activity
                logger.warning(f"Unknown browser type: {browser_type}, falling back to activity")
                from .activity_browser import ActivityBrowser

                self.browsers["activity"] = ActivityBrowser()
                browser_type = "activity"

        # Mount the new browser
        browser = self.browsers[browser_type]
        await mount_point.mount(browser)

        # Set focus and handle pending doc navigation after mount
        def post_mount() -> None:
            if hasattr(browser, "focus"):
                browser.focus()
            # If a pending doc was requested (e.g. from delegate browser click),
            # navigate to it now that the activity browser is mounted
            pending = getattr(self, "_pending_doc_id", None)
            if pending is not None and browser_type == "activity":
                self._pending_doc_id = None
                if hasattr(browser, "select_document_by_id"):
                    self.run_worker(browser.select_document_by_id(pending))

        self.call_after_refresh(post_mount)

        # Parent reference is set automatically by Textual during mount

        # Restore state if we have it
        if browser_type in self.browser_states and hasattr(browser, "restore_state"):
            browser.restore_state(self.browser_states[browser_type])

        self.current_browser = browser_type

        # Let each browser handle its own status updates

    async def action_switch_activity(self) -> None:
        """Switch to the Activity browser."""
        await self.switch_browser("activity")

    async def action_switch_tasks(self) -> None:
        """Switch to the Tasks browser."""
        await self.switch_browser("task")

    async def action_switch_delegates(self) -> None:
        """Switch to the Delegate browser."""
        await self.switch_browser("delegate")

    async def action_quit(self) -> None:
        """Quit the application."""
        logger.debug("action_quit called")
        self.exit()

    async def on_activity_view_view_document(self, event: Any) -> None:
        """Handle ViewDocument message from ActivityView - switch to document browser."""
        await self._view_document(event.doc_id)

    async def _view_document(self, doc_id: int) -> None:
        """Switch to activity browser and view a specific document."""
        logger.debug(f"Viewing doc #{doc_id}")

        # Switch to activity browser (docs are viewable there)
        await self.switch_browser("activity")

        # Try to select the document in the browser
        activity_browser = self.browsers.get("activity")
        if activity_browser and hasattr(activity_browser, "select_document_by_id"):
            await activity_browser.select_document_by_id(doc_id)

    async def on_key(self, event: events.Key) -> None:
        """Global key routing - handle screen switching and browser-specific keys."""
        key = event.key

        # Debug key - dump widget tree
        if key == "ctrl+d":
            self._dump_widget_tree()
            event.stop()
            return

        # Don't handle q when a modal screen is active — let the modal handle it
        if key == "q" and len(self.screen_stack) > 1:
            return

        # Q to quit from activity, task, or delegate browser
        if key == "q" and self.current_browser in ["activity", "task", "delegate"]:
            logger.debug(f"Q pressed in {self.current_browser} - exiting")
            self.exit()
            event.stop()
            return

        # Q from sub-browsers goes back to activity (the new default)
        if key == "q" and self.current_browser in ["log"]:
            await self.switch_browser("activity")
            event.stop()
            return

        # Don't handle any other keys - let them bubble to browsers

    async def view_document_fullscreen(self, doc_id: int) -> None:
        """View a document fullscreen - switch to document browser and open it."""
        await self._view_document(doc_id)

    async def _show_document_preview(self, doc_id: int) -> None:
        """Show document in a fullscreen preview."""
        from emdx.ui.modals import DocumentPreviewScreen

        def on_preview_result(result: dict | None) -> None:
            if result:
                import asyncio

                asyncio.create_task(self._handle_preview_result(result))

        self.push_screen(DocumentPreviewScreen(doc_id), on_preview_result)

    async def _handle_preview_result(self, result: dict) -> None:
        """Handle result from document preview modal."""
        action = result.get("action")
        doc_id = result.get("doc_id")

        if action == "edit" and doc_id:
            # Open in document browser for editing
            await self._view_document(doc_id)
        elif action == "open_full" and doc_id:
            # Open in document browser
            await self._view_document(doc_id)

    def _dump_widget_tree(self) -> None:
        """Debug function to dump the widget tree and regions (ctrl+d)."""
        lines = [f"Screen size={self.screen.size} region={self.screen.region}"]

        def dump_widget(widget: Any, indent: int = 0) -> None:
            prefix = "  " * indent
            lines.append(
                f"{prefix}{widget.__class__.__name__} id={widget.id} region={widget.region}"
            )  # noqa: E501
            for child in widget.children:
                dump_widget(child, indent + 1)

        dump_widget(self.screen)
        logger.debug("Widget tree:\n%s", "\n".join(lines))

    def action_cycle_theme(self) -> None:
        """Open theme selector modal."""
        from emdx.ui.theme_selector import ThemeSelectorScreen

        def on_theme_selected(theme_name: str | None) -> None:
            if theme_name:
                self.notify(f"Theme: {theme_name}", timeout=2)

        self.push_screen(ThemeSelectorScreen(), on_theme_selected)

    def action_open_command_palette(self) -> None:
        """Open the command palette modal."""
        import asyncio

        try:
            from emdx.ui.command_palette import CommandPaletteScreen

            def on_palette_result(result: dict | None) -> None:
                if result:
                    asyncio.create_task(self._handle_palette_result(result))

            self.push_screen(CommandPaletteScreen(), on_palette_result)

        except Exception as e:
            logger.error(f"Failed to open command palette: {e}", exc_info=True)
            raise

    async def _handle_palette_result(self, result: dict) -> None:
        """Handle a result from the command palette."""
        action = result.get("action")

        if action == "view_document":
            doc_id = result.get("doc_id")
            if doc_id:
                current = self.browsers.get(self.current_browser)
                if current and hasattr(current, "select_document_by_id"):
                    await current.select_document_by_id(doc_id)
                else:
                    await self._view_document(doc_id)

        elif action == "command":
            command_id = result.get("command_id")
            if command_id:
                await self._execute_palette_command(command_id)

    async def _execute_palette_command(self, command_id: str) -> None:
        """Execute a command from the palette by ID."""
        logger.debug(f"Palette command: {command_id}")

        # Navigation commands
        if command_id == "nav.activity":
            await self.switch_browser("activity")
        elif command_id == "nav.tasks":
            await self.switch_browser("task")
        elif command_id == "nav.delegates":
            await self.switch_browser("delegate")
        elif command_id == "nav.logs":
            await self.switch_browser("log")

        # Theme command
        elif command_id == "theme.select":
            self.action_cycle_theme()

        # App commands
        elif command_id == "app.refresh":
            current = self.browsers.get(self.current_browser)
            if current and hasattr(current, "action_refresh"):
                await current.action_refresh()
        elif command_id == "app.help":
            current = self.browsers.get(self.current_browser)
            if current and hasattr(current, "action_show_help"):
                current.action_show_help()
        elif command_id == "app.quit":
            self.exit()

        else:
            logger.warning(f"Unknown command: {command_id}")

    def action_toggle_theme(self) -> None:
        """Quick toggle between dark and light theme."""
        current_theme = self.theme
        new_theme = get_opposite_theme(current_theme)

        # Apply the new theme
        self.theme = new_theme
        set_theme(new_theme)

        # Show indicator
        mode = "🌙 Dark" if is_dark_theme(new_theme) else "☀️ Light"
        logger.debug(f"Theme toggled: {current_theme} -> {new_theme}")
        self.notify(f"{mode} mode", timeout=1.5)

    def action_open_url(self, url: str) -> None:
        """Open a URL in the default browser (used by @click meta on links)."""
        import webbrowser

        webbrowser.open(url)
        self.notify(f"Opened {url[:60]}", timeout=2)

    def action_select_doc(self, doc_id: int) -> None:
        """Navigate to a document by ID (used by @click meta on doc refs).

        IMPORTANT: This must be synchronous because Textual's @click meta
        actions are dispatched synchronously. An async action that mutates
        the DOM (remove_children/mount) during a click handler will deadlock
        the message loop and freeze the TUI. Instead we store the target
        doc ID and use run_worker to perform the async switch outside the
        click handler's call stack.
        """
        self._pending_doc_id = doc_id
        self.notify(f"Opening doc #{doc_id}...", timeout=1.5)

        async def _navigate() -> None:
            activity = self.browsers.get("activity")
            if (
                self.current_browser == "activity"
                and activity
                and hasattr(activity, "select_document_by_id")
            ):
                await activity.select_document_by_id(doc_id)
                self._pending_doc_id = None
            else:
                await self.switch_browser("activity")
                # switch_browser's post_mount callback handles _pending_doc_id

        self.run_worker(_navigate(), exclusive=True)
