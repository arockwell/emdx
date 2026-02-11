"""Main cascade view widget with stage navigation and preview."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.services.cascade_service import (
    get_document,
    get_recent_pipeline_activity,
    list_documents_at_stage,
    save_document_to_cascade,
    update_cascade_stage,
)

from .constants import NEXT_STAGE, STAGES, STAGE_EMOJI
from .document_list import DocumentList
from .new_idea_screen import NewIdeaScreen
from .preview_panel import PreviewPanel
from .stage_summary_bar import StageSummaryBar

logger = logging.getLogger(__name__)


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
        Binding("i", "show_input", "Input", show=True),
        Binding("o", "show_output", "Output", show=True),
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
        height: 50%;
        border-bottom: solid $secondary;
    }

    #pv-pipeline-section {
        height: 50%;
    }

    #pv-pipeline-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    #pv-pipeline-table {
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

    # Auto-refresh interval in seconds
    AUTO_REFRESH_INTERVAL = 2.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.summary: Optional[StageSummaryBar] = None
        self.doc_list: Optional[DocumentList] = None
        self.pipeline_table: Optional[DataTable] = None
        self.preview: Optional[PreviewPanel] = None
        self._pipeline_data: List[Dict[str, Any]] = []
        self._selected_pipeline_idx: Optional[int] = None
        self._pipeline_view_mode: str = "output"  # "input" or "output"
        self._auto_refresh_timer = None

    def compose(self) -> ComposeResult:
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog

        self.summary = StageSummaryBar(id="pv-summary")
        yield self.summary

        with Horizontal(id="pv-main"):
            # Left column: Work Items, Pipeline Activity
            with Vertical(id="pv-left-column"):
                self.doc_list = DocumentList(id="pv-doc-list")
                yield self.doc_list

                with Vertical(id="pv-pipeline-section"):
                    yield Static("[bold]Pipeline Activity[/bold]", id="pv-pipeline-header")
                    self.pipeline_table = DataTable(id="pv-pipeline-table", cursor_type="row")
                    yield self.pipeline_table

            # Right column: Preview (document or live log)
            with Vertical(id="pv-preview-container"):
                yield Static("[bold]Preview[/bold]", id="pv-preview-header")
                with ScrollableContainer(id="pv-preview-scroll"):
                    yield RichLog(id="pv-preview-content", highlight=True, markup=True)
                yield RichLog(id="pv-preview-log", highlight=True, markup=True)

        yield Static("", id="pv-status")

        # Initialize preview panel helper
        self.preview = PreviewPanel(self)

    def on_mount(self) -> None:
        """Initialize on mount."""
        # Setup tables
        self._setup_pipeline_table()
        self.refresh_all()
        # Start auto-refresh timer
        self._start_auto_refresh()

    def on_unmount(self) -> None:
        """Clean up on unmount."""
        self._stop_auto_refresh()
        if self.preview:
            self.preview.stop_log_stream()

    def _start_auto_refresh(self) -> None:
        """Start the auto-refresh timer."""
        if self._auto_refresh_timer is None:
            self._auto_refresh_timer = self.set_interval(
                self.AUTO_REFRESH_INTERVAL,
                self._auto_refresh_tick,
                name="cascade_auto_refresh"
            )

    def _stop_auto_refresh(self) -> None:
        """Stop the auto-refresh timer."""
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()
            self._auto_refresh_timer = None

    def _auto_refresh_tick(self) -> None:
        """Called periodically to refresh data."""
        # Refresh pipeline activity (shows running executions)
        self._refresh_pipeline_table()

        # Refresh stage counts in summary bar
        if self.summary:
            self.summary.refresh_stats()

        # Refresh document list for current stage
        if self.doc_list:
            current_stage = STAGES[self.current_stage_idx] if self.current_stage_idx < len(STAGES) else "idea"
            self.doc_list.load_stage(current_stage)

        # If we're viewing a pipeline item, refresh the preview if execution completed
        if self._selected_pipeline_idx is not None and self._selected_pipeline_idx < len(self._pipeline_data):
            act = self._pipeline_data[self._selected_pipeline_idx]
            if act.get("output_id") and self._pipeline_view_mode == "output":
                if self.preview and self.preview._selected_exec and self.preview._selected_exec.get("status") == "running":
                    new_status = act.get("status")
                    if new_status != "running":
                        self._show_pipeline_preview(act)

    def _setup_pipeline_table(self) -> None:
        """Setup the pipeline activity table columns."""
        if self.pipeline_table:
            self.pipeline_table.add_column("Exec", width=6)
            self.pipeline_table.add_column("Time", width=8)
            self.pipeline_table.add_column("Input", width=7)
            self.pipeline_table.add_column("\u2192", width=14)
            self.pipeline_table.add_column("Output", width=7)
            self.pipeline_table.add_column("Status", width=10)

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

        # Refresh pipeline activity table
        self._refresh_pipeline_table()

        # Update status - show auto-refresh is active
        self._update_status("[green]\u25cf[/green] Auto-refresh \u2502 [dim]h/l[/dim] stages \u2502 [dim]j/k[/dim] docs \u2502 [dim]a[/dim] advance \u2502 [dim]p[/dim] process \u2502 [dim]s[/dim] synthesize")

    def _refresh_pipeline_table(self) -> None:
        """Refresh the unified pipeline activity table."""
        if not self.pipeline_table:
            return

        # Remember current selection to restore after refresh
        old_cursor_row = self.pipeline_table.cursor_row if self.pipeline_table.row_count > 0 else 0

        self.pipeline_table.clear()
        self._pipeline_data = get_recent_pipeline_activity(limit=10)

        for act in self._pipeline_data:
            # Execution ID
            exec_id = act.get("exec_id")
            exec_display = f"#{exec_id}" if exec_id else "-"

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

            # Input doc ID
            input_id = act.get("input_id")
            input_display = f"#{input_id}" if input_id else "-"

            # Transition: from_stage -> to_stage with emojis
            from_stage = act.get("from_stage", "?")
            to_stage = act.get("output_stage", "?")
            from_emoji = STAGE_EMOJI.get(from_stage, "")
            to_emoji = STAGE_EMOJI.get(to_stage, "")
            if to_stage and to_stage != "?":
                transition = f"{from_emoji}{from_stage}\u2192{to_emoji}{to_stage}"
            else:
                transition = f"{from_emoji}{from_stage}\u2192..."

            # Output doc ID (if produced)
            output_id = act.get("output_id")
            output_display = f"#{output_id}" if output_id else "[dim]-[/dim]"

            # Status
            status = act.get("status", "?")
            if status == "completed":
                status_display = "[green]\u2713 done[/green]"
            elif status == "running":
                status_display = "[yellow]\u27f3 run[/yellow]"
            elif status == "failed":
                status_display = "[red]\u2717 fail[/red]"
            else:
                status_display = f"[dim]{status}[/dim]"

            self.pipeline_table.add_row(exec_display, time_str, input_display, transition, output_display, status_display)

        # Restore cursor position if possible
        if self.pipeline_table.row_count > 0:
            new_row = min(old_cursor_row, self.pipeline_table.row_count - 1)
            self.pipeline_table.move_cursor(row=new_row)

    def _show_pipeline_preview(self, act: Dict[str, Any]) -> None:
        """Show preview for pipeline activity based on current view mode."""
        if not self.preview:
            return
        if self._pipeline_view_mode == "input":
            input_id = act.get("input_id")
            if input_id:
                self.preview.show_document(input_id)
            else:
                self._update_status("[yellow]No input document[/yellow]")
        else:
            # Output mode (default)
            output_id = act.get("output_id")
            if output_id:
                self.preview.show_document(output_id)
            else:
                # Still running or failed - show execution log
                self.preview.show_execution(act)

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

    def on_document_list_document_selected(self, event: DocumentList.DocumentSelected) -> None:
        """Handle document selection."""
        if self.preview:
            self.preview.show_document(event.doc_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in pipeline table."""
        table = event.data_table

        if table.id == "pv-pipeline-table":
            # Pipeline activity selected - show output doc or live log
            row_idx = event.cursor_row
            if hasattr(self, '_pipeline_data') and row_idx < len(self._pipeline_data):
                self._selected_pipeline_idx = row_idx
                act = self._pipeline_data[row_idx]
                # Show output doc if available, otherwise show execution log
                output_id = act.get("output_id")
                if output_id and self.preview:
                    self.preview.show_document(output_id)
                elif self.preview:
                    # Still running or failed - show execution preview
                    self.preview.show_execution(act)

    def action_prev_stage(self) -> None:
        """Move to previous stage."""
        if self.current_stage_idx > 0:
            self.current_stage_idx -= 1

    def action_next_stage(self) -> None:
        """Move to next stage."""
        if self.current_stage_idx < len(STAGES) - 1:
            self.current_stage_idx += 1

    def action_move_down(self) -> None:
        """Move cursor down in focused table."""
        # Check if pipeline table is focused
        if self.pipeline_table and self.pipeline_table.has_focus:
            self.pipeline_table.action_cursor_down()
            row_idx = self.pipeline_table.cursor_row
            if row_idx < len(self._pipeline_data):
                self._selected_pipeline_idx = row_idx
                self._show_pipeline_preview(self._pipeline_data[row_idx])
        elif self.doc_list:
            self.doc_list.move_cursor(1)
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id and self.preview:
                self.preview.show_document(doc_id)

    def action_move_up(self) -> None:
        """Move cursor up in focused table."""
        # Check if pipeline table is focused
        if self.pipeline_table and self.pipeline_table.has_focus:
            self.pipeline_table.action_cursor_up()
            row_idx = self.pipeline_table.cursor_row
            if row_idx < len(self._pipeline_data):
                self._selected_pipeline_idx = row_idx
                self._show_pipeline_preview(self._pipeline_data[row_idx])
        elif self.doc_list:
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

    def action_show_input(self) -> None:
        """Show input document for selected pipeline activity."""
        self._pipeline_view_mode = "input"

        if self._selected_pipeline_idx is None:
            self._update_status("[yellow]Select a pipeline row first[/yellow]")
            return

        if self._selected_pipeline_idx >= len(self._pipeline_data):
            return

        act = self._pipeline_data[self._selected_pipeline_idx]
        input_id = act.get("input_id")
        if input_id and self.preview:
            self.preview.show_document(input_id)
            self._update_status(f"[cyan]Input mode[/cyan] - showing #{input_id} (press 'o' for output)")
        else:
            self._update_status("[yellow]No input document[/yellow]")

    def action_show_output(self) -> None:
        """Show output document for selected pipeline activity."""
        self._pipeline_view_mode = "output"

        if self._selected_pipeline_idx is None:
            self._update_status("[yellow]Select a pipeline row first[/yellow]")
            return

        if self._selected_pipeline_idx >= len(self._pipeline_data):
            return

        act = self._pipeline_data[self._selected_pipeline_idx]
        output_id = act.get("output_id")
        if output_id and self.preview:
            self.preview.show_document(output_id)
            self._update_status(f"[cyan]Output mode[/cyan] - showing #{output_id} (press 'i' for input)")
        elif self.preview:
            # No output yet - show execution log
            self.preview.show_execution(act)
            self._update_status("[yellow]No output yet - showing execution log[/yellow]")

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
            update_cascade_stage(doc_id, next_stage)
            self._update_status(f"[green]Moved #{doc_id}: {stage} \u2192 {next_stage}[/green]")
            self.refresh_all()

    def action_new_idea(self) -> None:
        """Open modal to create a new cascade idea."""
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
