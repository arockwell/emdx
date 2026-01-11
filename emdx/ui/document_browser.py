#!/usr/bin/env python3
"""
Document browser - extracted from the monolith.

Uses the Presenter pattern to separate business logic from UI rendering.
The DocumentBrowserPresenter handles data loading, filtering, and CRUD
operations while this widget focuses on display and user interaction.
"""

import logging
from typing import Any, Dict, List, Optional, Protocol

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Input, Label, RichLog, Static

from emdx.models.tags import get_document_tags

from .presenters import DocumentBrowserPresenter
from .viewmodels import DocumentDetailVM, DocumentListVM
from .vim_editor import VimEditor

logger = logging.getLogger(__name__)


class TextAreaHost(Protocol):
    """Protocol defining what VimEditTextArea and SelectionTextArea expect from their host."""
    
    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode."""
        ...
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode information."""
        ...
        
    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (for SelectionTextArea)."""
        ...


class DocumentBrowser(Widget):
    """Document browser widget that can host text areas."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("e", "edit_document", "Edit"),
        Binding("n", "new_document", "New"),
        Binding("/", "search", "Search"),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags"),
        Binding("s", "selection_mode", "Select"),
        Binding("x", "execute_document", "Run Agent"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS_PATH = "document_browser.tcss"
    
    # Reactive properties
    mode = reactive("NORMAL")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # UI state
        self.edit_mode: bool = False
        self.editing_doc_id: Optional[int] = None
        self.tag_action: Optional[str] = None

        # Debounce preview updates
        self._pending_preview_doc_id: Optional[int] = None
        self._preview_timer = None

        # Current ViewModel (updated by presenter callbacks)
        self._current_vm: Optional[DocumentListVM] = None

        # Initialize presenter with update callbacks
        self.presenter = DocumentBrowserPresenter(
            on_list_update=self._on_list_update,
            on_detail_update=self._on_detail_update,
        )

    async def _on_list_update(self, vm: DocumentListVM) -> None:
        """Handle ViewModel updates from presenter."""
        self._current_vm = vm
        await self._render_document_list()

    async def _on_detail_update(self, vm: DocumentDetailVM) -> None:
        """Handle detail ViewModel updates from presenter."""
        # This callback can be used for detail panel updates in the future
        pass
        
    def compose(self) -> ComposeResult:
        """Compose the document browser UI."""
        # Docked inputs at the top (hidden by default)
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input",
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")
        yield Label("", id="vim-mode-indicator")
        
        with Horizontal():
            with Vertical(id="sidebar") as sidebar:
                # Remove debug background
                pass
                with Vertical(id="table-container", classes="table-section") as table_container:
                    # Apply direct styles - 2/3 of sidebar
                    table_container.styles.height = "66%"
                    table_container.styles.min_height = 10
                    table_container.styles.padding = (1, 0, 0, 0)  # Top padding for spacing
                    yield DataTable(id="doc-table")
                with Vertical(id="details-container", classes="details-section") as details_container:
                    # Apply direct styles - 1/3 of sidebar
                    details_container.styles.height = "34%"
                    details_container.styles.min_height = 8
                    details_container.styles.padding = 0
                    details_container.styles.border_top = ("heavy", "gray")
                    yield RichLog(
                        id="details-panel",
                        classes="details-richlog",
                        wrap=True, 
                        highlight=True, 
                        markup=True, 
                    auto_scroll=False
                )
            with Vertical(id="preview-container"):
                with ScrollableContainer(id="preview"):
                    yield RichLog(
                        id="preview-content",
                        classes="preview-richlog",
                        wrap=True, highlight=True, markup=True, auto_scroll=False
                    )
        
        # Status bar at the bottom
        yield Static("Ready", id="browser-status", classes="browser-status")
                    
    async def on_mount(self) -> None:
        """Initialize the document browser."""
        logger.info("DocumentBrowser mounted - LHS split implementation")

        # Initialize preview mode manager
        from .preview_mode_manager import PreviewModeManager
        preview_container = self.query_one("#preview-container", Vertical)
        self.preview_manager = PreviewModeManager(preview_container)

        # Setup table
        table = self.query_one("#doc-table", DataTable)
        table.add_column("ID", width=4)
        table.add_column("Tags", width=8)
        table.add_column(" ", width=1)  # Padding column
        table.add_column("Title", width=74)
        table.cursor_type = "row"
        table.show_header = True  # Show built-in headers
        table.cell_padding = 0  # Remove cell padding for tight spacing
        
        # Disable focus on non-interactive widgets
        preview_content = self.query_one("#preview-content")
        preview_content.can_focus = False
        
        # Setup details panel
        try:
            details_panel = self.query_one("#details-panel")
            details_panel.can_focus = False
            
            # Add initial content to details panel
            details_panel.write("📋 **Document Details**")
            details_panel.write("")
            details_panel.write("[dim]Select a document to view details[/dim]")
        except (LookupError, AttributeError) as e:
            logger.error(f"Error setting up details panel: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error setting up details panel: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        search_input = self.query_one("#search-input")
        search_input.can_focus = False
        tag_input = self.query_one("#tag-input")
        tag_input.can_focus = False
        
        # Hide inputs initially
        search_input.display = False
        tag_input.display = False
        
        # Set focus to table so keys work immediately
        table.focus()
        
        # Load documents via presenter
        await self.presenter.load_documents()

    async def load_documents(
        self, limit: int = 100, offset: int = 0, append: bool = False
    ) -> None:
        """Load documents from database with pagination.

        Delegates to presenter for data loading.

        Args:
            limit: Number of documents to fetch
            offset: Starting offset for pagination
            append: If True, append to existing docs instead of replacing
        """
        await self.presenter.load_documents(limit=limit, offset=offset, append=append)

    async def load_more_documents(self) -> None:
        """Load more documents when user scrolls near the end."""
        await self.presenter.load_more_documents()
            
    async def _render_document_list(self) -> None:
        """Render the document list from current ViewModel.

        This method is called by the presenter callback when data changes.
        It renders the ViewModel data to the UI without any data fetching.
        """
        if not self._current_vm:
            return

        vm = self._current_vm
        table = self.query_one("#doc-table", DataTable)
        table.clear()

        # Render documents from ViewModel (data is already formatted)
        for doc in vm.filtered_documents:
            table.add_row(
                str(doc.id),
                doc.tags_display,
                "",  # Empty padding column
                doc.title,
            )

        # Update status using ViewModel status text
        try:
            status_text = vm.status_text
            if self.mode == "NORMAL":
                status_text += " | e=edit | n=new | /=search | t=tag | x=execute | r=refresh | q=quit"
            elif self.mode == "SEARCH":
                status_text += " | Enter=apply | ESC=cancel"
            self.update_status(status_text)
        except Exception as e:
            logger.error(f"Status update failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def update_table(self) -> None:
        """Update the table with filtered documents.

        Kept for backward compatibility - delegates to _render_document_list.
        """
        await self._render_document_list()
            
    def save_state(self) -> Dict[str, Any]:
        """Save current state for restoration."""
        state: Dict[str, Any] = {
            "mode": self.mode,
            "current_search": self._current_vm.search_query if self._current_vm else "",
        }

        # Save cursor position
        try:
            table = self.query_one("#doc-table", DataTable)
            state["cursor_position"] = table.cursor_coordinate
        except Exception:
            pass

        return state

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore saved state."""
        self.mode = state.get("mode", "NORMAL")
        # Search query will be applied when load_documents is called

        # Restore cursor position
        if "cursor_position" in state:
            try:
                table = self.query_one("#doc-table", DataTable)
                table.cursor_coordinate = state["cursor_position"]
            except Exception:
                pass
                
    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        
        # Handle delete key
        if key == "d" and not self.edit_mode and self.mode == "NORMAL":
            await self._handle_delete()
            event.stop()
            return
        
        # Handle escape key to exit modes
        # Don't handle escape for SELECTION mode here - let SelectionTextArea handle it
        if key == "escape":
            if self.edit_mode:
                # For new document mode, just cancel without saving
                if getattr(self, 'new_document_mode', False):
                    self.new_document_mode = False
                await self.exit_edit_mode()
                event.stop()
            elif self.mode == "SEARCH":
                self.exit_search_mode()
                event.stop()
            elif self.mode == "TAG":
                self.exit_tag_mode()
                event.stop()
            # Note: SELECTION mode escape is handled by SelectionTextArea itself
    
    async def _handle_delete(self) -> None:
        """Handle delete key press - immediately delete document."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is None:
            return

        row_idx = table.cursor_row
        doc = self.presenter.get_document_at_index(row_idx)
        if not doc:
            return

        success = await self.presenter.delete_document(doc.id, hard_delete=False)

        if success:
            # Restore cursor position, adjusting if needed
            if self.presenter.filtered_count > 0:
                # If we deleted the last item, move cursor to the new last item
                new_cursor_row = min(row_idx, self.presenter.filtered_count - 1)
                table.cursor_coordinate = (new_cursor_row, 0)

            self.update_status(f"Document '{doc.title}' deleted")
        else:
            self.update_status("Error deleting document")
                
    async def enter_edit_mode(self) -> None:
        """Enter edit mode for the selected document."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is None:
            return

        row_idx = table.cursor_row
        doc_item = self.presenter.get_document_at_index(row_idx)
        if not doc_item:
            return

        self.editing_doc_id = doc_item.id

        # Load full document via presenter
        detail_vm = self.presenter.get_document_detail(doc_item.id)
        if not detail_vm:
            return
        full_doc = {"id": detail_vm.id, "title": detail_vm.title, "content": detail_vm.content}

        # Store original preview for restoration
        self.original_preview_content = full_doc["content"]
        self.edit_mode = True

        # Extract content without unicode box if present
        content = self._extract_content_without_title_box(
            full_doc["content"], full_doc["title"]
        )

        # Switch to editing mode via manager
        title_input, vim_editor = await self.preview_manager.switch_to_editing(
            host=self, title=full_doc["title"], content=content, is_new=False
        )

        # Focus on title input first
        self.call_after_refresh(lambda: title_input.focus())

        # Update status
        self._update_vim_status("EDIT DOCUMENT | Tab=switch fields | Ctrl+S=save | ESC=cancel")
        
    def action_save_and_exit_edit(self) -> None:
        """Save document and exit edit mode (called by VimEditTextArea)."""
        logger.info("action_save_and_exit_edit called")
        try:
            # Use call_after_refresh to avoid timing issues
            self.call_after_refresh(self._async_save_and_exit_edit_mode)
        except Exception as e:
            logger.error(f"Error in action_save_and_exit_edit: {e}")
            # Fallback - try direct call
            try:
                import asyncio
                asyncio.create_task(self.save_and_exit_edit_mode())
            except Exception:
                pass
            
    def _async_exit_edit_mode(self) -> None:
        """Async wrapper for exit_edit_mode."""
        logger.info("_async_exit_edit_mode called")
        import asyncio
        asyncio.create_task(self.exit_edit_mode())
        
    def _async_save_and_exit_edit_mode(self) -> None:
        """Async wrapper for save_and_exit_edit_mode."""
        logger.info("_async_save_and_exit_edit_mode called")
        import asyncio
        asyncio.create_task(self.save_and_exit_edit_mode())
        
    async def save_and_exit_edit_mode(self) -> None:
        """Save the document and exit edit mode."""
        if not self.edit_mode:
            return

        try:
            title_input = self.query_one("#title-input", Input)
            vim_editor = self.query_one("#vim-editor-container", VimEditor)

            title = title_input.value.strip()
            content = vim_editor.text_area.text

            if not title:
                self._update_vim_status("ERROR: Title required | Enter title and press Ctrl+S")
                return

            if getattr(self, "new_document_mode", False):
                # Save new document via presenter
                doc_id = await self.presenter.save_new_document(title, content)
                if doc_id:
                    logger.info(f"Created new document with ID: {doc_id}")
                    self.new_document_mode = False
                else:
                    self._update_vim_status("ERROR: Failed to save document")
                    return
            else:
                # Update existing document via presenter
                if self.editing_doc_id:
                    success = await self.presenter.update_existing_document(
                        self.editing_doc_id, title, content
                    )
                    if not success:
                        self._update_vim_status("ERROR: Failed to update document")
                        return
                    logger.info(f"Updated document ID: {self.editing_doc_id}")

            # Exit edit mode and reload documents
            await self.exit_edit_mode()
            await self.load_documents()

        except Exception as e:
            logger.error(f"Error in save_and_exit_edit_mode: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
    def _format_content_with_title_box(self, title: str, content: str) -> str:
        """Format content with title as markdown header."""
        # Simply use markdown header - Rich will render it with the unicode box
        formatted = f"# {title}\n\n{content}"
        return formatted
    
    def _extract_content_without_title_box(self, content: str, title: str) -> str:
        """Extract content without the title header or unicode box if present."""
        lines = content.split('\n')
        
        # Check for markdown header first
        if lines and lines[0].strip() == f"# {title}":
            # Skip the header line and optional blank line
            start_idx = 1
            if len(lines) > 1 and not lines[1].strip():
                start_idx = 2
            return '\n'.join(lines[start_idx:])
        
        # Check if content starts with a unicode box (various styles)
        if len(lines) >= 3:
            # Check for double-line box (╔═╗)
            if lines[0].startswith('╔') and lines[2].startswith('╚'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
            
            # Check for heavy-line box (┏━┓)
            elif lines[0].startswith('┏') and lines[2].startswith('┗'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
            
            # Check for single-line box (┌─┐)
            elif lines[0].startswith('┌') and lines[2].startswith('└'):
                start_idx = 3
                if len(lines) > 3 and not lines[3].strip():
                    start_idx = 4
                return '\n'.join(lines[start_idx:])
        
        # No header or box found, return original content
        return content
    
    def _update_vim_status(self, message: str = "") -> None:
        """Update status bar with vim mode info (called by VimEditTextArea)."""
        try:
            # Update vim mode indicator
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            if message:
                vim_indicator.update(f"VIM: {message}")
                vim_indicator.add_class("active")
            else:
                vim_indicator.update("VIM: NORMAL | ESC=exit")
                vim_indicator.add_class("active")
                
            # Also update main status
            app = self.app
            if hasattr(app, 'update_status'):
                if message:
                    app.update_status(f"Edit Mode | {message}")
                else:
                    app.update_status("Edit Mode | ESC=exit | Ctrl+S=save")
        except (LookupError, AttributeError) as e:
            logger.debug(f"Could not update vim status: {type(e).__name__}: {e}")
            
    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (called by SelectionTextArea)."""
        if self.mode == "SELECTION":
            # Exit selection mode
            try:
                self.call_after_refresh(self._async_exit_selection_mode)
            except (AttributeError, RuntimeError) as e:
                logger.debug(f"Could not exit selection mode: {type(e).__name__}: {e}")
        
    def _async_exit_selection_mode(self) -> None:
        """Async wrapper for exit_selection_mode."""
        import asyncio
        asyncio.create_task(self.exit_selection_mode())
        
    async def exit_edit_mode(self) -> None:
        """Exit edit mode and restore preview."""
        if not self.edit_mode:
            return

        self.edit_mode = False
        # Clean up new document mode flag if it was set
        if hasattr(self, "new_document_mode"):
            self.new_document_mode = False

        # Clear vim mode indicator
        try:
            vim_indicator = self.query_one("#vim-mode-indicator", Label)
            vim_indicator.update("")
            vim_indicator.remove_class("active")
        except Exception:
            pass

        # Get current document content for preview
        content = ""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None:
            doc_item = self.presenter.get_document_at_index(table.cursor_row)
            if doc_item:
                detail_vm = self.presenter.get_document_detail(doc_item.id)
                if detail_vm:
                    content = detail_vm.content

        # Switch to viewing mode via manager
        await self.preview_manager.switch_to_viewing(content)

        # Return focus to table
        table.focus()

    async def enter_new_document_mode(self) -> None:
        """Enter mode to create a new document."""
        # Store that we're creating a new document
        self.editing_doc_id = None  # No existing document
        self.edit_mode = True
        self.new_document_mode = True

        # Switch to editing mode via manager (with empty title and content)
        title_input, vim_editor = await self.preview_manager.switch_to_editing(
            host=self, title="", content="", is_new=True
        )

        # Focus on title input first - use call_after_refresh to ensure it's ready
        self.call_after_refresh(lambda: title_input.focus())

        # Update status
        self._update_vim_status(
            "NEW DOCUMENT | Enter title | Tab=switch to content | Ctrl+S=save | ESC=cancel"
        )
        
    def action_cursor_down(self) -> None:
        """Move cursor down."""
        table = self.query_one("#doc-table", DataTable)
        table.action_cursor_down()
        
    def action_cursor_up(self) -> None:
        """Move cursor up."""
        table = self.query_one("#doc-table", DataTable)
        table.action_cursor_up()
        
    def action_cursor_top(self) -> None:
        """Move cursor to top."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            
    async def action_cursor_bottom(self) -> None:
        """Move cursor to bottom - loads all remaining documents first."""
        # Load all remaining documents before going to bottom
        while self.presenter.has_more:
            await self.load_more_documents()

        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0:
            table.cursor_coordinate = (table.row_count - 1, 0)
            
    async def action_edit_document(self) -> None:
        """Edit the current document."""
        await self.enter_edit_mode()
    
    async def action_refresh(self) -> None:
        """Refresh the document list."""
        await self.load_documents()
        
    def update_status(self, message: str) -> None:
        """Update the document browser status bar."""
        try:
            status = self.query_one("#browser-status", Static)
            status.update(message)
        except Exception:
            # Fallback to app status if our status bar doesn't exist
            app = self.app
            if hasattr(app, 'update_status'):
                app.update_status(message)
    
    def action_execute_document(self) -> None:
        """Open multi-stage agent execution overlay for the current document."""
        table = self.query_one("#doc-table", DataTable)
        doc_item = self.presenter.get_document_at_index(table.cursor_row)
        if not doc_item:
            self.update_status("No document selected for agent execution")
            return

        doc_id = doc_item.id
        doc_title = doc_item.title

        # Import the new agent execution overlay
        from .agent_execution_overlay import AgentExecutionOverlay

        async def handle_execution_result(result):
            """Handle the result from agent execution overlay."""
            if result and result.get('document_id') and result.get('agent_id'):
                document_id = result['document_id']
                agent_id = result['agent_id']
                worktree_index = result.get('worktree_index')
                config = result.get('config', {})
                background = config.get('background', True)

                # Execute the agent
                try:
                    from ..agents.executor import agent_executor

                    logger.info(f"Starting agent execution: agent={agent_id}, doc={document_id}, background={background}")

                    execution_id = await agent_executor.execute_agent(
                        agent_id=agent_id,
                        input_type='document',
                        input_doc_id=document_id,
                        background=background,
                        variables=config.get('variables', {})
                    )

                    self.update_status(f"✅ Agent #{execution_id} started!")
                    logger.info(f"Agent execution started: #{execution_id}")

                except Exception as e:
                    logger.error(f"Error starting agent: {e}", exc_info=True)
                    self.update_status(f"❌ Error starting agent: {str(e)}")
            else:
                # User cancelled
                self.update_status("Agent execution cancelled")
                logger.info("Agent execution cancelled by user")

        # Open the new multi-stage agent execution overlay
        # Pre-select the current document and start at agent selection stage
        overlay = AgentExecutionOverlay(
            initial_document_id=doc_id,  # Pre-select current document
            start_stage=None,  # Will auto-start at agent stage when document is pre-selected
        )
        # Pass the async callback to push_screen - it will be called when the overlay is dismissed
        self.app.push_screen(overlay, handle_execution_result)
    
    async def action_new_document(self) -> None:
        """Create a new document."""
        # Don't allow new document in log browser mode
        if getattr(self, 'mode', 'NORMAL') == "LOG_BROWSER":
            return
        await self.enter_new_document_mode()
        
    def action_search(self) -> None:
        """Enter search mode."""
        self.mode = "SEARCH"
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.can_focus = True
        search_input.focus()
        
    def action_add_tags(self) -> None:
        """Enter tag adding mode."""
        self.mode = "TAG"
        self.tag_action = "add"
        tag_input = self.query_one("#tag-input", Input)
        tag_input.display = True
        tag_input.can_focus = True
        tag_input.focus()
        
    def action_remove_tags(self) -> None:
        """Enter tag removal mode."""
        self.mode = "TAG"
        self.tag_action = "remove"
        # Show tag selector with existing tags
        table = self.query_one("#doc-table", DataTable)
        doc_item = self.presenter.get_document_at_index(table.cursor_row)
        if not doc_item:
            return

        tags = get_document_tags(doc_item.id)

        if not tags:
            return  # No tags to remove

        # For now, just use input - proper selector later
        tag_input = self.query_one("#tag-input", Input)
        tag_input.placeholder = f"Remove tags: {', '.join(tags)}"
        tag_input.display = True
        tag_input.can_focus = True
        tag_input.focus()

    async def action_selection_mode(self) -> None:
        """Enter selection mode for document content."""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is None:
            return

        doc_item = self.presenter.get_document_at_index(table.cursor_row)
        if not doc_item:
            return

        # Load full document for selection via presenter
        detail_vm = self.presenter.get_document_detail(doc_item.id)
        if not detail_vm:
            return

        # Switch to selecting mode via manager
        selection_area = await self.preview_manager.switch_to_selecting(
            host=self, content=detail_vm.content
        )
        selection_area.focus()

        # Update mode
        self.mode = "SELECTION"

        # Update status
        try:
            app = self.app
            if hasattr(app, "update_status"):
                app.update_status("Selection Mode | ESC=exit | Enter=copy selection")
        except Exception:
            pass
            
    async def exit_selection_mode(self) -> None:
        """Exit selection mode and restore preview."""
        if self.mode != "SELECTION":
            return

        self.mode = "NORMAL"

        # Get current document content for preview
        content = ""
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None:
            doc_item = self.presenter.get_document_at_index(table.cursor_row)
            if doc_item:
                detail_vm = self.presenter.get_document_detail(doc_item.id)
                if detail_vm:
                    content = detail_vm.content

        # Switch to viewing mode via manager
        await self.preview_manager.switch_to_viewing(content)

        # Return focus to table
        table.focus()

        # Update status
        try:
            app = self.app
            if hasattr(app, "update_status"):
                vm = self._current_vm
                if vm:
                    status_text = f"{vm.filtered_count}/{vm.total_count} docs"
                else:
                    status_text = "0/0 docs"
                status_text += " | e=edit | n=new | /=search | t=tag | x=execute | r=refresh | q=quit"
                app.update_status(status_text)
        except (LookupError, AttributeError) as e:
            logger.debug(
                f"Could not update status after exiting selection mode: {type(e).__name__}: {e}"
            )
    
    async def on_data_table_row_highlighted(self, event) -> None:
        """Update preview and details panel when row is highlighted."""
        if self.edit_mode:
            return

        row_idx = event.cursor_row

        # Load more documents when near the end (within 20 rows)
        if self.presenter.should_load_more(row_idx):
            await self.load_more_documents()

        doc_item = self.presenter.get_document_at_index(row_idx)
        if not doc_item:
            return

        # Get document detail via presenter (includes caching)
        detail_vm = self.presenter.get_document_detail(doc_item.id)

        if detail_vm and not self.edit_mode:
            # Schedule preview update with debouncing (50ms delay)
            self._pending_preview_doc_id = doc_item.id
            if self._preview_timer:
                self._preview_timer.stop()
            self._preview_timer = self.set_timer(
                0.05, lambda: self._do_preview_update_from_vm(detail_vm)
            )

    def _do_preview_update_from_vm(self, detail_vm: DocumentDetailVM) -> None:
        """Update the preview from a DocumentDetailVM."""
        if self.edit_mode:
            return

        try:
            preview_container = self.query_one("#preview", ScrollableContainer)
            preview = preview_container.query_one("#preview-content", RichLog)
            preview.clear()

            # Render content as markdown (limit size for performance)
            from rich.markdown import Markdown

            try:
                content = detail_vm.content
                # Limit preview to first 5000 chars for performance
                if len(content) > 5000:
                    content = content[:5000] + "\n\n[dim]... (truncated for preview)[/dim]"
                if content.strip():
                    markdown = Markdown(content)
                    preview.write(markdown)
                else:
                    preview.write("[dim]Empty document[/dim]")
            except Exception:
                # Fallback to plain text if markdown fails
                preview.write(detail_vm.content[:5000])
        except Exception:
            # Preview widget not found or not ready - ignore
            pass

        # Update details panel
        self.call_later(lambda: self._update_details_from_vm(detail_vm))

    def _update_details_from_vm(self, detail_vm: DocumentDetailVM) -> None:
        """Update details panel from DocumentDetailVM."""
        import asyncio

        asyncio.create_task(self._render_details_panel(detail_vm))

    async def _render_details_panel(self, detail_vm: DocumentDetailVM) -> None:
        """Render the details panel from a DocumentDetailVM."""
        try:
            details_panel = self.query_one("#details-panel", RichLog)
            details_panel.clear()

            # Format details with emoji and rich formatting
            details = []

            # ID and basic info
            details.append(f"📄 **ID:** {detail_vm.id}")
            details.append(f"📂 **Project:** {detail_vm.project}")

            # Tags with emoji formatting
            if detail_vm.tags:
                details.append(f"🏷️  **Tags:** {detail_vm.tags_formatted}")
            else:
                details.append("🏷️  **Tags:** [dim]None[/dim]")

            # Dates
            if detail_vm.created_at:
                created = detail_vm.created_at
                if isinstance(created, str):
                    created = created[:16]
                details.append(f"📅 **Created:** {created}")

            if detail_vm.updated_at:
                updated = detail_vm.updated_at
                if isinstance(updated, str):
                    updated = updated[:16]
                details.append(f"✏️  **Updated:** {updated}")

            if detail_vm.accessed_at:
                accessed = detail_vm.accessed_at
                if isinstance(accessed, str):
                    accessed = accessed[:16]
                details.append(f"👁️  **Accessed:** {accessed}")

            # Access count and content stats
            details.append(f"📊 **Views:** {detail_vm.access_count}")
            details.append(
                f"📝 **Words:** {detail_vm.word_count} | "
                f"**Chars:** {detail_vm.char_count} | "
                f"**Lines:** {detail_vm.line_count}"
            )

            # Write each detail on a separate line
            for detail in details:
                details_panel.write(detail)

        except Exception as e:
            logger.error(f"Error rendering details panel: {e}")
            # Fallback - just show basic info
            try:
                details_panel = self.query_one("#details-panel", RichLog)
                details_panel.clear()
                details_panel.write(f"📄 Document {detail_vm.id}: {detail_vm.title}")
            except Exception:
                pass

                
    async def on_input_submitted(self, event) -> None:
        """Handle input submission."""
        if event.input.id == "search-input":
            # Handle search via presenter
            query = event.input.value.strip()
            await self.apply_search(query)
            self.exit_search_mode()
            
        elif event.input.id == "tag-input":
            # Handle tag operations
            if self.tag_action == "add":
                await self.add_tags_to_current_doc(event.input.value)
            elif self.tag_action == "remove":
                await self.remove_tags_from_current_doc(event.input.value)
            self.exit_tag_mode()
            
    def exit_search_mode(self) -> None:
        """Exit search mode."""
        self.mode = "NORMAL"
        search_input = self.query_one("#search-input", Input)
        search_input.display = False
        search_input.can_focus = False
        search_input.value = ""
        table = self.query_one("#doc-table", DataTable)
        table.focus()
        
    def exit_tag_mode(self) -> None:
        """Exit tag mode."""
        self.mode = "NORMAL"
        tag_input = self.query_one("#tag-input", Input)
        tag_input.display = False
        tag_input.can_focus = False
        tag_input.value = ""
        tag_input.placeholder = "Enter tags separated by spaces..."
        table = self.query_one("#doc-table", DataTable)
        table.focus()
        
    async def apply_search(self, query: Optional[str] = None) -> None:
        """Apply current search filter via presenter.

        Args:
            query: Search query. If None, uses internal search state.
        """
        search_query = query if query is not None else ""
        await self.presenter.apply_search(search_query)

    async def add_tags_to_current_doc(self, tag_text: str) -> None:
        """Add tags to current document."""
        table = self.query_one("#doc-table", DataTable)
        doc_item = self.presenter.get_document_at_index(table.cursor_row)
        if not doc_item:
            return

        tags = [tag.strip() for tag in tag_text.split() if tag.strip()]
        if tags:
            await self.presenter.add_tags(doc_item.id, tags)

    async def remove_tags_from_current_doc(self, tag_text: str) -> None:
        """Remove tags from current document."""
        table = self.query_one("#doc-table", DataTable)
        doc_item = self.presenter.get_document_at_index(table.cursor_row)
        if not doc_item:
            return

        tags = [tag.strip() for tag in tag_text.split() if tag.strip()]
        if tags:
            await self.presenter.remove_tags(doc_item.id, tags)
