"""Pipeline Browser - TUI for viewing and managing the streaming pipeline."""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Static, MarkdownViewer

from emdx.database.documents import (
    get_document,
    get_pipeline_stats,
    list_documents_at_stage,
    update_document_stage,
)
from emdx.database.connection import db_connection

logger = logging.getLogger(__name__)

# Pipeline stages in order
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


def get_recent_pipeline_activity(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent pipeline activity from executions and document changes."""
    with db_connection.get_connection() as conn:
        # Get recent executions related to pipeline
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
                d.parent_id
            FROM executions e
            LEFT JOIN documents d ON e.doc_id = d.id
            WHERE e.doc_title LIKE 'Pipeline:%' OR d.stage IS NOT NULL
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
        self.stats = get_pipeline_stats()
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
            if title.startswith("Pipeline: "):
                title = title[10:]  # Remove "Pipeline: " prefix

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

                lineage = "## 📊 Pipeline Results\n\n"

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
    """Shows recent pipeline activity."""

    DEFAULT_CSS = """
    ActivityFeed {
        height: 8;
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

    def compose(self) -> ComposeResult:
        yield Static("[bold]Recent Activity[/bold]", id="activity-header")
        table = DataTable(id="activity-table")
        table.add_column("Time", width=8)
        table.add_column("Doc", width=6)
        table.add_column("Status", width=10)
        table.add_column("Details", width=50)
        table.cursor_type = "none"
        table.show_cursor = False
        yield table

    def refresh_activity(self) -> None:
        """Refresh the activity feed."""
        table = self.query_one("#activity-table", DataTable)
        table.clear()

        activities = get_recent_pipeline_activity(limit=10)

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
            if title.startswith("Pipeline: "):
                title = title[10:]
            stage = act.get("stage") or ""
            parent = act.get("parent_id")

            details = title[:35]
            if stage:
                details += f" → {stage}"
            if parent:
                details += f" (from #{parent})"

            table.add_row(time_str, doc_id, status_display, details)


class PipelineView(Widget):
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
        Binding("a", "advance_doc", "Advance", show=True),
        Binding("p", "process", "Process", show=True),
        Binding("s", "synthesize", "Synthesize", show=True),
        Binding("ctrl+a", "select_all", "Select All", show=False),
        Binding("escape", "clear_selection", "Clear", show=False),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    PipelineView {
        layout: vertical;
        height: 100%;
    }

    #pv-summary {
        height: 3;
    }

    #pv-main {
        height: 1fr;
    }

    #pv-list-container {
        width: 45%;
        height: 100%;
    }

    #pv-preview-container {
        width: 55%;
        height: 100%;
    }

    #pv-activity {
        height: 8;
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
        self.preview: Optional[DocumentPreview] = None
        self.activity: Optional[ActivityFeed] = None

    def compose(self) -> ComposeResult:
        self.summary = StageSummaryBar(id="pv-summary")
        yield self.summary

        with Horizontal(id="pv-main"):
            with Vertical(id="pv-list-container"):
                self.doc_list = DocumentList(id="pv-doc-list")
                yield self.doc_list
            with Vertical(id="pv-preview-container"):
                self.preview = DocumentPreview(id="pv-preview")
                yield self.preview

        self.activity = ActivityFeed(id="pv-activity")
        yield self.activity

        yield Static("", id="pv-status")

    def on_mount(self) -> None:
        """Initialize on mount."""
        self.refresh_all()

    def refresh_all(self) -> None:
        """Refresh all components."""
        # Update summary bar
        if self.summary:
            self.summary.current_stage = STAGES[self.current_stage_idx]
            self.summary.refresh_stats()

        # Load documents for current stage
        if self.doc_list:
            stage = STAGES[self.current_stage_idx]
            self.doc_list.load_stage(stage)

            # Update preview with first doc
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id and self.preview:
                self.preview.show_document(doc_id)
            elif self.preview:
                self.preview.clear()

        # Refresh activity feed
        if self.activity:
            self.activity.refresh_activity()

        # Update status
        self._update_status("[dim]h/l[/dim] stages │ [dim]j/k[/dim] docs │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]s[/dim] synthesize │ [dim]r[/dim] refresh")

    def watch_current_stage_idx(self, idx: int) -> None:
        """React to stage change."""
        if self.summary:
            self.summary.current_stage = STAGES[idx]
            self.summary._update_display()
        if self.doc_list:
            self.doc_list.load_stage(STAGES[idx])
            # Update preview
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id and self.preview:
                self.preview.show_document(doc_id)
            elif self.preview:
                self.preview.clear()

    def on_document_list_document_selected(self, event: DocumentList.DocumentSelected) -> None:
        """Handle document selection."""
        if self.preview:
            self.preview.show_document(event.doc_id)

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
            if doc_id and self.preview:
                self.preview.show_document(doc_id)

    def action_move_up(self) -> None:
        """Move cursor up."""
        if self.doc_list:
            self.doc_list.move_cursor(-1)
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id and self.preview:
                self.preview.show_document(doc_id)

    def action_view_doc(self) -> None:
        """View selected document fullscreen."""
        if self.doc_list:
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self.post_message(self.ViewDocument(doc_id))

    def action_advance_doc(self) -> None:
        """Advance selected document to next stage."""
        stage = STAGES[self.current_stage_idx]
        if stage == "done":
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

    def action_process(self) -> None:
        """Process the current stage."""
        stage = STAGES[self.current_stage_idx]
        if stage == "done":
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
        stage = STAGES[self.current_stage_idx]

        if stage == "done":
            self._update_status("[yellow]Cannot synthesize from 'done' stage[/yellow]")
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
        from ..database.documents import get_document, save_document_to_pipeline

        combined_parts = []
        for doc_id in doc_ids:
            doc = get_document(str(doc_id))
            if doc:
                combined_parts.append(f"=== Document #{doc_id}: {doc['title']} ===\n{doc['content']}")

        combined_content = "\n\n---\n\n".join(combined_parts)

        # Create a synthesis input document (keeps sources intact for now)
        title = f"Synthesis: {len(doc_ids)} {stage} documents"
        synthesis_doc_id = save_document_to_pipeline(
            title=title,
            content=combined_content,
            stage=stage,  # Same stage - will be processed by Claude
        )

        self._update_status(f"[cyan]Synthesizing {len(doc_ids)} docs via Claude...[/cyan]")

        # Now process it through Claude (same as 'p' key but automatic)
        import subprocess
        cmd = ["poetry", "run", "emdx", "pipeline", "process", stage, "--sync", "--doc", str(synthesis_doc_id)]

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._update_status(f"[green]Started synthesis #{synthesis_doc_id} through Claude[/green]")
        except Exception as e:
            self._update_status(f"[red]Error starting synthesis: {e}[/red]")

        # Refresh after delay to show results
        self.set_timer(5.0, self.refresh_all)

    def action_refresh(self) -> None:
        """Refresh all data."""
        self.refresh_all()

    def _update_status(self, text: str) -> None:
        """Update status bar."""
        status = self.query_one("#pv-status", Static)
        status.update(text)


