"""File browser widget for EMDX TUI."""

import logging
from pathlib import Path
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Static, TextArea

from .file_list import FileList
from .file_preview import FilePreview

logger = logging.getLogger(__name__)


class FileEditTextArea(TextArea):
    """TextArea for file editing that handles ESC key."""

    def __init__(self, file_browser, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_browser = file_browser

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            # Let the FileBrowser handle ESC
            self.file_browser.action_handle_escape()
            event.stop()
            return
        # TextArea doesn't have on_key method, so we don't call super()


class FileBrowserVimApp:
    """Mock app instance for vim editor in file browser context."""

    def __init__(self, file_browser):
        self.file_browser = file_browser

    def action_save_and_exit_edit(self):
        try:
            # Call _exit_edit_mode directly since action_handle_escape doesn't exist
            self.file_browser._exit_edit_mode()
        except AttributeError as e:
            # Fallback if file_browser not accessible
            logger.error(f"FileBrowserVimApp: Cannot access file_browser._exit_edit_mode: {e}")
            pass

    def action_cancel_edit(self):
        try:
            self.file_browser.action_handle_escape()
        except AttributeError:
            # Fallback if file_browser not accessible
            self.file_browser._exit_edit_mode()

    def action_save_document(self):
        # Just update status - file will be saved when exiting
        pass

    def _update_vim_status(self, message=""):
        # Update file browser status with vim info
        try:
            if hasattr(self.file_browser, 'vim_editor'):
                mode = self.file_browser.vim_editor.vim_mode
                if message:
                    status = f"📝 VIM {mode}: {message}"
                else:
                    status = f"📝 VIM {mode} - ESC to save and exit"
                self.file_browser.query_one("#file-status-bar", Static).update(status)
        except Exception as e:
            logger.debug(f"Error updating vim status: {e}")


class FileSelectionTextArea(TextArea):
    """TextArea for file selection that handles ESC key."""
    
    def __init__(self, file_browser, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_browser = file_browser
    
    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            # Let the FileBrowser handle ESC
            self.file_browser.action_handle_escape()
            event.stop()
            return
        # TextArea doesn't have on_key method, so we don't call super()


class FileBrowser(Container):
    """File browser widget with dual-pane layout."""
    
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
        except:
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
            pass  # Widgets not ready yet
    
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
            pass  # Widgets not ready yet
    
    def action_move_down(self) -> None:
        """Move selection down."""
        try:
            file_list = self.query_one("#file-list", FileList)
            if self.selected_index < len(file_list.files) - 1:
                self.selected_index += 1
        except Exception:
            pass
    
    def action_move_up(self) -> None:
        """Move selection up."""
        if self.selected_index > 0:
            self.selected_index -= 1
    
    def action_go_top(self) -> None:
        """Go to first item."""
        self.selected_index = 0
    
    def action_go_bottom(self) -> None:
        """Go to last item."""
        file_list = self.query_one("#file-list", FileList)
        if file_list.files:
            self.selected_index = len(file_list.files) - 1
    
    def action_enter_dir(self) -> None:
        """Enter selected directory or save file."""
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
    
    def action_parent_dir(self) -> None:
        """Go to parent directory."""
        parent = self.current_path.parent
        if parent != self.current_path:  # Not at root
            self.current_path = parent
    
    def action_toggle_hidden(self) -> None:
        """Toggle showing hidden files."""
        self.show_hidden = not self.show_hidden
    
    def action_quit(self) -> None:
        """Exit file browser."""
        # Post a quit event that the main browser can handle
        self.post_message(self.QuitFileBrowser())
    
    def action_save_file(self) -> None:
        """Save selected file to EMDX."""
        try:
            file_list = self.query_one("#file-list", FileList)
            selected = file_list.get_selected_file()
            
            if selected and selected.is_file():
                # Will be implemented with modal
                from .file_modals import SaveFileModal
                self.app.push_screen(
                    SaveFileModal(selected),
                    self.handle_save_result
                )
            else:
                self.app.bell()
        except Exception:
            pass
    
    def action_execute_file(self) -> None:
        """Execute selected file with Claude."""
        try:
            file_list = self.query_one("#file-list", FileList)
            selected = file_list.get_selected_file()
            
            if selected and selected.is_file():
                # Check if file is in EMDX first
                doc_id = self._get_file_doc_id(selected)
                
                from .file_modals import ExecuteFileModal
                self.app.push_screen(
                    ExecuteFileModal(selected, doc_id),
                    self.handle_execute_result
                )
            else:
                self.app.bell()
        except Exception:
            pass
    
    def action_edit_file(self) -> None:
        """Edit selected file in integrated editor."""
        try:
            file_list = self.query_one("#file-list", FileList)
            selected_file = file_list.get_selected_file()
            
            if not selected_file or not selected_file.is_file():
                self.query_one("#file-status-bar", Static).update(
                    "❌ No file selected for editing"
                )
                return
            
            # Exit selection mode if active
            if self.selection_mode:
                self.action_toggle_selection_mode()
            
            # Switch to edit mode
            logger.info(f"🗂️ Entering edit mode for {selected_file}")
            self.edit_mode = True
            self._switch_to_edit_mode(selected_file)
                
        except Exception as e:
            logger.error(f"🗂️ Error entering edit mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Edit mode error: {e}"
            )
    
    def _switch_to_edit_mode(self, selected_file: Path) -> None:
        """Switch preview to edit mode by replacing FilePreview widget."""
        try:
            # Read file content
            try:
                content = selected_file.read_text(encoding='utf-8', errors='ignore')
            except Exception as e:
                self.query_one("#file-status-bar", Static).update(
                    f"❌ Cannot read file: {e}"
                )
                return
            
            # Get the horizontal container that holds file-list and file-preview
            horizontal_container = self.query_one(".file-browser-content", Horizontal)
            
            # Remove the existing FilePreview
            try:
                old_preview = self.query_one("#file-preview", FilePreview)
                old_preview.remove()
            except Exception as e:
                logger.warning(f"🗂️ Could not remove old preview: {e}")
            
            # Use unified vim editor with line numbers
            from .vim_editor import VimEditor
            
            # Create mock app instance for vim editor
            vim_app = FileBrowserVimApp(self)
            
            # Create unified vim editor with line numbers
            self.vim_editor = VimEditor(
                vim_app,
                content=content,
                id="edit-preview-container",
                classes="file-preview-pane"
            )
            
            # Store file path for saving
            self.vim_editor.text_area.file_path = selected_file
            
            # Mount the vim editor
            horizontal_container.mount(self.vim_editor)
            
            # Focus after mounting
            self.call_after_refresh(lambda: self.vim_editor.focus_editor())
            
            # Update status with vim mode info
            mode = self.vim_editor.vim_mode
            self.query_one("#file-status-bar", Static).update(
                f"📝 VIM {mode}: {selected_file.name} - ESC to save and exit"
            )
            
        except Exception as e:
            logger.error(f"🗂️ Error switching to edit mode: {e}")
            raise
    
    def action_handle_escape(self) -> None:
        """Handle escape key - exit current mode."""
        if self.edit_mode:
            self._exit_edit_mode()
        elif self.selection_mode:
            self._exit_selection_mode()
        else:
            # If not in any special mode, exit file browser back to main
            self.action_quit()
    
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

        # For all other keys, use default handling
        super().on_key(event)

    def _exit_edit_mode(self) -> None:
        """Exit edit mode and save file."""
        try:
            # Save and exit using vim editor
            if hasattr(self, 'vim_editor'):
                self.save_and_exit_edit_mode(self.vim_editor.text_area)
            self.edit_mode = False

        except Exception as e:
            logger.error(f"🗂️ Error exiting edit mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Exit edit mode error: {e}"
            )

    def _exit_selection_mode(self) -> None:
        """Exit selection mode and return to preview."""
        try:
            file_list = self.query_one("#file-list", FileList)
            selected_file = file_list.get_selected_file()

            if selected_file:
                # Use the existing toggle method to exit selection mode
                self.selection_mode = False
                self._switch_to_formatted_mode(None, selected_file)
            
        except Exception as e:
            logger.error(f"🗂️ Error exiting selection mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Exit selection mode error: {e}"
            )
    
    def save_and_exit_edit_mode(self, edit_area) -> None:
        """Save edited file and exit edit mode."""
        try:
            if not hasattr(edit_area, 'file_path'):
                logger.error("🗂️ Edit area missing file_path")
                return
            
            file_path = edit_area.file_path
            new_content = edit_area.text
            
            # Save file
            try:
                file_path.write_text(new_content, encoding='utf-8')
                logger.info(f"🗂️ Saved file: {file_path}")
            except Exception as e:
                self.query_one("#file-status-bar", Static).update(
                    f"❌ Save failed: {e}"
                )
                return
            
            # Exit edit mode - restore FilePreview widget
            horizontal_container = self.query_one(".file-browser-content", Horizontal)
            
            # Reset edit mode flag
            self.edit_mode = False
            if hasattr(self, "vim_editor"):
                delattr(self, "vim_editor")
            
            # Use call_after_refresh to ensure proper widget cleanup and recreation
            def _recreate_widgets():
                try:
                    # Save current cursor position
                    current_cursor_row = self.selected_index
                    
                    # Remove vim editor widget if it exists
                    try:
                        vim_editor = self.query_one("#edit-preview-container")
                        vim_editor.remove()
                    except Exception:
                        pass
                    
                    # Just recreate the FilePreview widget to replace the vim editor
                    from .file_preview import FilePreview
                    new_preview = FilePreview(id="file-preview", classes="file-preview-pane")
                    
                    # Mount the new preview widget
                    horizontal_container.mount(new_preview)
                    
                    # Refresh the existing file list and restore cursor position
                    try:
                        file_list = self.query_one("#file-list", FileList)
                        file_list.populate_files(self.current_path, self.show_hidden)
                        
                        # Restore cursor position carefully to avoid infinite loops
                        if file_list.row_count > current_cursor_row:
                            # Use call_after_refresh to ensure populate_files is complete
                            def _restore_cursor():
                                try:
                                    self.selected_index = current_cursor_row
                                except Exception as e:
                                    logger.error(f"🗂️ Error restoring cursor: {e}")
                            self.call_after_refresh(_restore_cursor)
                    except Exception as e:
                        logger.error(f"🗂️ Error refreshing file list: {e}")
                    
                    # Preview the file after everything is mounted
                    self.call_after_refresh(lambda: self._preview_after_save(new_preview, file_path))
                    
                except Exception as e:
                    logger.error(f"🗂️ Error recreating widgets: {e}")
                    
            self.call_after_refresh(_recreate_widgets)
            
        except Exception as e:
            logger.error(f"🗂️ Error saving and exiting edit mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Save error: {e}"
            )
    
    def _preview_after_save(self, new_preview, file_path):
        """Preview file after saving and widget recreation."""
        try:
            new_preview.preview_file(file_path)
            # Ensure preview starts at the top
            new_preview.scroll_to(0, 0, animate=False)
            
            # Update status with success message
            try:
                file_count = len(self.query_one("#file-list", FileList).files)
                status = f"✅ Saved {file_path.name} - {file_count} items"
                if not self.show_hidden:
                    status += " (hidden files excluded)"
                self.query_one("#file-status-bar", Static).update(status)
            except Exception as e:
                logger.error(f"🗂️ Error updating status after save: {e}")
                
        except Exception as e:
            logger.error(f"🗂️ Error in delayed preview after save: {e}")
    
    def action_search(self) -> None:
        """Search for files."""
        # TODO: Implement search
        self.query_one("#file-status-bar", Static).update(
            "Search coming soon..."
        )
    
    def action_toggle_selection_mode(self) -> None:
        """Toggle between formatted view and text selection mode."""
        try:
            file_list = self.query_one("#file-list", FileList)
            selected_file = file_list.get_selected_file()
            
            if not selected_file or not selected_file.is_file():
                self.query_one("#file-status-bar", Static).update(
                    "❌ No file selected for text selection"
                )
                return
            
            preview_container = self.query_one("#file-preview", FilePreview)
            
            if not self.selection_mode:
                logger.info("🗂️ Entering selection mode")
                self.selection_mode = True
                self._switch_to_selection_mode(preview_container, selected_file)
            else:
                logger.info("🗂️ Exiting selection mode")
                self.selection_mode = False
                self._switch_to_formatted_mode(preview_container, selected_file)
                
        except Exception as e:
            logger.error(f"🗂️ Error toggling selection mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Selection mode error: {e}"
            )
    
    def _switch_to_selection_mode(self, preview_container, selected_file: Path) -> None:
        """Switch preview to selection mode by replacing FilePreview widget."""
        try:
            # Read file content
            if selected_file.suffix.lower() in {'.md', '.txt', '.py', '.js', '.json', '.yaml', '.yml'}:
                content = selected_file.read_text(encoding='utf-8', errors='ignore')
            else:
                content = f"Binary file: {selected_file.name}\nSize: {selected_file.stat().st_size} bytes"
            
            # Get the horizontal container that holds file-list and file-preview
            horizontal_container = self.query_one(".file-browser-content", Horizontal)
            
            # Remove the existing FilePreview
            try:
                old_preview = self.query_one("#file-preview", FilePreview)
                old_preview.remove()
            except Exception as e:
                logger.warning(f"🗂️ Could not remove old preview: {e}")
            
            # Create a simple container for selection with unique ID
            from textual.containers import ScrollableContainer
            
            selection_container = ScrollableContainer(id="selection-preview-container", classes="file-preview-pane")
            text_area = FileSelectionTextArea(
                self,
                text=content,
                read_only=True,
                id="selection-content"
            )
            
            # Mount the selection container and area
            horizontal_container.mount(selection_container)
            selection_container.mount(text_area)
            
            # Update status
            self.query_one("#file-status-bar", Static).update(
                "📝 SELECTION MODE: Select text with mouse, 's' to exit"
            )
            
        except Exception as e:
            logger.error(f"🗂️ Error switching to selection mode: {e}")
            raise
    
    def _switch_to_formatted_mode(self, preview_container, selected_file: Path) -> None:
        """Switch preview back to formatted mode."""
        try:
            # Get the horizontal container that holds file-list and file-preview
            horizontal_container = self.query_one(".file-browser-content", Horizontal)
            
            # Remove the selection container
            selection_container = self.query_one("#selection-preview-container")
            selection_container.remove()
            
            # Recreate the FilePreview widget
            from .file_preview import FilePreview
            new_preview = FilePreview(id="file-preview", classes="file-preview-pane")
            horizontal_container.mount(new_preview)
            
            # Use call_after_refresh to ensure widget is mounted before previewing
            def _preview_after_mount():
                try:
                    new_preview.preview_file(selected_file)
                    # Ensure preview starts at the top
                    new_preview.scroll_to(0, 0, animate=False)
                except Exception as e:
                    logger.error(f"🗂️ Error in delayed preview: {e}")
            
            self.call_after_refresh(_preview_after_mount)
            
            # Update status  
            file_count = len(self.query_one("#file-list", FileList).files)
            status = f"{file_count} items"
            if not self.show_hidden:
                status += " (hidden files excluded)"
            self.query_one("#file-status-bar", Static).update(status)
            
        except Exception as e:
            logger.error(f"🗂️ Error switching to formatted mode: {e}")
            # Fallback: just clear and show basic info
            try:
                horizontal_container = self.query_one(".file-browser-content", Horizontal)
                fallback_container = ScrollableContainer(id="file-preview", classes="file-preview-pane")
                from textual.widgets import Static
                fallback_container.mount(Static(f"Preview of {selected_file.name}"))
                horizontal_container.mount(fallback_container)
            except Exception:
                pass
    
    def handle_save_result(self, result: Optional[dict]) -> None:
        """Handle result from save modal."""
        if result:
            try:
                if result.get('success'):
                    self.query_one("#file-status-bar", Static).update(
                        f"✅ Saved to EMDX: {result.get('title', 'Unknown')} (#{result.get('doc_id', '')})"
                    )
                    # Refresh to show checkmark
                    self.refresh_files()
                else:
                    self.query_one("#file-status-bar", Static).update(
                        f"❌ Save failed: {result.get('error', 'Unknown error')}"
                    )
            except Exception:
                pass
    
    def handle_execute_result(self, result: Optional[dict]) -> None:
        """Handle result from execute modal."""
        if result:
            try:
                if result.get('success'):
                    self.query_one("#file-status-bar", Static).update(
                        f"🚀 Execution started: {result.get('execution_id', 'Unknown')}"
                    )
                else:
                    self.query_one("#file-status-bar", Static).update(
                        f"❌ Execute failed: {result.get('error', 'Unknown error')}"
                    )
            except Exception:
                pass
    
    def _get_file_doc_id(self, file_path: Path) -> Optional[int]:
        """Get EMDX document ID if file is already saved."""
        try:
            from emdx.database import db
            
            # Check by exact filename match
            with db.get_connection() as conn:
                result = conn.execute(
                    "SELECT id FROM documents WHERE title = ? AND is_deleted = 0 ORDER BY id DESC LIMIT 1",
                    (file_path.name,)
                ).fetchone()
                
                if result:
                    return result['id']

        except Exception:
            pass

        return None

    def on_file_list_file_selected(self, event) -> None:
        """Handle file selection changes from FileList."""
        logger.info(f"🗂️ File selection changed to index {event.index}")
        self.selected_index = event.index
        self.update_preview()

    def on_key(self, event) -> None:
        """Handle key events with proper isolation from main browser."""
        # Ensure file browser handles its own keys and doesn't let them bubble to main browser
        try:
            # Log key events for debugging
            logger.debug(f"🗂️ FileBrowser received key: {event.key}")

            # If we're in edit or selection mode, ensure keys don't bubble up
            if self.edit_mode or self.selection_mode:
                event.stop()

        except Exception as e:
            logger.error(f"🗂️ Error in FileBrowser key handling: {e}")

    class QuitFileBrowser(events.Event):
        """Event sent when quitting file browser."""
        pass
