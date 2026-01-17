"""Pipeline Browser - TUI for viewing and managing the streaming pipeline."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Static

from emdx.database.documents import (
    get_document,
    get_oldest_at_stage,
    get_pipeline_stats,
    list_documents_at_stage,
    update_document_stage,
)

logger = logging.getLogger(__name__)

# Pipeline stages in order
STAGES = ["idea", "prompt", "analyzed", "planned", "done"]
STAGE_COLORS = {
    "idea": "cyan",
    "prompt": "yellow",
    "analyzed": "green",
    "planned": "blue",
    "done": "dim",
}


class StageColumn(Widget):
    """A column representing one pipeline stage."""

    DEFAULT_CSS = """
    StageColumn {
        width: 1fr;
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }

    StageColumn.selected {
        border: double $accent;
    }

    StageColumn #stage-header {
        height: 3;
        text-align: center;
        background: $surface;
        padding: 1 0;
    }

    StageColumn #stage-count {
        height: 1;
        text-align: center;
        color: $text-muted;
    }

    StageColumn #stage-docs {
        height: 1fr;
    }

    StageColumn DataTable {
        height: 100%;
    }
    """

    selected = reactive(False)

    def __init__(self, stage: str, **kwargs):
        super().__init__(**kwargs)
        self.stage = stage
        self.docs = []

    def compose(self) -> ComposeResult:
        color = STAGE_COLORS.get(self.stage, "white")
        yield Static(f"[bold {color}]{self.stage.upper()}[/]", id="stage-header")
        yield Static("0 docs", id="stage-count")
        with Vertical(id="stage-docs"):
            table = DataTable(id=f"table-{self.stage}")
            table.add_column("ID", width=6)
            table.add_column("Title", width=30)
            table.cursor_type = "row"
            yield table

    def watch_selected(self, selected: bool) -> None:
        """Update styling when selection changes."""
        self.set_class(selected, "selected")

    def refresh_docs(self) -> None:
        """Refresh the documents list for this stage."""
        self.docs = list_documents_at_stage(self.stage, limit=50)

        # Update count
        count_widget = self.query_one("#stage-count", Static)
        count = len(self.docs)
        count_widget.update(f"{count} doc{'s' if count != 1 else ''}")

        # Update table
        table = self.query_one(f"#table-{self.stage}", DataTable)
        table.clear()
        for doc in self.docs:
            title = doc["title"][:28] + ".." if len(doc["title"]) > 30 else doc["title"]
            table.add_row(str(doc["id"]), title, key=str(doc["id"]))

    def get_selected_doc_id(self) -> Optional[int]:
        """Get the currently selected document ID."""
        table = self.query_one(f"#table-{self.stage}", DataTable)
        if table.row_count > 0 and table.cursor_row is not None:
            row_key = table.get_row_at(table.cursor_row)
            if row_key:
                try:
                    return int(row_key[0])
                except (ValueError, IndexError):
                    pass
        return None


class PipelineView(Widget):
    """Main pipeline view with stage columns."""

    class ViewDocument(Message):
        """Message to view a document."""
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
        Binding("h", "move_left", "Left stage", show=False),
        Binding("l", "move_right", "Right stage", show=False),
        Binding("left", "move_left", "Left stage", show=False),
        Binding("right", "move_right", "Right stage", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("enter", "view_doc", "View", show=True),
        Binding("a", "advance_doc", "Advance", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("p", "process", "Process", show=True),
    ]

    DEFAULT_CSS = """
    PipelineView {
        layout: vertical;
        height: 100%;
    }

    #pipeline-header {
        height: 3;
        text-align: center;
        background: $surface;
        padding: 1;
    }

    #pipeline-columns {
        height: 1fr;
    }

    #pipeline-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    current_stage_idx = reactive(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_columns = {}

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Pipeline[/bold] - idea [dim]→[/dim] prompt [dim]→[/dim] analyzed [dim]→[/dim] planned [dim]→[/dim] done",
            id="pipeline-header"
        )
        with Horizontal(id="pipeline-columns"):
            for stage in STAGES:
                col = StageColumn(stage, id=f"col-{stage}")
                self.stage_columns[stage] = col
                yield col
        yield Static("", id="pipeline-status")

    def on_mount(self) -> None:
        """Initialize on mount."""
        self.refresh_all()
        self._update_selection()

    def refresh_all(self) -> None:
        """Refresh all stage columns."""
        stats = get_pipeline_stats()
        total = sum(stats.values())

        for stage, col in self.stage_columns.items():
            col.refresh_docs()

        status = self.query_one("#pipeline-status", Static)
        status.update(f"Total: {total} docs │ [dim]h/l[/dim] stages │ [dim]j/k[/dim] nav │ [dim]a[/dim] advance │ [dim]p[/dim] process │ [dim]r[/dim] refresh")

    def _update_selection(self) -> None:
        """Update which column is selected."""
        for idx, stage in enumerate(STAGES):
            col = self.stage_columns[stage]
            col.selected = (idx == self.current_stage_idx)

    def watch_current_stage_idx(self, idx: int) -> None:
        """React to stage index change."""
        self._update_selection()

    def action_move_left(self) -> None:
        """Move to previous stage."""
        if self.current_stage_idx > 0:
            self.current_stage_idx -= 1

    def action_move_right(self) -> None:
        """Move to next stage."""
        if self.current_stage_idx < len(STAGES) - 1:
            self.current_stage_idx += 1

    def action_move_down(self) -> None:
        """Move cursor down in current stage."""
        stage = STAGES[self.current_stage_idx]
        col = self.stage_columns[stage]
        table = col.query_one(f"#table-{stage}", DataTable)
        if table.row_count > 0:
            table.action_cursor_down()

    def action_move_up(self) -> None:
        """Move cursor up in current stage."""
        stage = STAGES[self.current_stage_idx]
        col = self.stage_columns[stage]
        table = col.query_one(f"#table-{stage}", DataTable)
        if table.row_count > 0:
            table.action_cursor_up()

    def action_view_doc(self) -> None:
        """View selected document."""
        stage = STAGES[self.current_stage_idx]
        col = self.stage_columns[stage]
        doc_id = col.get_selected_doc_id()
        if doc_id:
            self.post_message(self.ViewDocument(doc_id))

    def action_advance_doc(self) -> None:
        """Advance selected document to next stage."""
        stage = STAGES[self.current_stage_idx]
        if stage == "done":
            self._update_status("[yellow]Already at final stage[/yellow]")
            return

        col = self.stage_columns[stage]
        doc_id = col.get_selected_doc_id()
        if not doc_id:
            self._update_status("[yellow]No document selected[/yellow]")
            return

        next_idx = STAGES.index(stage) + 1
        next_stage = STAGES[next_idx]

        update_document_stage(doc_id, next_stage)
        self._update_status(f"[green]Moved #{doc_id}: {stage} → {next_stage}[/green]")
        self.refresh_all()

    def action_refresh(self) -> None:
        """Refresh all data."""
        self.refresh_all()
        self._update_status("[dim]Refreshed[/dim]")

    def action_process(self) -> None:
        """Process the current stage."""
        stage = STAGES[self.current_stage_idx]
        if stage == "done":
            self._update_status("[yellow]'done' is terminal - nothing to process[/yellow]")
            return

        col = self.stage_columns[stage]
        doc_id = col.get_selected_doc_id()
        self.post_message(self.ProcessStage(stage, doc_id))

    def _update_status(self, text: str) -> None:
        """Update status bar."""
        status = self.query_one("#pipeline-status", Static)
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
            "[dim]h/l[/dim] stages │ [dim]j/k[/dim] nav │ [dim]a[/dim] advance │ [dim]p[/dim] process",
            id="help-bar",
        )

    def on_pipeline_view_view_document(self, event: PipelineView.ViewDocument) -> None:
        """Handle request to view document."""
        logger.info(f"Would view document #{event.doc_id}")
        # Forward to parent app
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_pipeline_view_process_stage(self, event: PipelineView.ProcessStage) -> None:
        """Handle request to process a stage."""
        import subprocess
        stage = event.stage
        doc_id = event.doc_id

        # Build command
        cmd = ["poetry", "run", "emdx", "pipeline", "process", stage]
        if doc_id:
            cmd.extend(["--doc", str(doc_id)])

        try:
            # Run in background
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._update_status(f"[green]Started processing {stage}[/green]")
        except Exception as e:
            self._update_status(f"[red]Error: {e}[/red]")

        # Refresh after a short delay
        self.set_timer(2.0, self._refresh)

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
