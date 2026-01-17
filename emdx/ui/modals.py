#!/usr/bin/env python3
"""
Modal screens for EMDX TUI.
"""

import logging
from typing import List, Tuple

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

# Set up logging for debugging
logger = logging.getLogger(__name__)
key_logger = logging.getLogger("key_events")



class DeleteConfirmScreen(ModalScreen):
    """Modal screen for delete confirmation."""

    CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }

    #dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 0 2;
        width: 60;
        height: 11;
        border: thick $background 80%;
        background: $surface;
    }

    #question {
        column-span: 2;
        height: 3;
        content-align: center middle;
        text-style: bold;
    }

    Button {
        width: 100%;
    }
    """

    BINDINGS = [
        ("y", "confirm_delete", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, doc_id: int, doc_title: str):
        super().__init__()
        self.doc_id = doc_id
        self.doc_title = doc_title
        logger.info(f"DeleteConfirmScreen initialized for doc #{doc_id}: {doc_title}")

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(
                f'Delete document #{self.doc_id}?\n"{self.doc_title}"\n\n'
                f"[dim]Press [bold]y[/bold] to delete, [bold]n[/bold] to cancel[/dim]",
                id="question",
            )
            yield Button("Cancel (n)", variant="primary", id="cancel")
            yield Button("Delete (y)", variant="error", id="delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.info(f"Button pressed: {event.button.id}")
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_delete(self) -> None:
        logger.info("action_confirm_delete called")
        self.dismiss(True)

    def action_cancel(self) -> None:
        logger.info("action_cancel called")
        self.dismiss(False)
    
    def on_dismiss(self, result) -> None:
        """Log when modal is dismissed."""
        logger.info(f"DeleteConfirmScreen dismissed with result: {result}")

    def on_mount(self) -> None:
        """Ensure modal has focus when mounted."""
        logger.info(f"DeleteConfirmScreen mounted for doc #{self.doc_id}")
        self.focus()
        # Log the current screen stack for debugging
        if hasattr(self.app, 'screen_stack'):
            logger.info(f"Screen stack after mount: {len(self.app.screen_stack)} screens")

    def on_key(self, event) -> None:
        """Log key events for debugging."""
        key_logger.info(f"DeleteConfirmScreen.on_key: key={event.key}, character={event.character}")
        # Don't consume the event - let bindings handle it
        # Important: Don't call event.stop() or event.prevent_default() here
        # as that would prevent the bindings from working


class KeybindingsHelpScreen(ModalScreen):
    """Modal screen showing available keybindings."""

    CSS = """
    KeybindingsHelpScreen {
        align: center middle;
    }

    #help-dialog {
        padding: 1 2;
        width: 50;
        height: auto;
        max-height: 80%;
        border: thick $background 80%;
        background: $surface;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    .help-section {
        padding-top: 1;
    }

    .help-section-title {
        text-style: bold;
        color: $accent;
    }

    .help-row {
        padding-left: 2;
    }

    .help-key {
        text-style: bold;
        color: $text;
        width: 12;
    }

    .help-desc {
        color: $text-muted;
    }

    #help-footer {
        text-align: center;
        padding-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, bindings: List[Tuple[str, str, str]] = None, title: str = "Keybindings"):
        """Initialize help screen.

        Args:
            bindings: List of (section, key, description) tuples.
                      If None, uses default Activity view bindings.
            title: Title for the help dialog.
        """
        super().__init__()
        self.title = title
        self.bindings_data = bindings or self._default_bindings()

    def _default_bindings(self) -> List[Tuple[str, str, str]]:
        """Default keybindings for Activity view."""
        return [
            ("Navigation", "j / k", "Move down / up"),
            ("Navigation", "Enter", "Expand / collapse"),
            ("Navigation", "l / h", "Expand / collapse"),
            ("Navigation", "Tab", "Next pane"),
            ("Actions", "i", "Copy document (gist)"),
            ("Actions", "g", "Add to group"),
            ("Actions", "G", "Create new group"),
            ("Actions", "u", "Remove from group"),
            ("Actions", "f", "Fullscreen preview"),
            ("Actions", "r", "Refresh"),
            ("General", "?", "Show this help"),
            ("General", "q", "Quit"),
        ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(f"─── {self.title} ───", id="help-title")

            # Group bindings by section
            current_section = None
            for section, key, desc in self.bindings_data:
                if section != current_section:
                    current_section = section
                    yield Static(f"[bold $accent]{section}[/]", classes="help-section-title")

                yield Static(f"  [bold]{key:<10}[/] [dim]{desc}[/]", classes="help-row")

            yield Static("Press ? or Esc to close", id="help-footer")

    def action_close(self) -> None:
        self.dismiss()

    def on_key(self, event) -> None:
        # Close on any key for convenience
        if event.key not in ("escape", "question_mark", "q"):
            # Let specific bindings handle their keys
            pass


class HelpMixin:
    """Mixin to add ? keybinding help to any widget.

    Usage:
        class MyWidget(HelpMixin, Widget):
            BINDINGS = [...]

            # Optional: Override to customize help
            HELP_TITLE = "My Widget"
            HELP_CATEGORIES = {
                "cursor_down": "Navigation",
                "cursor_up": "Navigation",
                ...
            }

    The mixin will auto-generate help from BINDINGS, or you can
    override get_help_bindings() for full control.
    """

    # Override these in subclasses for customization
    HELP_TITLE: str = "Keybindings"
    HELP_CATEGORIES: dict = {}  # action_name -> category

    # Default category mappings for common actions
    _DEFAULT_CATEGORIES = {
        # Navigation
        "cursor_down": "Navigation",
        "cursor_up": "Navigation",
        "cursor_top": "Navigation",
        "cursor_bottom": "Navigation",
        "expand": "Navigation",
        "collapse": "Navigation",
        "expand_children": "Navigation",
        "collapse_children": "Navigation",
        "select": "Navigation",
        "focus_next": "Navigation",
        "focus_prev": "Navigation",
        # Actions
        "create_gist": "Actions",
        "add_to_group": "Actions",
        "create_group": "Actions",
        "ungroup": "Actions",
        "fullscreen": "Actions",
        "refresh": "Actions",
        "edit_document": "Editing",
        "new_document": "Editing",
        "add_tags": "Tags",
        "remove_tags": "Tags",
        "search": "Search",
        "toggle_archived": "View",
        "selection_mode": "View",
        # General
        "show_help": "General",
        "quit": "General",
    }

    # Human-readable key names
    _KEY_DISPLAY = {
        "question_mark": "?",
        "escape": "Esc",
        "enter": "Enter",
        "tab": "Tab",
        "shift+tab": "Shift+Tab",
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
        "space": "Space",
    }

    def get_help_bindings(self) -> List[Tuple[str, str, str]]:
        """Get bindings formatted for help display.

        Returns list of (category, key, description) tuples.
        Override this method for full customization.
        """
        bindings_list = []
        categories = {**self._DEFAULT_CATEGORIES, **self.HELP_CATEGORIES}

        # Get BINDINGS from the class
        raw_bindings = getattr(self, 'BINDINGS', [])

        for binding in raw_bindings:
            # Handle both tuple and Binding object formats
            if hasattr(binding, 'key'):
                # Textual Binding object
                key = binding.key
                action = binding.action
                description = binding.description
                show = getattr(binding, 'show', True)
            else:
                # Tuple format: (key, action, description)
                key, action, description = binding[:3]
                show = True

            # Skip hidden bindings
            if not show:
                continue

            # Skip internal actions
            if action in ('close', 'cancel'):
                continue

            # Get category
            category = categories.get(action, "Other")

            # Format key for display
            display_key = self._KEY_DISPLAY.get(key, key)

            bindings_list.append((category, display_key, description))

        # Sort by category, then by key
        category_order = ["Navigation", "Actions", "Editing", "Tags", "Search", "View", "Other", "General"]

        def sort_key(item):
            cat = item[0]
            try:
                return (category_order.index(cat), item[1])
            except ValueError:
                return (len(category_order), item[1])

        bindings_list.sort(key=sort_key)

        # Add help binding at the end if not already present
        has_help = any(b[2] == "Show this help" or b[1] == "?" for b in bindings_list)
        if not has_help:
            bindings_list.append(("General", "?", "Show this help"))

        return bindings_list

    def action_show_help(self) -> None:
        """Show keybindings help modal."""
        bindings = self.get_help_bindings()
        title = getattr(self, 'HELP_TITLE', 'Keybindings')
        self.app.push_screen(KeybindingsHelpScreen(bindings=bindings, title=title))
