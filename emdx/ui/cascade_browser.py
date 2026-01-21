"""Cascade Browser - TUI for viewing and managing the cascade transformation pipeline."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, MarkdownViewer, Static

from emdx.database.documents import (
    get_document,
    get_cascade_stats,
    list_documents_at_stage,
    update_document_stage,
)
from emdx.database.connection import db_connection

logger = logging.getLogger(__name__)

# Fixed cascade stages
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_EMOJI = {
    "idea": "💡",
    "prompt": "📝",
    "analyzed": "🔍",
    "planned": "📋",
    "done": "✅",
}
NEXT_STAGE = {
    "idea": "prompt",
    "prompt": "analyzed",
    "analyzed": "planned",
    "planned": "done",
}


class NewIdeaScreen(ModalScreen):
    """Modal screen for entering a new cascade idea."""

    CSS = """
    NewIdeaScreen {
        align: center middle;
    }
    #idea-dialog {
        width: 70;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #idea-label {
        width: 100%;
        padding-bottom: 1;
    }
    #idea-input {
        width: 100%;
        margin-bottom: 1;
    }
    #idea-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    #idea-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.idea_text = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="idea-dialog"):
            yield Label("💡 Enter new idea for the cascade:", id="idea-label")
            yield Input(placeholder="Describe your idea...", id="idea-input")
            with Horizontal(id="idea-buttons"):
                yield Button("Add Idea", variant="primary", id="add-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-btn":
            idea_input = self.query_one("#idea-input", Input)
            self.idea_text = idea_input.value.strip()
            if self.idea_text:
                self.dismiss(self.idea_text)
            else:
                label = self.query_one("#idea-label", Label)
                label.update("[red]⚠️ Idea cannot be empty[/red]")
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in the input field."""
        self.idea_text = event.value.strip()
        if self.idea_text:
            self.dismiss(self.idea_text)
        else:
            label = self.query_one("#idea-label", Label)
            label.update("[red]⚠️ Idea cannot be empty[/red]")

    def on_mount(self) -> None:
        idea_input = self.query_one("#idea-input", Input)
        idea_input.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


def get_recent_cascade_activity(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent cascade activity from executions and document changes."""
    with db_connection.get_connection() as conn:
        # Get recent executions related to cascade
        cursor = conn.execute(
            """
            SELECT
                e.id,
                e.doc_id,
                e.doc_title,
                e.status,
                e.started_at,
                e.completed_at,
                d.stage,
                d.parent_id,
                e.cascade_run_id
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.doc_title LIKE 'Cascade:%' OR e.doc_title LIKE 'Pipeline:%' OR d.stage IS NOT NULL OR e.cascade_run_id IS NOT NULL
            ORDER BY e.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "exec_id": row[0],
                "doc_id": row[1],
                "doc_title": row[2],
                "status": row[3],
                "started_at": row[4],
                "completed_at": row[5],
                "stage": row[6],
                "parent_id": row[7],
                "cascade_run_id": row[8],
            })
        return results


def get_recent_stage_transitions(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent stage transitions (documents created from parent documents).

    A transition is when a document moves from one stage to the next,
    tracked via the parent_id relationship.
    """
    # Reverse mapping: to_stage -> from_stage
    PREV_STAGE = {
        "prompt": "idea",
        "analyzed": "prompt",
        "planned": "analyzed",
        "done": "planned",
    }

    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                child.id as child_id,
                child.title as child_title,
                child.stage as to_stage,
                child.created_at,
                parent.id as parent_id,
                parent.title as parent_title
            FROM documents child
            INNER JOIN documents parent ON child.parent_id = parent.id
            WHERE child.stage IS NOT NULL
            ORDER BY child.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            to_stage = row[2]
            # Derive from_stage from to_stage (parent was at previous stage)
            from_stage = PREV_STAGE.get(to_stage, "?")
            results.append({
                "child_id": row[0],
                "child_title": row[1],
                "to_stage": to_stage,
                "created_at": row[3],
                "parent_id": row[4],
                "parent_title": row[5],
                "from_stage": from_stage,
            })
        return results


def get_recent_cascade_runs(limit: int = 5) -> List[Dict[str, Any]]:
    """Get recent cascade runs with their status and progress."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT
                cr.id,
                cr.start_doc_id,
                cr.current_doc_id,
                cr.start_stage,
                cr.stop_stage,
                cr.current_stage,
                cr.status,
                cr.pr_url,
                cr.started_at,
                cr.completed_at,
                cr.error_message,
                d.title as start_doc_title
            FROM cascade_runs cr
            LEFT JOIN documents d ON cr.start_doc_id = d.id
            ORDER BY cr.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "run_id": row[0],
                "start_doc_id": row[1],
                "current_doc_id": row[2],
                "start_stage": row[3],
                "stop_stage": row[4],
                "current_stage": row[5],
                "status": row[6],
                "pr_url": row[7],
                "started_at": row[8],
                "completed_at": row[9],
                "error_message": row[10],
                "start_doc_title": row[11],
            })
        return results


class StageSummaryBar(Widget):
    """Compact bar showing all stages with counts and current selection."""

    DEFAULT_CSS = """
    StageSummaryBar {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    StageSummaryBar #stage-bar {
        height: 1;
        text-align: center;
    }

    StageSummaryBar #stage-detail {
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    current_stage = reactive("idea")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stats: Dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="stage-bar")
        yield Static("", id="stage-detail")

    def refresh_stats(self) -> None:
        """Refresh stage statistics."""
        self.stats = get_cascade_stats()
        self._update_display()

    def _update_display(self) -> None:
        """Update the display."""
        bar = self.query_one("#stage-bar", Static)
        detail = self.query_one("#stage-detail", Static)

        # Build stage bar with arrows
        parts = []
        for stage in STAGES:
            count = self.stats.get(stage, 0)
            emoji = STAGE_EMOJI.get(stage, "")

            if stage == self.current_stage:
                # Highlighted current stage
                parts.append(f"[bold reverse] {emoji} {stage.upper()} ({count}) [/]")
            elif count > 0:
                parts.append(f"[bold]{emoji} {stage}[/bold] ({count})")
            else:
                parts.append(f"[dim]{emoji} {stage} (0)[/dim]")

        bar.update(" → ".join(parts))

        # Show detail for current stage
        count = self.stats.get(self.current_stage, 0)
        if count > 0:
            detail.update(f"[bold]← h[/bold] prev stage │ [bold]l →[/bold] next stage │ {count} document{'s' if count != 1 else ''} at {self.current_stage}")
        else:
            detail.update(f"[bold]← h[/bold] prev stage │ [bold]l →[/bold] next stage │ No documents at {self.current_stage}")


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
        def __init__(self, selected_ids: List[int]):
            self.selected_ids = selected_ids
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docs: List[Dict[str, Any]] = []
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
            marker = "●" if doc_id in self.selected_ids else " "

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
                child_info = self._get_child_info(doc_id)
                if pr_url:
                    title = f"🔗 {title}"  # Has PR
                elif child_info:
                    title = f"✓ {title}"  # Has outputs but no PR
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

    def _get_child_info(self, parent_id: int) -> Optional[Dict[str, Any]]:
        """Get info about child documents (outputs from processing)."""
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, stage FROM documents WHERE parent_id = ? LIMIT 1",
                (parent_id,)
            )
            row = cursor.fetchone()
            if row:
                return {"id": row[0], "title": row[1], "stage": row[2]}
        return None

    def _get_doc_pr_url(self, doc_id: int) -> Optional[str]:
        """Get PR URL for a document."""
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT pr_url FROM documents WHERE id = ?",
                (doc_id,)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None

    def _update_selection_status(self) -> None:
        """Update the selection status bar."""
        status = self.query_one("#selection-status", Static)
        count = len(self.selected_ids)
        if count > 0:
            ids = ", ".join(f"#{id}" for id in sorted(self.selected_ids))
            status.update(f"[bold cyan]Selected ({count}):[/] {ids} │ [dim]Space[/dim] toggle │ [dim]s[/dim] synthesize selected")
        else:
            status.update("[dim]Space to select docs for synthesis │ s synthesizes all if none selected[/dim]")

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

    def get_selected_ids(self) -> List[int]:
        """Get list of selected document IDs."""
        return list(self.selected_ids)

    def get_selected_doc_id(self) -> Optional[int]:
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


