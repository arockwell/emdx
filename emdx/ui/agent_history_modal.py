#!/usr/bin/env python3
"""
Modal dialog for viewing agent execution history.
"""

import json

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Static
from textual.binding import Binding

from ..agents.registry import agent_registry


class AgentHistoryModal(ModalScreen):
    """Modal for viewing agent execution history."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
    ]

    DEFAULT_CSS = """
    AgentHistoryModal {
        align: center middle;
    }

    #history-dialog {
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        width: 90;
        height: 80%;
    }

    #history-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #history-log {
        height: 1fr;
        border: solid $primary;
        margin: 1 0;
    }
    """

    def __init__(self, agent_id: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent_id = agent_id
        self.agent = agent_registry.get_agent(agent_id)

    def compose(self) -> ComposeResult:
        """Create the history dialog."""
        with Vertical(id="history-dialog"):
            yield Static(
                f"Execution History: {self.agent.config.display_name}",
                id="history-title",
            )
            yield RichLog(id="history-log")
            yield Button("Close", id="close-button")

    async def on_mount(self) -> None:
        """Load execution history."""
        log = self.query_one("#history-log", RichLog)

        try:
            from ..database.connection import db_connection

            with db_connection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        ae.id,
                        ae.status,
                        ae.started_at,
                        ae.completed_at,
                        ae.input_type,
                        ae.input_query,
                        ae.error_message,
                        ae.execution_time_ms,
                        ae.iterations_used,
                        ae.output_doc_ids,
                        d.title as input_doc_title
                    FROM agent_executions ae
                    LEFT JOIN documents d ON ae.input_doc_id = d.id
                    WHERE ae.agent_id = ?
                    ORDER BY ae.started_at DESC
                    LIMIT 50
                """,
                    (self.agent_id,),
                )

                rows = cursor.fetchall()

                if not rows:
                    log.write("[yellow]No execution history found[/yellow]")
                    return

                for row in rows:
                    # Format execution entry
                    status_icon = {
                        "completed": "✅",
                        "failed": "❌",
                        "running": "🔄",
                        "cancelled": "⚠️",
                    }.get(row["status"], "❓")

                    log.write(f"\n[bold]{status_icon} Execution #{row['id']}[/bold]")
                    log.write(f"Started: {row['started_at']}")

                    if row["input_type"] == "document":
                        log.write(
                            f"Input: Document - {row['input_doc_title'] or 'Unknown'}"
                        )
                    else:
                        log.write(f"Input: Query - {row['input_query'][:100]}...")

                    if row["status"] == "completed":
                        log.write(f"Completed: {row['completed_at']}")
                        if row["execution_time_ms"]:
                            log.write(
                                f"Duration: {row['execution_time_ms'] / 1000:.1f}s"
                            )
                        if row["iterations_used"]:
                            log.write(f"Iterations: {row['iterations_used']}")
                        if row["output_doc_ids"]:
                            doc_ids = json.loads(row["output_doc_ids"])
                            log.write(
                                f"Output Docs: {', '.join(f'#{id}' for id in doc_ids)}"
                            )
                    elif row["status"] == "failed":
                        log.write(f"[red]Failed: {row['error_message']}[/red]")

                    log.write("-" * 60)

        except Exception as e:
            log.write(f"[red]Error loading history: {e}[/red]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "close-button":
            self.action_close()

    def action_close(self) -> None:
        """Close the dialog."""
        self.dismiss()
