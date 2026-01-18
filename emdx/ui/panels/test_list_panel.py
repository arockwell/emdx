#!/usr/bin/env python3
"""
Test application for ListPanel.

Run with:
    python -m emdx.ui.panels.test_list_panel

Or from the project root:
    poetry run python -m emdx.ui.panels.test_list_panel
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, RichLog

from emdx.ui.panels import ListPanel, ListItem, ColumnDef, ListPanelConfig


class TestListPanelApp(App):
    """Test application demonstrating ListPanel functionality."""

    TITLE = "ListPanel Test"
    SUB_TITLE = "Press ? for help, q to quit"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #list-container {
        width: 50%;
        height: 100%;
        border-right: solid $primary;
    }

    #preview-container {
        width: 50%;
        height: 100%;
    }

    #preview-content {
        padding: 1 2;
        height: 100%;
    }

    #log-container {
        height: 8;
        border-top: solid $primary;
    }

    #event-log {
        height: 100%;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "clear_log", "Clear Log"),
        Binding("1", "load_small", "10 items"),
        Binding("2", "load_medium", "100 items"),
        Binding("3", "load_large", "1000 items"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the test application UI."""
        yield Header()

        with Vertical():
            with Horizontal(id="main-container"):
                with Vertical(id="list-container"):
                    yield ListPanel(
                        columns=[
                            ColumnDef("ID", width=6),
                            ColumnDef("Type", width=8),
                            ColumnDef("Name", width=30),
                            ColumnDef("Status", width=10),
                        ],
                        config=ListPanelConfig(
                            show_search=True,
                            search_placeholder="Search items... (try 'active' or '42')",
                            lazy_load_threshold=20,
                            status_format="{filtered}/{total} items",
                        ),
                        show_status=True,
                        id="test-list",
                    )

                with Vertical(id="preview-container"):
                    yield Static(
                        "[dim]Select an item to see details[/dim]",
                        id="preview-content",
                    )

            with Vertical(id="log-container"):
                yield RichLog(id="event-log", highlight=True, markup=True, wrap=True)

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize with sample data."""
        self.log_event("[bold green]App started[/]")
        await self.load_data(count=50)

    async def load_data(self, count: int = 50, has_more: bool = True) -> None:
        """Load sample data."""
        statuses = ["Active", "Pending", "Done", "Error", "Blocked"]
        types = ["Doc", "Note", "Task", "Bug", "Feature"]

        items = []
        for i in range(1, count + 1):
            status = statuses[i % len(statuses)]
            item_type = types[i % len(types)]
            items.append(
                ListItem(
                    id=i,
                    values=[
                        str(i),
                        item_type,
                        f"Item number {i}",
                        status,
                    ],
                    data={
                        "description": f"This is a detailed description for item {i}.",
                        "created": "2024-01-15",
                        "priority": "High" if i % 3 == 0 else "Normal",
                    },
                )
            )

        list_panel = self.query_one("#test-list", ListPanel)
        list_panel.set_items(items, has_more=has_more)
        self.log_event(f"[cyan]Loaded {count} items[/]")

    def log_event(self, message: str) -> None:
        """Log an event to the event log."""
        try:
            log = self.query_one("#event-log", RichLog)
            log.write(message)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Handle item selection."""
        item = event.item
        preview = self.query_one("#preview-content", Static)

        # Format preview content
        data = item.data or {}
        preview.update(
            f"[bold]{item.values[2]}[/bold]\n\n"
            f"[dim]ID:[/] {item.id}\n"
            f"[dim]Type:[/] {item.values[1]}\n"
            f"[dim]Status:[/] {item.values[3]}\n"
            f"[dim]Priority:[/] {data.get('priority', 'N/A')}\n"
            f"[dim]Created:[/] {data.get('created', 'N/A')}\n\n"
            f"[italic]{data.get('description', 'No description')}[/italic]"
        )

        self.log_event(f"Selected: [yellow]#{item.id}[/] {item.values[2]}")

    async def on_list_panel_item_activated(
        self, event: ListPanel.ItemActivated
    ) -> None:
        """Handle item activation (Enter key)."""
        self.log_event(f"[bold green]Activated:[/] #{event.item.id} {event.item.values[2]}")
        self.notify(f"Activated: {event.item.values[2]}")

    async def on_list_panel_search_submitted(
        self, event: ListPanel.SearchSubmitted
    ) -> None:
        """Handle search submission."""
        if event.query:
            self.log_event(f"[blue]Search:[/] '{event.query}'")
        else:
            self.log_event("[blue]Search cleared[/]")

    async def on_list_panel_load_more_requested(
        self, event: ListPanel.LoadMoreRequested
    ) -> None:
        """Handle load more request."""
        self.log_event(
            f"[magenta]Load more requested[/] at index {event.current_index}/{event.total_count}"
        )

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_show_help(self) -> None:
        """Show help dialog."""
        help_text = """
[bold]ListPanel Test App[/]

[cyan]Navigation:[/]
  j/k    - Move down/up
  g/G    - Go to top/bottom
  Enter  - Activate item

[cyan]Search:[/]
  /      - Start search
  Escape - Cancel search

[cyan]Test Actions:[/]
  1      - Load 10 items
  2      - Load 100 items
  3      - Load 1000 items
  r      - Refresh (50 items)
  c      - Clear event log

[cyan]General:[/]
  q      - Quit
  ?      - This help
"""
        self.notify(help_text, title="Help", timeout=10)

    async def action_refresh(self) -> None:
        """Refresh data."""
        await self.load_data(count=50)

    async def action_load_small(self) -> None:
        """Load 10 items."""
        await self.load_data(count=10, has_more=False)

    async def action_load_medium(self) -> None:
        """Load 100 items."""
        await self.load_data(count=100, has_more=False)

    async def action_load_large(self) -> None:
        """Load 1000 items."""
        await self.load_data(count=1000, has_more=False)

    def action_clear_log(self) -> None:
        """Clear the event log."""
        try:
            log = self.query_one("#event-log", RichLog)
            log.clear()
            self.log_event("[dim]Log cleared[/]")
        except Exception:
            pass


if __name__ == "__main__":
    app = TestListPanelApp()
    app.run()
