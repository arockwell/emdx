"""FileBrowser view widget - main component combining navigation and actions."""

import logging
from pathlib import Path
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static

from ..file_list import FileList
from ..file_preview import FilePreview
from .actions import FileBrowserActions
from .navigation import FileBrowserNavigation

logger = logging.getLogger(__name__)


class FileBrowserView(FileBrowserNavigation, FileBrowserActions, Container):
    """File browser widget with dual-pane layout.

    This class combines:
    - FileBrowserNavigation: Movement and directory navigation
    - FileBrowserActions: File operations and mode switching
    """

    # Allow this widget to receive focus and handle key events
    can_focus = True

    DEFAULT_CSS = """
    .file-browser {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    .breadcrumb {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        dock: top;
    }

    .file-browser-content {
        height: 1fr;
        layout: horizontal;
    }

    .file-list-pane {
        width: 50%;
        border-right: solid $primary;
    }

    .file-preview-pane {
        width: 50%;
        padding: 0 1;
    }

    .status-bar {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
        dock: bottom;
    }

    #save-modal-container {
        align: center middle;
        background: $surface;
        border: thick $primary;
        padding: 2 4;
        width: 80;
        height: 30;
    }

    #execute-modal-container {
        align: center middle;
        background: $surface;
        border: thick $primary;
        padding: 2 4;
        width: 60;
        height: 20;
    }

    #modal-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #file-preview-container {
        height: 10;
        border: solid $primary;
        margin: 1 0;
    }

    #button-container {
        margin-top: 1;
        align: center middle;
        height: 3;
    }

    #button-container Button {
        margin: 0 1;
    }

    .success-text {
        color: $success;
    }

    .warning-text {
        color: $warning;
    }

    /* Vim editor styling */
    .constrained-textarea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
        box-sizing: border-box !important;
        padding: 0 1 !important;
    }

    .file-browser-vim-textarea {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
        box-sizing: border-box !important;
        padding: 1 1 0 1 !important;
    }

    .vim-line-numbers {
        width: 4;
        background: $background;
        color: $text-muted;
        text-align: right;
        padding-right: 1;
        padding-top: 1;
        margin: 0;
        border: none;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }

    #vim-edit-container {
        height: 100%;
        background: $background;
    }
    """

    BINDINGS = [
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("l", "enter_dir", "Enter/Right", show=False),
        Binding("h", "parent_dir", "Parent/Left", show=False),
        Binding("enter", "enter_dir", "Enter", show=False),
        Binding("g", "go_top", "Top", show=False),
        Binding("G", "go_bottom", "Bottom", show=False),
        Binding(".", "toggle_hidden", "Hidden", show=False),
        Binding("q", "quit", "Back", show=True),
        Binding("s", "toggle_selection_mode", "Select", show=True),
        Binding("x", "execute_file", "Execute", show=True),
        Binding("e", "edit_file", "Edit", show=True),
        Binding("/", "search", "Search", show=True),
    ]

    current_path = reactive(Path.cwd())
    selected_index = reactive(0)
    show_hidden = reactive(False)
    selection_mode = reactive(False)
    edit_mode = reactive(False)

    def __init__(self, start_path: Optional[Path] = None, **kwargs):
        """Initialize file browser.

        Args:
            start_path: Initial directory to browse (defaults to cwd)
        """
        logger.info(f"🗂️ Initializing FileBrowser with start_path={start_path}")
        super().__init__(**kwargs)
        if start_path and start_path.exists():
            self.current_path = start_path.resolve()
        logger.info(f"🗂️ FileBrowser current_path set to: {self.current_path}")
        self.add_class("file-browser")

    def compose(self) -> ComposeResult:
        """Compose the file browser layout."""
        with Vertical():
            # Path breadcrumb
            yield Static(str(self.current_path), id="path-breadcrumb", classes="breadcrumb")

            # Main content area
            with Horizontal(classes="file-browser-content"):
                yield FileList(id="file-list", classes="file-list-pane")
                yield FilePreview(id="file-preview", classes="file-preview-pane")

            # Status bar
            yield Static("Ready", id="file-status-bar", classes="status-bar")

    def on_mount(self) -> None:
        """Initialize when mounted."""
        logger.info(f"🗂️ FileBrowser mounted, refreshing files for {self.current_path}")
        # Use call_after_refresh to ensure widget is fully mounted
        self.call_after_refresh(self._initial_refresh)

    def _initial_refresh(self) -> None:
        """Perform initial file refresh after mounting is complete."""
        logger.info(f"🗂️ Performing initial refresh, is_mounted={self.is_mounted}")
        self.refresh_files()
        self.update_preview()

        # Set focus to file list so keys work immediately
        try:
            file_list = self.query_one("#file-list", FileList)
            file_list.focus()
        except Exception:
            # If that fails, focus the container itself
            self.focus()

    def watch_current_path(self, old_path: Path, new_path: Path) -> None:
        """React to path changes."""
        # Only refresh if we're mounted
        if self.is_mounted:
            self.refresh_files()
            try:
                self.query_one("#path-breadcrumb", Static).update(str(new_path))
            except Exception:
                pass  # Widget not ready yet
            self.selected_index = 0

    def watch_selected_index(self, old: int, new: int) -> None:
        """React to selection changes."""
        if self.is_mounted:
            try:
                file_list = self.query_one("#file-list", FileList)
                file_list.selected_index = new
                self.update_preview()
            except Exception:
                pass  # Widget not ready yet

    def watch_show_hidden(self, old: bool, new: bool) -> None:
        """React to hidden files toggle."""
        if self.is_mounted:
            self.refresh_files()

    def refresh_files(self) -> None:
        """Refresh the file listing."""
        logger.info(f"🗂️ refresh_files called, is_mounted={self.is_mounted}, path={self.current_path}")
        if not self.is_mounted:
            logger.info("🗂️ Not mounted, skipping file refresh")
            return

        try:
            logger.info("🗂️ Getting file list widget")
            file_list = self.query_one("#file-list", FileList)
            logger.info("🗂️ Calling populate_files")
            file_list.populate_files(self.current_path, self.show_hidden)

            # Update status
            file_count = len(file_list.files)
            status = f"{file_count} items"
            if not self.show_hidden:
                status += " (hidden files excluded)"
            logger.info(f"🗂️ Updating status bar with: {status}")
            self.query_one("#file-status-bar", Static).update(status)
        except Exception as e:
            logger.error(f"🗂️ Error in refresh_files: {e}")
            # Widgets not ready yet

    def update_preview(self) -> None:
        """Update the preview pane."""
        if not self.is_mounted:
            return

        try:
            file_list = self.query_one("#file-list", FileList)
            selected_file = file_list.get_selected_file()

            logger.info(f"🗂️ update_preview: selected_file={selected_file}")
            if selected_file:
                preview = self.query_one("#file-preview", FilePreview)
                logger.info(f"🗂️ Calling preview.preview_file({selected_file})")
                preview.preview_file(selected_file)
                # Ensure preview always starts at the top
                preview.scroll_to(0, 0, animate=False)
            else:
                logger.info("🗂️ No file selected for preview")
        except Exception as e:
            logger.error(f"🗂️ Error in update_preview: {e}")
            # Widgets not ready yet

    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially ESC for mode switching."""
        if event.key == "escape":
            if self.edit_mode:
                self._exit_edit_mode()
                event.stop()
                event.prevent_default()
                return
            elif self.selection_mode:
                self._exit_selection_mode()
                event.stop()
                event.prevent_default()
                return
            else:
                # If not in any special mode, exit file browser back to main
                self.action_quit()
                event.stop()
                event.prevent_default()
                return

        # Ensure file browser handles its own keys and doesn't let them bubble to main browser
        try:
            # If we're in edit or selection mode, ensure keys don't bubble up
            if self.edit_mode or self.selection_mode:
                event.stop()

        except Exception as e:
            logger.error(f"🗂️ Error in FileBrowser key handling: {e}")

    def on_file_list_file_selected(self, event) -> None:
        """Handle file selection changes from FileList."""
        self.selected_index = event.index
        self.update_preview()

    class QuitFileBrowser(events.Event):
        """Event sent when quitting file browser."""
        pass


# Backward compatibility alias
FileBrowser = FileBrowserView