class PipelineBrowser(Widget):
    """Browser wrapper for PipelineView."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_workflow", "Workflows"),
        ("3", "switch_documents", "Documents"),
        ("4", "switch_pipeline", "Pipeline"),
        ("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    PipelineBrowser {
        layout: vertical;
        height: 100%;
    }

    #pipeline-view {
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
        self.pipeline_view: Optional[PipelineView] = None

    def compose(self) -> ComposeResult:
        self.pipeline_view = PipelineView(id="pipeline-view")
        yield self.pipeline_view
        yield Static(
            "[dim]1[/dim] Activity │ [dim]2[/dim] Workflows │ [dim]3[/dim] Documents │ [bold]4[/bold] Pipeline │ "
            "[dim]Enter[/dim] view │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]s[/dim] synthesize",
            id="help-bar",
        )

    def on_pipeline_view_view_document(self, event: PipelineView.ViewDocument) -> None:
        """Handle request to view document."""
        logger.info(f"Would view document #{event.doc_id}")
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_pipeline_view_process_stage(self, event: PipelineView.ProcessStage) -> None:
        """Handle request to process a stage."""
        import subprocess
        stage = event.stage
        doc_id = event.doc_id

        cmd = ["poetry", "run", "emdx", "pipeline", "process", stage, "--sync"]
        if doc_id:
            cmd.extend(["--doc", str(doc_id)])

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._update_status(f"[green]Started processing {stage} (sync mode)[/green]")
        except Exception as e:
            self._update_status(f"[red]Error: {e}[/red]")

        # Refresh after delay
        self.set_timer(3.0, self._refresh)

    def _refresh(self) -> None:
        """Refresh the pipeline view."""
        if self.pipeline_view:
            self.pipeline_view.refresh_all()

    def _update_status(self, text: str) -> None:
        """Update status."""
        if self.pipeline_view:
            self.pipeline_view._update_status(text)

    async def action_switch_activity(self) -> None:
        """Switch to activity browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    async def action_switch_workflow(self) -> None:
        """Switch to workflow browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("workflow")

    async def action_switch_documents(self) -> None:
        """Switch to document browser."""
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")

    async def action_switch_pipeline(self) -> None:
        """Already on pipeline, do nothing."""
        pass

    def action_show_help(self) -> None:
        """Show help."""
        pass

    def update_status(self, text: str) -> None:
        """Update status - for compatibility with browser container."""
        pass

    def focus(self, scroll_visible: bool = True) -> None:
        """Focus the pipeline view."""
        if self.pipeline_view:
            self.pipeline_view.focus()
