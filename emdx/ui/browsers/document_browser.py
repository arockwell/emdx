"""
DocumentBrowser - Document browser using the panel-based architecture.

This browser replaces the original document_browser.py with a simpler
implementation using ListPanel, PreviewPanel, and InputPanel components.

Features:
- Document listing with hierarchy support
- Full-text search and tag filtering
- Markdown preview
- Document editing (new, edit, delete)
- Tag management (add, remove)
- Pagination with lazy loading
- Selection mode for copying content

This implementation is significantly simpler than the original by leveraging
reusable panel components that handle navigation, search, and preview.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog, Static

from emdx.models.tags import get_document_tags

from ..modals import HelpMixin
from ..panels import (
    ColumnDef,
    InputMode,
    InputPanel,
    ListItem,
    ListPanel,
    ListPanelConfig,
    PreviewPanel,
    PreviewPanelConfig,
)
from ..presenters import DocumentBrowserPresenter
from ..viewmodels import DocumentDetailVM, DocumentListItem, DocumentListVM

logger = logging.getLogger(__name__)


class DocumentBrowser(HelpMixin, Widget):
    """Document browser using the panel-based architecture.

    This is a simplified reimplementation of DocumentBrowser using
    reusable panel components. It provides the same functionality:

    - Document list with vim-style navigation
    - Search and tag filtering
    - Markdown preview
    - Editing and creating documents
    - Tag management

    The implementation is much simpler because ListPanel and PreviewPanel
    handle the complex UI logic.
    """

    HELP_TITLE = "Document Browser V2"

    DEFAULT_CSS = """
    DocumentBrowser {
        layout: horizontal;
        height: 100%;
        layers: base overlay;
    }

    DocumentBrowser #doc-sidebar {
        width: 40%;
        min-width: 40;
        height: 100%;
        layer: base;
    }

    DocumentBrowser #doc-list {
        height: 2fr;
    }

    DocumentBrowser #doc-details {
        height: 1fr;
        border-top: solid $primary;
        padding: 0 1;
    }

    DocumentBrowser #doc-preview {
        width: 60%;
        min-width: 40;
        border-left: solid $primary;
        layer: base;
    }

    DocumentBrowser #tag-input-panel {
        layer: overlay;
    }

    DocumentBrowser #browser-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        dock: bottom;
    }

    DocumentBrowser #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("e", "edit_document", "Edit"),
        Binding("n", "new_document", "New"),
        Binding("d", "delete_document", "Delete", show=False),
        Binding("t", "add_tags", "Add Tags"),
        Binding("T", "remove_tags", "Remove Tags", show=False),
        Binding("s", "selection_mode", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "show_help", "Help"),
        Binding("i", "create_gist", "Gist", show=False),
        Binding("l", "expand_children", "Expand", show=False),
        Binding("right", "expand_children", "Expand", show=False),
        Binding("h", "collapse_children", "Collapse", show=False),
        Binding("left", "collapse_children", "Collapse", show=False),
        Binding("a", "toggle_archived", "Archived", show=False),
    ]

    # Reactive properties
    mode = reactive("NORMAL")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # UI state
        self.edit_mode: bool = False
        self.editing_doc_id: Optional[int] = None
        self.new_document_mode: bool = False
        self.tag_action: Optional[str] = None  # "add" or "remove"

        # Current ViewModel (updated by presenter callbacks)
        self._current_vm: Optional[DocumentListVM] = None

        # Initialize presenter with update callbacks
        self.presenter = DocumentBrowserPresenter(
            on_list_update=self._on_list_update,
            on_detail_update=self._on_detail_update,
        )

    def compose(self) -> ComposeResult:
        """Compose the document browser layout with panels."""
        # Tag input panel (overlay, hidden by default)
        yield InputPanel(
            mode=InputMode.TAG,
            overlay=True,
            id="tag-input-panel",
        )

        with Horizontal():
            # Left sidebar with list and details
            with Vertical(id="doc-sidebar"):
                # Document list panel
                yield ListPanel(
                    columns=[
                        ColumnDef("ID", width=4),
                        ColumnDef("Tags", width=8),
                        ColumnDef(" ", width=1),  # Padding
                        ColumnDef("Title", width=50),
                    ],
                    config=ListPanelConfig(
                        show_search=True,
                        search_placeholder="Search... (try 'tags:docker,python')",
                        status_format="{filtered}/{total} docs",
                        lazy_load_threshold=20,
                    ),
                    show_status=True,
                    id="doc-list",
                )

                # Details panel (metadata)
                yield RichLog(
                    id="doc-details",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False,
                )

            # Preview panel
            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=True,
                    enable_selection=True,
                    show_title_in_edit=True,
                    empty_message="Select a document to preview",
                ),
                host=self,  # For vim editor callbacks
                id="doc-preview",
            )

        # Status bar
        yield Static("Ready", id="browser-status", classes="browser-status")

        # Navigation help bar
        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Workflows │ [dim]3[/dim] Documents │ "
            "[dim]j/k[/dim] nav │ [dim]e[/dim] edit │ [dim]n[/dim] new │ [dim]t[/dim] tag │ [dim]/[/dim] search │ [dim]?[/dim] help",
            id="help-bar",
        )

    async def on_mount(self) -> None:
        """Initialize the document browser."""
        logger.info("DocumentBrowser mounted")

        # Disable focus on details panel
        try:
            details = self.query_one("#doc-details", RichLog)
            details.can_focus = False
            details.write("📋 **Document Details**")
            details.write("")
            details.write("[dim]Select a document to view details[/dim]")
        except Exception as e:
            logger.debug(f"Could not setup details panel: {e}")

        # Load initial documents
        await self.presenter.load_documents()

    # -------------------------------------------------------------------------
    # Presenter Callbacks
    # -------------------------------------------------------------------------

    async def _on_list_update(self, vm: DocumentListVM) -> None:
        """Handle ViewModel updates from presenter."""
        self._current_vm = vm
        await self._render_document_list()

    async def _on_detail_update(self, vm: DocumentDetailVM) -> None:
        """Handle detail ViewModel updates from presenter."""
        pass  # Handled by item selection

    async def _render_document_list(self) -> None:
        """Render the document list from current ViewModel."""
        if not self._current_vm:
            return

        vm = self._current_vm
        list_panel = self.query_one("#doc-list", ListPanel)

        # Convert DocumentListItems to ListItems
        items = []
        for doc in vm.filtered_documents:
            display_title = self._format_hierarchy_title(doc)
            items.append(
                ListItem(
                    id=doc.id,
                    values=[str(doc.id), doc.tags_display, "", display_title],
                    data=doc,  # Store full document info
                )
            )

        list_panel.set_items(items, has_more=vm.has_more)

        # Update status
        self._update_status_text()

    def _format_hierarchy_title(self, doc: DocumentListItem) -> str:
        """Format document title with hierarchy tree characters."""
        if doc.depth == 0:
            prefix = ""
            if doc.has_children:
                if self.presenter.is_expanded(doc.id):
                    prefix = "▼ "
                else:
                    prefix = "▶ "
        else:
            indent = "  " * (doc.depth - 1)
            branch = "└─"
            prefix = f"{indent}{branch}"

        archived_suffix = " [archived]" if doc.is_archived else ""

        rel_prefix = ""
        if doc.relationship and doc.depth > 0:
            rel_map = {
                "supersedes": "↑",
                "exploration": "◇",
                "variant": "≈",
            }
            rel_prefix = f"{rel_map.get(doc.relationship, '')} "

        return f"{prefix}{rel_prefix}{doc.title}{archived_suffix}"

    def _update_status_text(self) -> None:
        """Update the status bar text."""
        if not self._current_vm:
            return

        vm = self._current_vm
        status_text = vm.status_text

        if self.mode == "NORMAL":
            status_text += " | e=edit n=new /=search t=tag l/h=expand a=archived"

        try:
            status = self.query_one("#browser-status", Static)
            status.update(status_text)
        except Exception:
            pass

    def update_status(self, message: str) -> None:
        """Update the status bar with a custom message."""
        try:
            status = self.query_one("#browser-status", Static)
            status.update(message)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # List Panel Event Handlers
    # -------------------------------------------------------------------------

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Update preview when document is selected."""
        if self.edit_mode:
            return

        item = event.item
        doc_item = item.data  # DocumentListItem stored in data

        if not doc_item:
            return

        # Get document detail from presenter
        detail_vm = self.presenter.get_document_detail(doc_item.id)
        if not detail_vm:
            return

        # Update preview panel
        preview = self.query_one("#doc-preview", PreviewPanel)
        await preview.show_content(detail_vm.content, title=detail_vm.title)

        # Update details panel
        self._render_details_panel(detail_vm)

    async def on_list_panel_load_more_requested(
        self, event: ListPanel.LoadMoreRequested
    ) -> None:
        """Load more documents when scrolling near end."""
        await self.presenter.load_more_documents()

    async def on_list_panel_search_submitted(
        self, event: ListPanel.SearchSubmitted
    ) -> None:
        """Handle search submission."""
        query = event.query
        await self.presenter.apply_search(query)

    def _render_details_panel(self, detail_vm: DocumentDetailVM) -> None:
        """Render the details panel from a DocumentDetailVM."""
        try:
            details_panel = self.query_one("#doc-details", RichLog)
            details_panel.clear()

            details = []
            details.append(f"📄 **ID:** {detail_vm.id}")
            details.append(f"📂 **Project:** {detail_vm.project}")

            if detail_vm.tags:
                details.append(f"🏷️  **Tags:** {detail_vm.tags_formatted}")
            else:
                details.append("🏷️  **Tags:** [dim]None[/dim]")

            if detail_vm.created_at:
                created = str(detail_vm.created_at)[:16]
                details.append(f"📅 **Created:** {created}")

            if detail_vm.updated_at:
                updated = str(detail_vm.updated_at)[:16]
                details.append(f"✏️  **Updated:** {updated}")

            if detail_vm.accessed_at:
                accessed = str(detail_vm.accessed_at)[:16]
                details.append(f"👁️  **Accessed:** {accessed}")

            details.append(f"📊 **Views:** {detail_vm.access_count}")
            details.append(
                f"📝 **Words:** {detail_vm.word_count} | "
                f"**Chars:** {detail_vm.char_count} | "
                f"**Lines:** {detail_vm.line_count}"
            )

            for detail in details:
                details_panel.write(detail)

        except Exception as e:
            logger.error(f"Error rendering details panel: {e}")

    # -------------------------------------------------------------------------
    # Preview Panel Event Handlers
    # -------------------------------------------------------------------------

    async def on_preview_panel_edit_requested(
        self, event: PreviewPanel.EditRequested
    ) -> None:
        """Handle edit request from preview panel."""
        await self.action_edit_document()

    async def on_preview_panel_content_changed(
        self, event: PreviewPanel.ContentChanged
    ) -> None:
        """Handle content save from edit mode."""
        title = event.title
        content = event.content

        if not title:
            self.update_status("ERROR: Title required")
            return

        if self.new_document_mode:
            doc_id = await self.presenter.save_new_document(title, content)
            if doc_id:
                logger.info(f"Created new document with ID: {doc_id}")
                self.new_document_mode = False
                self.update_status(f"Created document #{doc_id}")
            else:
                self.update_status("ERROR: Failed to save document")
        else:
            if self.editing_doc_id:
                success = await self.presenter.update_existing_document(
                    self.editing_doc_id, title, content
                )
                if success:
                    logger.info(f"Updated document ID: {self.editing_doc_id}")
                    self.update_status(f"Updated document #{self.editing_doc_id}")
                else:
                    self.update_status("ERROR: Failed to update document")

        self.edit_mode = False
        self.editing_doc_id = None

    async def on_preview_panel_mode_changed(
        self, event: PreviewPanel.ModeChanged
    ) -> None:
        """Handle preview mode changes."""
        from ..panels import PreviewMode

        if event.new_mode == PreviewMode.SELECTING:
            self.mode = "SELECTION"
            self.update_status("Selection Mode | ESC=exit | Enter=copy")
        elif event.old_mode == PreviewMode.SELECTING:
            self.mode = "NORMAL"
            self._update_status_text()
        elif event.new_mode == PreviewMode.EDITING:
            self.mode = "EDIT"
            self.update_status("Edit Mode | Tab=switch | Ctrl+S=save | ESC=cancel")
        elif event.old_mode == PreviewMode.EDITING:
            self.mode = "NORMAL"
            self._update_status_text()

    # -------------------------------------------------------------------------
    # Tag Input Event Handlers
    # -------------------------------------------------------------------------

    async def on_input_panel_input_submitted(
        self, event: InputPanel.InputSubmitted
    ) -> None:
        """Handle tag input submission."""
        if event.mode == InputMode.TAG:
            tags = [tag.strip() for tag in event.value.split() if tag.strip()]

            list_panel = self.query_one("#doc-list", ListPanel)
            selected_item = list_panel.get_selected_item()
            if not selected_item:
                return

            doc_id = selected_item.id

            if self.tag_action == "add":
                await self.presenter.add_tags(doc_id, tags)
                self.update_status(f"Added tags to document #{doc_id}")
            elif self.tag_action == "remove":
                await self.presenter.remove_tags(doc_id, tags)
                self.update_status(f"Removed tags from document #{doc_id}")

            self.tag_action = None

    async def on_input_panel_input_cancelled(
        self, event: InputPanel.InputCancelled
    ) -> None:
        """Handle tag input cancellation."""
        self.tag_action = None
        list_panel = self.query_one("#doc-list", ListPanel)
        list_panel.focus_table()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    async def action_edit_document(self) -> None:
        """Edit the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            self.update_status("No document selected")
            return

        doc_item = selected_item.data
        if not doc_item:
            return

        self.editing_doc_id = doc_item.id
        self.edit_mode = True

        # Get full document content
        detail_vm = self.presenter.get_document_detail(doc_item.id)
        if not detail_vm:
            return

        # Extract content without title header if present
        content = self._extract_content_without_title(detail_vm.content, detail_vm.title)

        # Enter edit mode in preview panel
        preview = self.query_one("#doc-preview", PreviewPanel)
        await preview.enter_edit_mode(
            title=detail_vm.title,
            content=content,
            is_new=False,
        )

    async def action_new_document(self) -> None:
        """Create a new document."""
        self.editing_doc_id = None
        self.edit_mode = True
        self.new_document_mode = True

        preview = self.query_one("#doc-preview", PreviewPanel)
        await preview.enter_edit_mode(title="", content="", is_new=True)

    async def action_delete_document(self) -> None:
        """Delete the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            self.update_status("No document selected")
            return

        doc_id = selected_item.id
        doc_title = selected_item.values[3]  # Title column

        success = await self.presenter.delete_document(doc_id, hard_delete=False)
        if success:
            self.update_status(f"Deleted document '{doc_title}'")
        else:
            self.update_status("Error deleting document")

    def action_add_tags(self) -> None:
        """Add tags to the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            return

        self.tag_action = "add"
        tag_input = self.query_one("#tag-input-panel", InputPanel)
        tag_input.show(
            label="Add Tags:",
            placeholder="Enter tags separated by spaces...",
        )

    def action_remove_tags(self) -> None:
        """Remove tags from the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            return

        doc_item = selected_item.data
        if not doc_item:
            return

        # Get current tags
        tags = get_document_tags(doc_item.id)
        if not tags:
            self.update_status("No tags to remove")
            return

        self.tag_action = "remove"
        tag_input = self.query_one("#tag-input-panel", InputPanel)
        tag_input.show(
            label="Remove Tags:",
            placeholder=f"Current: {', '.join(tags)}",
        )

    async def action_selection_mode(self) -> None:
        """Enter selection mode for copying content."""
        preview = self.query_one("#doc-preview", PreviewPanel)
        if preview.has_content:
            await preview.enter_selection_mode()

    async def action_refresh(self) -> None:
        """Refresh the document list."""
        await self.presenter.load_documents()
        self.update_status("Refreshed")

    async def action_create_gist(self) -> None:
        """Create a copy of the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            self.update_status("No document selected")
            return

        doc_item = selected_item.data
        if not doc_item:
            return

        detail_vm = self.presenter.get_document_detail(doc_item.id)
        if not detail_vm:
            self.update_status("Could not load document")
            return

        try:
            from emdx.database.documents import save_document
            from emdx.utils.git import get_git_project

            project = get_git_project()
            new_doc_id = save_document(
                title=f"{detail_vm.title} (copy)",
                content=detail_vm.content,
                project=project,
            )

            self.update_status(f"Created gist #{new_doc_id}")
            await self.presenter.load_documents()

        except Exception as e:
            self.update_status(f"Error: {e}")

    async def action_expand_children(self) -> None:
        """Expand children of the selected document."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            return

        doc_item = selected_item.data
        if not doc_item:
            return

        if not doc_item.has_children:
            self.update_status(f"Document #{doc_item.id} has no children")
            return

        if self.presenter.is_expanded(doc_item.id):
            self.update_status(f"Document #{doc_item.id} is already expanded")
            return

        success = await self.presenter.expand_document(doc_item.id)
        if success:
            self.update_status(f"Expanded #{doc_item.id}")
        else:
            self.update_status(f"Could not expand #{doc_item.id}")

    async def action_collapse_children(self) -> None:
        """Collapse children or navigate to parent."""
        list_panel = self.query_one("#doc-list", ListPanel)
        selected_item = list_panel.get_selected_item()

        if not selected_item:
            return

        doc_item = selected_item.data
        if not doc_item:
            return

        if self.presenter.is_expanded(doc_item.id):
            await self.presenter.collapse_document(doc_item.id)
            self.update_status(f"Collapsed #{doc_item.id}")
            return

        if doc_item.parent_id is not None:
            parent = self.presenter.get_parent_document(doc_item)
            if parent:
                list_panel.select_item_by_id(parent.id)
                self.update_status(f"Moved to parent #{parent.id}")
                return

        self.update_status("No parent or children to collapse")

    async def action_toggle_archived(self) -> None:
        """Toggle display of archived documents."""
        await self.presenter.toggle_archived()
        if self.presenter.include_archived:
            self.update_status("Showing archived documents")
        else:
            self.update_status("Hiding archived documents")

    # -------------------------------------------------------------------------
    # VimEditor Host Protocol Methods
    # -------------------------------------------------------------------------

    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode (called by VimEditor)."""
        import asyncio

        asyncio.create_task(self._save_and_exit_edit())

    async def _save_and_exit_edit(self) -> None:
        """Async implementation of save and exit."""
        preview = self.query_one("#doc-preview", PreviewPanel)
        await preview.exit_edit_mode(save=True)

    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode info (called by VimEditor)."""
        if message:
            self.update_status(f"Edit Mode | {message}")
        else:
            self.update_status("Edit Mode | ESC=exit | Ctrl+S=save")

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode (called by SelectionTextArea)."""
        import asyncio

        if self.mode == "SELECTION":
            preview = self.query_one("#doc-preview", PreviewPanel)
            asyncio.create_task(preview.exit_selection_mode())

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def _extract_content_without_title(self, content: str, title: str) -> str:
        """Extract content without title header if present."""
        lines = content.split("\n")

        # Check for markdown header
        if lines and lines[0].strip() == f"# {title}":
            start_idx = 1
            if len(lines) > 1 and not lines[1].strip():
                start_idx = 2
            return "\n".join(lines[start_idx:])

        # Check for unicode box patterns
        if len(lines) >= 3:
            box_chars = ["╔", "┏", "┌"]
            close_chars = ["╚", "┗", "└"]
            for box, close in zip(box_chars, close_chars):
                if lines[0].startswith(box) and lines[2].startswith(close):
                    start_idx = 3
                    if len(lines) > 3 and not lines[3].strip():
                        start_idx = 4
                    return "\n".join(lines[start_idx:])

        return content

    def save_state(self) -> Dict[str, Any]:
        """Save current state for restoration."""
        state: Dict[str, Any] = {
            "mode": self.mode,
            "search_query": self._current_vm.search_query if self._current_vm else "",
        }

        list_panel = self.query_one("#doc-list", ListPanel)
        state["list_state"] = list_panel.save_state()

        return state

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore saved state."""
        self.mode = state.get("mode", "NORMAL")

        if "list_state" in state:
            list_panel = self.query_one("#doc-list", ListPanel)
            list_panel.restore_state(state["list_state"])

    async def select_document_by_id(self, doc_id: int) -> bool:
        """Select a document by its ID.

        Args:
            doc_id: The document ID to select

        Returns:
            True if document was found and selected, False otherwise
        """
        list_panel = self.query_one("#doc-list", ListPanel)
        success = list_panel.select_item_by_id(doc_id)

        if not success:
            # Document not in current list - try searching
            logger.info(f"Document #{doc_id} not in current list, searching...")
            await self.presenter.search(f"#{doc_id}")
            return False

        return True
