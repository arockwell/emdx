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

from emdx.ui.widgets.processing_progress import ProcessingProgress

from emdx.database.documents import (
    get_document,
    get_cascade_stats,
    list_documents_at_stage,
    update_document_stage,
)
from emdx.database.connection import db_connection
from emdx.database.cascade_timing import (
    get_all_stage_timing_stats,
    get_expected_timing,
    get_stuck_documents,
    get_processing_status,
)
from emdx.services.cascade_progress import (
    CascadeProgressTracker,
    format_progress,
)

logger = logging.getLogger(__name__)

# Module-level progress tracker instance
_progress_tracker = CascadeProgressTracker()

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


class StuckDiagnosticScreen(ModalScreen):
    """Modal screen for diagnosing stuck documents."""

    CSS = """
    StuckDiagnosticScreen {
        align: center middle;
    }
    #diag-dialog {
        width: 80;
        height: auto;
        max-height: 30;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }
    #diag-title {
        width: 100%;
        text-align: center;
        padding-bottom: 1;
    }
    #diag-content {
        width: 100%;
        height: auto;
        max-height: 20;
        overflow-y: auto;
        padding: 1;
        background: $panel;
        margin-bottom: 1;
    }
    #diag-buttons {
        width: 100%;
        height: 3;
        align: center middle;
    }
    #diag-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_screen", "Close"),
    ]

    def __init__(self, doc_id: int, title: str, stuck_info: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.doc_id = doc_id
        self.doc_title = title
        self.stuck_info = stuck_info

    def compose(self) -> ComposeResult:
        with Vertical(id="diag-dialog"):
            yield Label(f"🔍 Diagnostic: Document #{self.doc_id}", id="diag-title")
            yield Static(self._build_diagnostic_content(), id="diag-content")
            with Horizontal(id="diag-buttons"):
                yield Button("Retry Processing", variant="primary", id="retry-btn")
                yield Button("Close", variant="default", id="close-btn")

    def _format_time(self, seconds: float) -> str:
        """Format seconds into a human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    def _build_diagnostic_content(self) -> str:
        """Build the diagnostic content display."""
        lines = []
        lines.append(f"[bold]Title:[/bold] {self.doc_title[:60]}")
        lines.append("")

        if self.stuck_info:
            # Time information
            time_at_stage = self.stuck_info.get("time_at_stage", 0)
            expected_time = self.stuck_info.get("expected_time", 0)
            threshold = self.stuck_info.get("threshold", 0)

            lines.append(f"[bold]Stage:[/bold] {self.stuck_info.get('stage', '?')}")
            lines.append(f"[bold]Time at stage:[/bold] {self._format_time(time_at_stage)}")
            lines.append(f"[bold]Expected time:[/bold] {self._format_time(expected_time)}")
            lines.append(f"[bold]Threshold:[/bold] {self._format_time(threshold)}")
            lines.append("")

            # Status indicators
            if self.stuck_info.get("has_failed_execution"):
                lines.append("[bold red]❌ FAILED EXECUTION[/bold red]")
                error_msg = self.stuck_info.get("error_message")
                if error_msg:
                    lines.append(f"[red]Error: {error_msg}[/red]")
            elif self.stuck_info.get("is_stuck"):
                ratio = time_at_stage / expected_time if expected_time > 0 else 0
                lines.append(f"[bold yellow]⚠️ STUCK[/bold yellow] ({ratio:.1f}x expected time)")
            else:
                lines.append("[green]✓ Normal - no issues detected[/green]")

            lines.append("")
            lines.append("[dim]Suggested actions:[/dim]")
            if self.stuck_info.get("has_failed_execution"):
                lines.append("• Retry processing with 'p' key")
                lines.append("• Check logs for detailed error info")
            else:
                lines.append("• Wait longer (processing may be complex)")
                lines.append("• Retry processing with 'p' key")
                lines.append("• Manually advance with 'a' key")
        else:
            lines.append("[green]✓ This document appears healthy[/green]")
            lines.append("")
            lines.append("[dim]No stuck indicators detected.[/dim]")

        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "retry-btn":
            self.dismiss("retry")
        else:
            self.dismiss(None)

    def action_dismiss_screen(self) -> None:
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
    """Compact bar showing all stages with counts, timing info, and current selection."""

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
        self.timing_stats: Dict[str, Dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="stage-bar")
        yield Static("", id="stage-detail")

    def refresh_stats(self) -> None:
        """Refresh stage statistics and timing data."""
        self.stats = get_cascade_stats()
        self.timing_stats = get_all_stage_timing_stats()
        self._update_display()

    def _format_time(self, seconds: float) -> str:
        """Format seconds into a human-readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        else:
            return f"{int(seconds / 3600)}h"

    def _update_display(self) -> None:
        """Update the display."""
        bar = self.query_one("#stage-bar", Static)
        detail = self.query_one("#stage-detail", Static)

        # Build stage bar with arrows and timing hints
        parts = []
        for stage in STAGES:
            count = self.stats.get(stage, 0)
            emoji = STAGE_EMOJI.get(stage, "")

            # Get timing hint for this stage transition
            timing_hint = ""
            if stage != "done":
                timing_key = f"{stage}→{NEXT_STAGE.get(stage, '')}"
                timing_info = self.timing_stats.get(timing_key, {})
                avg = timing_info.get("avg")
                if avg is not None:
                    timing_hint = f" ~{self._format_time(avg)}"

            if stage == self.current_stage:
                # Highlighted current stage
                parts.append(f"[bold reverse] {emoji} {stage.upper()} ({count}){timing_hint} [/]")
            elif count > 0:
                parts.append(f"[bold]{emoji} {stage}[/bold] ({count}){timing_hint}")
            else:
                parts.append(f"[dim]{emoji} {stage} (0){timing_hint}[/dim]")

        bar.update(" → ".join(parts))

        # Show detail for current stage with timing info
        count = self.stats.get(self.current_stage, 0)
        timing_detail = ""
        if self.current_stage != "done":
            timing_key = f"{self.current_stage}→{NEXT_STAGE.get(self.current_stage, '')}"
            timing_info = self.timing_stats.get(timing_key, {})
            avg = timing_info.get("avg")
            p95 = timing_info.get("p95")
            hist_count = timing_info.get("count", 0)
            if hist_count > 0:
                avg_str = self._format_time(avg) if avg else "?"
                p95_str = self._format_time(p95) if p95 else "?"
                timing_detail = f" │ avg: {avg_str}, p95: {p95_str} ({hist_count} samples)"

        if count > 0:
            detail.update(f"[bold]← h[/bold] prev │ [bold]l →[/bold] next │ {count} doc{'s' if count != 1 else ''}{timing_detail}")
        else:
            detail.update(f"[bold]← h[/bold] prev │ [bold]l →[/bold] next │ No documents at {self.current_stage}")


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
        self.stuck_docs: Dict[int, Dict[str, Any]] = {}  # doc_id -> stuck info

    def compose(self) -> ComposeResult:
        table = DataTable(id="doc-table")
        table.add_column("", width=3)  # Selection + stuck marker column
        table.add_column("ID", width=6)
        table.add_column("Title", width=36)
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

        # Load stuck document info for this stage
        self.stuck_docs = {}
        if stage != "done":
            stuck_list = get_stuck_documents(stage)
            self.stuck_docs = {d["doc_id"]: d for d in stuck_list}

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

            # Selection marker with stuck indicator
            marker = "●" if doc_id in self.selected_ids else " "

            # Add stuck indicator
            stuck_info = self.stuck_docs.get(doc_id)
            if stuck_info:
                if stuck_info.get("has_failed_execution"):
                    marker = f"{marker}❌"  # Failed execution
                elif stuck_info.get("is_stuck"):
                    marker = f"{marker}⚠️"  # Stuck (taking too long)
            else:
                marker = f"{marker} "  # Pad for alignment

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
                if len(title) > 34:
                    title = title[:31] + "..."
            else:
                if len(title) > 34:
                    title = title[:31] + "..."

            # Parent ID
            parent = str(doc.get("parent_id") or "-")

            # Created time
            created = ""
            if doc.get("created_at"):
                created = doc["created_at"].strftime("%m/%d %H:%M")

            table.add_row(marker, doc_id_str, title, parent, created, key=doc_id_str)

    def get_stuck_info(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Get stuck info for a document if available."""
        return self.stuck_docs.get(doc_id)

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
        Binding("d", "diagnose", "Diagnose", show=True),
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

    #pv-list-container {
        width: 45%;
        height: 100%;
    }

    #pv-preview-container {
        width: 55%;
        height: 100%;
    }

    #pv-activity {
        height: 10;
    }

    #pv-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    current_stage_idx = reactive(0)
    # Processing state tracking
    processing_doc_id: reactive[Optional[int]] = reactive(None)
    processing_started_at: reactive[Optional[datetime]] = reactive(None)
    processing_stage: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.summary: Optional[StageSummaryBar] = None
        self.doc_list: Optional[DocumentList] = None
        self.preview: Optional[DocumentPreview] = None
        self.activity: Optional[ActivityFeed] = None
        self.progress_widget: Optional[ProcessingProgress] = None
        self._progress_timer = None

    def compose(self) -> ComposeResult:
        self.summary = StageSummaryBar(id="pv-summary")
        yield self.summary

        # Processing progress widget (hidden by default, shown when processing)
        self.progress_widget = ProcessingProgress(id="pv-progress")
        yield self.progress_widget

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
        # Start polling timer to check for processing status
        self._progress_timer = self.set_interval(2.0, self._check_processing_status)

    def _check_processing_status(self) -> None:
        """Check for any running processing and update progress display."""
        # Check if we're tracking a processing operation
        if self.processing_doc_id:
            status = get_processing_status(self.processing_doc_id)
            if status:
                if status.get("execution_status") == "completed":
                    # Processing finished successfully
                    if self.progress_widget:
                        self.progress_widget.stop_processing(success=True)
                    self.processing_doc_id = None
                    self.processing_started_at = None
                    self.processing_stage = None
                    self.refresh_all()
                elif status.get("execution_status") == "failed":
                    # Processing failed
                    if self.progress_widget:
                        self.progress_widget.stop_processing(success=False)
                    self._update_status(f"[red]❌ Processing failed for #{self.processing_doc_id}[/red]")
                    self.processing_doc_id = None
                    self.processing_started_at = None
                    self.processing_stage = None
                    self.refresh_all()
                else:
                    # Still running - update elapsed time display and widget
                    elapsed = status.get("elapsed_seconds", 0)
                    self._update_progress_display(elapsed)

                    # Check if stuck based on timing
                    if self.progress_widget and self.processing_stage:
                        expected = get_expected_timing(
                            self.processing_stage,
                            NEXT_STAGE.get(self.processing_stage, "done")
                        )
                        if elapsed > expected * 2:
                            self.progress_widget.mark_stuck(True)
            else:
                # No timing record found - might have completed without our tracking
                if self.progress_widget:
                    self.progress_widget.stop_processing()
                self.processing_doc_id = None
                self.processing_started_at = None
                self.processing_stage = None

    def _update_progress_display(self, elapsed_seconds: float) -> None:
        """Update the status bar with processing progress."""
        if not self.processing_doc_id:
            return

        # Format elapsed time
        if elapsed_seconds < 60:
            time_str = f"{int(elapsed_seconds)}s"
        elif elapsed_seconds < 3600:
            mins = int(elapsed_seconds / 60)
            secs = int(elapsed_seconds % 60)
            time_str = f"{mins}m {secs}s"
        else:
            hours = int(elapsed_seconds / 3600)
            mins = int((elapsed_seconds % 3600) / 60)
            time_str = f"{hours}h {mins}m"

        # Get expected timing for this transition
        if self.processing_stage and NEXT_STAGE.get(self.processing_stage):
            expected = get_expected_timing(self.processing_stage, NEXT_STAGE[self.processing_stage])
            expected_str = f"~{int(expected)}s" if expected < 60 else f"~{int(expected/60)}m"

            # Show progress with spinner animation
            spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner_idx = int(elapsed_seconds) % len(spinner_frames)
            spinner = spinner_frames[spinner_idx]

            self._update_status(
                f"[cyan]{spinner} Processing #{self.processing_doc_id}...[/cyan] "
                f"[bold]{time_str}[/bold] (expected: {expected_str}) │ "
                f"{self.processing_stage} → {NEXT_STAGE.get(self.processing_stage, '?')}"
            )
        else:
            self._update_status(f"[cyan]⟳ Processing #{self.processing_doc_id}...[/cyan] {time_str}")

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
            if doc_id and self.preview:
                self.preview.show_document(doc_id)
            elif self.preview:
                self.preview.clear()

        # Refresh activity feed
        if self.activity:
            self.activity.refresh_activity()

        # Update status (only if not currently processing)
        if not self.processing_doc_id:
            self._update_status("[dim]h/l[/dim] stages │ [dim]j/k[/dim] docs │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]d[/dim] diagnose │ [dim]r[/dim] refresh")

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

        # Now process it through Claude (same as 'p' key but automatic)
        import subprocess
        cmd = ["poetry", "run", "emdx", "cascade", "process", stage, "--sync", "--doc", str(synthesis_doc_id)]

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

    def action_toggle_activity_view(self) -> None:
        """Toggle between cascade runs view and executions view."""
        if self.activity:
            self.activity.toggle_view()

    def action_diagnose(self) -> None:
        """Show diagnostic info for selected document."""
        if not self.doc_list:
            return

        doc_id = self.doc_list.get_selected_doc_id()
        if not doc_id:
            self._update_status("[yellow]No document selected[/yellow]")
            return

        # Get document info
        doc = get_document(str(doc_id))
        if not doc:
            self._update_status(f"[red]Document #{doc_id} not found[/red]")
            return

        # Get stuck info if available
        stuck_info = self.doc_list.get_stuck_info(doc_id)

        def handle_diagnostic_result(result: str | None) -> None:
            if result == "retry":
                # Trigger a reprocess of this document
                if self.current_stage_idx < len(STAGES):
                    stage = STAGES[self.current_stage_idx]
                    if stage != "done":
                        self.post_message(self.ProcessStage(stage, doc_id))
                        self._update_status(f"[cyan]Retrying processing for #{doc_id}...[/cyan]")

        self.app.push_screen(
            StuckDiagnosticScreen(doc_id, doc["title"], stuck_info),
            handle_diagnostic_result,
        )

    def _update_status(self, text: str) -> None:
        """Update status bar."""
        status = self.query_one("#pv-status", Static)
        status.update(text)