class DocumentPreview(Widget):
    """Preview pane for selected document content."""

    DEFAULT_CSS = """
    DocumentPreview {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }

    DocumentPreview #preview-header {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    DocumentPreview #preview-content {
        height: 1fr;
        overflow-y: auto;
    }

    DocumentPreview MarkdownViewer {
        height: 100%;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_doc_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Static("[dim]Select a document to preview[/dim]", id="preview-header")
        yield MarkdownViewer("", id="preview-content", show_table_of_contents=False)

    def show_document(self, doc_id: int) -> None:
        """Show a document in the preview."""
        if doc_id == self.current_doc_id:
            return

        self.current_doc_id = doc_id
        doc = get_document(str(doc_id))

        if doc:
            header = self.query_one("#preview-header", Static)

            # Build header with more info
            stage = doc.get("stage") or "none"
            parent = doc.get("parent_id")
            parent_info = f" [dim]← parent #{parent}[/dim]" if parent else ""

            # For done stage, show the output chain
            if stage == "done":
                children = self._get_document_children(doc_id)
                if children:
                    child_info = " → ".join(f"#{c['id']} ({c['stage']})" for c in children)
                    header.update(
                        f"[bold]#{doc['id']}[/bold] │ {STAGE_EMOJI.get(stage, '')} {stage} │ [green]Outputs: {child_info}[/green]\n"
                        f"[dim]{doc['title'][:70]}[/dim]"
                    )
                else:
                    header.update(
                        f"[bold]#{doc['id']}[/bold] │ {STAGE_EMOJI.get(stage, '')} {stage} │ [yellow]No outputs yet[/yellow]\n"
                        f"[dim]{doc['title'][:70]}[/dim]"
                    )
            else:
                header.update(
                    f"[bold]#{doc['id']}[/bold] │ {STAGE_EMOJI.get(stage, '')} {stage}{parent_info}\n"
                    f"[dim]{doc['title'][:70]}[/dim]"
                )

            content_widget = self.query_one("#preview-content", MarkdownViewer)
            content = doc["content"]

            # For done stage, show a summary with lineage and PR link
            if stage == "done":
                children = self._get_document_children(doc_id)
                pr_url = doc.get("pr_url")

                lineage = "## 📊 Cascade Results\n\n"

                # Show PR link prominently if available
                if pr_url:
                    lineage += f"### 🔗 Pull Request\n\n**[{pr_url}]({pr_url})**\n\n"

                lineage += f"**Input:** #{doc_id}\n\n"

                if children:
                    lineage += "**Outputs:**\n"
                    for child in children:
                        child_pr = child.get('pr_url')
                        pr_indicator = " 🔗" if child_pr else ""
                        lineage += f"- #{child['id']} → {child['stage']}: {child['title'][:50]}{pr_indicator}\n"

                lineage += "\n---\n\n## Original Input\n\n"
                content = lineage + content

            if len(content) > 8000:
                content = content[:8000] + "\n\n[...truncated...]"
            content_widget.document.update(content)

    def _get_document_children(self, parent_id: int) -> List[Dict[str, Any]]:
        """Get all child documents recursively."""
        children = []
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, stage, pr_url FROM documents WHERE parent_id = ? ORDER BY id",
                (parent_id,)
            )
            for row in cursor.fetchall():
                child = {"id": row[0], "title": row[1], "stage": row[2], "pr_url": row[3]}
                children.append(child)
                # Recursively get grandchildren
                children.extend(self._get_document_children(row[0]))
        return children

    def clear(self) -> None:
        """Clear the preview."""
        self.current_doc_id = None
        header = self.query_one("#preview-header", Static)
        header.update("[dim]Select a document to preview[/dim]")
        content = self.query_one("#preview-content", MarkdownViewer)
        content.document.update("")


class ActivityFeed(Widget):
    """Shows recent pipeline activity with cascade run grouping."""

    DEFAULT_CSS = """
    ActivityFeed {
        height: 10;
        border: solid $primary;
    }

    ActivityFeed #activity-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    ActivityFeed #activity-table {
        height: 1fr;
    }
    """

    show_runs = reactive(True)  # Toggle between runs view and executions view

    def compose(self) -> ComposeResult:
        yield Static("[bold]Cascade Runs[/bold] [dim](r to toggle view)[/dim]", id="activity-header")
        table = DataTable(id="activity-table")
        table.cursor_type = "none"
        table.show_cursor = False
        yield table

    def refresh_activity(self) -> None:
        """Refresh the activity feed."""
        table = self.query_one("#activity-table", DataTable)
        table.clear()

        # Clear existing columns
        while table.columns:
            table.remove_column(table.columns[0].key)

        if self.show_runs:
            self._show_cascade_runs(table)
        else:
            self._show_executions(table)

    def _show_cascade_runs(self, table: DataTable) -> None:
        """Show cascade runs grouped view."""
        header = self.query_one("#activity-header", Static)
        header.update("[bold]Cascade Runs[/bold] [dim](r to toggle view)[/dim]")

        table.add_column("Time", width=8)
        table.add_column("Run", width=5)
        table.add_column("Progress", width=22)
        table.add_column("Status", width=10)
        table.add_column("Document", width=35)

        runs = get_recent_cascade_runs(limit=8)

        for run in runs:
            # Time
            time_str = ""
            if run.get("started_at"):
                try:
                    dt = datetime.fromisoformat(run["started_at"])
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "?"

            # Run ID
            run_id = f"#{run.get('run_id', '?')}"

            # Progress: start_stage → current_stage → stop_stage
            start = run.get("start_stage", "?")
            current = run.get("current_stage", "?")
            stop = run.get("stop_stage", "done")
            start_emoji = STAGE_EMOJI.get(start, "")
            current_emoji = STAGE_EMOJI.get(current, "")
            stop_emoji = STAGE_EMOJI.get(stop, "")

            if run.get("status") == "completed":
                progress = f"{start_emoji}{start} → {stop_emoji}{stop} ✓"
            elif run.get("status") == "running":
                progress = f"{start_emoji}{start} → {current_emoji}[bold]{current}[/] → {stop_emoji}{stop}"
            else:
                progress = f"{start_emoji}{start} → {current_emoji}{current}"

            # Status with color
            status = run.get("status", "?")
            if status == "completed":
                if run.get("pr_url"):
                    status_display = "[green]✓ PR[/green]"
                else:
                    status_display = "[green]✓ done[/green]"
            elif status == "running":
                status_display = "[yellow]⟳ running[/yellow]"
            elif status == "failed":
                status_display = "[red]✗ failed[/red]"
            elif status == "paused":
                status_display = "[cyan]⏸ paused[/cyan]"
            else:
                status_display = f"[dim]{status}[/dim]"

            # Document title
            title = run.get("start_doc_title", "")[:35]
            doc_id = run.get("start_doc_id", "?")
            doc_info = f"#{doc_id} {title}"

            table.add_row(time_str, run_id, progress, status_display, doc_info)

        if not runs:
            table.add_row("", "", "[dim]No cascade runs yet[/dim]", "", "")

    def _show_executions(self, table: DataTable) -> None:
        """Show individual executions view."""
        header = self.query_one("#activity-header", Static)
        header.update("[bold]Recent Executions[/bold] [dim](r to toggle view)[/dim]")

        table.add_column("Time", width=8)
        table.add_column("Doc", width=6)
        table.add_column("Run", width=5)
        table.add_column("Status", width=10)
        table.add_column("Details", width=45)

        activities = get_recent_cascade_activity(limit=10)

        for act in activities:
            # Time
            time_str = ""
            if act.get("completed_at"):
                try:
                    dt = datetime.fromisoformat(act["completed_at"])
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "?"
            elif act.get("started_at"):
                try:
                    dt = datetime.fromisoformat(act["started_at"])
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "?"

            # Doc ID
            doc_id = str(act.get("doc_id") or "?")

            # Cascade run ID (if part of a run)
            run_id = act.get("cascade_run_id")
            run_str = f"#{run_id}" if run_id else "[dim]-[/dim]"

            # Status with color
            status = act.get("status", "?")
            if status == "completed":
                status_display = "[green]✓ done[/green]"
            elif status == "running":
                status_display = "[yellow]⟳ running[/yellow]"
            elif status == "failed":
                status_display = "[red]✗ failed[/red]"
            else:
                status_display = f"[dim]{status}[/dim]"

            # Details
            title = act.get("doc_title", "")
            if title.startswith("Cascade: "):
                title = title[9:]
            elif title.startswith("Pipeline: "):
                title = title[10:]  # Legacy support
            stage = act.get("stage") or ""
            parent = act.get("parent_id")

            details = title[:30]
            if stage:
                details += f" → {stage}"
            if parent:
                details += f" (#{parent})"

            table.add_row(time_str, doc_id, run_str, status_display, details)

    def toggle_view(self) -> None:
        """Toggle between runs view and executions view."""
        self.show_runs = not self.show_runs
        self.refresh_activity()


class CascadeView(Widget):
    """Main pipeline view with stage navigation and preview."""

    class ViewDocument(Message):
        """Message to view a document fullscreen."""
        def __init__(self, doc_id: int):
            self.doc_id = doc_id
            super().__init__()

    class ProcessStage(Message):
        """Message to process a stage."""
        def __init__(self, stage: str, doc_id: Optional[int] = None):
            self.stage = stage
            self.doc_id = doc_id
            super().__init__()

    BINDINGS = [
        Binding("h", "prev_stage", "Prev Stage", show=False),
        Binding("l", "next_stage", "Next Stage", show=False),
        Binding("left", "prev_stage", "Prev Stage", show=False),
        Binding("right", "next_stage", "Next Stage", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("space", "toggle_select", "Select", show=True),
        Binding("enter", "view_doc", "View Full", show=True),
        Binding("n", "new_idea", "New Idea", show=True),
        Binding("a", "advance_doc", "Advance", show=True),
        Binding("p", "process", "Process", show=True),
        Binding("s", "synthesize", "Synthesize", show=True),
        Binding("ctrl+a", "select_all", "Select All", show=False),
        Binding("escape", "clear_selection", "Clear", show=False),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("v", "toggle_activity_view", "Toggle View", show=True),
    ]

    DEFAULT_CSS = """
    CascadeView {
        layout: vertical;
        height: 100%;
    }

    #pv-summary {
        height: 3;
    }

    #pv-main {
        height: 1fr;
    }

    /* Left column: stacked lists */
    #pv-left-column {
        width: 45%;
        height: 100%;
    }

    #pv-doc-list {
        height: 40%;
        border-bottom: solid $secondary;
    }

    #pv-runs-section {
        height: 30%;
        border-bottom: solid $secondary;
    }

    #pv-runs-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #pv-runs-table {
        height: 1fr;
    }

    #pv-exec-section {
        height: 30%;
    }

    #pv-exec-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #pv-exec-table {
        height: 1fr;
    }

    /* Right column: preview pane */
    #pv-preview-container {
        width: 55%;
        height: 100%;
        border-left: solid $primary;
    }

    #pv-preview-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #pv-preview-scroll {
        height: 1fr;
    }

    #pv-preview-content {
        padding: 0 1;
    }

    #pv-preview-log {
        height: 1fr;
        display: none;
    }

    #pv-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    current_stage_idx = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.summary: Optional[StageSummaryBar] = None
        self.doc_list: Optional[DocumentList] = None
        self.transitions_table: Optional[DataTable] = None
        self.exec_table: Optional[DataTable] = None
        # For live log streaming
        self.log_stream: Optional['LogStream'] = None
        self.streaming_exec_id: Optional[int] = None
        self._selected_exec: Optional[Dict[str, Any]] = None
        self._exec_data: List[Dict[str, Any]] = []
        self._log_subscriber = None

    def compose(self) -> ComposeResult:
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog

        self.summary = StageSummaryBar(id="pv-summary")
        yield self.summary

        with Horizontal(id="pv-main"):
            # Left column: Work Items, Runs, Executions
            with Vertical(id="pv-left-column"):
                self.doc_list = DocumentList(id="pv-doc-list")
                yield self.doc_list

                with Vertical(id="pv-runs-section"):
                    yield Static("[bold]Transitions[/bold]", id="pv-runs-header")
                    self.transitions_table = DataTable(id="pv-transitions-table", cursor_type="row")
                    yield self.transitions_table

                with Vertical(id="pv-exec-section"):
                    yield Static("[bold]Recent Executions[/bold]", id="pv-exec-header")
                    self.exec_table = DataTable(id="pv-exec-table", cursor_type="row")
                    yield self.exec_table

            # Right column: Preview (document or live log)
            with Vertical(id="pv-preview-container"):
                yield Static("[bold]Preview[/bold]", id="pv-preview-header")
                with ScrollableContainer(id="pv-preview-scroll"):
                    yield RichLog(id="pv-preview-content", highlight=True, markup=True)
                yield RichLog(id="pv-preview-log", highlight=True, markup=True)

        yield Static("", id="pv-status")

    def on_mount(self) -> None:
        """Initialize on mount."""
        # Setup tables
        self._setup_transitions_table()
        self._setup_exec_table()
        self.refresh_all()

    def _setup_transitions_table(self) -> None:
        """Setup the transitions table columns."""
        if self.transitions_table:
            self.transitions_table.add_column("Time", width=8)
            self.transitions_table.add_column("Parent", width=7)
            self.transitions_table.add_column("→", width=12)
            self.transitions_table.add_column("Child", width=20)

    def _setup_exec_table(self) -> None:
        """Setup the executions table columns."""
        if self.exec_table:
            self.exec_table.add_column("ID", width=6)
            self.exec_table.add_column("Time", width=8)
            self.exec_table.add_column("Status", width=10)
            self.exec_table.add_column("Title", width=30)

    def refresh_all(self) -> None:
        """Refresh all components."""
        # Update summary bar
        if self.summary:
            if self.current_stage_idx < len(STAGES):
                self.summary.current_stage = STAGES[self.current_stage_idx]
            self.summary.refresh_stats()

        # Load documents for current stage
        if self.doc_list and self.current_stage_idx < len(STAGES):
            stage = STAGES[self.current_stage_idx]
            self.doc_list.load_stage(stage)

            # Update preview with first doc
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

        # Refresh transitions and executions tables
        self._refresh_transitions_table()
        self._refresh_exec_table()

        # Update status
        self._update_status("[dim]h/l[/dim] stages │ [dim]j/k[/dim] docs │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]s[/dim] synthesize │ [dim]r[/dim] refresh")

    def _refresh_transitions_table(self) -> None:
        """Refresh the stage transitions table."""
        if not self.transitions_table:
            return

        self.transitions_table.clear()
        transitions = get_recent_stage_transitions(limit=8)

        for trans in transitions:
            # Time - handle both datetime objects and ISO strings
            time_str = ""
            created_at = trans.get("created_at")
            if created_at:
                try:
                    if isinstance(created_at, datetime):
                        time_str = created_at.strftime("%H:%M:%S")
                    else:
                        dt = datetime.fromisoformat(str(created_at))
                        time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "?"

            # Parent ID
            parent_id = f"#{trans.get('parent_id', '?')}"

            # Transition: from_stage → to_stage with emojis
            from_stage = trans.get("from_stage", "?")
            to_stage = trans.get("to_stage", "?")
            from_emoji = STAGE_EMOJI.get(from_stage, "")
            to_emoji = STAGE_EMOJI.get(to_stage, "")
            transition = f"{from_emoji}{from_stage}→{to_emoji}{to_stage}"

            # Child document (truncated)
            title = trans.get("child_title", "?")
            if len(title) > 14:
                title = title[:11] + "..."
            child_display = f"#{trans.get('child_id', '?')} {title}"

            self.transitions_table.add_row(time_str, parent_id, transition, child_display)

    def _refresh_exec_table(self) -> None:
        """Refresh the executions table."""
        if not self.exec_table:
            return

        self.exec_table.clear()
        self._exec_data = get_recent_cascade_activity(limit=8)

        for act in self._exec_data:
            # Exec ID
            exec_id = f"#{act.get('exec_id', '?')}"

            # Time - handle both datetime objects and ISO strings
            time_str = ""
            ts = act.get("completed_at") or act.get("started_at")
            if ts:
                try:
                    if isinstance(ts, datetime):
                        time_str = ts.strftime("%H:%M:%S")
                    else:
                        dt = datetime.fromisoformat(str(ts))
                        time_str = dt.strftime("%H:%M:%S")
                except:
                    time_str = "?"

            # Status
            status = act.get("status", "?")
            if status == "completed":
                status_display = "[green]✓ done[/green]"
            elif status == "running":
                status_display = "[yellow]⟳ running[/yellow]"
            elif status == "failed":
                status_display = "[red]✗ failed[/red]"
            else:
                status_display = f"[dim]{status}[/dim]"

            # Title
            title = act.get("doc_title", "")
            if title.startswith("Cascade: "):
                title = title[9:]
            title = title[:28]

            self.exec_table.add_row(exec_id, time_str, status_display, title)

    def _show_document_preview(self, doc_id: int) -> None:
        """Show document content in preview pane."""
        from textual.widgets import RichLog
        from textual.containers import ScrollableContainer

        self._stop_log_stream()

        try:
            header = self.query_one("#pv-preview-header", Static)
            preview_scroll = self.query_one("#pv-preview-scroll", ScrollableContainer)
            preview_content = self.query_one("#pv-preview-content", RichLog)
            preview_log = self.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        # Show scroll view, hide log view
        preview_scroll.display = True
        preview_log.display = False

        preview_content.clear()

        doc = get_document(doc_id)
        if not doc:
            header.update("[bold]Preview[/bold]")
            preview_content.write("[dim]Document not found[/dim]")
            return

        header.update(f"[bold]#{doc_id}[/bold] {doc.get('title', '')[:40]}")

        # Show document content
        content = doc.get("content", "")
        if content:
            for line in content.split("\n")[:100]:
                preview_content.write(line)
        else:
            preview_content.write("[dim]No content[/dim]")

    def _show_execution_preview(self, exec_data: Dict[str, Any]) -> None:
        """Show execution log in preview pane - live if running."""
        from textual.widgets import RichLog
        from textual.containers import ScrollableContainer
        from pathlib import Path

        self._stop_log_stream()
        self._selected_exec = exec_data

        try:
            header = self.query_one("#pv-preview-header", Static)
            preview_scroll = self.query_one("#pv-preview-scroll", ScrollableContainer)
            preview_content = self.query_one("#pv-preview-content", RichLog)
            preview_log = self.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        exec_id = exec_data.get("exec_id")
        status = exec_data.get("status", "")
        is_running = status == "running"

        # Get log file path
        from emdx.models.executions import get_execution
        exec_record = get_execution(exec_id) if exec_id else None
        log_file = exec_record.log_file if exec_record else None

        if is_running and log_file:
            # Show live log
            header.update(f"[green]● LIVE[/green] [bold]#{exec_id}[/bold]")
            preview_scroll.display = False
            preview_log.display = True
            preview_log.clear()

            log_path = Path(log_file)
            if log_path.exists():
                self._start_log_stream(log_path, preview_log)
            else:
                preview_log.write("[yellow]Waiting for log file...[/yellow]")
        else:
            # Show static log content
            header.update(f"[bold]#{exec_id}[/bold] {exec_data.get('doc_title', '')[:30]}")
            preview_scroll.display = False
            preview_log.display = True
            preview_log.clear()

            if log_file:
                log_path = Path(log_file)
                if log_path.exists():
                    content = log_path.read_text()
                    from emdx.ui.live_log_writer import LiveLogWriter
                    writer = LiveLogWriter(preview_log, auto_scroll=False)
                    writer.write(content)
                else:
                    preview_log.write("[dim]Log file not found[/dim]")
            else:
                preview_log.write("[dim]No log file[/dim]")

    def _start_log_stream(self, log_path: 'Path', preview_log: 'RichLog') -> None:
        """Start streaming a log file to the preview."""
        from emdx.services.log_stream import LogStream
        from emdx.ui.live_log_writer import LiveLogWriter
        from emdx.utils.stream_json_parser import parse_and_format_live_logs

        self.log_stream = LogStream(log_path)

        # Show initial content
        initial = self.log_stream.get_initial_content()
        if initial:
            formatted = parse_and_format_live_logs(initial)
            for line in formatted[-50:]:
                preview_log.write(line)
            preview_log.scroll_end(animate=False)

        # Subscribe for updates
        class LogSubscriber:
            def __init__(self, view: 'CascadeView', log_widget: 'RichLog'):
                self.view = view
                self.log_widget = log_widget

            def on_log_content(self, content: str) -> None:
                def update():
                    writer = LiveLogWriter(self.log_widget, auto_scroll=True)
                    writer.write(content)
                self.view.call_from_thread(update)

            def on_log_error(self, error: Exception) -> None:
                pass

        self._log_subscriber = LogSubscriber(self, preview_log)
        self.log_stream.subscribe(self._log_subscriber)

    def _stop_log_stream(self) -> None:
        """Stop any active log stream."""
        if self.log_stream and hasattr(self, '_log_subscriber'):
            self.log_stream.unsubscribe(self._log_subscriber)
        self.log_stream = None
        self.streaming_exec_id = None

    def watch_current_stage_idx(self, idx: int) -> None:
        """React to stage change."""
        if idx >= len(STAGES):
            return
        if self.summary:
            self.summary.current_stage = STAGES[idx]
            self.summary._update_display()
        if self.doc_list:
            self.doc_list.load_stage(STAGES[idx])
            # Update preview
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

    def on_document_list_document_selected(self, event: DocumentList.DocumentSelected) -> None:
        """Handle document selection."""
        self._show_document_preview(event.doc_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in runs or executions tables."""
        table = event.data_table

        if table.id == "pv-exec-table":
            # Execution selected - show in preview
            row_idx = event.cursor_row
            if hasattr(self, '_exec_data') and row_idx < len(self._exec_data):
                exec_data = self._exec_data[row_idx]
                self._show_execution_preview(exec_data)

    def action_prev_stage(self) -> None:
        """Move to previous stage."""
        if self.current_stage_idx > 0:
            self.current_stage_idx -= 1

    def action_next_stage(self) -> None:
        """Move to next stage."""
        if self.current_stage_idx < len(STAGES) - 1:
            self.current_stage_idx += 1

    def action_move_down(self) -> None:
        """Move cursor down."""
        if self.doc_list:
            self.doc_list.move_cursor(1)
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

    def action_move_up(self) -> None:
        """Move cursor up."""
        if self.doc_list:
            self.doc_list.move_cursor(-1)
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

    def action_view_doc(self) -> None:
        """View selected document fullscreen."""
        if self.doc_list:
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self.post_message(self.ViewDocument(doc_id))

    def action_advance_doc(self) -> None:
        """Advance selected document to next stage."""
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]
        if stage == "done" or NEXT_STAGE.get(stage) is None:
            self._update_status("[yellow]Already at final stage[/yellow]")
            return

        if not self.doc_list:
            return

        doc_id = self.doc_list.get_selected_doc_id()
        if not doc_id:
            self._update_status("[yellow]No document selected[/yellow]")
            return

        next_stage = NEXT_STAGE.get(stage)
        if next_stage:
            update_document_stage(doc_id, next_stage)
            self._update_status(f"[green]Moved #{doc_id}: {stage} → {next_stage}[/green]")
            self.refresh_all()

    def action_new_idea(self) -> None:
        """Open modal to create a new cascade idea."""
        from emdx.database.documents import save_document_to_cascade

        def handle_idea_result(idea_text: str | None) -> None:
            if idea_text:
                # Save the idea to cascade at 'idea' stage
                doc_id = save_document_to_cascade(
                    title=f"Cascade: {idea_text[:50]}{'...' if len(idea_text) > 50 else ''}",
                    content=idea_text,
                    stage="idea",
                )
                self._update_status(f"[green]Created idea #{doc_id}[/green]")
                # Navigate to idea stage and refresh
                self.current_stage_idx = 0  # idea is index 0
                self.refresh_all()

        self.app.push_screen(NewIdeaScreen(), handle_idea_result)

    def action_process(self) -> None:
        """Process the current stage."""
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]
        if stage == "done" or NEXT_STAGE.get(stage) is None:
            self._update_status("[yellow]'done' is terminal - nothing to process[/yellow]")
            return

        doc_id = self.doc_list.get_selected_doc_id() if self.doc_list else None
        self.post_message(self.ProcessStage(stage, doc_id))

    def action_toggle_select(self) -> None:
        """Toggle selection of current document."""
        if self.doc_list:
            self.doc_list.toggle_selection()

    def action_select_all(self) -> None:
        """Select all documents in current stage."""
        if self.doc_list:
            self.doc_list.select_all()

    def action_clear_selection(self) -> None:
        """Clear all selections."""
        if self.doc_list:
            self.doc_list.clear_selection()

    def action_synthesize(self) -> None:
        """Synthesize selected docs through Claude (or all if none selected)."""
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]

        if stage == "done" or NEXT_STAGE.get(stage) is None:
            self._update_status("[yellow]Cannot synthesize from terminal stage[/yellow]")
            return

        # Get selected doc IDs, or all docs if none selected
        selected_ids = self.doc_list.get_selected_ids() if self.doc_list else []

        if not selected_ids:
            # No selection - use all docs at stage
            docs = list_documents_at_stage(stage)
            doc_ids = [d["id"] for d in docs]
        else:
            doc_ids = selected_ids

        if len(doc_ids) < 2:
            self._update_status(f"[yellow]Need 2+ docs to synthesize (selected: {len(doc_ids)})[/yellow]")
            return

        # Build combined content for Claude to synthesize
        from ..database.documents import get_document, save_document_to_cascade

        combined_parts = []
        for doc_id in doc_ids:
            doc = get_document(str(doc_id))
            if doc:
                combined_parts.append(f"=== Document #{doc_id}: {doc['title']} ===\n{doc['content']}")

        combined_content = "\n\n---\n\n".join(combined_parts)

        # Create a synthesis input document (keeps sources intact for now)
        title = f"Synthesis: {len(doc_ids)} {stage} documents"
        synthesis_doc_id = save_document_to_cascade(
            title=title,
            content=combined_content,
            stage=stage,  # Same stage - will be processed by Claude
        )

        self._update_status(f"[cyan]Synthesizing {len(doc_ids)} docs via Claude...[/cyan]")

        # Post a ProcessStage message so the proper handler runs it with live logs
        self.post_message(self.ProcessStage(stage, synthesis_doc_id))

        # Refresh to show the new synthesis document
        self.refresh_all()

    def action_refresh(self) -> None:
        """Refresh all data."""
        self.refresh_all()

    def action_toggle_activity_view(self) -> None:
        """Refresh all data (v key)."""
        self.refresh_all()

    def _update_status(self, text: str) -> None:
        """Update status bar."""
        status = self.query_one("#pv-status", Static)
        status.update(text)


class CascadeBrowser(Widget):
    """Browser wrapper for CascadeView."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_cascade", "Cascade"),
        ("3", "switch_search", "Search"),
        ("4", "switch_github", "GitHub"),
        ("5", "switch_documents", "Documents"),
        ("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    CascadeBrowser {
        layout: vertical;
        height: 100%;
    }

    #cascade-view {
        height: 1fr;
    }

    #help-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.cascade_view: Optional[CascadeView] = None

    def compose(self) -> ComposeResult:
        self.cascade_view = CascadeView(id="cascade-view")
        yield self.cascade_view
        yield Static(
            "[dim]1[/dim] Activity │ [bold]2[/bold] Cascade │ [dim]3[/dim] Search │ [dim]4[/dim] GitHub │ [dim]5[/dim] Docs │ "
            "[dim]n[/dim] new idea │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]s[/dim] synthesize",
            id="help-bar",
        )

    def on_cascade_view_view_document(self, event: CascadeView.ViewDocument) -> None:
        """Handle request to view document."""
        logger.info(f"Would view document #{event.doc_id}")
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_cascade_view_process_stage(self, event: CascadeView.ProcessStage) -> None:
        """Handle request to process a stage - runs Claude with live logs."""
        import asyncio
        from pathlib import Path
        from datetime import datetime

        stage = event.stage
        doc_id = event.doc_id

        # Get the document to process
        if doc_id:
            doc = get_document(str(doc_id))
            if not doc:
                self._update_status(f"[red]Document #{doc_id} not found[/red]")
                return
        else:
            # Get oldest at stage
            docs = list_documents_at_stage(stage)
            if not docs:
                self._update_status(f"[yellow]No documents at stage '{stage}'[/yellow]")
                return
            doc = docs[0]
            doc_id = doc["id"]

        self._update_status(f"[cyan]Processing #{doc_id}: {doc.get('title', '')[:40]}...[/cyan]")

        # Run in background thread to not block UI
        def run_process():
            from emdx.services.claude_executor import execute_claude_sync, DEFAULT_ALLOWED_TOOLS
            from emdx.models.executions import create_execution, update_execution_status
            from emdx.commands.cascade import STAGE_PROMPTS, NEXT_STAGE

            # Build prompt
            prompt = STAGE_PROMPTS[stage].format(content=doc.get("content", ""))

            # Set up log file
            log_dir = Path.cwd() / ".emdx" / "logs" / "cascade"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            # Create execution record
            exec_id = create_execution(
                doc_id=doc_id,
                doc_title=f"Cascade: {doc.get('title', '')}",
                log_file=str(log_file),
                working_dir=str(Path.cwd()),
            )

            # Update UI to show execution started
            def update_started():
                self._update_status(f"[green]● Running #{exec_id}[/green] Processing {stage}...")
                if self.cascade_view:
                    self.cascade_view.refresh_all()
            self.call_from_thread(update_started)

            # Execute Claude
            timeout = 1800 if stage == "planned" else 300
            try:
                result = execute_claude_sync(
                    task=prompt,
                    execution_id=exec_id,
                    log_file=log_file,
                    allowed_tools=DEFAULT_ALLOWED_TOOLS,
                    working_dir=str(Path.cwd()),
                    doc_id=str(doc_id),
                    timeout=timeout,
                )

                if result.get("success"):
                    output = result.get("output", "")

                    # Create child document with output
                    if output:
                        from emdx.database.documents import save_document, update_document_stage
                        next_stage = NEXT_STAGE.get(stage, "done")
                        child_title = f"{doc.get('title', '')} [{stage}→{next_stage}]"
                        new_doc_id = save_document(
                            title=child_title,
                            content=output,
                            project=doc.get("project"),
                            parent_id=doc_id,
                        )
                        update_document_stage(new_doc_id, next_stage)
                        update_document_stage(doc_id, "done")

                        def update_success():
                            self._update_status(f"[green]✓ Done![/green] Created #{new_doc_id} at {next_stage}")
                            if self.cascade_view:
                                self.cascade_view.refresh_all()
                        self.call_from_thread(update_success)
                    else:
                        update_execution_status(exec_id, "completed")
                        def update_done():
                            self._update_status(f"[green]✓ Completed[/green] (no output)")
                            if self.cascade_view:
                                self.cascade_view.refresh_all()
                        self.call_from_thread(update_done)
                else:
                    update_execution_status(exec_id, "failed", exit_code=1)
                    error = result.get("error", "Unknown error")
                    def update_failed():
                        self._update_status(f"[red]✗ Failed:[/red] {error[:50]}")
                        if self.cascade_view:
                            self.cascade_view.refresh_all()
                    self.call_from_thread(update_failed)

            except Exception as e:
                update_execution_status(exec_id, "failed", exit_code=1)
                def update_error():
                    self._update_status(f"[red]✗ Error:[/red] {str(e)[:50]}")
                    if self.cascade_view:
                        self.cascade_view.refresh_all()
                self.call_from_thread(update_error)

        # Run in executor to not block event loop
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(run_process)

    def _refresh(self) -> None:
        """Refresh the cascade view."""
        if self.cascade_view:
            self.cascade_view.refresh_all()

    def _update_status(self, text: str) -> None:
        """Update status."""
        if self.cascade_view:
            self.cascade_view._update_status(text)

    async def action_switch_activity(self) -> None:
        """Switch to activity browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    async def action_switch_cascade(self) -> None:
        """Already on cascade, do nothing."""
        pass

    async def action_switch_documents(self) -> None:
        """Switch to document browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")

    async def action_switch_search(self) -> None:
        """Switch to search screen."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("search")

    async def action_switch_github(self) -> None:
        """Switch to GitHub browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("github")

    def action_show_help(self) -> None:
        """Show help."""
        pass

    def update_status(self, text: str) -> None:
        """Update status - for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the cascade view."""
        if self.cascade_view:
            self.cascade_view.focus()
