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
    """List of documents at the current stage with more detail."""

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
    """

    class DocumentSelected(Message):
        """Fired when a document is selected."""
        def __init__(self, doc_id: int):
            self.doc_id = doc_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docs: List[Dict[str, Any]] = []
        self.current_stage = "idea"

    def compose(self) -> ComposeResult:
        table = DataTable(id="doc-table")
        table.add_column("ID", width=6)
        table.add_column("Title", width=40)
        table.add_column("Parent", width=8)
        table.add_column("Created", width=12)
        table.cursor_type = "row"
        yield table

    def load_stage(self, stage: str) -> None:
        """Load documents for a stage."""
        self.current_stage = stage
        self.docs = list_documents_at_stage(stage, limit=50)
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table display."""
        table = self.query_one("#doc-table", DataTable)
        table.clear()

        if not self.docs:
            return

        for doc in self.docs:
            doc_id = str(doc["id"])

            # Title - show more of it
            title = doc["title"]
            if title.startswith("Pipeline: "):
                title = title[10:]  # Remove "Pipeline: " prefix
            if len(title) > 38:
                title = title[:35] + "..."

            # Parent ID
            parent = str(doc.get("parent_id") or "-")

            # Created time
            created = ""
            if doc.get("created_at"):
                created = doc["created_at"].strftime("%m/%d %H:%M")

            table.add_row(doc_id, title, parent, created, key=doc_id)

    def get_selected_doc_id(self) -> Optional[int]:
        """Get currently selected document ID."""
        table = self.query_one("#doc-table", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                try:
                    return int(row_key[0])
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

            header.update(
                f"[bold]#{doc['id']}[/bold] │ {STAGE_EMOJI.get(stage, '')} {stage}{parent_info}\n"
                f"[dim]{doc['title'][:70]}[/dim]"
            )

            content_widget = self.query_one("#preview-content", MarkdownViewer)
            content = doc["content"]
            if len(content) > 8000:
                content = content[:8000] + "\n\n[...truncated...]"
            content_widget.document.update(content)

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
        Binding("enter", "view_doc", "View Full", show=True),
        Binding("a", "advance_doc", "Advance", show=True),
        Binding("p", "process", "Process", show=True),
        Binding("s", "synthesize", "Synthesize", show=True),
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

    def action_synthesize(self) -> None:
        """Synthesize all docs at current stage."""
        stage = STAGES[self.current_stage_idx]
        docs = list_documents_at_stage(stage)

        if len(docs) < 2:
            self._update_status(f"[yellow]Need 2+ docs at '{stage}' to synthesize[/yellow]")
            return

        import subprocess
        try:
            result = subprocess.run(
                ["poetry", "run", "emdx", "pipeline", "synthesize", stage],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self._update_status(f"[green]Synthesized {len(docs)} docs from '{stage}'[/green]")
            else:
                self._update_status(f"[red]Synthesize failed[/red]")
        except Exception as e:
            self._update_status(f"[red]Error: {e}[/red]")

        self.refresh_all()

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
