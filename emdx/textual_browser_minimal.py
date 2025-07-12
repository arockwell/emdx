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
from textual.widgets import Button, DataTable, Input, Label, RichLog

from emdx.database import db


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
    ]

    def __init__(self, doc_id: int):
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
                f'Delete document #{self.doc_id}?\n"{self.doc_title}"\n\n[dim]Press [bold]y[/bold] to delete, [bold]n[/bold] to cancel[/dim]',
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

    CSS = """
    #sidebar {
        width: 50%;
        border-right: solid $primary;
    }

    #preview {
        width: 50%;
        padding: 0;
    }

    RichLog {
        padding: 0 1;
        background: $background;
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
        Binding("e", "edit", "Edit", show=False),
        Binding("d", "delete", "Delete", show=False),
        Binding("v", "view", "View", show=False),
        Binding("enter", "view", "View", show=False),
    ]

    mode = reactive("NORMAL")
    search_query = reactive("")

    def __init__(self):
        super().__init__()
        self.documents = []
        self.filtered_docs = []
        self.current_doc_id = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type to search...", id="search-input")

        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="doc-table")
            with ScrollableContainer(id="preview"):
                yield RichLog(
                    id="preview-content", wrap=True, highlight=True, markup=True, auto_scroll=False
                )

        yield Label("", id="status")

    def on_mount(self) -> None:
        self.load_documents()
        self.setup_table()
        self.update_status()
        if self.filtered_docs:
            self.on_row_selected()

    def load_documents(self):
        try:
            db.ensure_schema()
            docs = db.list_documents(limit=1000)
            self.documents = docs
            self.filtered_docs = docs
        except Exception as e:
            self.exit(message=f"Error loading documents: {e}")

    def setup_table(self):
        table = self.query_one("#doc-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "Title", "Project", "Created", "Views")

        for doc in self.filtered_docs:
            created = doc["created_at"].strftime("%Y-%m-%d")
            table.add_row(
                str(doc["id"]),
                doc["title"][:40] + "..." if len(doc["title"]) > 40 else doc["title"],
                doc["project"] or "None",
                created,
                str(doc["access_count"]),
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
            preview_log = self.query_one("#preview-content", RichLog)
            preview_log.clear()
            preview_log.write(f"[red]Error loading preview: {e}[/red]")

    def update_status(self):
        status = self.query_one("#status", Label)
        status.update(f"{len(self.filtered_docs)}/{len(self.documents)} documents")

    def watch_mode(self, old_mode: str, new_mode: str):
        if new_mode == "SEARCH":
            search = self.query_one("#search-input", Input)
            search.add_class("visible")
            search.focus()
        else:
            search = self.query_one("#search-input", Input)
            search.remove_class("visible")
            search.value = ""
            table = self.query_one("#doc-table", DataTable)
            table.focus()

    def action_search_mode(self):
        self.mode = "SEARCH"

    def on_input_changed(self, event: Input.Changed):
        if event.input.id == "search-input":
            self.search_query = event.value
            self.filter_documents(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            self.mode = "NORMAL"

    def on_key(self, event: events.Key):
        if self.mode == "SEARCH":
            if event.key == "escape":
                self.mode = "NORMAL"
                self.search_query = ""
                self.filter_documents("")
                event.prevent_default()
        elif self.mode == "NORMAL":
            if event.character and self.current_doc_id:
                if event.character == "e":
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

    def filter_documents(self, query: str):
        if not query:
            self.filtered_docs = self.documents
        else:
            query_lower = query.lower()
            self.filtered_docs = [
                doc
                for doc in self.documents
                if query_lower in doc["title"].lower()
                or query_lower in (doc["project"] or "").lower()
            ]

        table = self.query_one("#doc-table", DataTable)
        table.clear()

        for doc in self.filtered_docs:
            created = doc["created_at"].strftime("%Y-%m-%d")
            table.add_row(
                str(doc["id"]),
                doc["title"][:40] + "..." if len(doc["title"]) > 40 else doc["title"],
                doc["project"] or "None",
                created,
                str(doc["access_count"]),
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
