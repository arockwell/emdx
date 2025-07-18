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
from .navigation_mixin import NavigationMixin
from .selection_mixin import SelectionMixin

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
    
    def action_save_and_exit_edit(self):
        """Save and exit edit mode (called by VimEditTextArea)."""
        self.file_browser._exit_edit_mode()
        
    def _update_vim_status(self, message=""):
        # Update file browser status with vim info
        try:
            if hasattr(self.file_browser, 'vim_area'):
                mode = self.file_browser.vim_area.vim_mode
                if message:
                    status = f"📝 VIM {mode}: {message}"
                else:
                    status = f"📝 VIM {mode} - ESC to save and exit"
                self.file_browser.query_one("#file-status-bar", Static).update(status)
        except Exception as e:
            logger.debug(f"Error updating vim status: {e}")


class FileBrowser(Container, NavigationMixin, SelectionMixin):
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
        *NavigationMixin.NAVIGATION_BINDINGS,  # Include j/k/g/G navigation from mixin
        *SelectionMixin.SELECTION_BINDINGS,    # Include selection mode bindings from mixin
        Binding("l", "enter_dir", "Enter/Right", show=False),
        Binding("h", "parent_dir", "Parent/Left", show=False),
        Binding("enter", "enter_dir", "Enter", show=False),
        Binding(".", "toggle_hidden", "Hidden", show=False),
        Binding("q", "quit", "Back", show=True),
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
        
        # Initialize mixin properties
        self.selection_mode: bool = False
    
    def get_primary_table(self):
        """Return the file list for navigation."""
        try:
            return self.query_one(FileList)
        except:
            return None
    
    def get_current_document_content(self) -> str:
        """Get current file content for selection mode."""
        try:
            file_list = self.query_one(FileList)
            selected_file = file_list.get_selected_file()
            if selected_file and selected_file.is_file():
                try:
                    content = selected_file.read_text(encoding='utf-8')
                    return f"# {selected_file.name}\n\n{content}"
                except Exception as e:
                    return f"# {selected_file.name}\n\nError reading file: {e}"
            return "No file selected for copying"
        except:
            return "File browser not ready for selection"
    
    def action_toggle_selection_mode(self) -> None:
        """Override SelectionMixin to use FileBrowser's preview container."""
        try:
            # Check if we have a file selected
            file_list = self.query_one(FileList)  
            selected_file = file_list.get_selected_file()
            if not selected_file or not selected_file.is_file():
                logger.info(f"🗂️ No file selected for selection mode: {selected_file}")
                return
                
            # Get the parent container that holds both file-list and file-preview
            horizontal_container = self.query_one(".file-browser-content", Horizontal)
            app = self.app
            
            if not self.selection_mode:
                # Enter selection mode
                logger.info(f"🗂️ Entering selection mode for: {selected_file}")
                self.selection_mode = True
                self._enter_selection_mode_file_browser(horizontal_container, app)
            else:
                # Exit selection mode
                logger.info(f"🗂️ Exiting selection mode for: {selected_file}")
                self.selection_mode = False
                self._exit_selection_mode_file_browser(horizontal_container, app)
                
        except Exception as e:
            logger.error(f"🗂️ Error in file browser selection mode: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _enter_selection_mode_file_browser(self, horizontal_container, app) -> None:
        """FileBrowser-specific selection mode entry."""
        # Get content and save scroll position
        plain_content = self.get_current_document_content()
        self.saved_scroll_x = 0
        self.saved_scroll_y = 0
        
        try:
            old_preview = self.query_one("#file-preview", FilePreview)
            self.saved_scroll_x = old_preview.scroll_x
            self.saved_scroll_y = old_preview.scroll_y
            old_preview.remove()
        except:
            pass
        
        # Create selection widgets
        from .text_areas import SelectionTextArea
        from textual.containers import ScrollableContainer
        
        selection_container = ScrollableContainer(id="file-selection-container", classes="file-preview-pane")
        text_area = SelectionTextArea(self, text=plain_content, id="file-selection-content")
        text_area.read_only = True
        text_area.can_focus = True
        text_area.word_wrap = True
        
        horizontal_container.mount(selection_container)
        selection_container.mount(text_area)
        
        self.call_after_refresh(lambda: text_area.focus())
        
        if hasattr(app, 'update_status'):
            app.update_status("SELECTION MODE: Select text, Ctrl+C to copy, ESC to exit")
    
    def _exit_selection_mode_file_browser(self, horizontal_container, app) -> None:
        """FileBrowser-specific selection mode exit."""
        # Remove selection container
        try:
            self.query_one("#file-selection-container").remove()
        except:
            pass
        
        # Recreate FilePreview widget
        from .file_preview import FilePreview
        new_preview = FilePreview(id="file-preview", classes="file-preview-pane")
        horizontal_container.mount(new_preview)
        
        # Restore preview content and scroll position
        file_list = self.query_one(FileList)
        selected_file = file_list.get_selected_file()
        
        if selected_file:
            self.call_after_refresh(lambda: new_preview.preview_file(selected_file))
            
            # Restore scroll position
            scroll_x = getattr(self, 'saved_scroll_x', 0)
            scroll_y = getattr(self, 'saved_scroll_y', 0)
            self.call_after_refresh(lambda: new_preview.scroll_to(scroll_x, scroll_y, animate=False))
    
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
    
    # Navigation methods provided by NavigationMixin
    
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
        # Read file content
        try:
            content = selected_file.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            self.query_one("#file-status-bar", Static).update(f"❌ Cannot read file: {e}")
            return
        
        # Remove existing preview
        horizontal_container = self.query_one(".file-browser-content", Horizontal)
        try:
            self.query_one("#file-preview", FilePreview).remove()
        except:
            pass
        
        # Create a simple container for editing (OLD WORKING APPROACH)
        from textual.containers import ScrollableContainer
        from .text_areas import VimEditTextArea
        
        edit_container = ScrollableContainer(id="edit-preview-container", classes="file-preview-pane")
        
        # Use simple VimEditTextArea directly (what worked before)
        edit_area = VimEditTextArea(
            self,
            text=content,
            read_only=False,
            id="edit-content"
        )
        edit_area.can_focus = True
        edit_area.file_path = selected_file  # Store file path for saving
        
        # Store edit area for status updates and saving
        self.vim_area = edit_area
        
        # Mount the edit container and area (SIMPLE APPROACH)
        horizontal_container.mount(edit_container)
        edit_container.mount(edit_area)
        edit_area.focus()
        
        # Update status with vim mode info
        mode = edit_area.vim_mode
        self.query_one("#file-status-bar", Static).update(
            f"📝 VIM {mode}: {selected_file.name} - ESC to save and exit"
        )
    
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
            # Save and exit using simple vim area
            if hasattr(self, 'vim_area'):
                self.save_and_exit_edit_mode(self.vim_area)
            self.edit_mode = False
            
        except Exception as e:
            logger.error(f"🗂️ Error exiting edit mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Exit edit mode error: {e}"
            )
    
    def _exit_selection_mode(self) -> None:
        """Exit selection mode and return to preview."""
        try:
            if self.selection_mode:
                # Use the mixin-based toggle method
                self.action_toggle_selection_mode()
            
        except Exception as e:
            logger.error(f"🗂️ Error exiting selection mode: {e}")
            self.query_one("#file-status-bar", Static).update(
                f"❌ Exit selection mode error: {e}"
            )
    
    def save_and_exit_edit_mode(self, edit_area) -> None:
        """Save edited file and exit edit mode."""
        if not hasattr(edit_area, 'file_path'):
            return
        
        # Save file
        try:
            edit_area.file_path.write_text(edit_area.text, encoding='utf-8')
        except Exception as e:
            self.query_one("#file-status-bar", Static).update(f"❌ Save failed: {e}")
            return
        
        # Exit edit mode
        self.edit_mode = False
        if hasattr(self, "vim_area"):
            delattr(self, "vim_area")
        
        # Recreate widgets
        horizontal_container = self.query_one(".file-browser-content", Horizontal)
        current_cursor_row = self.selected_index
        
        # Remove vim editor and mount new preview
        try:
            self.query_one("#edit-preview-container").remove()
        except:
            pass
        
        from .file_preview import FilePreview
        new_preview = FilePreview(id="file-preview", classes="file-preview-pane")
        horizontal_container.mount(new_preview)
        
        # Refresh file list and restore cursor
        file_list = self.query_one("#file-list", FileList)
        file_list.populate_files(self.current_path, self.show_hidden)
        
        if file_list.row_count > current_cursor_row:
            self.call_after_refresh(lambda: setattr(file_list, 'cursor_coordinate', (current_cursor_row, 0)))
        
        # Preview the file
        self.call_after_refresh(lambda: self._preview_after_save(new_preview, edit_area.file_path))
    
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