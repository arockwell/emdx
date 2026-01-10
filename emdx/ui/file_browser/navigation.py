"""Navigation mixin for FileBrowser - handles movement and directory navigation."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .view import FileBrowserView

logger = logging.getLogger(__name__)


class FileBrowserNavigation:
    """Mixin providing navigation functionality for FileBrowser.

    Handles:
    - Cursor movement (up/down/top/bottom)
    - Directory navigation (enter/parent)
    - Hidden files toggle
    """

    def action_move_down(self: "FileBrowserView") -> None:
        """Move selection down."""
        try:
            from ..file_list import FileList
            file_list = self.query_one("#file-list", FileList)
            if self.selected_index < len(file_list.files) - 1:
                self.selected_index += 1
        except Exception:
            pass

    def action_move_up(self: "FileBrowserView") -> None:
        """Move selection up."""
        if self.selected_index > 0:
            self.selected_index -= 1

    def action_go_top(self: "FileBrowserView") -> None:
        """Go to first item."""
        self.selected_index = 0

    def action_go_bottom(self: "FileBrowserView") -> None:
        """Go to last item."""
        from ..file_list import FileList
        file_list = self.query_one("#file-list", FileList)
        if file_list.files:
            self.selected_index = len(file_list.files) - 1

    def action_enter_dir(self: "FileBrowserView") -> None:
        """Enter selected directory or save file."""
        from textual.widgets import Static
        from ..file_list import FileList

        try:
            file_list = self.query_one("#file-list", FileList)
            selected = file_list.get_selected_file()

            if selected:
                if selected.is_dir():
                    try:
                        # Check if we have permission
                        list(selected.iterdir())
                        self.current_path = selected
                    except PermissionError:
                        self.app.bell()
                        self.query_one("#file-status-bar", Static).update(
                            f"Permission denied: {selected}"
                        )
                else:
                    # For files, default action is save
                    self.action_save_file()
        except Exception:
            pass

    def action_parent_dir(self: "FileBrowserView") -> None:
        """Go to parent directory."""
        parent = self.current_path.parent
        if parent != self.current_path:  # Not at root
            self.current_path = parent

    def action_toggle_hidden(self: "FileBrowserView") -> None:
        """Toggle showing hidden files."""
        self.show_hidden = not self.show_hidden
