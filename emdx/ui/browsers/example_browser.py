"""
ExampleBrowser - Demonstrates the minimal API for building browsers.

This browser shows how to use the existing panel components (ListPanel
and PreviewPanel) to build a complete browser UI in ~40 lines of code.

Features demonstrated:
- ListPanel with vim navigation and search
- PreviewPanel with markdown rendering
- Message-based communication between panels
- State save/restore

For more examples, see: docs/browser-dx-design.md
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget

from ..panels import (
    ListPanel,
    PreviewPanel,
    ColumnDef,
    ListItem,
    ListPanelConfig,
    PreviewPanelConfig,
)


class ExampleBrowser(Widget):
    """A minimal example browser using panel components.

    This demonstrates the simplest possible browser implementation:
    - ~40 lines of code
    - Full vim-style navigation
    - Search functionality
    - Markdown preview
    - Automatic panel communication

    Usage:
        browser = ExampleBrowser()
        # Mount it in your Textual app
    """

    DEFAULT_CSS = """
    ExampleBrowser {
        layout: horizontal;
        height: 100%;
    }

    ExampleBrowser #example-list {
        width: 50%;
        min-width: 30;
    }

    ExampleBrowser #example-preview {
        width: 50%;
        min-width: 30;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    def compose(self) -> ComposeResult:
        """Compose the browser layout with panels."""
        # List panel with vim navigation and search
        yield ListPanel(
            columns=[
                ColumnDef("ID", width=5),
                ColumnDef("Name", width=30),
                ColumnDef("Status", width=10),
            ],
            config=ListPanelConfig(
                show_search=True,
                search_placeholder="Search items...",
                status_format="{filtered}/{total} items",
            ),
            show_status=True,
            id="example-list",
        )

        # Preview panel with markdown rendering
        yield PreviewPanel(
            config=PreviewPanelConfig(
                enable_editing=False,
                enable_selection=True,
                empty_message="Select an item to preview",
            ),
            id="example-preview",
        )

    async def on_mount(self) -> None:
        """Initialize with sample data."""
        await self._load_sample_data()

    async def _load_sample_data(self) -> None:
        """Load sample items into the list."""
        items = [
            ListItem(
                id=1,
                values=["1", "Getting Started", "Active"],
                data={
                    "description": "Introduction to the example browser",
                    "content": "# Getting Started\n\nThis is an example browser demonstrating the panel system.\n\n## Features\n\n- Vim-style navigation (j/k)\n- Search with /\n- Markdown preview",
                },
            ),
            ListItem(
                id=2,
                values=["2", "Navigation", "Active"],
                data={
                    "description": "How to navigate the browser",
                    "content": "# Navigation\n\nUse these keys to navigate:\n\n- `j` - Move down\n- `k` - Move up\n- `g` - Go to top\n- `G` - Go to bottom\n- `/` - Search",
                },
            ),
            ListItem(
                id=3,
                values=["3", "Panel Communication", "Active"],
                data={
                    "description": "How panels communicate",
                    "content": "# Panel Communication\n\nPanels communicate via Textual messages:\n\n```python\nasync def on_list_panel_item_selected(self, event):\n    preview.show_content(event.item.data['content'])\n```\n\nThis keeps panels decoupled and reusable.",
                },
            ),
            ListItem(
                id=4,
                values=["4", "Building New Browsers", "Pending"],
                data={
                    "description": "Guide to creating your own browser",
                    "content": "# Building New Browsers\n\nTo create a new browser:\n\n1. Create a Widget subclass\n2. Yield ListPanel and PreviewPanel in compose()\n3. Handle `on_list_panel_item_selected`\n4. Done!\n\nSee `docs/browser-dx-design.md` for full documentation.",
                },
            ),
            ListItem(
                id=5,
                values=["5", "Testing", "Done"],
                data={
                    "description": "How to test your browser",
                    "content": "# Testing\n\nUse the test harness:\n\n```python\nfrom emdx.ui.testing import BrowserTestHarness\n\nasync def test_navigation(harness):\n    await harness.mount()\n    await harness.press('j')\n    assert harness.get_selected_index() == 1\n```",
                },
            ),
        ]

        list_panel = self.query_one("#example-list", ListPanel)
        list_panel.set_items(items)

    async def on_list_panel_item_selected(
        self, event: ListPanel.ItemSelected
    ) -> None:
        """Update preview when item is selected."""
        item = event.item
        preview = self.query_one("#example-preview", PreviewPanel)

        # Get content from item data
        content = ""
        if item.data:
            content = item.data.get("content", "")
            if not content:
                # Fallback to description
                desc = item.data.get("description", "")
                content = f"# {item.values[1]}\n\n{desc}"

        await preview.show_content(content, title=item.values[1])

    async def on_list_panel_item_activated(
        self, event: ListPanel.ItemActivated
    ) -> None:
        """Handle Enter key on item."""
        self.notify(f"Activated: {event.item.values[1]}")

    async def on_list_panel_search_submitted(
        self, event: ListPanel.SearchSubmitted
    ) -> None:
        """Handle search submission."""
        if event.query:
            self.notify(f"Searching for: {event.query}")
        else:
            self.notify("Search cleared")

    def action_refresh(self) -> None:
        """Refresh the browser."""
        import asyncio

        asyncio.create_task(self._load_sample_data())
        self.notify("Refreshed")

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
