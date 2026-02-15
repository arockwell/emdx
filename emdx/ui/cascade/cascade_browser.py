"""Cascade browser — top-level widget with execution orchestration."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from emdx.services.cascade_service import (
    get_document,
    list_documents_at_stage,
    monitor_execution_completion,
)
from emdx.services.document_service import save_document
from emdx.services.execution_service import create_execution

from .cascade_view import CascadeView
from .constants import NEXT_STAGE

logger = logging.getLogger(__name__)


class CascadeBrowser(Widget):
    """Browser wrapper for CascadeView with execution orchestration."""

    BINDINGS = [
        ("1", "switch_activity", "Activity"),
        ("2", "switch_cascade", "Cascade"),
        ("3", "switch_search", "Search"),
        ("4", "switch_documents", "Documents"),
        ("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    CascadeBrowser {
        layout: vertical;
        height: 100%;
    }
    #cascade-view { height: 1fr; }
    #help-bar { height: 1; background: $surface; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.cascade_view: CascadeView | None = None

    def compose(self) -> ComposeResult:
        self.cascade_view = CascadeView(id="cascade-view")
        yield self.cascade_view
        yield Static(
            "[dim]1[/dim] Activity \u2502 [bold]2[/bold] Cascade \u2502 [dim]3[/dim] Search \u2502 [dim]4[/dim] Docs \u2502 "  # noqa: E501
            "[dim]n[/dim] new idea \u2502 [dim]a[/dim] advance \u2502 [dim]p[/dim] process \u2502 [dim]s[/dim] synthesize",  # noqa: E501
            id="help-bar",
        )

    def on_cascade_view_view_document(self, event: CascadeView.ViewDocument) -> None:
        logger.info(f"Would view document #{event.doc_id}")
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_cascade_view_process_stage(self, event: CascadeView.ProcessStage) -> None:
        """Handle request to process a stage — runs Claude with live logs."""
        stage, doc_id = event.stage, event.doc_id

        doc: dict[str, Any] | None
        if doc_id:
            raw = get_document(str(doc_id))
            doc = dict(raw) if raw else None
            if not doc:
                self._update_status(f"[red]Document #{doc_id} not found[/red]")
                return
        else:
            docs = list_documents_at_stage(stage)
            if not docs:
                self._update_status(f"[yellow]No documents at stage '{stage}'[/yellow]")
                return
            doc = dict(docs[0])
            doc_id = doc["id"]

        assert doc_id is not None and doc is not None  # Guaranteed by the if/else above
        self._update_status(f"[cyan]Processing #{doc_id}: {doc.get('title', '')[:40]}...[/cyan]")

        from emdx.commands.cascade import STAGE_PROMPTS
        from emdx.services.claude_executor import DEFAULT_ALLOWED_TOOLS, execute_claude_detached

        prompt = STAGE_PROMPTS[stage].format(content=doc.get("content", ""))

        log_dir = Path.cwd() / ".emdx" / "logs" / "cascade"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.write_text(f"# Cascade: {stage} processing for doc #{doc_id}\n# Started: {datetime.now().isoformat()}\n")  # noqa: E501

        exec_id = create_execution(
            doc_id=doc_id, doc_title=f"Cascade: {doc.get('title', '')}",
            log_file=str(log_file), working_dir=str(Path.cwd()),
        )

        try:
            pid = execute_claude_detached(
                task=prompt, execution_id=exec_id, log_file=log_file,
                allowed_tools=list(DEFAULT_ALLOWED_TOOLS), working_dir=str(Path.cwd()),
                doc_id=str(doc_id),
            )
            self._update_status(f"[green]\u25cf Started #{exec_id}[/green] (PID {pid}) - monitoring...")  # noqa: E501
            if self.cascade_view:
                self.cascade_view.refresh_all()
            self._start_completion_monitor(exec_id, doc_id, doc, stage, str(log_file))
        except Exception as e:
            from emdx.services.execution_service import update_execution_status
            update_execution_status(exec_id, "failed", exit_code=1)
            self._update_status(f"[red]\u2717 Failed to start:[/red] {str(e)[:50]}")
            if self.cascade_view:
                self.cascade_view.refresh_all()

    def _start_completion_monitor(
        self, exec_id: int, doc_id: int,
        doc: dict[str, Any], stage: str, log_file: str,
    ) -> None:
        """Monitor execution in a background thread, updating UI on completion."""
        import concurrent.futures

        app = self.app
        view = self.cascade_view

        def on_update(status_markup: str) -> None:
            def _apply() -> None:
                self._update_status(status_markup)
                if view:
                    view.refresh_all()
            app.call_from_thread(_apply)

        def run() -> None:
            monitor_execution_completion(
                exec_id=exec_id, doc_id=doc_id, doc=doc, stage=stage,
                log_file=Path(log_file), next_stage_map=NEXT_STAGE,
                on_update=on_update, save_doc=save_document,
            )

        concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(run)

    def _update_status(self, text: str) -> None:
        if self.cascade_view:
            self.cascade_view._update_status(text)

    async def action_switch_activity(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("activity")

    async def action_switch_cascade(self) -> None:
        pass

    async def action_switch_documents(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("document")

    async def action_switch_search(self) -> None:
        if hasattr(self.app, "switch_browser"):
            await self.app.switch_browser("search")

    def action_show_help(self) -> None:
        pass

    def update_status(self, text: str) -> None:
        pass

    def focus(self, scroll_visible: bool = True) -> Self:  # type: ignore[override]
        if self.cascade_view:
            self.cascade_view.focus()
        return self  # type: ignore[return-value]
