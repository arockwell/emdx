# Browser Developer Experience (DX) Design

This document outlines the developer experience for building new browsers with the panel system. The goal is to make building browsers feel like assembling Lego blocks.

## Current State

The panel system is **partially implemented** with:
- `ListPanel` - Fully implemented with vim navigation, search, lazy loading
- `PreviewPanel` - Fully implemented with viewing, editing, and selection modes
- `PanelBase` - Abstract base class implementing the protocol
- `PanelProtocol` - Type-safe interface for all panels

**What's needed to complete the vision:**
- `Browser` base class for composing panels
- `StatusPanel` and `DetailPanel` implementations
- Testing utilities
- Scaffolding command

## Table of Contents

1. [Minimal Viable Browser](#1-minimal-viable-browser)
2. [Using Existing Panels](#2-using-existing-panels)
3. [The Browser Base Class (Proposed)](#3-the-browser-base-class-proposed)
4. [Documentation Template](#4-documentation-template)
5. [Code Generation / Scaffolding](#5-code-generation--scaffolding)
6. [Type Checking Support](#6-type-checking-support)
7. [Debugging Support](#7-debugging-support)
8. [Testing Utilities](#8-testing-utilities)

---

## 1. Minimal Viable Browser

### Goal: 50 lines of code for a fully functional browser

A minimal browser should:
- Show a list of items
- Show a preview when item is selected
- Have a status bar
- Work with standard keybindings (vim-style j/k navigation)

### Current Complexity vs Proposed

**Current approach:** 300-700+ lines per browser (see `task_browser.py` at 357 lines)

**Proposed approach (with existing panels):** ~50 lines for equivalent functionality

### The Simplest Possible Browser (Using Existing Panels)

```python
# emdx/ui/browsers/example_browser.py
"""Example browser - demonstrates using existing panel components."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget

from emdx.ui.panels import ListPanel, PreviewPanel, ColumnDef, ListItem


class ExampleBrowser(Widget):
    """A minimal browser using existing panel components."""

    DEFAULT_CSS = """
    ExampleBrowser {
        layout: horizontal;
        height: 100%;
    }
    #example-list { width: 50%; }
    #example-preview { width: 50%; border-left: solid $primary; }
    """

    def compose(self) -> ComposeResult:
        yield ListPanel(
            columns=[ColumnDef("ID", 5), ColumnDef("Name", 30), ColumnDef("Status", 10)],
            show_status=True,
            id="example-list",
        )
        yield PreviewPanel(id="example-preview")

    async def on_mount(self) -> None:
        """Load items on mount."""
        items = [
            ListItem(id=1, values=["1", "First Item", "active"], data={"desc": "First"}),
            ListItem(id=2, values=["2", "Second Item", "pending"], data={"desc": "Second"}),
            ListItem(id=3, values=["3", "Third Item", "done"], data={"desc": "Third"}),
        ]
        self.query_one("#example-list", ListPanel).set_items(items)

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Update preview when item selected."""
        item = event.item
        preview = self.query_one("#example-preview", PreviewPanel)
        await preview.show_content(
            f"# {item.values[1]}\n\nStatus: {item.values[2]}\n\n{item.data.get('desc', '')}"
        )
```

**~35 lines** using existing components. The `ListPanel` provides:
- Vim-style navigation (j/k/g/G)
- Search with / key
- Lazy loading support
- Selection events
- Status bar

The `PreviewPanel` provides:
- Markdown rendering
- Edit mode with vim bindings
- Text selection mode
- State save/restore

### Future Vision: Declarative Browser Base Class

Once the `Browser` base class is implemented, this becomes even simpler:

```python
from emdx.ui.panels import Browser, ListPanel, PreviewPanel

class ExampleBrowser(Browser):
    title = "Example Browser"
    layout = "list-preview"

    async def load_items(self):
        return [{"id": 1, "name": "First", "status": "active"}]

    async def get_preview(self, item):
        return f"# {item['name']}\n\nStatus: {item['status']}"
```

**~15 lines.** This is the ultimate goal.

---

## 2. Using Existing Panels

### Currently Implemented Panels

#### ListPanel (emdx/ui/panels/list_panel.py)

Full-featured list display with:

```python
from emdx.ui.panels import ListPanel, ColumnDef, ListItem, ListPanelConfig

# Basic usage
list_panel = ListPanel(
    columns=[
        ColumnDef("ID", width=5),
        ColumnDef("Name", width=40),
        ColumnDef("Status", width=10),
    ],
    config=ListPanelConfig(
        show_search=True,
        search_placeholder="Search...",
        lazy_load_threshold=20,
        status_format="{filtered}/{total} items",
    ),
    show_status=True,
    id="my-list",
)

# Setting items
items = [
    ListItem(id=1, values=["1", "Document One", "Active"], data={"content": "..."}),
    ListItem(id=2, values=["2", "Document Two", "Draft"], data={"content": "..."}),
]
list_panel.set_items(items, has_more=True)  # has_more enables lazy loading

# Messages emitted
# ListPanel.ItemSelected(item, index) - When row highlighted
# ListPanel.ItemActivated(item, index) - When Enter pressed
# ListPanel.SearchSubmitted(query) - When search submitted
# ListPanel.LoadMoreRequested(current_index, total_count) - Near end of list
```

**Keybindings (built-in):**
- `j` / `k` - Move down/up
- `g` / `G` - Go to top/bottom
- `/` - Enter search mode
- `Enter` - Activate selected item
- `Escape` - Cancel search

#### PreviewPanel (emdx/ui/panels/preview_panel.py)

Multi-mode content preview:

```python
from emdx.ui.panels import PreviewPanel, PreviewPanelConfig

# Basic usage
preview = PreviewPanel(
    config=PreviewPanelConfig(
        enable_editing=True,
        enable_selection=True,
        markdown_rendering=True,
        empty_message="Select an item to preview",
        truncate_preview=50000,
    ),
    id="my-preview",
)

# Show content (viewing mode)
await preview.show_content("# Title\n\nMarkdown content here...", title="My Doc")

# Enter edit mode
title_input, vim_editor = await preview.enter_edit_mode(
    title="Document Title",
    content="Content to edit...",
    is_new=False,
)

# Enter selection mode (for copying text)
selection_area = await preview.enter_selection_mode()

# Messages emitted
# PreviewPanel.ContentChanged(title, content) - When content saved
# PreviewPanel.EditRequested() - When edit keybinding pressed
# PreviewPanel.SelectionCopied(text) - When text copied
# PreviewPanel.ModeChanged(old_mode, new_mode) - When mode changes
```

**Modes:**
- `PreviewMode.VIEWING` - Display content with markdown rendering
- `PreviewMode.EDITING` - Vim-style editing with title input
- `PreviewMode.SELECTING` - Text selection for copying
- `PreviewMode.EMPTY` - No content to show

### Message-Based Communication

Panels communicate via Textual messages. Handle them in your browser:

```python
class MyBrowser(Widget):
    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected):
        """Update preview when item selected."""
        preview = self.query_one("#preview", PreviewPanel)
        await preview.show_content(event.item.data.get("content", ""))

    async def on_list_panel_load_more_requested(self, event: ListPanel.LoadMoreRequested):
        """Load more items for infinite scroll."""
        more_items = await self._load_items(offset=event.total_count)
        list_panel = self.query_one("#list", ListPanel)
        list_panel.append_items(more_items, has_more=len(more_items) == 50)

    async def on_preview_panel_content_changed(self, event: PreviewPanel.ContentChanged):
        """Handle saved content."""
        await self._save_document(event.title, event.content)
```

### State Save/Restore

Both panels support state persistence:

```python
# Save state
state = {
    "list": list_panel.save_state(),
    "preview": preview_panel.save_state(),
}

# Restore state
list_panel.restore_state(state["list"])
preview_panel.restore_state(state["preview"])
```

---

## 3. The Browser Base Class (Proposed)

The `Browser` base class (to be implemented) will compose panels into a complete UI:

```python
# emdx/ui/panels/browser.py
"""Base browser class that composes panels into a complete UI."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from .list_panel import ListPanel, ColumnDef, ListItem
from .preview_panel import PreviewPanel
from .status_panel import StatusPanel
from .layouts import LAYOUTS


class Browser(Widget):
    """Base class for all browsers with panel composition."""

    # Override in subclasses
    title: str = "Browser"
    panels: Dict[str, Panel] = {}
    layout: str = "list-preview"

    # Standard vim-style bindings (inherited by all browsers)
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("enter", "select", "Select"),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "show_help", "Help"),
        Binding("/", "search", "Search"),
    ]

    def __init__(self):
        super().__init__()
        self._items: List[Dict[str, Any]] = []
        self._selected_index: int = 0
        self._search_query: str = ""

    def compose(self) -> ComposeResult:
        """Compose panels according to layout."""
        layout_cls = LAYOUTS.get(self.layout)
        if layout_cls:
            yield layout_cls(self.panels)
        else:
            # Default: horizontal split
            with Horizontal():
                if "list" in self.panels:
                    yield self.panels["list"]
                if "preview" in self.panels:
                    yield self.panels["preview"]
            if "status" in self.panels:
                yield self.panels["status"]

    async def on_mount(self) -> None:
        """Load items and setup on mount."""
        await self.refresh_items()
        # Focus the list panel
        if "list" in self.panels:
            self.panels["list"].focus()

    async def refresh_items(self) -> None:
        """Refresh items from data source."""
        self._items = await self.load_items()
        if "list" in self.panels:
            self.panels["list"].set_items(self._items)
        self._update_status()

    async def load_items(self) -> List[Dict[str, Any]]:
        """Override to load items. Must return list of dicts."""
        return []

    async def get_preview(self, item: Dict[str, Any]) -> str:
        """Override to return preview content for an item."""
        return str(item)

    async def on_item_selected(self, index: int) -> None:
        """Called when selection changes. Updates preview."""
        self._selected_index = index
        if 0 <= index < len(self._items):
            item = self._items[index]
            content = await self.get_preview(item)
            if "preview" in self.panels:
                self.panels["preview"].set_content(content)

    def _update_status(self) -> None:
        """Update status bar."""
        if "status" in self.panels:
            count = len(self._items)
            msg = f"{count} items | j/k nav | Enter select | ? help"
            self.panels["status"].set_text(msg)

    # Standard actions (can be overridden)
    def action_cursor_down(self) -> None:
        if "list" in self.panels:
            self.panels["list"].cursor_down()

    def action_cursor_up(self) -> None:
        if "list" in self.panels:
            self.panels["list"].cursor_up()

    # ... other standard actions
```

### Cognitive Load Analysis

| Aspect | Current Approach | Proposed Approach |
|--------|-----------------|-------------------|
| Lines of code | 300-700+ | 30-50 |
| Concepts to learn | Textual widgets, CSS, layouts, events, bindings | 3 panel types, 1 base class |
| Boilerplate | ~200 lines | 0 lines |
| Time to first browser | 1-2 hours | 5 minutes |
| Customization | Edit source | Override methods or config |

---

## 4. Documentation Template

### Browser Creation Guide

Every browser guide should follow this structure:

#### Quick Start (5 min read)

```markdown
# Creating a Browser

## 1. Minimal Example

\```python
from emdx.ui.panels import Browser, ListPanel, PreviewPanel

class MyBrowser(Browser):
    title = "My Browser"
    panels = {
        "list": ListPanel(columns=["ID", "Name"]),
        "preview": PreviewPanel(),
    }

    async def load_items(self):
        return [{"id": 1, "name": "Example"}]
\```

## 2. Register with BrowserContainer

\```python
# In emdx/ui/browser_container.py
BROWSER_REGISTRY = {
    "my": ("MyBrowser", "emdx.ui.browsers.my_browser"),
    # ...
}
\```

## 3. Test It

\```bash
emdx gui  # Press 'm' to switch to your browser
\```
```

#### Panel Types Reference

```markdown
# Panel Types

## ListPanel

Shows a table of items with selection.

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `columns` | `list[str]` | `["ID"]` | Column headers |
| `column_widths` | `list[int]` | `[10]` | Column widths |
| `show_header` | `bool` | `True` | Show column headers |
| `cursor_type` | `str` | `"row"` | Cursor type |

### Example

\```python
ListPanel(
    columns=["ID", "Title", "Status", "Date"],
    column_widths=[6, 40, 10, 12],
    show_header=True,
)
\```

### Methods

- `set_items(items: list[dict])` - Set the items to display
- `get_selected()` - Get the currently selected item
- `cursor_down()` / `cursor_up()` - Move cursor
- `scroll_to(index: int)` - Scroll to specific row

## PreviewPanel

Shows content preview with markdown rendering.

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `render_markdown` | `bool` | `True` | Render as markdown |
| `wrap` | `bool` | `True` | Wrap long lines |
| `syntax_highlight` | `bool` | `True` | Highlight code blocks |

### Example

\```python
PreviewPanel(
    render_markdown=True,
    wrap=True,
)
\```

### Methods

- `set_content(content: str)` - Set the preview content
- `clear()` - Clear the preview

## DetailPanel

Shows structured metadata with labels.

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `fields` | `list[str]` | `[]` | Field names to show |
| `show_empty` | `bool` | `False` | Show empty fields |

### Example

\```python
DetailPanel(
    fields=["id", "status", "created_at", "tags"],
)
\```

## StatusPanel

Shows a status bar at the bottom.

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_keybindings` | `bool` | `True` | Show key hints |

## InputPanel

Shows a search/command input.

### Configuration

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `placeholder` | `str` | `"Search..."` | Placeholder text |
| `hidden` | `bool` | `True` | Start hidden |
```

#### Customization Guide

```markdown
# Customizing Panels

## Custom Keybindings

\```python
class MyBrowser(Browser):
    BINDINGS = Browser.BINDINGS + [
        Binding("x", "custom_action", "Custom"),
        Binding("d", "delete_item", "Delete"),
    ]

    def action_custom_action(self):
        item = self.get_selected_item()
        # Do something with item
\```

## Custom Layouts

\```python
class MyBrowser(Browser):
    layout = "custom"

    def compose(self) -> ComposeResult:
        # Full control over layout
        with Vertical():
            with Horizontal():
                yield self.panels["sidebar"]
                yield self.panels["main"]
            yield self.panels["status"]
\```

## Custom Rendering

\```python
class MyBrowser(Browser):
    panels = {
        "list": ListPanel(
            columns=["Status", "Name"],
            render_cell=lambda col, val: f"[green]{val}[/]" if col == "Status" else val
        ),
    }
\```
```

---

## 5. Code Generation / Scaffolding

### The `emdx scaffold browser` Command

```bash
# Generate a new browser with interactive prompts
emdx scaffold browser my-feature

# Generate with options
emdx scaffold browser my-feature --layout list-detail-preview --data-source db

# Generate minimal browser
emdx scaffold browser my-feature --minimal
```

### What It Generates

```
emdx/ui/browsers/my_feature_browser.py    # Main browser class
tests/ui/test_my_feature_browser.py       # Test file
docs/browsers/my-feature.md               # Documentation
```

### Generated Browser File

```python
# emdx/ui/browsers/my_feature_browser.py
"""My Feature Browser - Browse and manage my features.

Generated by: emdx scaffold browser my-feature
"""

from typing import Any, Dict, List

from emdx.ui.panels import (
    Browser,
    ListPanel,
    PreviewPanel,
    DetailPanel,
    StatusPanel,
)


class MyFeatureBrowser(Browser):
    """Browser for viewing and managing features.

    Keybindings:
        j/k     - Navigate up/down
        Enter   - Select item
        /       - Search
        r       - Refresh
        ?       - Show help
    """

    title = "My Feature Browser"

    panels = {
        "list": ListPanel(
            columns=["ID", "Name", "Status"],
            column_widths=[6, 40, 10],
        ),
        "detail": DetailPanel(
            fields=["id", "name", "status", "created_at"],
        ),
        "preview": PreviewPanel(),
        "status": StatusPanel(),
    }

    layout = "list-detail-preview"

    async def load_items(self) -> List[Dict[str, Any]]:
        """Load items from data source.

        TODO: Replace with actual data loading logic.
        """
        # Example: Load from database
        # from emdx.models.my_feature import list_features
        # return list_features()

        return [
            {"id": 1, "name": "Example Feature", "status": "active"},
        ]

    async def get_preview(self, item: Dict[str, Any]) -> str:
        """Generate preview content for selected item.

        TODO: Customize preview rendering.
        """
        return f"""# {item.get('name', 'Untitled')}

**Status:** {item.get('status', 'unknown')}

## Description

Add your preview content here.
"""

    async def get_detail(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Get detail panel data for selected item.

        TODO: Add any computed fields.
        """
        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "created_at": item.get("created_at", "N/A"),
        }

    # Add custom actions below
    # def action_my_custom_action(self):
    #     """Handle custom keybinding."""
    #     pass
```

### Generated Test File

```python
# tests/ui/test_my_feature_browser.py
"""Tests for My Feature Browser."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from emdx.ui.browsers.my_feature_browser import MyFeatureBrowser
from emdx.ui.testing import BrowserTestHarness


class TestMyFeatureBrowser:
    """Test suite for MyFeatureBrowser."""

    @pytest.fixture
    def browser(self):
        """Create browser instance for testing."""
        return MyFeatureBrowser()

    @pytest.fixture
    def harness(self, browser):
        """Create test harness with mocked panels."""
        return BrowserTestHarness(browser)

    @pytest.mark.asyncio
    async def test_load_items(self, browser):
        """Test that items load correctly."""
        items = await browser.load_items()
        assert isinstance(items, list)
        assert len(items) > 0
        assert "id" in items[0]

    @pytest.mark.asyncio
    async def test_get_preview(self, browser):
        """Test preview generation."""
        item = {"id": 1, "name": "Test", "status": "active"}
        preview = await browser.get_preview(item)
        assert isinstance(preview, str)
        assert "Test" in preview

    @pytest.mark.asyncio
    async def test_navigation(self, harness):
        """Test j/k navigation."""
        await harness.mount()

        # Press j to move down
        await harness.press("j")
        assert harness.browser._selected_index == 1

        # Press k to move up
        await harness.press("k")
        assert harness.browser._selected_index == 0

    @pytest.mark.asyncio
    async def test_refresh(self, harness):
        """Test refresh action."""
        await harness.mount()

        with patch.object(harness.browser, 'load_items', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = [{"id": 2, "name": "New"}]
            await harness.press("r")
            mock_load.assert_called_once()
```

### Scaffold CLI Implementation

```python
# emdx/commands/scaffold.py
"""Code generation commands."""

import os
from pathlib import Path
from typing import Optional

import typer

from emdx.utils.templates import render_template

app = typer.Typer()


@app.command()
def browser(
    name: str = typer.Argument(..., help="Browser name (kebab-case)"),
    layout: str = typer.Option(
        "list-preview",
        "--layout", "-l",
        help="Layout type: list-only, list-preview, list-detail-preview"
    ),
    data_source: str = typer.Option(
        "custom",
        "--data-source", "-d",
        help="Data source: custom, db, api"
    ),
    minimal: bool = typer.Option(
        False,
        "--minimal", "-m",
        help="Generate minimal browser without boilerplate"
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory (default: emdx/ui/browsers/)"
    ),
):
    """Generate a new browser with panel system.

    Example:
        emdx scaffold browser my-feature
        emdx scaffold browser task-list --layout list-detail-preview
    """
    # Convert name to formats
    class_name = "".join(word.capitalize() for word in name.split("-")) + "Browser"
    file_name = name.replace("-", "_") + "_browser.py"

    # Default output directory
    if output_dir is None:
        output_dir = Path("emdx/ui/browsers")

    # Ensure directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    test_dir = Path("tests/ui")
    test_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = Path("docs/browsers")
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Render templates
    context = {
        "name": name,
        "class_name": class_name,
        "file_name": file_name,
        "layout": layout,
        "data_source": data_source,
        "minimal": minimal,
    }

    # Generate browser file
    browser_content = render_template("browser.py.jinja2", context)
    browser_path = output_dir / file_name
    browser_path.write_text(browser_content)
    typer.echo(f"Created: {browser_path}")

    # Generate test file
    test_content = render_template("browser_test.py.jinja2", context)
    test_path = test_dir / f"test_{file_name}"
    test_path.write_text(test_content)
    typer.echo(f"Created: {test_path}")

    # Generate documentation
    if not minimal:
        doc_content = render_template("browser_doc.md.jinja2", context)
        doc_path = docs_dir / f"{name}.md"
        doc_path.write_text(doc_content)
        typer.echo(f"Created: {doc_path}")

    typer.echo(f"\n✨ Browser '{name}' created successfully!")
    typer.echo(f"\nNext steps:")
    typer.echo(f"  1. Edit {browser_path} to customize load_items() and get_preview()")
    typer.echo(f"  2. Register in emdx/ui/browser_container.py")
    typer.echo(f"  3. Run tests: pytest {test_path}")
```

---

## 6. Type Checking Support

### Goal: Full IDE autocomplete and type errors

### Panel Configuration Types

```python
# emdx/ui/panels/types.py
"""Type definitions for panel configuration."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional, TypedDict, Union


# Column configuration for ListPanel
class ColumnConfig(TypedDict, total=False):
    """Configuration for a table column."""
    name: str
    width: int
    align: Literal["left", "center", "right"]
    render: Callable[[Any], str]


# Layout types
LayoutType = Literal[
    "list-only",
    "list-preview",
    "list-detail",
    "list-detail-preview",
    "custom",
]


@dataclass
class ListPanelConfig:
    """Configuration for ListPanel with full type hints."""

    columns: List[str] = field(default_factory=lambda: ["ID"])
    column_widths: List[int] = field(default_factory=lambda: [10])
    column_config: Optional[Dict[str, ColumnConfig]] = None
    show_header: bool = True
    cursor_type: Literal["row", "cell", "none"] = "row"
    zebra_stripes: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if len(self.columns) != len(self.column_widths):
            raise ValueError(
                f"columns ({len(self.columns)}) and column_widths "
                f"({len(self.column_widths)}) must have same length"
            )


@dataclass
class PreviewPanelConfig:
    """Configuration for PreviewPanel."""

    render_markdown: bool = True
    wrap: bool = True
    syntax_highlight: bool = True
    max_height: Optional[int] = None


@dataclass
class DetailPanelConfig:
    """Configuration for DetailPanel."""

    fields: List[str] = field(default_factory=list)
    field_labels: Optional[Dict[str, str]] = None
    show_empty: bool = False
    compact: bool = False


@dataclass
class StatusPanelConfig:
    """Configuration for StatusPanel."""

    show_keybindings: bool = True
    template: str = "{count} items | {keybindings}"


# Panel instance type
PanelConfig = Union[
    ListPanelConfig,
    PreviewPanelConfig,
    DetailPanelConfig,
    StatusPanelConfig,
]
```

### Typed Panel Classes

```python
# emdx/ui/panels/list_panel.py
"""ListPanel with full type hints."""

from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from textual.widgets import DataTable

from .types import ColumnConfig, ListPanelConfig

T = TypeVar("T", bound=Dict[str, Any])


class ListPanel(DataTable, Generic[T]):
    """Table panel for displaying list of items.

    Type Parameters:
        T: The type of items in the list (default: Dict[str, Any])

    Example:
        ```python
        # Basic usage
        panel = ListPanel(columns=["ID", "Name"])

        # With type hints
        panel: ListPanel[TaskItem] = ListPanel(
            columns=["ID", "Title", "Status"],
            column_widths=[6, 40, 10],
        )
        ```
    """

    def __init__(
        self,
        columns: List[str] = None,
        column_widths: List[int] = None,
        column_config: Optional[Dict[str, ColumnConfig]] = None,
        show_header: bool = True,
        cursor_type: str = "row",
        **kwargs,
    ):
        super().__init__(**kwargs)

        # Store config
        self._config = ListPanelConfig(
            columns=columns or ["ID"],
            column_widths=column_widths or [10],
            column_config=column_config,
            show_header=show_header,
            cursor_type=cursor_type,
        )

        self._items: List[T] = []
        self._render_cell: Optional[Callable[[str, Any, T], str]] = None

    def set_items(self, items: List[T]) -> None:
        """Set items to display in the table.

        Args:
            items: List of item dictionaries. Each dict should have
                   keys matching the column names.
        """
        self._items = items
        self._refresh_table()

    def get_selected(self) -> Optional[T]:
        """Get the currently selected item.

        Returns:
            The selected item dict, or None if no selection.
        """
        if self.cursor_row is None or self.cursor_row >= len(self._items):
            return None
        return self._items[self.cursor_row]

    def get_selected_index(self) -> int:
        """Get the index of the selected item."""
        return self.cursor_row or 0

    def set_cell_renderer(
        self,
        renderer: Callable[[str, Any, T], str]
    ) -> None:
        """Set custom cell renderer.

        Args:
            renderer: Function(column_name, cell_value, row_item) -> str
        """
        self._render_cell = renderer
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh table with current items."""
        self.clear(columns=True)

        # Add columns
        for col, width in zip(self._config.columns, self._config.column_widths):
            self.add_column(col, width=width)

        # Add rows
        for item in self._items:
            row = []
            for col in self._config.columns:
                # Get lowercase version for dict access
                key = col.lower().replace(" ", "_")
                value = item.get(key, item.get(col, ""))

                # Apply custom renderer if set
                if self._render_cell:
                    value = self._render_cell(col, value, item)

                row.append(str(value))

            self.add_row(*row)
```

### IDE Integration

With proper type hints, IDEs provide:

```python
# In your browser file - IDE shows autocomplete and type errors

class MyBrowser(Browser):
    panels = {
        "list": ListPanel(
            columns=["ID", "Name"],
            column_widths=[6, 40],
            cursor_type="row",  # IDE shows: "row" | "cell" | "none"
        ),
        "preview": PreviewPanel(
            render_markdown=True,
            # IDE error: 'wraps' is not a valid option (typo for 'wrap')
            wraps=True,  # <-- Red squiggle!
        ),
    }

    async def load_items(self) -> list[dict]:  # IDE knows return type
        return [{"id": 1}]

    async def get_preview(self, item: dict) -> str:
        # IDE shows item has 'id' key from load_items
        return f"ID: {item['id']}"
```

### Type Stubs for Complex Scenarios

```python
# emdx/ui/panels/__init__.pyi
"""Type stubs for panel module."""

from typing import Any, Callable, Dict, List, Literal, Optional, overload

class ListPanel:
    @overload
    def __init__(
        self,
        columns: List[str],
        column_widths: List[int],
        *,
        show_header: bool = True,
        cursor_type: Literal["row", "cell", "none"] = "row",
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        column_config: Dict[str, Any],
        show_header: bool = True,
    ) -> None: ...

    def set_items(self, items: List[Dict[str, Any]]) -> None: ...
    def get_selected(self) -> Optional[Dict[str, Any]]: ...
    def cursor_down(self) -> None: ...
    def cursor_up(self) -> None: ...


class PreviewPanel:
    def __init__(
        self,
        *,
        render_markdown: bool = True,
        wrap: bool = True,
        syntax_highlight: bool = True,
    ) -> None: ...

    def set_content(self, content: str) -> None: ...
    def clear(self) -> None: ...


class Browser:
    title: str
    panels: Dict[str, Any]
    layout: Literal["list-only", "list-preview", "list-detail-preview"]

    async def load_items(self) -> List[Dict[str, Any]]: ...
    async def get_preview(self, item: Dict[str, Any]) -> str: ...
    async def get_detail(self, item: Dict[str, Any]) -> Dict[str, Any]: ...
```

---

## 7. Debugging Support

### Panel Communication Logging

```python
# emdx/ui/panels/debug.py
"""Debugging utilities for panel system."""

import logging
from functools import wraps
from typing import Any, Callable

# Dedicated logger for panel events
panel_logger = logging.getLogger("emdx.panels")


def log_panel_event(func: Callable) -> Callable:
    """Decorator to log panel method calls."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        panel_name = getattr(self, 'id', self.__class__.__name__)
        panel_logger.debug(
            f"[{panel_name}] {func.__name__}("
            f"args={args[:3]}..., kwargs={list(kwargs.keys())})"
        )
        try:
            result = func(self, *args, **kwargs)
            panel_logger.debug(f"[{panel_name}] {func.__name__} -> OK")
            return result
        except Exception as e:
            panel_logger.error(f"[{panel_name}] {func.__name__} -> ERROR: {e}")
            raise
    return wrapper


class PanelDebugMixin:
    """Mixin to add debugging to any panel."""

    def __init__(self, *args, debug: bool = False, **kwargs):
        self._debug = debug
        super().__init__(*args, **kwargs)

    def _log(self, msg: str, level: str = "debug") -> None:
        """Log a debug message."""
        if self._debug:
            getattr(panel_logger, level)(f"[{self.id}] {msg}")

    def _log_state(self) -> None:
        """Log current panel state."""
        if self._debug:
            state = self._get_debug_state()
            panel_logger.debug(f"[{self.id}] STATE: {state}")

    def _get_debug_state(self) -> dict:
        """Override to provide panel-specific state."""
        return {}
```

### Panel Lifecycle Logging

```python
# emdx/ui/panels/base.py
"""Base panel with lifecycle logging."""

import logging
from textual.widget import Widget

logger = logging.getLogger("emdx.panels.lifecycle")


class Panel(Widget):
    """Base class for all panels with lifecycle logging."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug(f"Panel created: {self.__class__.__name__} (id={self.id})")

    def on_mount(self) -> None:
        """Called when panel is mounted."""
        logger.debug(f"Panel mounted: {self.id}")
        logger.debug(f"  Region: {self.region}")
        logger.debug(f"  Size: {self.size}")

    def on_unmount(self) -> None:
        """Called when panel is unmounted."""
        logger.debug(f"Panel unmounted: {self.id}")

    def on_focus(self) -> None:
        """Called when panel receives focus."""
        logger.debug(f"Panel focused: {self.id}")

    def on_blur(self) -> None:
        """Called when panel loses focus."""
        logger.debug(f"Panel blurred: {self.id}")

    def on_resize(self, event) -> None:
        """Called when panel is resized."""
        logger.debug(f"Panel resized: {self.id} -> {event.size}")
```

### Dev Tools for Inspecting Panel State

```python
# emdx/ui/dev_tools.py
"""Developer tools for debugging panel-based browsers."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Tree


class PanelInspector(ModalScreen):
    """Modal for inspecting panel state at runtime.

    Press Ctrl+D to open in any browser.
    """

    CSS = """
    PanelInspector {
        align: center middle;
    }

    #inspector-dialog {
        width: 80%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="inspector-dialog"):
            yield Static("[bold]Panel Inspector[/bold] (Ctrl+D)", id="title")
            yield Tree("Panels", id="panel-tree")
            yield Static("", id="panel-details")

    def on_mount(self) -> None:
        """Build panel tree from app state."""
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        """Refresh the panel tree."""
        tree = self.query_one("#panel-tree", Tree)
        tree.clear()

        # Get current browser from app
        app = self.app
        if hasattr(app, 'browsers') and hasattr(app, 'current_browser'):
            browser = app.browsers.get(app.current_browser)
            if browser:
                self._add_browser_to_tree(tree.root, browser)

    def _add_browser_to_tree(self, parent, browser) -> None:
        """Add browser and its panels to tree."""
        browser_node = parent.add(f"[bold]{browser.__class__.__name__}[/bold]")

        # Add panels
        if hasattr(browser, 'panels'):
            for name, panel in browser.panels.items():
                self._add_panel_to_tree(browser_node, name, panel)

    def _add_panel_to_tree(self, parent, name: str, panel) -> None:
        """Add a panel node with its state."""
        state = self._get_panel_state(panel)
        state_str = ", ".join(f"{k}={v}" for k, v in state.items())

        node = parent.add(f"{name}: [dim]{panel.__class__.__name__}[/dim]")
        node.add_leaf(f"[dim]{state_str}[/dim]")

    def _get_panel_state(self, panel) -> dict:
        """Get relevant state from a panel."""
        state = {
            "focused": panel.has_focus if hasattr(panel, 'has_focus') else False,
            "size": str(panel.size) if hasattr(panel, 'size') else "?",
        }

        # ListPanel specific
        if hasattr(panel, '_items'):
            state["items"] = len(panel._items)
        if hasattr(panel, 'cursor_row'):
            state["cursor"] = panel.cursor_row

        return state

    def action_close(self) -> None:
        self.dismiss()

    def action_refresh(self) -> None:
        self._refresh_tree()


# Add to Browser base class
class BrowserDebugMixin:
    """Mixin to add debug tools to browsers."""

    BINDINGS = [
        ("ctrl+d", "show_inspector", "Inspector", False),
    ]

    def action_show_inspector(self) -> None:
        """Show the panel inspector."""
        self.app.push_screen(PanelInspector())
```

### Log Configuration

```python
# Example .env or config for debugging
EMDX_LOG_LEVEL=DEBUG
EMDX_LOG_PANELS=1  # Enable panel lifecycle logging
EMDX_LOG_EVENTS=1  # Enable event logging
```

```python
# emdx/utils/logging_config.py
"""Logging configuration for panel debugging."""

import logging
import os


def configure_panel_logging():
    """Configure logging for panel system debugging."""

    # Check environment
    log_panels = os.environ.get("EMDX_LOG_PANELS", "0") == "1"
    log_events = os.environ.get("EMDX_LOG_EVENTS", "0") == "1"

    # Panel lifecycle logger
    panel_logger = logging.getLogger("emdx.panels.lifecycle")
    panel_logger.setLevel(logging.DEBUG if log_panels else logging.WARNING)

    # Panel event logger
    event_logger = logging.getLogger("emdx.panels.events")
    event_logger.setLevel(logging.DEBUG if log_events else logging.WARNING)

    # Add handler if needed
    if log_panels or log_events:
        handler = logging.FileHandler(".emdx/debug/panels.log")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        ))
        panel_logger.addHandler(handler)
        event_logger.addHandler(handler)
```

---

## 8. Testing Utilities

### BrowserTestHarness

```python
# emdx/ui/testing/harness.py
"""Test harness for browser testing."""

from typing import Any, Dict, List, Optional, Type
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App


class BrowserTestHarness:
    """Test harness for testing browsers without full Textual runtime.

    Usage:
        ```python
        @pytest.fixture
        def harness():
            browser = MyBrowser()
            return BrowserTestHarness(browser)

        @pytest.mark.asyncio
        async def test_navigation(harness):
            await harness.mount()
            await harness.press("j")
            assert harness.get_selected_index() == 1
        ```
    """

    def __init__(self, browser):
        """Initialize harness with a browser instance."""
        self.browser = browser
        self._app: Optional[App] = None
        self._mounted = False

        # Mock panels if they have complex widget dependencies
        self._mock_panels()

    def _mock_panels(self) -> None:
        """Create mock panels for testing."""
        if hasattr(self.browser, 'panels'):
            for name, panel in self.browser.panels.items():
                # Wrap panel methods that need mocking
                if hasattr(panel, 'set_items'):
                    original = panel.set_items
                    panel.set_items = MagicMock(side_effect=original)

    async def mount(self, items: Optional[List[Dict]] = None) -> None:
        """Mount the browser and optionally set items.

        Args:
            items: Optional list of items to use instead of load_items()
        """
        if items is not None:
            self.browser.load_items = AsyncMock(return_value=items)

        # Call on_mount
        await self.browser.on_mount()
        self._mounted = True

    async def press(self, key: str) -> None:
        """Simulate a key press.

        Args:
            key: Key to press (e.g., "j", "k", "enter", "escape")
        """
        # Map key to action
        action_map = {
            "j": "cursor_down",
            "k": "cursor_up",
            "g": "cursor_top",
            "G": "cursor_bottom",
            "enter": "select",
            "r": "refresh",
            "/": "search",
            "?": "show_help",
        }

        action = action_map.get(key)
        if action:
            method = getattr(self.browser, f"action_{action}", None)
            if method:
                result = method()
                if hasattr(result, '__await__'):
                    await result

    async def type_text(self, text: str) -> None:
        """Simulate typing text.

        Args:
            text: Text to type
        """
        for char in text:
            await self.press(char)

    def get_selected_index(self) -> int:
        """Get the currently selected index."""
        return self.browser._selected_index

    def get_selected_item(self) -> Optional[Dict]:
        """Get the currently selected item."""
        idx = self.get_selected_index()
        items = self.browser._items
        if 0 <= idx < len(items):
            return items[idx]
        return None

    def get_items(self) -> List[Dict]:
        """Get all items in the browser."""
        return self.browser._items

    def get_preview_content(self) -> str:
        """Get the current preview content."""
        if "preview" in self.browser.panels:
            panel = self.browser.panels["preview"]
            if hasattr(panel, '_content'):
                return panel._content
        return ""

    def get_status_text(self) -> str:
        """Get the current status bar text."""
        if "status" in self.browser.panels:
            panel = self.browser.panels["status"]
            if hasattr(panel, '_text'):
                return panel._text
        return ""

    def assert_item_count(self, expected: int) -> None:
        """Assert the number of items."""
        actual = len(self.get_items())
        assert actual == expected, f"Expected {expected} items, got {actual}"

    def assert_selected(self, index: int) -> None:
        """Assert the selected index."""
        actual = self.get_selected_index()
        assert actual == index, f"Expected selection at {index}, got {actual}"

    def assert_preview_contains(self, text: str) -> None:
        """Assert the preview contains text."""
        content = self.get_preview_content()
        assert text in content, f"Expected '{text}' in preview, got: {content[:100]}"
```

### Mock Panel Implementations

```python
# emdx/ui/testing/mocks.py
"""Mock panel implementations for testing."""

from typing import Any, Dict, List, Optional


class MockListPanel:
    """Mock ListPanel for testing."""

    def __init__(self, columns: List[str] = None, **kwargs):
        self.columns = columns or ["ID"]
        self._items: List[Dict] = []
        self._cursor_row: int = 0
        self.id = "mock-list"

        # Track method calls
        self.set_items_calls: List[List[Dict]] = []
        self.focus_calls: int = 0

    def set_items(self, items: List[Dict]) -> None:
        self._items = items
        self.set_items_calls.append(items)

    def get_selected(self) -> Optional[Dict]:
        if 0 <= self._cursor_row < len(self._items):
            return self._items[self._cursor_row]
        return None

    @property
    def cursor_row(self) -> int:
        return self._cursor_row

    def cursor_down(self) -> None:
        if self._cursor_row < len(self._items) - 1:
            self._cursor_row += 1

    def cursor_up(self) -> None:
        if self._cursor_row > 0:
            self._cursor_row -= 1

    def focus(self) -> None:
        self.focus_calls += 1


class MockPreviewPanel:
    """Mock PreviewPanel for testing."""

    def __init__(self, **kwargs):
        self._content: str = ""
        self.id = "mock-preview"

        # Track method calls
        self.set_content_calls: List[str] = []
        self.clear_calls: int = 0

    def set_content(self, content: str) -> None:
        self._content = content
        self.set_content_calls.append(content)

    def clear(self) -> None:
        self._content = ""
        self.clear_calls += 1

    def get_content(self) -> str:
        return self._content


class MockStatusPanel:
    """Mock StatusPanel for testing."""

    def __init__(self, **kwargs):
        self._text: str = ""
        self.id = "mock-status"

        # Track method calls
        self.set_text_calls: List[str] = []

    def set_text(self, text: str) -> None:
        self._text = text
        self.set_text_calls.append(text)

    def get_text(self) -> str:
        return self._text
```

### Test Fixtures

```python
# emdx/ui/testing/fixtures.py
"""Pytest fixtures for browser testing."""

import pytest
from typing import Dict, List

from .harness import BrowserTestHarness
from .mocks import MockListPanel, MockPreviewPanel, MockStatusPanel


@pytest.fixture
def mock_panels() -> Dict:
    """Create a set of mock panels."""
    return {
        "list": MockListPanel(columns=["ID", "Name"]),
        "preview": MockPreviewPanel(),
        "status": MockStatusPanel(),
    }


@pytest.fixture
def sample_items() -> List[Dict]:
    """Create sample items for testing."""
    return [
        {"id": 1, "name": "First", "status": "active"},
        {"id": 2, "name": "Second", "status": "pending"},
        {"id": 3, "name": "Third", "status": "done"},
    ]


@pytest.fixture
def large_item_set() -> List[Dict]:
    """Create a large set of items for pagination testing."""
    return [
        {"id": i, "name": f"Item {i}", "status": "active"}
        for i in range(1, 101)
    ]


# Convenience decorator for async browser tests
def async_browser_test(func):
    """Decorator for async browser tests."""
    return pytest.mark.asyncio(func)
```

### Example Test File

```python
# tests/ui/test_example_browser.py
"""Complete test example for a browser."""

import pytest
from unittest.mock import AsyncMock, patch

from emdx.ui.browsers.example_browser import ExampleBrowser
from emdx.ui.testing import (
    BrowserTestHarness,
    MockListPanel,
    MockPreviewPanel,
    async_browser_test,
)


class TestExampleBrowser:
    """Test suite for ExampleBrowser."""

    @pytest.fixture
    def browser(self):
        """Create browser instance."""
        return ExampleBrowser()

    @pytest.fixture
    def harness(self, browser):
        """Create test harness."""
        return BrowserTestHarness(browser)

    @pytest.fixture
    def sample_items(self):
        """Sample items for testing."""
        return [
            {"id": 1, "name": "Alpha", "status": "active"},
            {"id": 2, "name": "Beta", "status": "pending"},
            {"id": 3, "name": "Gamma", "status": "done"},
        ]

    # =========================================
    # Data Loading Tests
    # =========================================

    @async_browser_test
    async def test_load_items_returns_list(self, browser):
        """Test that load_items returns a list."""
        items = await browser.load_items()
        assert isinstance(items, list)

    @async_browser_test
    async def test_load_items_has_required_fields(self, browser):
        """Test that items have required fields."""
        items = await browser.load_items()
        if items:
            item = items[0]
            assert "id" in item
            assert "name" in item

    @async_browser_test
    async def test_items_displayed_on_mount(self, harness, sample_items):
        """Test that items are displayed after mount."""
        await harness.mount(items=sample_items)
        harness.assert_item_count(3)

    # =========================================
    # Navigation Tests
    # =========================================

    @async_browser_test
    async def test_cursor_down(self, harness, sample_items):
        """Test j key moves cursor down."""
        await harness.mount(items=sample_items)

        harness.assert_selected(0)
        await harness.press("j")
        harness.assert_selected(1)

    @async_browser_test
    async def test_cursor_up(self, harness, sample_items):
        """Test k key moves cursor up."""
        await harness.mount(items=sample_items)

        await harness.press("j")  # Move to 1
        await harness.press("j")  # Move to 2
        await harness.press("k")  # Move to 1
        harness.assert_selected(1)

    @async_browser_test
    async def test_cursor_stays_in_bounds(self, harness, sample_items):
        """Test cursor doesn't go out of bounds."""
        await harness.mount(items=sample_items)

        # Try to go above first item
        await harness.press("k")
        await harness.press("k")
        harness.assert_selected(0)

        # Try to go below last item
        await harness.press("G")  # Go to bottom
        await harness.press("j")
        await harness.press("j")
        harness.assert_selected(2)  # Should stay at last item

    @async_browser_test
    async def test_go_to_top(self, harness, sample_items):
        """Test g key goes to top."""
        await harness.mount(items=sample_items)

        await harness.press("j")
        await harness.press("j")
        await harness.press("g")
        harness.assert_selected(0)

    @async_browser_test
    async def test_go_to_bottom(self, harness, sample_items):
        """Test G key goes to bottom."""
        await harness.mount(items=sample_items)

        await harness.press("G")
        harness.assert_selected(2)

    # =========================================
    # Preview Tests
    # =========================================

    @async_browser_test
    async def test_preview_updates_on_selection(self, harness, sample_items):
        """Test preview updates when selection changes."""
        await harness.mount(items=sample_items)

        # Check initial preview
        harness.assert_preview_contains("Alpha")

        # Move to second item
        await harness.press("j")
        harness.assert_preview_contains("Beta")

    @async_browser_test
    async def test_preview_content_format(self, browser):
        """Test preview content format."""
        item = {"id": 1, "name": "Test", "status": "active"}
        preview = await browser.get_preview(item)

        assert "Test" in preview
        assert "active" in preview

    # =========================================
    # Refresh Tests
    # =========================================

    @async_browser_test
    async def test_refresh_reloads_items(self, harness, sample_items):
        """Test r key refreshes items."""
        await harness.mount(items=sample_items)

        # Mock a new load
        new_items = [{"id": 10, "name": "New", "status": "new"}]
        harness.browser.load_items = AsyncMock(return_value=new_items)

        await harness.press("r")

        harness.assert_item_count(1)
        assert harness.get_items()[0]["name"] == "New"

    # =========================================
    # Edge Case Tests
    # =========================================

    @async_browser_test
    async def test_empty_item_list(self, harness):
        """Test browser handles empty item list."""
        await harness.mount(items=[])

        harness.assert_item_count(0)
        assert harness.get_selected_item() is None

    @async_browser_test
    async def test_single_item(self, harness):
        """Test browser with single item."""
        await harness.mount(items=[{"id": 1, "name": "Only"}])

        harness.assert_item_count(1)
        await harness.press("j")  # Should not crash
        harness.assert_selected(0)  # Should stay at 0
```

---

## Summary: The Lego Block Vision

### What's Already Implemented

The following components are **fully working** and can be used today:

| Component | Location | Status |
|-----------|----------|--------|
| `ListPanel` | `emdx/ui/panels/list_panel.py` | Complete |
| `PreviewPanel` | `emdx/ui/panels/preview_panel.py` | Complete |
| `PanelBase` | `emdx/ui/panels/base.py` | Complete |
| `PanelProtocol` | `emdx/ui/panels/protocol.py` | Complete |
| `ExampleBrowser` | `emdx/ui/browsers/example_browser.py` | Complete |
| `BrowserTestHarness` | `emdx/ui/testing/harness.py` | Complete |
| `MockListPanel` | `emdx/ui/testing/mocks.py` | Complete |
| `MockPreviewPanel` | `emdx/ui/testing/mocks.py` | Complete |

### What Still Needs Implementation

| Component | Description | Priority |
|-----------|-------------|----------|
| `Browser` base class | Declarative browser composition | High |
| `StatusPanel` | Standalone status bar widget | Medium |
| `DetailPanel` | Metadata display widget | Medium |
| `emdx scaffold browser` | Code generation command | Medium |
| Panel inspector dev tools | Runtime debugging | Low |

### Before vs After Comparison

**Before (Traditional Approach):**
```
Developer wants to build a browser
    ↓
Study 700+ lines of existing browser code
    ↓
Understand Textual widgets, CSS, layouts
    ↓
Copy-paste from existing browser
    ↓
Modify extensively
    ↓
Debug layout issues
    ↓
Add keybindings manually
    ↓
Write tests from scratch
    ↓
~2-4 hours to first working browser
```

**After (With Existing Panels):**
```
Developer wants to build a browser
    ↓
Import ListPanel and PreviewPanel
    ↓
Handle on_list_panel_item_selected
    ↓
~35 lines of code, 30 minutes
```

**Future (With Browser Base Class):**
```
Developer wants to build a browser
    ↓
Run: emdx scaffold browser my-feature
    ↓
Edit load_items() and get_preview()
    ↓
Run tests (already generated)
    ↓
~15 lines of code, 10 minutes
```

### Key DX Improvements Achieved

| Aspect | Before | With Panels | With Browser Base (Future) |
|--------|--------|-------------|---------------------------|
| Lines of code | 300-700+ | 35-50 | 15-30 |
| Learning curve | Hours | 30 min | 10 min |
| Documentation | Scattered | This document | + Scaffolding |
| Testing | Manual setup | Test harness | Generated tests |
| Vim navigation | Manual impl | Built-in | Built-in |
| Search | Manual impl | Built-in | Built-in |
| State persistence | Manual impl | Built-in | Built-in |

### Quick Start: Build a Browser Now

Using existing components, you can build a browser in ~35 lines:

```python
from textual.app import ComposeResult
from textual.widget import Widget
from emdx.ui.panels import ListPanel, PreviewPanel, ColumnDef, ListItem

class MyBrowser(Widget):
    DEFAULT_CSS = "MyBrowser { layout: horizontal; }"

    def compose(self) -> ComposeResult:
        yield ListPanel(
            columns=[ColumnDef("ID", 5), ColumnDef("Name", 40)],
            show_status=True,
            id="list",
        )
        yield PreviewPanel(id="preview")

    async def on_mount(self):
        items = [ListItem(id=1, values=["1", "Example"], data={"content": "# Hello"})]
        self.query_one("#list", ListPanel).set_items(items)

    async def on_list_panel_item_selected(self, event):
        await self.query_one("#preview", PreviewPanel).show_content(
            event.item.data.get("content", "")
        )
```

Run the tests: `poetry run pytest tests/ui/test_example_browser.py -v`

The goal is to make browser development feel less like building from scratch and more like configuring pre-built components - like Lego blocks that snap together.
