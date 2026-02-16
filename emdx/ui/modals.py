#!/usr/bin/env python3
"""
Modal screens for EMDX TUI.
"""

import logging
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Log, RichLog, Static

logger = logging.getLogger(__name__)


class KeybindingsHelpScreen(ModalScreen[None]):
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

    def __init__(
        self,
        bindings: list[tuple[str, str, str]] | None = None,
        title: str = "Keybindings",
    ):
        """Initialize help screen.

        Args:
            bindings: List of (section, key, description) tuples.
                      If None, uses default Activity view bindings.
            title: Title for the help dialog.
        """
        super().__init__()
        self.title = title
        self.bindings_data = bindings or self._default_bindings()

    def _default_bindings(self) -> list[tuple[str, str, str]]:
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

    def on_key(self, event: events.Key) -> None:
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
    HELP_CATEGORIES: dict[str, str] = {}  # action_name -> category

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

    def get_help_bindings(self) -> list[tuple[str, str, str]]:
        """Get bindings formatted for help display.

        Returns list of (category, key, description) tuples.
        Override this method for full customization.
        """
        bindings_list = []
        categories = {**self._DEFAULT_CATEGORIES, **self.HELP_CATEGORIES}

        # Get BINDINGS from the class
        raw_bindings = getattr(self, "BINDINGS", [])

        for binding in raw_bindings:
            # Handle both tuple and Binding object formats
            if hasattr(binding, "key"):
                # Textual Binding object
                key = binding.key
                action = binding.action
                description = binding.description
                show = getattr(binding, "show", True)
            else:
                # Tuple format: (key, action, description)
                key, action, description = binding[:3]
                show = True

            # Skip hidden bindings
            if not show:
                continue

            # Skip internal actions
            if action in ("close", "cancel"):
                continue

            # Get category
            category = categories.get(action, "Other")

            # Format key for display
            display_key = self._KEY_DISPLAY.get(key, key)

            bindings_list.append((category, display_key, description))

        # Sort by category, then by key
        category_order = [
            "Navigation",
            "Actions",
            "Editing",
            "Tags",
            "Search",
            "View",
            "Other",
            "General",
        ]  # noqa: E501

        def sort_key(item: tuple[str, str, str]) -> tuple[int, str]:
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
        title = getattr(self, "HELP_TITLE", "Keybindings")
        self.app.push_screen(KeybindingsHelpScreen(bindings=bindings, title=title))  # type: ignore[attr-defined]


class DocumentPreviewScreen(Screen):
    """Full-screen document preview with copy mode toggle."""

    CSS = """
    DocumentPreviewScreen {
        layout: vertical;
    }

    #preview-header {
        height: 2;
        padding: 0 2;
        background: $surface-darken-1;
    }

    #preview-title {
        text-style: bold;
    }

    #preview-meta {
        color: $text-muted;
    }

    #preview-rendered {
        height: 1fr;
        padding: 0 2;
    }

    #preview-copy {
        height: 1fr;
        padding: 0 2;
        display: none;
    }

    #preview-footer {
        height: 1;
        background: $surface-darken-1;
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("e", "edit", "Edit"),
        Binding("c", "toggle_copy_mode", "Copy Mode"),
    ]

    def __init__(self, doc_id: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.doc_id = doc_id
        self._doc_data: dict[str, Any] | None = None
        self._raw_content: str = ""
        self._copy_mode = False

    def compose(self) -> ComposeResult:
        with Vertical(id="preview-header"):
            yield Static("Loading...", id="preview-title")
            yield Static("", id="preview-meta")
        yield RichLog(
            id="preview-rendered",
            highlight=True,
            markup=True,
            wrap=True,
            auto_scroll=False,
        )
        yield Log(
            id="preview-copy",
            highlight=True,
            auto_scroll=False,
        )
        yield Static(
            "Esc/q=Close │ e=Edit │ c=Copy Mode",
            id="preview-footer",
        )

    async def on_mount(self) -> None:
        """Load and display the document."""
        try:
            from emdx.services.document_service import get_document

            result = get_document(self.doc_id)
            self._doc_data = dict(result) if result else None
            if not self._doc_data:
                self.query_one("#preview-title", Static).update(
                    f"Document #{self.doc_id} not found"
                )
                return

            title = self._doc_data.get("title", "Untitled")
            self.query_one("#preview-title", Static).update(title)

            meta_parts = []
            if self._doc_data.get("project"):
                meta_parts.append(f"Project: {self._doc_data['project']}")
            meta_parts.append(f"ID: #{self.doc_id}")
            self.query_one("#preview-meta", Static).update(" │ ".join(meta_parts))

            content = self._doc_data.get("content", "")
            if len(content) > 50000:
                content = content[:50000]
            self._raw_content = content

            rendered = self.query_one("#preview-rendered", RichLog)
            if content.strip():
                try:
                    from .markdown_config import MarkdownConfig

                    md = MarkdownConfig.create_markdown(content)
                    rendered.write(md)
                except Exception:
                    rendered.write(content)
            else:
                rendered.write("[dim]Empty document[/dim]")

        except Exception as e:
            logger.error(f"Error loading document preview: {e}")
            self.query_one("#preview-title", Static).update(f"Error: {e}")

    def action_close(self) -> None:
        """Close the preview and return to previous screen."""
        self.dismiss(None)

    def action_edit(self) -> None:
        """Edit the document."""
        self.dismiss({"action": "edit", "doc_id": self.doc_id})

    def action_toggle_copy_mode(self) -> None:
        """Toggle between rendered preview and selectable copy mode."""
        rendered = self.query_one("#preview-rendered", RichLog)
        copy_log = self.query_one("#preview-copy", Log)
        footer = self.query_one("#preview-footer", Static)

        self._copy_mode = not self._copy_mode
        if self._copy_mode:
            copy_log.clear()
            if self._raw_content.strip():
                copy_log.write(self._raw_content)
            rendered.display = False
            copy_log.display = True
            footer.update(
                "Esc/q=Close │ e=Edit │ c=Preview Mode │ "
                "[bold]COPY MODE[/bold] - select text with mouse"
            )
        else:
            rendered.display = True
            copy_log.display = False
            footer.update("Esc/q=Close │ e=Edit │ c=Copy Mode")
