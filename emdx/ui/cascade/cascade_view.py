"""Main cascade view widget with stage navigation and preview."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

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
from emdx.services.execution_service import get_execution, update_execution_status

from .constants import NEXT_STAGE, STAGE_EMOJI, STAGES
from .document_list import DocumentList
from .new_idea_screen import NewIdeaScreen
from .stage_summary_bar import StageSummaryBar

logger = logging.getLogger(__name__)

class CascadeView(Widget):
    """Main pipeline view with stage navigation and preview."""

    class ViewDocument(Message):
        def __init__(self, doc_id: int):
            self.doc_id = doc_id
            super().__init__()

    class ProcessStage(Message):
        def __init__(self, stage: str, doc_id: int | None = None):
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
    CascadeView { layout: vertical; height: 100%; }
    #pv-summary { height: 3; }
    #pv-main { height: 1fr; }
    #pv-left-column { width: 45%; height: 100%; }
    #pv-doc-list { height: 50%; border-bottom: solid $secondary; }
    #pv-pipeline-section { height: 50%; }
    #pv-pipeline-header { height: 1; background: $surface; padding: 0 1; }
    #pv-pipeline-table { height: 1fr; }
    #pv-preview-container { width: 55%; height: 100%; border-left: solid $primary; }
    #pv-preview-header { height: 1; background: $surface; padding: 0 1; }
    #pv-preview-scroll { height: 1fr; }
    #pv-preview-content { padding: 0 1; }
    #pv-preview-log { height: 1fr; display: none; }
    #pv-status { height: 1; background: $surface; padding: 0 1; }
    """

    current_stage_idx = reactive(0)
    AUTO_REFRESH_INTERVAL = 2.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.summary: StageSummaryBar | None = None
        self.doc_list: DocumentList | None = None
        self.pipeline_table: DataTable | None = None
        self._pipeline_data: list[dict[str, Any]] = []
        self._selected_pipeline_idx: int | None = None
        self._pipeline_view_mode: str = "output"
        self._auto_refresh_timer = None
        self._log_stream = None
        self._log_subscriber = None
        self._selected_exec: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        from textual.containers import ScrollableContainer
        from textual.widgets import RichLog

        self.summary = StageSummaryBar(id="pv-summary")
        yield self.summary

        with Horizontal(id="pv-main"):
            with Vertical(id="pv-left-column"):
                self.doc_list = DocumentList(id="pv-doc-list")
                yield self.doc_list
                with Vertical(id="pv-pipeline-section"):
                    yield Static("[bold]Pipeline Activity[/bold]", id="pv-pipeline-header")
                    self.pipeline_table = DataTable(id="pv-pipeline-table", cursor_type="row")
                    yield self.pipeline_table
            with Vertical(id="pv-preview-container"):
                yield Static("[bold]Preview[/bold]", id="pv-preview-header")
                with ScrollableContainer(id="pv-preview-scroll"):
                    yield RichLog(id="pv-preview-content", highlight=True, markup=True)
                yield RichLog(id="pv-preview-log", highlight=True, markup=True)

        yield Static("", id="pv-status")

    def on_mount(self) -> None:
        self._setup_pipeline_table()
        self.refresh_all()
        self._start_auto_refresh()

    def on_unmount(self) -> None:
        self._stop_auto_refresh()
        self._stop_log_stream()

    # ── Auto-refresh ──────────────────────────────────────────────

    def _start_auto_refresh(self) -> None:
        if self._auto_refresh_timer is None:
            self._auto_refresh_timer = self.set_interval(
                self.AUTO_REFRESH_INTERVAL, self._auto_refresh_tick, name="cascade_auto_refresh"
            )

    def _stop_auto_refresh(self) -> None:
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()
            self._auto_refresh_timer = None

    def _auto_refresh_tick(self) -> None:
        self._refresh_pipeline_table()
        if self.summary:
            self.summary.refresh_stats()
        if self.doc_list:
            stage = STAGES[self.current_stage_idx] if self.current_stage_idx < len(STAGES) else "idea"
            self.doc_list.load_stage(stage)
        # Refresh preview if a running execution just completed
        if self._selected_pipeline_idx is not None and self._selected_pipeline_idx < len(self._pipeline_data):
            act = self._pipeline_data[self._selected_pipeline_idx]
            if act.get("output_id") and self._pipeline_view_mode == "output":
                if self._selected_exec and self._selected_exec.get("status") == "running" and act.get("status") != "running":
                    self._show_pipeline_preview(act)

    # ── Pipeline table ────────────────────────────────────────────

    def _setup_pipeline_table(self) -> None:
        if self.pipeline_table:
            for label, w in [("Exec", 6), ("Time", 8), ("Input", 7), ("\u2192", 14), ("Output", 7), ("Status", 10)]:
                self.pipeline_table.add_column(label, width=w)

    def refresh_all(self) -> None:
        if self.summary:
            if self.current_stage_idx < len(STAGES):
                self.summary.current_stage = STAGES[self.current_stage_idx]
            self.summary.refresh_stats()
        if self.doc_list and self.current_stage_idx < len(STAGES):
            self.doc_list.load_stage(STAGES[self.current_stage_idx])
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)
        self._refresh_pipeline_table()
        self._update_status("[green]\u25cf[/green] Auto-refresh \u2502 [dim]h/l[/dim] stages \u2502 [dim]j/k[/dim] docs \u2502 [dim]a[/dim] advance \u2502 [dim]p[/dim] process \u2502 [dim]s[/dim] synthesize")

    def _refresh_pipeline_table(self) -> None:
        if not self.pipeline_table:
            return
        old_row = self.pipeline_table.cursor_row if self.pipeline_table.row_count > 0 else 0
        self.pipeline_table.clear()
        self._pipeline_data = get_recent_pipeline_activity(limit=10)

        STATUS_DISPLAY = {"completed": "[green]\u2713 done[/green]", "running": "[yellow]\u27f3 run[/yellow]", "failed": "[red]\u2717 fail[/red]"}

        for act in self._pipeline_data:
            exec_id = act.get("exec_id")
            ts = act.get("completed_at") or act.get("started_at")
            try:
                time_str = (ts.strftime("%H:%M:%S") if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)).strftime("%H:%M:%S")) if ts else ""
            except Exception:
                time_str = "?"

            from_stage, to_stage = act.get("from_stage", "?"), act.get("output_stage", "?")
            fe, te = STAGE_EMOJI.get(from_stage, ""), STAGE_EMOJI.get(to_stage, "")
            transition = f"{fe}{from_stage}\u2192{te}{to_stage}" if to_stage and to_stage != "?" else f"{fe}{from_stage}\u2192..."
            output_id = act.get("output_id")
            status = act.get("status", "?")

            self.pipeline_table.add_row(
                f"#{exec_id}" if exec_id else "-", time_str,
                f"#{act.get('input_id')}" if act.get("input_id") else "-",
                transition, f"#{output_id}" if output_id else "[dim]-[/dim]",
                STATUS_DISPLAY.get(status, f"[dim]{status}[/dim]"),
            )

        if self.pipeline_table.row_count > 0:
            self.pipeline_table.move_cursor(row=min(old_row, self.pipeline_table.row_count - 1))

    # ── Preview (document + execution log) ────────────────────────

    def _show_document_preview(self, doc_id: int) -> None:
        """Show document content in the preview pane."""
        self._stop_log_stream()
        try:
            header = self.query_one("#pv-preview-header", Static)
            from textual.containers import ScrollableContainer
            from textual.widgets import RichLog
            scroll = self.query_one("#pv-preview-scroll", ScrollableContainer)
            content = self.query_one("#pv-preview-content", RichLog)
            log_widget = self.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        scroll.display = True
        log_widget.display = False
        content.clear()

        doc = get_document(doc_id)
        if not doc:
            header.update("[bold]Preview[/bold]")
            content.write("[dim]Document not found[/dim]")
            return

        header.update(f"[bold]#{doc_id}[/bold] {doc.get('title', '')[:40]}")
        text = doc.get("content", "")
        if text:
            for line in text.split("\n")[:100]:
                content.write(line)
        else:
            content.write("[dim]No content[/dim]")

    def _show_execution_preview(self, exec_data: dict[str, Any]) -> None:
        """Show execution log in preview pane — live if running."""
        self._stop_log_stream()
        self._selected_exec = exec_data

        try:
            header = self.query_one("#pv-preview-header", Static)
            from textual.containers import ScrollableContainer
            from textual.widgets import RichLog
            scroll = self.query_one("#pv-preview-scroll", ScrollableContainer)
            log_widget = self.query_one("#pv-preview-log", RichLog)
        except Exception:
            return

        exec_id = exec_data.get("exec_id")
        status = exec_data.get("status", "")
        is_running = status == "running"

        exec_record = get_execution(exec_id) if exec_id else None
        log_file = exec_record.log_file if exec_record else None

        # Auto-fix zombie processes
        if exec_record and exec_record.is_zombie:
            update_execution_status(exec_id, "failed", -1)
            is_running = False
            exec_data["status"] = "failed"

        scroll.display = False
        log_widget.display = True
        log_widget.clear()

        if is_running and log_file:
            log_path = Path(log_file)
            if log_path.exists():
                header.update(f"[green]\u25cf LIVE[/green] [bold]#{exec_id}[/bold]")
                self._start_log_stream(log_path, log_widget)
            else:
                update_execution_status(exec_id, "failed", -1)
                header.update(f"[red]\u25cf STALE[/red] [bold]#{exec_id}[/bold]")
                log_widget.write("[red]Execution was stale - automatically marked as failed[/red]")
                log_widget.write(f"[dim]Log file not found: {log_file}[/dim]")
        else:
            header.update(f"[bold]#{exec_id}[/bold] {exec_data.get('doc_title', '')[:30]}")
            if log_file:
                log_path = Path(log_file)
                if log_path.exists():
                    from emdx.ui.live_log_writer import LiveLogWriter
                    LiveLogWriter(log_widget, auto_scroll=False).write(log_path.read_text())
                else:
                    log_widget.write("[dim]Log file not found[/dim]")
            else:
                log_widget.write("[dim]No log file[/dim]")

    def _start_log_stream(self, log_path: Path, log_widget) -> None:
        from emdx.services.log_stream import LogStream
        from emdx.ui.live_log_writer import LiveLogWriter
        from emdx.utils.stream_json_parser import parse_and_format_live_logs

        self._log_stream = LogStream(log_path)
        initial = self._log_stream.get_initial_content()
        if initial:
            for line in parse_and_format_live_logs(initial)[-50:]:
                log_widget.write(line)
            log_widget.scroll_end(animate=False)

        view = self

        class _Subscriber:
            def __init__(self, w):
                self.w = w
            def on_log_content(self, content):
                try:
                    view.app.call_from_thread(lambda: (LiveLogWriter(self.w, auto_scroll=True).write(content), self.w.refresh()))
                except Exception as e:
                    logger.error(f"call_from_thread failed: {e}")
            def on_log_error(self, error):
                logger.error(f"Log stream error: {error}")

        self._log_subscriber = _Subscriber(log_widget)
        self._log_stream.subscribe(self._log_subscriber)

    def _stop_log_stream(self) -> None:
        if self._log_stream and self._log_subscriber:
            self._log_stream.unsubscribe(self._log_subscriber)
        self._log_stream = None
        self._log_subscriber = None

    # ── Pipeline preview routing ──────────────────────────────────

    def _show_pipeline_preview(self, act: dict[str, Any]) -> None:
        if self._pipeline_view_mode == "input":
            input_id = act.get("input_id")
            if input_id:
                self._show_document_preview(input_id)
            else:
                self._update_status("[yellow]No input document[/yellow]")
        else:
            output_id = act.get("output_id")
            if output_id:
                self._show_document_preview(output_id)
            else:
                self._show_execution_preview(act)

    # ── Stage navigation ──────────────────────────────────────────

    def watch_current_stage_idx(self, idx: int) -> None:
        if idx >= len(STAGES):
            return
        if self.summary:
            self.summary.current_stage = STAGES[idx]
            self.summary._update_display()
        if self.doc_list:
            self.doc_list.load_stage(STAGES[idx])
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

    # ── Event handlers ────────────────────────────────────────────

    def on_document_list_document_selected(self, event: DocumentList.DocumentSelected) -> None:
        self._show_document_preview(event.doc_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "pv-pipeline-table":
            return
        row_idx = event.cursor_row
        if row_idx < len(self._pipeline_data):
            self._selected_pipeline_idx = row_idx
            act = self._pipeline_data[row_idx]
            output_id = act.get("output_id")
            if output_id:
                self._show_document_preview(output_id)
            else:
                self._show_execution_preview(act)

    # ── Actions ───────────────────────────────────────────────────

    def action_prev_stage(self) -> None:
        if self.current_stage_idx > 0:
            self.current_stage_idx -= 1

    def action_next_stage(self) -> None:
        if self.current_stage_idx < len(STAGES) - 1:
            self.current_stage_idx += 1

    def _move_cursor_and_preview(self, direction: int) -> None:
        """Move cursor in the focused table and update preview."""
        if self.pipeline_table and self.pipeline_table.has_focus:
            (self.pipeline_table.action_cursor_down if direction > 0 else self.pipeline_table.action_cursor_up)()
            row_idx = self.pipeline_table.cursor_row
            if row_idx < len(self._pipeline_data):
                self._selected_pipeline_idx = row_idx
                self._show_pipeline_preview(self._pipeline_data[row_idx])
        elif self.doc_list:
            self.doc_list.move_cursor(direction)
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self._show_document_preview(doc_id)

    def action_move_down(self) -> None:
        self._move_cursor_and_preview(1)

    def action_move_up(self) -> None:
        self._move_cursor_and_preview(-1)

    def action_view_doc(self) -> None:
        if self.doc_list:
            doc_id = self.doc_list.get_selected_doc_id()
            if doc_id:
                self.post_message(self.ViewDocument(doc_id))

    def _get_selected_pipeline_act(self) -> dict[str, Any] | None:
        if self._selected_pipeline_idx is None:
            self._update_status("[yellow]Select a pipeline row first[/yellow]")
            return None
        if self._selected_pipeline_idx >= len(self._pipeline_data):
            return None
        return self._pipeline_data[self._selected_pipeline_idx]

    def action_show_input(self) -> None:
        self._pipeline_view_mode = "input"
        act = self._get_selected_pipeline_act()
        if not act:
            return
        input_id = act.get("input_id")
        if input_id:
            self._show_document_preview(input_id)
            self._update_status(f"[cyan]Input mode[/cyan] - showing #{input_id} (press 'o' for output)")
        else:
            self._update_status("[yellow]No input document[/yellow]")

    def action_show_output(self) -> None:
        self._pipeline_view_mode = "output"
        act = self._get_selected_pipeline_act()
        if not act:
            return
        output_id = act.get("output_id")
        if output_id:
            self._show_document_preview(output_id)
            self._update_status(f"[cyan]Output mode[/cyan] - showing #{output_id} (press 'i' for input)")
        else:
            self._show_execution_preview(act)
            self._update_status("[yellow]No output yet - showing execution log[/yellow]")

    def action_advance_doc(self) -> None:
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]
        next_stage = NEXT_STAGE.get(stage)
        if not next_stage:
            self._update_status("[yellow]Already at final stage[/yellow]")
            return
        if not self.doc_list:
            return
        doc_id = self.doc_list.get_selected_doc_id()
        if not doc_id:
            self._update_status("[yellow]No document selected[/yellow]")
            return
        update_cascade_stage(doc_id, next_stage)
        self._update_status(f"[green]Moved #{doc_id}: {stage} \u2192 {next_stage}[/green]")
        self.refresh_all()

    def action_new_idea(self) -> None:
        def handle(idea_text: str | None) -> None:
            if idea_text:
                doc_id = save_document_to_cascade(
                    title=f"Cascade: {idea_text[:50]}{'...' if len(idea_text) > 50 else ''}",
                    content=idea_text, stage="idea",
                )
                self._update_status(f"[green]Created idea #{doc_id}[/green]")
                self.current_stage_idx = 0
                self.refresh_all()
        self.app.push_screen(NewIdeaScreen(), handle)

    def action_process(self) -> None:
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]
        if not NEXT_STAGE.get(stage):
            self._update_status("[yellow]'done' is terminal - nothing to process[/yellow]")
            return
        doc_id = self.doc_list.get_selected_doc_id() if self.doc_list else None
        self.post_message(self.ProcessStage(stage, doc_id))

    def action_toggle_select(self) -> None:
        if self.doc_list:
            self.doc_list.toggle_selection()

    def action_select_all(self) -> None:
        if self.doc_list:
            self.doc_list.select_all()

    def action_clear_selection(self) -> None:
        if self.doc_list:
            self.doc_list.clear_selection()

    def action_synthesize(self) -> None:
        if self.current_stage_idx >= len(STAGES):
            return
        stage = STAGES[self.current_stage_idx]
        if not NEXT_STAGE.get(stage):
            self._update_status("[yellow]Cannot synthesize from terminal stage[/yellow]")
            return

        selected_ids = self.doc_list.get_selected_ids() if self.doc_list else []
        if not selected_ids:
            selected_ids = [d["id"] for d in list_documents_at_stage(stage)]
        if len(selected_ids) < 2:
            self._update_status(f"[yellow]Need 2+ docs to synthesize (selected: {len(selected_ids)})[/yellow]")
            return

        parts = []
        for did in selected_ids:
            doc = get_document(str(did))
            if doc:
                parts.append(f"=== Document #{did}: {doc['title']} ===\n{doc['content']}")

        synthesis_doc_id = save_document_to_cascade(
            title=f"Synthesis: {len(selected_ids)} {stage} documents",
            content="\n\n---\n\n".join(parts), stage=stage,
        )
        self._update_status(f"[cyan]Synthesizing {len(selected_ids)} docs via Claude...[/cyan]")
        self.post_message(self.ProcessStage(stage, synthesis_doc_id))
        self.refresh_all()

    def action_refresh(self) -> None:
        self.refresh_all()

    def action_toggle_activity_view(self) -> None:
        self.refresh_all()

    def _update_status(self, text: str) -> None:
        self.query_one("#pv-status", Static).update(text)
