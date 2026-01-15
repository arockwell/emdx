"""Inline group picker for Activity view.

Appears at the bottom of the view when pressing 'g' on a document.
Allows filtering and selecting a group to add the document to,
or creating a new group.
"""

import logging
from typing import Callable, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

logger = logging.getLogger(__name__)

# Import groups database
try:
    from emdx.database import groups as groups_db
    HAS_GROUPS = True
except ImportError:
    groups_db = None
    HAS_GROUPS = False


class GroupPicker(Widget):
    """Inline group picker widget.

    Shows at the bottom of the Activity view with:
    - Input field for filtering/creating groups
    - List of matching groups
    - Keyboard navigation
    """

    class GroupSelected(Message):
        """Fired when a group is selected."""
        def __init__(self, group_id: int, group_name: str, doc_id: Optional[int], source_group_id: Optional[int]) -> None:
            self.group_id = group_id
            self.group_name = group_name
            self.doc_id = doc_id
            self.source_group_id = source_group_id
            super().__init__()

    class GroupCreated(Message):
        """Fired when a new group is created."""
        def __init__(self, group_id: int, group_name: str, doc_id: Optional[int], source_group_id: Optional[int]) -> None:
            self.group_id = group_id
            self.group_name = group_name
            self.doc_id = doc_id
            self.source_group_id = source_group_id
            super().__init__()

    class Cancelled(Message):
        """Fired when picker is cancelled."""
        pass

    DEFAULT_CSS = """
    GroupPicker {
        height: auto;
        max-height: 12;
        dock: bottom;
        background: $surface;
        border-top: solid $primary;
        padding: 0 1;
        display: none;
    }

    GroupPicker.visible {
        display: block;
    }

    GroupPicker #group-input {
        width: 100%;
        height: 3;
        margin-bottom: 0;
    }

    GroupPicker #group-list {
        height: auto;
        max-height: 8;
        padding: 0;
    }

    GroupPicker .group-item {
        height: 1;
        padding: 0 1;
    }

    GroupPicker .group-item.selected {
        background: $accent;
    }

    GroupPicker #group-hint {
        height: 1;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.groups: list[dict] = []
        self.filtered_groups: list[dict] = []
        self.selected_index: int = 0
        self.doc_id: Optional[int] = None
        self.source_group_id: Optional[int] = None  # When nesting a group
        self._visible = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type group name to filter or create...", id="group-input")
        yield Static("", id="group-list")
        yield Static("↑↓ Navigate | Enter Select | Tab Create new | Esc Cancel", id="group-hint")

    def show(self, doc_id: Optional[int] = None, source_group_id: Optional[int] = None) -> None:
        """Show the picker for a document or group.

        Args:
            doc_id: Document to add to a group
            source_group_id: Group to nest under another group
        """
        self.doc_id = doc_id
        self.source_group_id = source_group_id
        self._visible = True
        self.add_class("visible")
        self._load_groups()
        self._update_list()

        # Focus the input
        input_widget = self.query_one("#group-input", Input)
        input_widget.value = ""
        input_widget.focus()

    def hide(self) -> None:
        """Hide the picker."""
        self._visible = False
        self.remove_class("visible")
        self.doc_id = None
        self.source_group_id = None

    def _load_groups(self) -> None:
        """Load recent groups from database."""
        if not HAS_GROUPS or not groups_db:
            self.groups = []
            return

        try:
            # Get all active groups, sorted by most recently used
            all_groups = groups_db.list_groups(include_inactive=False)
            # Exclude the source group if nesting (can't nest under itself)
            if self.source_group_id:
                self.groups = [g for g in all_groups if g["id"] != self.source_group_id]
            else:
                self.groups = all_groups
            self.filtered_groups = self.groups.copy()
            self.selected_index = 0
        except Exception as e:
            logger.error(f"Error loading groups: {e}")
            self.groups = []
            self.filtered_groups = []

    def _filter_groups(self, query: str) -> None:
        """Filter groups by query."""
        if not query:
            self.filtered_groups = self.groups.copy()
        else:
            query_lower = query.lower()
            self.filtered_groups = [
                g for g in self.groups
                if query_lower in g["name"].lower()
            ]
        self.selected_index = 0
        self._update_list()

    def _update_list(self) -> None:
        """Update the displayed list."""
        list_widget = self.query_one("#group-list", Static)

        if not self.filtered_groups:
            input_widget = self.query_one("#group-input", Input)
            if input_widget.value:
                list_widget.update(f"  [dim]Press Tab to create '[/dim]{input_widget.value}[dim]'[/dim]")
            else:
                list_widget.update("  [dim]No groups yet. Type a name and press Tab to create.[/dim]")
            return

        lines = []
        for i, group in enumerate(self.filtered_groups[:8]):  # Show max 8
            prefix = "▶ " if i == self.selected_index else "  "
            type_icons = {
                "initiative": "📋",
                "round": "🔄",
                "batch": "📦",
                "session": "💾",
                "custom": "🏷️",
            }
            icon = type_icons.get(group.get("group_type", "batch"), "📁")
            doc_count = group.get("doc_count", 0)
            name = group["name"][:40]

            if i == self.selected_index:
                lines.append(f"[reverse]{prefix}{icon} {name} ({doc_count} docs)[/reverse]")
            else:
                lines.append(f"{prefix}{icon} {name} [dim]({doc_count} docs)[/dim]")

        if len(self.filtered_groups) > 8:
            lines.append(f"  [dim]... and {len(self.filtered_groups) - 8} more[/dim]")

        list_widget.update("\n".join(lines))

    def _select_current(self) -> None:
        """Select the currently highlighted group."""
        if not self.filtered_groups or self.selected_index >= len(self.filtered_groups):
            return

        group = self.filtered_groups[self.selected_index]
        doc_id = self.doc_id  # Capture before hide() clears it
        source_group_id = self.source_group_id
        self.hide()
        self.post_message(self.GroupSelected(group["id"], group["name"], doc_id, source_group_id))

    def _create_new_group(self, name: str) -> None:
        """Create a new group with the given name."""
        if not name.strip():
            return

        if not HAS_GROUPS or not groups_db:
            return

        try:
            doc_id = self.doc_id  # Capture before hide() clears it
            source_group_id = self.source_group_id
            group_id = groups_db.create_group(
                name=name.strip(),
                group_type="batch",  # Default to batch
            )
            self.hide()
            self.post_message(self.GroupCreated(group_id, name.strip(), doc_id, source_group_id))
        except Exception as e:
            logger.error(f"Error creating group: {e}")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "group-input":
            self._filter_groups(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in input."""
        if event.input.id == "group-input":
            if self.filtered_groups:
                self._select_current()
            elif event.value.strip():
                # No matches - create new group
                self._create_new_group(event.value)

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.post_message(self.Cancelled())
            self.hide()
            event.stop()
        elif event.key == "tab":
            # Create new group with current input
            input_widget = self.query_one("#group-input", Input)
            if input_widget.value.strip():
                self._create_new_group(input_widget.value)
                event.stop()
        elif event.key in ("up", "k"):
            if self.selected_index > 0:
                self.selected_index -= 1
                self._update_list()
            event.stop()
        elif event.key in ("down", "j"):
            if self.selected_index < len(self.filtered_groups) - 1:
                self.selected_index += 1
                self._update_list()
            event.stop()
        elif event.key == "enter":
            if self.filtered_groups:
                self._select_current()
            else:
                input_widget = self.query_one("#group-input", Input)
                if input_widget.value.strip():
                    self._create_new_group(input_widget.value)
            event.stop()

    @property
    def is_visible(self) -> bool:
        """Check if picker is visible."""
        return self._visible
