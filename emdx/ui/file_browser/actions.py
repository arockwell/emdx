"""Actions mixin for FileBrowser - handles file operations and mode switching."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from textual import events
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Static, TextArea

if TYPE_CHECKING:
    from .view import FileBrowserView

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


class FileBrowserActions:
    """Mixin providing action functionality for FileBrowser.

    Handles:
    - File save/execute/edit operations
    - Edit mode switching
    - Selection mode switching
    - Modal result handling
    """

    def action_quit(self: "FileBrowserView") -> None:
        """Exit file browser."""
        # Post a quit event that the main browser can handle
        self.post_message(self.QuitFileBrowser())

    def action_save_file(self: "FileBrowserView") -> None:
        """Save selected file to EMDX."""
        from ..file_list import FileList

        try:
            file_list = self.query_one("#file-list", FileList)
            selected = file_list.get_selected_file()

            if selected and selected.is_file():
                # Will be implemented with modal
                from ..file_modals import SaveFileModal
                self.app.push_screen(
                    SaveFileModal(selected),
                    self.handle_save_result
                )
            else:
                self.app.bell()
        except Exception:
            pass

    def action_execute_file(self: "FileBrowserView") -> None:
        """Execute selected file with Claude."""
        from ..file_list import FileList

        try:
            file_list = self.query_one("#file-list", FileList)
            selected = file_list.get_selected_file()

            if selected and selected.is_file():
                # Check if file is in EMDX first
                doc_id = self._get_file_doc_id(selected)

                from ..file_modals import ExecuteFileModal
                self.app.push_screen(
                    ExecuteFileModal(selected, doc_id),
                    self.handle_execute_result
                )
            else:
                self.app.bell()
        except Exception:
            pass

    def action_edit_file(self: "FileBrowserView") -> None:
        """Edit selected file in integrated editor."""
        from ..file_list import FileList

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

    def _switch_to_edit_mode(self: "FileBrowserView", selected_file: Path) -> None:
        """Switch preview to edit mode by replacing FilePreview widget."""
        from ..file_preview import FilePreview
        from ..vim_editor import VimEditor

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

    def action_handle_escape(self: "FileBrowserView") -> None:
        """Handle escape key - exit current mode."""
        if self.edit_mode:
            self._exit_edit_mode()
        elif self.selection_mode:
            self._exit_selection_mode()
        else:
            # If not in any special mode, exit file browser back to main
            self.action_quit()

    def _exit_edit_mode(self: "FileBrowserView") -> None:
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

    def _exit_selection_mode(self: "FileBrowserView") -> None:
        """Exit selection mode and return to preview."""
        from ..file_list import FileList

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

    def save_and_exit_edit_mode(self: "FileBrowserView", edit_area) -> None:
        """Save edited file and exit edit mode."""
        from ..file_list import FileList
        from ..file_preview import FilePreview

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

    def _preview_after_save(self: "FileBrowserView", new_preview, file_path) -> None:
        """Preview file after saving and widget recreation."""
        from ..file_list import FileList

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

    def action_search(self: "FileBrowserView") -> None:
        """Search for files. Note: File search not yet implemented."""
        self.query_one("#file-status-bar", Static).update(
            "Search not implemented - use shell commands to search"
        )

    def action_toggle_selection_mode(self: "FileBrowserView") -> None:
        """Toggle between formatted view and text selection mode."""
        from ..file_list import FileList
        from ..file_preview import FilePreview

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

    def _switch_to_selection_mode(self: "FileBrowserView", preview_container, selected_file: Path) -> None:
        """Switch preview to selection mode by replacing FilePreview widget."""
        from ..file_preview import FilePreview

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

    def _switch_to_formatted_mode(self: "FileBrowserView", preview_container, selected_file: Path) -> None:
        """Switch preview back to formatted mode."""
        from ..file_list import FileList
        from ..file_preview import FilePreview

        try:
            # Get the horizontal container that holds file-list and file-preview
            horizontal_container = self.query_one(".file-browser-content", Horizontal)

            # Remove the selection container
            selection_container = self.query_one("#selection-preview-container")
            selection_container.remove()

            # Recreate the FilePreview widget
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
                fallback_container.mount(Static(f"Preview of {selected_file.name}"))
                horizontal_container.mount(fallback_container)
            except Exception:
                pass

    def handle_save_result(self: "FileBrowserView", result: Optional[dict]) -> None:
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

    def handle_execute_result(self: "FileBrowserView", result: Optional[dict]) -> None:
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

    def _get_file_doc_id(self: "FileBrowserView", file_path: Path) -> Optional[int]:
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
