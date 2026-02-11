"""Cascade browser - top-level widget with execution orchestration."""

import logging
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from emdx.services.cascade_service import (
    get_document,
    list_documents_at_stage,
    save_document_to_cascade,
    update_cascade_stage,
)
from emdx.services.document_service import save_document
from emdx.services.execution_service import (
    create_execution,
    get_execution,
    update_execution_status,
)

from .cascade_view import CascadeView
from .constants import NEXT_STAGE

logger = logging.getLogger(__name__)


class CascadeBrowser(Widget):
    """Browser wrapper for CascadeView."""

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
            "[dim]1[/dim] Activity \u2502 [bold]2[/bold] Cascade \u2502 [dim]3[/dim] Search \u2502 [dim]4[/dim] Docs \u2502 "
            "[dim]n[/dim] new idea \u2502 [dim]a[/dim] advance \u2502 [dim]p[/dim] process \u2502 [dim]s[/dim] synthesize",
            id="help-bar",
        )

    def on_cascade_view_view_document(self, event: CascadeView.ViewDocument) -> None:
        """Handle request to view document."""
        logger.info(f"Would view document #{event.doc_id}")
        if hasattr(self.app, "_view_document"):
            self.call_later(lambda: self.app._view_document(event.doc_id))

    def on_cascade_view_process_stage(self, event: CascadeView.ProcessStage) -> None:
        """Handle request to process a stage - runs Claude with live logs."""
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

        # Use detached execution like the CLI does - much more reliable
        from emdx.services.claude_executor import execute_claude_detached, DEFAULT_ALLOWED_TOOLS
        from emdx.commands.cascade import STAGE_PROMPTS

        # Build prompt
        prompt = STAGE_PROMPTS[stage].format(content=doc.get("content", ""))

        # Set up log file
        log_dir = Path.cwd() / ".emdx" / "logs" / "cascade"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{doc_id}_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Create log file immediately so UI can show it
        with open(log_file, 'w') as f:
            f.write(f"# Cascade: {stage} processing for doc #{doc_id}\n")
            f.write(f"# Started: {datetime.now().isoformat()}\n")

        # Create execution record
        exec_id = create_execution(
            doc_id=doc_id,
            doc_title=f"Cascade: {doc.get('title', '')}",
            log_file=str(log_file),
            working_dir=str(Path.cwd()),
        )

        logger.info(f"Created execution #{exec_id} with log file: {log_file}")

        try:
            # Start detached process - returns immediately with PID
            pid = execute_claude_detached(
                task=prompt,
                execution_id=exec_id,
                log_file=log_file,
                allowed_tools=list(DEFAULT_ALLOWED_TOOLS),
                working_dir=str(Path.cwd()),
                doc_id=str(doc_id),
            )

            # PID is tracked by execute_claude_detached via update_execution_pid
            self._update_status(f"[green]\u25cf Started #{exec_id}[/green] (PID {pid}) - monitoring...")

            # Refresh UI to show the new execution
            if self.cascade_view:
                self.cascade_view.refresh_all()

            # Start monitoring for completion in background
            self._start_completion_monitor(exec_id, doc_id, doc, stage, log_file)

        except Exception as e:
            update_execution_status(exec_id, "failed", exit_code=1)
            self._update_status(f"[red]\u2717 Failed to start:[/red] {str(e)[:50]}")
            if self.cascade_view:
                self.cascade_view.refresh_all()

    def _start_completion_monitor(
        self,
        exec_id: int,
        doc_id: int,
        doc: dict,
        stage: str,
        log_file: "Path"
    ) -> None:
        """Monitor a detached execution for completion.

        Watches the log file for a result JSON line, then processes the output.
        This runs in a background thread to not block the UI.
        """
        import json
        import os
        import time

        def monitor():
            poll_interval = 2.0  # Check every 2 seconds
            max_wait = 1800 if stage == "planned" else 300  # Same timeouts as before
            start_time = time.time()

            while True:
                elapsed = time.time() - start_time

                # Check timeout
                if elapsed > max_wait:
                    # Check if process is still alive
                    exec_record = get_execution(exec_id)
                    if exec_record and exec_record.pid:
                        try:
                            os.kill(exec_record.pid, 9)  # Force kill
                        except ProcessLookupError:
                            pass
                    update_execution_status(exec_id, "failed", exit_code=-1)
                    def update_timeout():
                        self._update_status(f"[red]\u2717 Timeout[/red] after {max_wait}s")
                        if self.cascade_view:
                            self.cascade_view.refresh_all()
                    self.app.call_from_thread(update_timeout)
                    return

                # Check if log file has a result line
                if log_file.exists():
                    try:
                        content = log_file.read_text()
                        for line in content.splitlines():
                            if line.startswith('{') and '"type":"result"' in line:
                                # Found result - parse it
                                try:
                                    result_data = json.loads(line)
                                    is_error = result_data.get("is_error", False)
                                    output = result_data.get("result", "")

                                    if is_error:
                                        update_execution_status(exec_id, "failed", exit_code=1)
                                        def update_failed():
                                            self._update_status(f"[red]\u2717 Failed[/red]")
                                            if self.cascade_view:
                                                self.cascade_view.refresh_all()
                                        self.app.call_from_thread(update_failed)
                                    else:
                                        update_execution_status(exec_id, "completed", exit_code=0)

                                        # Create child document with output
                                        if output:
                                            next_stage = NEXT_STAGE.get(stage, "done")
                                            child_title = f"{doc.get('title', '')} [{stage}\u2192{next_stage}]"
                                            new_doc_id = save_document(
                                                title=child_title,
                                                content=output,
                                                project=doc.get("project"),
                                                parent_id=doc_id,
                                            )
                                            update_cascade_stage(new_doc_id, next_stage)
                                            update_cascade_stage(doc_id, "done")

                                            def update_success():
                                                self._update_status(f"[green]\u2713 Done![/green] Created #{new_doc_id} at {next_stage}")
                                                if self.cascade_view:
                                                    self.cascade_view.refresh_all()
                                            self.app.call_from_thread(update_success)
                                        else:
                                            def update_done():
                                                self._update_status(f"[green]\u2713 Completed[/green]")
                                                if self.cascade_view:
                                                    self.cascade_view.refresh_all()
                                            self.app.call_from_thread(update_done)
                                    return

                                except json.JSONDecodeError:
                                    pass  # Not valid JSON, keep looking
                    except Exception as e:
                        logger.debug(f"Error reading log file: {e}")

                # Check if process died without result
                exec_record = get_execution(exec_id)
                if exec_record and exec_record.is_zombie:
                    update_execution_status(exec_id, "failed", exit_code=-1)
                    def update_zombie():
                        self._update_status(f"[red]\u2717 Process died[/red]")
                        if self.cascade_view:
                            self.cascade_view.refresh_all()
                    self.app.call_from_thread(update_zombie)
                    return

                time.sleep(poll_interval)

        # Run monitor in background thread
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        executor.submit(monitor)

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