class CascadeBrowser(Widget):
    """Browser wrapper for CascadeView."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_cascade", "Cascade"),
        ("3", "switch_documents", "Documents"),
        ("4", "switch_search", "Search"),
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
            "[dim]1[/dim] Activity │ [bold]2[/bold] Cascade │ [dim]3[/dim] Documents │ [dim]4[/dim] Search │ "
            "[dim]n[/dim] new │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]d[/dim] diagnose │ [dim]s[/dim] synth",
            id="help-bar",
        )

    def on_cascade_view_view_document(self, event: CascadeView.ViewDocument) -> None:
        """Handle request to view document."""
        logger.info(f"Would view document #{event.doc_id}")
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_cascade_view_process_stage(self, event: CascadeView.ProcessStage) -> None:
        """Handle request to process a stage."""
        import subprocess
        stage = event.stage
        doc_id = event.doc_id

        cmd = ["poetry", "run", "emdx", "cascade", "process", stage, "--sync"]
        if doc_id:
            cmd.extend(["--doc", str(doc_id)])

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._update_status(f"[green]Started processing {stage} (sync mode)[/green]")

            # Track processing state in the CascadeView for progress display
            if self.cascade_view and doc_id:
                self.cascade_view.processing_doc_id = doc_id
                self.cascade_view.processing_started_at = datetime.now()
                self.cascade_view.processing_stage = stage
        except Exception as e:
            self._update_status(f"[red]Error: {e}[/red]")

        # Refresh after delay
        self.set_timer(3.0, self._refresh)

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
