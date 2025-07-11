#!/usr/bin/env python3
"""
Minimal textual browser that signals for external nvim handling.
"""

import os
import subprocess
import sys
import tempfile

from rich.markdown import Markdown
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Input, Label, RichLog, TextArea

from emdx.sqlite_database import db
from emdx.tags import (
    add_tags_to_document,
    get_document_tags,
    remove_tags_from_document,
    search_by_tags,
)


class SelectionTextArea(TextArea):
    """TextArea that captures 's' key and escape to exit selection mode."""

    def __init__(self, app_instance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app_instance = app_instance

    def on_key(self, event: events.Key) -> None:
        if event.character == "s" or event.key == "escape":
            event.stop()
            event.prevent_default()
            self.app_instance.action_toggle_selection_mode()
            return
        # Let TextArea handle all other keys normally
        super().on_key(event)




class FullScreenView(Screen):
    """Full screen document viewer."""

    CSS = """
    FullScreenView {
        align: center middle;
    }

    #doc-viewer {
        width: 100%;
        height: 100%;
        padding: 0;
    }

    #header {
        dock: top;
        height: 3;
        background: $surface;
        padding: 0 2;
    }

    #footer {
        dock: bottom;
        height: 1;
        background: $surface;
        content-align: center middle;
    }
    """

    BINDINGS = [
        ("q", "close", "Close"),
        ("escape", "close", "Close"),
        ("j", "scroll_down", "Down"),
        ("k", "scroll_up", "Up"),
        ("ctrl+d", "page_down", "Page down"),
        ("ctrl+u", "page_up", "Page up"),
        ("g", "scroll_top", "Top"),
        ("shift+g", "scroll_bottom", "Bottom"),
        ("c", "copy_content", "Copy"),
    ]

    def __init__(self, doc_id: int):
        """Initialize the full screen viewer.

        Args:
            doc_id: The ID of the document to display.

        """
        super().__init__()
        self.doc_id = doc_id

    def compose(self) -> ComposeResult:
        # Just the document content - no header metadata
        with ScrollableContainer(id="doc-viewer"):
            yield RichLog(id="content", wrap=True, highlight=True, markup=True, auto_scroll=False)

        # Footer
        yield Label("Press q or ESC to return", id="footer")

    def on_mount(self) -> None:
        """Load document content when mounted."""
        doc = db.get_document(str(self.doc_id))
        if doc:
            content_log = self.query_one("#content", RichLog)
            content_log.clear()

            # Smart title handling - avoid double titles
            content = doc["content"].strip()

            # Check if content already starts with the title as H1
            content_lines = content.split("\n")
            first_line = content_lines[0].strip() if content_lines else ""

            if first_line == f"# {doc['title']}":
                # Content already has the title, just show content
                markdown_content = content
            else:
                # Add title if not already present
                markdown_content = f"""# {doc['title']}

{content}"""
            md = Markdown(markdown_content, code_theme="monokai")
            content_log.write(md)
            content_log.scroll_to(0, 0, animate=False)

    def action_close(self) -> None:
        """Close the viewer."""
        self.dismiss()

    def action_scroll_down(self) -> None:
        """Scroll down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=1)

    def action_scroll_up(self) -> None:
        """Scroll up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-1)

    def action_page_down(self) -> None:
        """Page down."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=10)

    def action_page_up(self) -> None:
        """Page up."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_relative(y=-10)

    def action_scroll_top(self) -> None:
        """Scroll to top."""
        self.query_one("#doc-viewer", ScrollableContainer).scroll_to(0, 0, animate=False)

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom."""
        container = self.query_one("#doc-viewer", ScrollableContainer)
        container.scroll_to(0, container.max_scroll_y, animate=False)

    def action_copy_content(self) -> None:
        """Copy current document content to clipboard."""
        try:
            doc = db.get_document(str(self.doc_id))
            if doc:
                self.copy_to_clipboard(doc['content'])
        except Exception:
            # Silently ignore copy errors in full screen view
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key events that aren't bindings."""
        # Let 's' key pass through - handled by main app
        pass


    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess

        # Try pbcopy on macOS first
        try:
            subprocess.run(['pbcopy'], input=text, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(['xclip', '-selection', 'clipboard'],
                             input=text, text=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(['xsel', '--clipboard', '--input'],
                                 input=text, text=True, check=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass





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

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(
                f'Delete document #{self.doc_id}?\n"{self.doc_title}"\n\n'
                f'[dim]Press [bold]y[/bold] to delete, [bold]n[/bold] to cancel[/dim]',
                id="question",
            )
            yield Button("Cancel (n)", variant="primary", id="cancel")
            yield Button("Delete (y)", variant="error", id="delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "delete":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_delete(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MinimalDocumentBrowser(App):
    """Minimal document browser that signals external wrapper for nvim."""

    ALLOW_SELECT = True  # Enable text selection mode

    CSS = """
    #sidebar {
        width: 50%;
        border-right: solid $primary;
    }

    #preview {
        width: 50%;
        padding: 0;
        overflow: hidden;
    }

    RichLog {
        padding: 0 1;
        background: $background;
        width: 100%;
        height: 100%;
        max-width: 100%;
    }
    
    TextArea {
        width: 100%;
        height: 100%;
    }
    
    #selection-content {
        /* Different styling to indicate selection mode */
        border: thick $warning;
    }


    DataTable {
        height: 100%;
    }


    Input {
        dock: top;
        margin: 0 1;
        display: none;
    }

    Input.visible {
        display: block;
    }

    #tag-input {
        display: none;
    }

    #tag-input.visible {
        display: block;
    }

    #tag-selector {
        dock: top;
        display: none;
        height: 1;
        margin: 0 1;
        text-align: center;
    }

    #tag-selector.visible {
        display: block;
    }

    #status {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("shift+g", "cursor_bottom", "Bottom", show=False),
        Binding("/", "search_mode", "Search", key_display="/"),
        Binding("r", "refresh", "Refresh", key_display="r"),
        Binding("e", "edit", "Edit", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("v", "view", "View", show=False),
        Binding("enter", "view", "View", show=False),
        Binding("t", "tag_mode", "Tag", key_display="t"),
        Binding("shift+t", "untag_mode", "Untag", show=False),
        Binding("tab", "focus_preview", "Focus Preview", key_display="Tab"),
        Binding("c", "copy_content", "Copy", key_display="c"),
        Binding("s", "toggle_selection_mode", "Select", key_display="s"),
    ]

    mode = reactive("NORMAL")
    search_query = reactive("")
    tag_action = reactive("")  # "add" or "remove"
    current_tag_completion = reactive(0)  # Current completion index
    selection_mode = reactive(False)  # Text selection mode

    def __init__(self):
        super().__init__()
        self.documents = []
        self.filtered_docs = []
        self.current_doc_id = None

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search... (try 'tags:docker,python' or 'tags:any:config')",
            id="search-input"
        )
        yield Input(placeholder="Enter tags separated by spaces...", id="tag-input")
        yield Label("", id="tag-selector")

        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with ScrollableContainer(id="preview"):
                yield RichLog(
                    id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
                )

        yield Label("", id="status")

    def on_mount(self) -> None:
        try:
            # Set can_focus property after widget is created
            preview_log = self.query_one("#preview-content", RichLog)
            preview_log.can_focus = True


            self.load_documents()
            self.setup_table()
            self.update_status()
            if self.filtered_docs:
                self.on_row_selected()
        except Exception as e:
            # If there's any error during mount, ensure we have a usable state
            import traceback
            traceback.print_exc()
            self.exit(message=f"Error during startup: {e}")

    def load_documents(self):
        try:
            db.ensure_schema()
            docs = db.list_documents(limit=1000)

            # Add tags to each document
            for doc in docs:
                doc['tags'] = get_document_tags(doc['id'])

            self.documents = docs
            self.filtered_docs = docs
        except Exception as e:
            self.exit(message=f"Error loading documents: {e}")

    def setup_table(self):
        table = self.query_one("#doc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "Title", "Tags")

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[:title_space-3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars
            tags_str = ", ".join(doc.get("tags", []))[:30]
            if len(", ".join(doc.get("tags", []))) > 30:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        table.focus()

    def on_row_selected(self):
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]
            self.current_doc_id = doc["id"]
            self.update_preview(doc["id"])

    def on_data_table_row_highlighted(self, message: DataTable.RowHighlighted) -> None:
        if message.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[message.cursor_row]
            self.current_doc_id = doc["id"]
            # If in selection mode, exit it and go back to normal preview
            if self.selection_mode:
                self.action_toggle_selection_mode()
            # Always update preview (after potentially exiting selection mode)
            self.update_preview(doc["id"])

    def update_preview(self, doc_id: int):
        try:
            doc = db.get_document(str(doc_id))
            if doc:
                preview_log = self.query_one("#preview-content", RichLog)
                preview_log.clear()

                # Smart title handling - avoid double titles
                content = doc["content"].strip()

                # Check if content already starts with the title as H1
                content_lines = content.split("\n")
                first_line = content_lines[0].strip() if content_lines else ""

                if first_line == f"# {doc['title']}":
                    # Content already has the title, just show content
                    markdown_content = content
                else:
                    # Add title if not already present
                    markdown_content = f"""# {doc['title']}

{content}"""

                md = Markdown(markdown_content, code_theme="monokai")
                preview_log.write(md)
                preview_log.scroll_to(0, 0, animate=False)

        except Exception as e:
            try:
                preview_log = self.query_one("#preview-content", RichLog)
                preview_log.clear()
                preview_log.write(f"[red]Error loading preview: {e}[/red]")
            except Exception:
                # If we can't find the preview log, we're probably in selection mode
                pass

    def update_status(self):
        status = self.query_one("#status", Label)
        search_input = self.query_one("#search-input", Input)

        if search_input.value and search_input.value.startswith("tags:"):
            tag_query = search_input.value[5:].strip()
            status.update(
                f"{len(self.filtered_docs)}/{len(self.documents)} documents "
                f"(tag search: {tag_query})"
            )
        elif search_input.value:
            status.update(
                f"{len(self.filtered_docs)}/{len(self.documents)} documents "
                f"(search: {search_input.value})"
            )
        else:
            status.update(f"{len(self.filtered_docs)}/{len(self.documents)} documents")

    def watch_mode(self, old_mode: str, new_mode: str):
        search = self.query_one("#search-input", Input)
        tag_input = self.query_one("#tag-input", Input)
        tag_selector = self.query_one("#tag-selector", Label)
        table = self.query_one("#doc-table", DataTable)

        if new_mode == "SEARCH":
            search.add_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.focus()
        elif new_mode == "TAG":
            search.remove_class("visible")

            # Show current tags in placeholder
            if self.current_doc_id:
                doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
                if doc:
                    current_tags = doc.get("tags", [])

                    if self.tag_action == "add":
                        # Show input for adding tags
                        tag_input.add_class("visible")
                        tag_selector.remove_class("visible")
                        if current_tags:
                            tag_input.placeholder = f"Add tags (current: {', '.join(current_tags)})"
                        else:
                            tag_input.placeholder = "Add tags (no current tags)"
                        tag_input.focus()
                    else:  # remove
                        # Show visual selector for removing tags
                        tag_input.remove_class("visible")
                        if current_tags:
                            tag_selector.add_class("visible")
                            self.current_tag_completion = 0  # Start with first tag
                            self.update_tag_selector()
                            status = self.query_one("#status", Label)
                            status.update("Tab to navigate, Enter to remove tag, Esc to cancel")
                        else:
                            tag_selector.remove_class("visible")
                            status = self.query_one("#status", Label)
                            status.update("No tags to remove")
                            self.mode = "NORMAL"
                            return

                    # Only reset completion index for add mode
                    if self.tag_action == "add":
                        self.current_tag_completion = 0
        else:
            search.remove_class("visible")
            tag_input.remove_class("visible")
            tag_selector.remove_class("visible")
            search.value = ""
            tag_input.value = ""
            self.current_tag_completion = 0  # Reset completion index
            table.focus()

    def action_search_mode(self):
        self.mode = "SEARCH"

    def action_tag_mode(self):
        if not self.current_doc_id:
            return
        self.tag_action = "add"
        self.mode = "TAG"

    def action_untag_mode(self):
        if not self.current_doc_id:
            return
        self.tag_action = "remove"
        self.mode = "TAG"

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search-input":
            self.search_query = event.value
            self.filter_documents(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self.mode = "NORMAL"
        elif event.input.id == "tag-input":
            # Process tag input for both add and remove
            tags = [tag.strip() for tag in event.value.split() if tag.strip()]
            if tags and self.current_doc_id:
                # Save current position
                table = self.query_one("#doc-table", DataTable)
                current_row = table.cursor_row
                current_doc_id = self.current_doc_id

                try:
                    if self.tag_action == "add":
                        added_tags = add_tags_to_document(self.current_doc_id, tags)
                        if added_tags:
                            status = self.query_one("#status", Label)
                            status.update(f"Added tags: {', '.join(added_tags)}")
                        else:
                            status = self.query_one("#status", Label)
                            status.update("No new tags added (may already exist)")
                    else:  # remove
                        removed_tags = remove_tags_from_document(self.current_doc_id, tags)
                        if removed_tags:
                            status = self.query_one("#status", Label)
                            status.update(f"Removed tags: {', '.join(removed_tags)}")
                        else:
                            status = self.query_one("#status", Label)
                            status.update("No tags removed (may not exist)")

                    # Refresh document data and restore position
                    self.load_documents()
                    self.filter_documents(self.search_query)
                    self.restore_table_position(current_doc_id, current_row)

                except Exception as e:
                    status = self.query_one("#status", Label)
                    status.update(f"Error: {e}")

            self.mode = "NORMAL"

    def on_key(self, event: events.Key):
        # Handle 's' key for selection mode toggle anywhere in the app
        if event.character == "s":
            # Always capture 's' at the app level, regardless of focus
            event.stop()
            event.prevent_default()
            self.action_toggle_selection_mode()
            return

        if self.mode == "SEARCH":
            if event.key == "escape":
                self.mode = "NORMAL"
                self.search_query = ""
                self.filter_documents("")
                event.prevent_default()
        elif self.mode == "TAG":
            if event.key == "escape":
                self.mode = "NORMAL"
                event.prevent_default()
            elif event.key == "tab" and self.tag_action == "remove":
                # Tab cycling for tag removal
                self.complete_tag_removal()
                event.prevent_default()
                event.stop()
            elif event.key == "enter" and self.tag_action == "remove":
                # Remove the highlighted tag
                self.remove_highlighted_tag()
                event.prevent_default()
        elif self.mode == "NORMAL":
            # Handle keys that don't require a document
            if event.key == "tab":
                event.prevent_default()
                event.stop()
                self.action_focus_preview()
            elif event.character == "s":
                event.prevent_default()
                event.stop()
                self.action_toggle_selection_mode()
            # Handle keys that require a document
            elif self.current_doc_id:
                if event.key == "enter":
                    event.prevent_default()
                    event.stop()
                    self.action_view()
                elif event.character == "e":
                    event.prevent_default()
                    event.stop()
                    self.action_edit()
                elif event.character == "d":
                    event.prevent_default()
                    event.stop()
                    self.action_delete()
                elif event.character == "v":
                    event.prevent_default()
                    event.stop()
                    self.action_view()
                elif event.character == "t":
                    event.prevent_default()
                    event.stop()
                    self.action_tag_mode()
                elif event.character == "T":
                    event.prevent_default()
                    event.stop()
                    self.action_untag_mode()
                elif event.character == "c":
                    event.prevent_default()
                    event.stop()
                    self.action_copy_content()

    def filter_documents(self, query: str):
        if not query:
            self.filtered_docs = self.documents
        elif query.startswith("tags:"):
            # Tag-based search mode: "tags:docker,kubernetes" or "tags:any:docker,python"
            tag_query = query[5:].strip()  # Remove "tags:" prefix

            if tag_query.startswith("any:"):
                # Search for documents with ANY of the specified tags
                tags = [tag.strip() for tag in tag_query[4:].split(",") if tag.strip()]
                mode = "any"
            else:
                # Default: search for documents with ALL specified tags
                tags = [tag.strip() for tag in tag_query.split(",") if tag.strip()]
                mode = "all"

            if tags:
                try:
                    # Use the existing search_by_tags function
                    results = search_by_tags(tags, mode=mode, limit=1000)

                    # Convert results to match our document format
                    result_ids = {doc["id"] for doc in results}
                    self.filtered_docs = [doc for doc in self.documents if doc["id"] in result_ids]
                except Exception:
                    # Fall back to simple filtering if search_by_tags fails
                    self.filtered_docs = [
                        doc for doc in self.documents
                        if any(
                            tag.lower() in [t.lower() for t in doc.get("tags", [])] for tag in tags
                        )
                    ]
            else:
                self.filtered_docs = self.documents
        else:
            # Regular search in title, project, and tags
            query_lower = query.lower()
            self.filtered_docs = [
                doc
                for doc in self.documents
                if query_lower in doc["title"].lower()
                or query_lower in (doc["project"] or "").lower()
                or any(query_lower in tag.lower() for tag in doc.get("tags", []))
            ]

        table = self.query_one("#doc-table", DataTable)
        table.clear()

        for doc in self.filtered_docs:
            # Format timestamp as MM-DD HH:MM (11 chars)
            timestamp = doc["created_at"].strftime("%m-%d %H:%M")

            # Calculate available space for title (50 total - 11 for timestamp)
            title_space = 50 - 11
            title = doc["title"][:title_space]
            if len(doc["title"]) >= title_space:
                title = title[:title_space-3] + "..."

            # Right-justify timestamp by padding title to full width
            formatted_title = f"{title:<{title_space}}{timestamp}"

            # Expanded tag display - limit to 30 chars
            tags_str = ", ".join(doc.get("tags", []))[:30]
            if len(", ".join(doc.get("tags", []))) > 30:
                tags_str += "..."

            table.add_row(
                str(doc["id"]),
                formatted_title,
                tags_str or "-",
            )

        self.update_status()

        if self.filtered_docs and table.row_count > 0:
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_down(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_down()

    def action_cursor_up(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.action_cursor_up()

    def action_cursor_top(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_cursor_bottom(self):
        if self.mode == "NORMAL":
            table = self.query_one("#doc-table", DataTable)
            if table.row_count > 0:
                table.cursor_coordinate = (table.row_count - 1, 0)
                self.on_row_selected()

    def action_edit(self):
        """Signal external wrapper for nvim editing."""
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        try:
            # Get document content
            doc = db.get_document(str(self.current_doc_id))
            if not doc:
                return

            # Create temp file for editing
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False, prefix=f"emdx_doc_{self.current_doc_id}_"
            )

            # Write header and content for editing
            temp_file.write(f"# Editing: {doc['title']} (ID: {doc['id']})\n")
            temp_file.write(f"# Project: {doc['project'] or 'None'}\n")
            temp_file.write(f"# Created: {doc['created_at'].strftime('%Y-%m-%d %H:%M')}\n")
            temp_file.write("# Lines starting with '#' will be removed\n")
            temp_file.write("#\n")
            temp_file.write("# First line (after comments) will be used as the title\n")
            temp_file.write("# The rest will be the content\n")
            temp_file.write("#\n")
            temp_file.write(f"{doc['title']}\n\n")
            temp_file.write(doc["content"])
            temp_file.close()

            # Signal external wrapper
            edit_signal = f"/tmp/emdx_edit_signal_{os.getpid()}"
            with open(edit_signal, "w") as f:
                f.write(f"{temp_file.name}|{self.current_doc_id}")

            # Exit to signal edit request
            self.exit()

        except Exception as e:
            # Show error in status
            status = self.query_one("#status", Label)
            status.update(f"Error preparing edit: {e}")

    def action_delete(self):
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        table = self.query_one("#doc-table", DataTable)
        if table.cursor_row is not None and table.cursor_row < len(self.filtered_docs):
            doc = self.filtered_docs[table.cursor_row]

            def check_delete(should_delete: bool) -> None:
                if should_delete:
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "emdx.cli",
                            "delete",
                            str(self.current_doc_id),
                            "--force",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        self.load_documents()
                        self.filter_documents(self.search_query)

            self.push_screen(DeleteConfirmScreen(doc["id"], doc["title"]), check_delete)

    def action_view(self):
        if self.mode == "SEARCH" or not self.current_doc_id:
            return

        self.push_screen(FullScreenView(self.current_doc_id))

    def action_refresh(self):
        """Refresh the document list."""
        # Save current state
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = None

        # Get current document ID if a row is selected
        if current_row is not None and current_row < len(self.filtered_docs):
            current_doc_id = self.filtered_docs[current_row]["id"]

        # Save search state
        search_query = self.search_query if self.mode == "SEARCH" else None

        # Reload documents
        self.load_documents()

        # Clear and rebuild table
        table.clear()
        self.setup_table()

        # Restore search if it was active
        if search_query:
            self.search_query = search_query
            search_input = self.query_one("#search-input", Input)
            search_input.value = search_query
            self.filter_documents(search_query)

        # Restore selection
        if current_doc_id:
            # Try to find the same document
            for idx, doc in enumerate(self.filtered_docs):
                if doc["id"] == current_doc_id:
                    table.cursor_coordinate = (idx, 0)
                    self.on_row_selected()
                    break
            else:
                # Document not found, restore row position if valid
                if current_row is not None and current_row < len(self.filtered_docs):
                    table.cursor_coordinate = (current_row, 0)
                    self.on_row_selected()
                elif self.filtered_docs:
                    # Default to first row if available
                    table.cursor_coordinate = (0, 0)
                    self.on_row_selected()
        elif self.filtered_docs and current_row is not None:
            # No previous doc ID, just restore row position
            new_row = min(current_row, len(self.filtered_docs) - 1)
            table.cursor_coordinate = (new_row, 0)
            self.on_row_selected()

        # Show notification
        status = self.query_one("#status", Label)
        status.update("Documents refreshed")


    def update_tag_selector(self):
        """Update the visual tag selector."""
        if not self.current_doc_id:
            return

        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        tag_selector = self.query_one("#tag-selector", Label)

        # Build visual representation: a  [b]  c
        visual_tags = []
        for i, tag in enumerate(current_tags):
            if i == self.current_tag_completion:
                visual_tags.append(f"[reverse]{tag}[/reverse]")
            else:
                visual_tags.append(tag)

        tag_selector.update("    ".join(visual_tags))

    def complete_tag_removal(self):
        """Handle tab cycling for tag removal."""
        if not self.current_doc_id:
            return

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags:
            return

        # Move to next tag
        self.current_tag_completion = (self.current_tag_completion + 1) % len(current_tags)

        # Update visual selector
        self.update_tag_selector()

    def remove_highlighted_tag(self):
        """Remove the currently highlighted tag."""
        if not self.current_doc_id:
            return

        # Save current table position
        table = self.query_one("#doc-table", DataTable)
        current_row = table.cursor_row
        current_doc_id = self.current_doc_id

        # Get current document tags
        doc = next((d for d in self.filtered_docs if d["id"] == self.current_doc_id), None)
        if not doc:
            return

        current_tags = doc.get("tags", [])
        if not current_tags or self.current_tag_completion >= len(current_tags):
            return

        # Get the tag to remove
        tag_to_remove = current_tags[self.current_tag_completion]

        try:
            # Remove the tag
            removed_tags = remove_tags_from_document(self.current_doc_id, [tag_to_remove])
            if removed_tags:
                # Show success message
                status = self.query_one("#status", Label)
                status.update(f"Removed tag: {tag_to_remove}")

                # Refresh document data but preserve position
                self.load_documents()
                self.filter_documents(self.search_query)

                # Restore table position
                self.restore_table_position(current_doc_id, current_row)

                # Exit tag mode
                self.mode = "NORMAL"
            else:
                status = self.query_one("#status", Label)
                status.update("Failed to remove tag")
        except Exception as e:
            status = self.query_one("#status", Label)
            status.update(f"Error removing tag: {e}")

    def restore_table_position(self, target_doc_id: int, fallback_row: int):
        """Restore table position to specific document or row."""
        table = self.query_one("#doc-table", DataTable)

        # First try to find the same document
        for idx, doc in enumerate(self.filtered_docs):
            if doc["id"] == target_doc_id:
                table.cursor_coordinate = (idx, 0)
                self.on_row_selected()
                return

        # Document not found (maybe filtered out), restore row position if valid
        if fallback_row is not None and fallback_row < len(self.filtered_docs):
            table.cursor_coordinate = (fallback_row, 0)
            self.on_row_selected()
        elif self.filtered_docs:
            # Default to first row if available
            table.cursor_coordinate = (0, 0)
            self.on_row_selected()

    def action_copy_content(self):
        """Copy current document content to clipboard."""
        if self.current_doc_id:
            try:
                doc = db.get_document(str(self.current_doc_id))
                if doc:
                    self.copy_to_clipboard(doc['content'])
            except Exception as e:
                status = self.query_one("#status", Label)
                status.update(f"Copy failed: {e}")


    def action_focus_preview(self):
        """Focus the preview pane."""
        # Allow focus preview to work in any mode
        try:
            preview_log = self.query_one("#preview-content", RichLog)
            preview_log.focus()
            status = self.query_one("#status", Label)
            status.update(
                "Preview focused - press 'c' to copy document content"
            )
        except Exception as e:
            status = self.query_one("#status", Label)
            status.update(f"Focus failed: {e}")

    def action_toggle_selection_mode(self):
        """Toggle text selection mode."""
        try:
            status = self.query_one("#status", Label)
            preview_container = self.query_one("#preview", ScrollableContainer)

            if not self.selection_mode:
                # Entering selection mode
                self.selection_mode = True

                # Get current document content
                markdown_content = ""
                if self.current_doc_id:
                    try:
                        doc = db.get_document(str(self.current_doc_id))
                        if doc:
                            content = doc["content"].strip()
                            if content.startswith(f"# {doc['title']}"):
                                markdown_content = content
                            else:
                                markdown_content = f"""# {doc['title']}

*Project: {doc['project']} | Tags: {', '.join(doc.get('tags', []))}*
*Created: {doc['created_at'].strftime('%Y-%m-%d %H:%M')}*

{content}"""
                    except Exception:
                        pass

                # Remove RichLog and add TextArea for selection
                preview_container.remove_children()

                # Add header to make it clear this is for selection only
                header_text = (
                    "═══ SELECTION MODE - Select text and Ctrl+C to copy, "
                    "press 's' or Esc to exit ═══\n\n"
                )

                # Use a simpler approach - just let them select and copy
                # We'll show a plain text version that's easier to select
                plain_content = header_text + markdown_content

                # Create a custom TextArea for selection that captures 's' key
                selection_area = SelectionTextArea(
                    self,  # Pass app instance so it can call toggle method
                    plain_content,
                    id="selection-content",
                    theme="dracula",
                    language="markdown",
                )

                # Try to set read_only after creation if it exists
                try:
                    selection_area.read_only = True
                except AttributeError:
                    # Fallback if read_only doesn't exist
                    pass

                preview_container.mount(selection_area)
                selection_area.focus()

                status.update(
                    "SELECT MODE: Select & copy text (edits ignored), press 's' or Esc to exit"
                )
            else:
                # Exiting selection mode - do this carefully
                self.selection_mode = False

                # First remove the TextArea
                preview_container.remove_children()

                # Create new RichLog with proper settings
                preview_log = RichLog(
                    id="preview-content",
                    wrap=True,
                    highlight=True,
                    markup=True,
                    auto_scroll=False,
                )
                preview_log.can_focus = True  # Set this after creation

                # Mount the new RichLog
                preview_container.mount(preview_log)

                # Wait for mount to complete before updating content
                self.call_after_refresh(self._restore_preview_content)

        except Exception as e:
            # If anything goes wrong, try to restore a working state
            import traceback
            traceback.print_exc()
            self.selection_mode = False
            status = self.query_one("#status", Label)
            status.update(f"Error toggling mode: {e}")

    def _restore_preview_content(self):
        """Restore preview content after switching back from selection mode."""
        try:
            # Update the preview with current document
            if self.current_doc_id:
                self.update_preview(self.current_doc_id)

            # Update status
            status = self.query_one("#status", Label)
            status.update("View mode restored - normal navigation active")

            # Return focus to table
            table = self.query_one("#doc-table", DataTable)
            table.focus()
        except Exception:
            import traceback
            traceback.print_exc()

    def watch_selection_mode(self, old_mode: bool, new_mode: bool):
        """React to selection mode changes."""
        # Mode switching is now handled in action_toggle_selection_mode
        pass


    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard with fallback methods."""
        import subprocess
        success = False

        # Try pbcopy on macOS first
        try:
            subprocess.run(['pbcopy'], input=text, text=True, check=True)
            success = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try xclip on Linux
            try:
                subprocess.run(['xclip', '-selection', 'clipboard'],
                             input=text, text=True, check=True)
                success = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try xsel on Linux as fallback
                try:
                    subprocess.run(['xsel', '--clipboard', '--input'],
                                 input=text, text=True, check=True)
                    success = True
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

        status = self.query_one("#status", Label)
        if success:
            status.update("Content copied to clipboard!")
        else:
            status.update("Clipboard not available - manual selection required")


    def action_quit(self):
        self.exit()


def run_minimal():
    """Run the minimal browser and return exit code."""
    try:
        # Check if documents exist
        db.ensure_schema()
        docs = db.list_documents(limit=1)
        if not docs:
            print("No documents found in knowledge base.")
            print("\nGet started with:")
            print("  emdx save <file>         - Save a markdown file")
            print("  emdx direct <title>      - Create a document directly")
            print("  emdx note 'quick note'   - Save a quick note")
            return 0

        # Run the browser
        app = MinimalDocumentBrowser()
        app.run()

        # Check if edit signal exists to determine return code
        edit_signal = f"/tmp/emdx_edit_signal_{os.getpid()}"
        if os.path.exists(edit_signal):
            return 42  # Edit requested
        else:
            return 0  # Normal exit

    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(run_minimal())

