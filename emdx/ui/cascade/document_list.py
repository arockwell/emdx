"""Document list widget for cascade browser."""

from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.services.cascade_service import (
    get_child_info,
    list_documents_at_stage,
)


class DocumentList(Widget):
    """List of documents at the current stage with multi-select support."""

    DEFAULT_CSS = """
    DocumentList {
        height: 100%;
        border: solid $primary;
    }

    DocumentList #doc-table {
        height: 100%;
    }

    DocumentList.focused {
        border: double $accent;
    }

    DocumentList #selection-status {
        height: 1;
        background: $surface;
        padding: 0 1;
        color: $text-muted;
    }
    """

    class DocumentSelected(Message):
        """Fired when a document is selected."""
        def __init__(self, doc_id: int):
            self.doc_id = doc_id
            super().__init__()

    class SelectionChanged(Message):
        """Fired when multi-selection changes."""
        def __init__(self, selected_ids: list[int]):
            self.selected_ids = selected_ids
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docs: list[dict[str, Any]] = []
        self.current_stage = "idea"
        self.selected_ids: set[int] = set()  # Multi-select tracking

    def compose(self) -> ComposeResult:
        table = DataTable(id="doc-table")
        table.add_column("", width=2)  # Selection marker column
        table.add_column("ID", width=6)
        table.add_column("Title", width=38)
        table.add_column("Parent", width=8)
        table.add_column("Created", width=12)
        table.cursor_type = "row"
        yield table
        yield Static("", id="selection-status")

    def load_stage(self, stage: str) -> None:
        """Load documents for a stage."""
        self.current_stage = stage
        self.docs = list_documents_at_stage(stage, limit=50)
        self.selected_ids.clear()  # Clear selection when changing stages
        self._refresh_table()
        self._update_selection_status()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        table = self.query_one("#doc-table", DataTable)
        table.clear()

        if not self.docs:
            return

        for doc in self.docs:
            doc_id = doc["id"]
            doc_id_str = str(doc_id)

            # Selection marker
            marker = "\u25cf" if doc_id in self.selected_ids else " "

            # Title - show more of it
            title = doc["title"]
            # Remove prefix from title display
            if title.startswith("Cascade: "):
                title = title[9:]  # Remove "Cascade: " prefix
            elif title.startswith("Pipeline: "):
                title = title[10:]  # Remove legacy "Pipeline: " prefix

            # For done stage, check for PR URL or children
            if self.current_stage == "done":
                pr_url = doc.get("pr_url")  # Now included in list query
                child_info = get_child_info(doc_id)
                if pr_url:
                    title = f"\U0001f517 {title}"  # Has PR
                elif child_info:
                    title = f"\u2713 {title}"  # Has outputs but no PR
                if len(title) > 36:
                    title = title[:33] + "..."
            else:
                if len(title) > 36:
                    title = title[:33] + "..."

            # Parent ID
            parent = str(doc.get("parent_id") or "-")

            # Created time
            created = ""
            if doc.get("created_at"):
                created = doc["created_at"].strftime("%m/%d %H:%M")

            table.add_row(marker, doc_id_str, title, parent, created, key=doc_id_str)

    def _update_selection_status(self) -> None:
        """Update the selection status bar."""
        status = self.query_one("#selection-status", Static)
        count = len(self.selected_ids)
        if count > 0:
            ids = ", ".join(f"#{id}" for id in sorted(self.selected_ids))
            status.update(f"[bold cyan]Selected ({count}):[/] {ids} \u2502 [dim]Space[/dim] toggle \u2502 [dim]s[/dim] synthesize selected")  # noqa: E501
        else:
            status.update("[dim]Space to select docs for synthesis \u2502 s synthesizes all if none selected[/dim]")  # noqa: E501

    def toggle_selection(self) -> None:
        """Toggle selection of current document."""
        doc_id = self.get_selected_doc_id()
        if doc_id:
            if doc_id in self.selected_ids:
                self.selected_ids.remove(doc_id)
            else:
                self.selected_ids.add(doc_id)
            self._refresh_table()
            self._update_selection_status()
            self.post_message(self.SelectionChanged(list(self.selected_ids)))

    def select_all(self) -> None:
        """Select all documents in current stage."""
        self.selected_ids = {doc["id"] for doc in self.docs}
        self._refresh_table()
        self._update_selection_status()
        self.post_message(self.SelectionChanged(list(self.selected_ids)))

    def clear_selection(self) -> None:
        """Clear all selections."""
        self.selected_ids.clear()
        self._refresh_table()
        self._update_selection_status()
        self.post_message(self.SelectionChanged([]))

    def get_selected_ids(self) -> list[int]:
        """Get list of selected document IDs."""
        return list(self.selected_ids)

    def get_selected_doc_id(self) -> int | None:
        """Get currently selected document ID (cursor position)."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                try:
                    return int(row_key[1])  # ID is now in column 1 (after marker)
                except (ValueError, IndexError):
                    pass
        return None

    def move_cursor(self, direction: int) -> None:
        """Move cursor up (-1) or down (+1)."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0:
            if direction > 0:
                table.action_cursor_down()
            else:
                table.action_cursor_up()

            # Notify of selection change
            doc_id = self.get_selected_doc_id()
            if doc_id:
                self.post_message(self.DocumentSelected(doc_id))
