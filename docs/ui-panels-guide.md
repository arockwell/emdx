# UI Panels Guide

A comprehensive guide to building browser UIs with the panel-based component system.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Panel Types](#panel-types)
3. [Layout System](#layout-system)
4. [Communication Patterns](#communication-patterns)
5. [Testing Guide](#testing-guide)
6. [Migration Guide](#migration-guide)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

Build a complete browser in 30 seconds:

```python
from textual.app import ComposeResult
from textual.widget import Widget
from emdx.ui.panels import (
    ListPanel, PreviewPanel, ColumnDef, ListItem,
    ListPanelConfig, PreviewPanelConfig,
)

class MyBrowser(Widget):
    """A minimal browser with list and preview panels."""

    DEFAULT_CSS = """
    MyBrowser {
        layout: horizontal;
        height: 100%;
    }
    MyBrowser #my-list { width: 50%; }
    MyBrowser #my-preview { width: 50%; border-left: solid $primary; }
    """

    def compose(self) -> ComposeResult:
        yield ListPanel(
            columns=[ColumnDef("ID", 5), ColumnDef("Name", 40)],
            config=ListPanelConfig(show_search=True),
            id="my-list",
        )
        yield PreviewPanel(
            config=PreviewPanelConfig(empty_message="Select an item"),
            id="my-preview",
        )

    async def on_mount(self) -> None:
        items = [
            ListItem(id=1, values=["1", "First Item"], data={"content": "# Hello"}),
            ListItem(id=2, values=["2", "Second Item"], data={"content": "# World"}),
        ]
        self.query_one("#my-list", ListPanel).set_items(items)

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        content = event.item.data.get("content", "") if event.item.data else ""
        await self.query_one("#my-preview", PreviewPanel).show_content(content)
```

**What you get out of the box:**

- Vim-style navigation (j/k/g/G)
- Search with `/` key
- Markdown rendering in preview
- Selection change events
- State save/restore

---

## Panel Types

### ListPanel

A DataTable-based list panel with vim-style navigation and search.

**Import:**

```python
from emdx.ui.panels import ListPanel, ListItem, ColumnDef, ListPanelConfig
```

**Basic Usage:**

```python
yield ListPanel(
    columns=[
        ColumnDef("ID", width=5),
        ColumnDef("Name", width=40),
        ColumnDef("Status", width=10),
    ],
    config=ListPanelConfig(
        show_search=True,
        search_placeholder="Search...",
        status_format="{filtered}/{total} items",
    ),
    show_status=True,
    id="my-list",
)
```

**Configuration Options (ListPanelConfig):**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_header` | bool | True | Show column headers |
| `cursor_type` | str | "row" | Cursor style: "row", "cell", "column" |
| `zebra_stripes` | bool | False | Alternate row backgrounds |
| `cell_padding` | int | 0 | Padding between cells |
| `show_search` | bool | True | Enable `/` search |
| `search_placeholder` | str | "Search..." | Search input placeholder |
| `lazy_load_threshold` | int | 20 | Load more when N rows from end |
| `status_format` | str | "{filtered}/{total} items" | Status bar format |

**API Reference:**

```python
# Setting items
list_panel.set_items(items: List[ListItem], has_more: bool = False)
list_panel.append_items(items: List[ListItem], has_more: bool = False)
list_panel.clear_items()

# Selection
list_panel.get_selected_item() -> Optional[ListItem]
list_panel.get_selected_index() -> Optional[int]
list_panel.select_item_by_id(item_id: Any) -> bool
list_panel.select_index(index: int) -> bool

# Filtering
list_panel.set_filter(filter_func: Optional[Callable[[ListItem], bool]])
list_panel.set_search_filter(query: str)

# State
list_panel.save_state() -> Dict[str, Any]
list_panel.restore_state(state: Dict[str, Any])

# Focus
list_panel.focus_table()
```

**ListItem Structure:**

```python
@dataclass
class ListItem:
    id: Any                      # Unique identifier
    values: List[str]            # Cell values (must match column count)
    data: Optional[Any] = None   # Arbitrary data for this item
```

**Messages Emitted:**

| Message | When | Attributes |
|---------|------|------------|
| `ListPanel.ItemSelected` | Row highlighted | `item: ListItem`, `index: int` |
| `ListPanel.ItemActivated` | Enter pressed | `item: ListItem`, `index: int` |
| `ListPanel.SearchSubmitted` | Search submitted | `query: str` |
| `ListPanel.LoadMoreRequested` | Near end of list | `current_index`, `total_count` |

**Default Keybindings:**

| Key | Action |
|-----|--------|
| `j` | Move cursor down |
| `k` | Move cursor up |
| `g` | Go to first item |
| `G` | Go to last item |
| `/` | Enter search mode |
| `Enter` | Activate current item |
| `Escape` | Cancel search |

---

### PreviewPanel

A content preview panel with markdown rendering and mode switching.

**Import:**

```python
from emdx.ui.panels import PreviewPanel, PreviewMode, PreviewPanelConfig
```

**Basic Usage:**

```python
yield PreviewPanel(
    config=PreviewPanelConfig(
        enable_editing=True,
        enable_selection=True,
        markdown_rendering=True,
        empty_message="Select an item to preview",
    ),
    id="my-preview",
)
```

**Configuration Options (PreviewPanelConfig):**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_editing` | bool | True | Allow edit mode |
| `enable_selection` | bool | True | Allow text selection mode |
| `show_title_in_edit` | bool | True | Show title input when editing |
| `markdown_rendering` | bool | True | Render content as markdown |
| `empty_message` | str | "[dim]No content to display[/dim]" | Empty state message |
| `truncate_preview` | int | 50000 | Max chars before truncating (0 = no limit) |

**API Reference:**

```python
# Displaying content
await preview.show_content(content: str, title: str = "", render_markdown: bool = True)
await preview.show_empty(message: Optional[str] = None)

# Modes
await preview.enter_edit_mode(title: str = "", content: str = "", is_new: bool = False)
await preview.exit_edit_mode(save: bool = False)
await preview.enter_selection_mode(content: str = "")
await preview.exit_selection_mode()

# Getters
preview.get_content() -> str
preview.get_title() -> str

# State
preview.save_state() -> Dict[str, Any]
preview.restore_state(state: Dict[str, Any])
```

**Preview Modes (PreviewMode enum):**

- `VIEWING` - Displaying content (read-only)
- `EDITING` - Editing content with vim bindings
- `SELECTING` - Text selection mode for copying
- `EMPTY` - No content to show

**Messages Emitted:**

| Message | When | Attributes |
|---------|------|------------|
| `PreviewPanel.ContentChanged` | Content modified in edit mode | `title`, `content` |
| `PreviewPanel.EditRequested` | User requests edit mode | - |
| `PreviewPanel.SelectionCopied` | Text copied in selection mode | `text` |
| `PreviewPanel.ModeChanged` | Preview mode changes | `old_mode`, `new_mode` |

**Default Keybindings:**

| Key | Action |
|-----|--------|
| `e` | Enter edit mode |
| `s` | Enter selection mode |
| `Escape` | Exit current mode |

---

### StatusPanel

A configurable status bar with multiple sections.

**Import:**

```python
from emdx.ui.panels import StatusPanel, StatusSection, StatusAlign, StatusPanelConfig
```

**Basic Usage:**

```python
yield StatusPanel(
    sections=[
        StatusSection("mode", width=10, align=StatusAlign.LEFT),
        StatusSection("message", width="auto", align=StatusAlign.LEFT),
        StatusSection("hints", width=40, align=StatusAlign.RIGHT),
    ],
    config=StatusPanelConfig(
        show_mode=True,
        show_hints=True,
        temporary_timeout=3.0,
    ),
    id="status-bar",
)
```

**Configuration Options (StatusPanelConfig):**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `height` | int | 1 | Status bar height |
| `show_mode` | bool | True | Show mode indicator |
| `show_hints` | bool | True | Show key hints |
| `hint_separator` | str | " \| " | Separator between hints |
| `temporary_timeout` | float | 3.0 | Default timeout for temp messages |
| `background` | str | "$boost" | Background color/style |

**StatusSection Structure:**

```python
@dataclass
class StatusSection:
    key: str                              # Unique section identifier
    width: Union[int, str] = "auto"       # Width in chars or "auto"
    align: StatusAlign = StatusAlign.LEFT # Text alignment
    default: str = ""                     # Default content
    style: str = ""                       # Optional Rich style
```

**API Reference:**

```python
# Section updates
status.set_section(key: str, content: str)
status.get_section(key: str) -> str

# Convenience methods
status.set_message(message: str, temporary: bool = True, timeout: float = None, style: str = "")
status.set_mode(mode: str)
status.set_hints(hints: List[str])
status.set_hints_from_bindings(bindings: List[tuple], max_hints: int = 5)
status.show_error(message: str, timeout: float = None)
status.show_success(message: str, timeout: float = None)
status.clear()

# State
status.save_state() -> Dict[str, Any]
status.restore_state(state: Dict[str, Any])
```

**Simplified Status Bar:**

For simple use cases, use `SimpleStatusBar`:

```python
from emdx.ui.panels import SimpleStatusBar

yield SimpleStatusBar(id="status")

# Usage
status.set("Ready | j/k=nav | /=search | q=quit")
```

---

### InputPanel

A modal input panel for search, tags, and text prompts.

**Import:**

```python
from emdx.ui.panels import InputPanel, InputMode, InputPanelConfig, SearchInput, TagInput
```

**Basic Usage:**

```python
yield InputPanel(
    mode=InputMode.SEARCH,
    config=InputPanelConfig(
        show_label=True,
        show_hints=True,
        history_enabled=True,
    ),
    overlay=True,
    id="search-input",
)
```

**Configuration Options (InputPanelConfig):**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `show_label` | bool | True | Show input label |
| `show_hints` | bool | True | Show key hints |
| `clear_on_submit` | bool | True | Clear input after submit |
| `clear_on_cancel` | bool | True | Clear input when cancelled |
| `history_enabled` | bool | True | Enable input history |
| `max_history` | int | 50 | Maximum history entries |
| `validate_on_change` | bool | False | Validate as user types |

**Input Modes (InputMode enum):**

- `SEARCH` - Search/filter input
- `TAG` - Tag entry (space-separated)
- `PROMPT` - General text prompt
- `CONFIRM` - Yes/no confirmation

**API Reference:**

```python
# Show/hide
input.show(
    label: Optional[str] = None,
    placeholder: Optional[str] = None,
    initial_value: str = "",
    callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], None]] = None,
    validator: Optional[Callable[[str], Union[bool, str]]] = None,
    mode: Optional[InputMode] = None,
)
input.hide(clear: bool = True)

# Value access
input.get_value() -> str
input.set_value(value: str)

# Error handling
input.set_error(message: str)
input.clear_error()

# Mode customization
input.set_mode_config(mode: InputMode, label: str = None, placeholder: str = None, hints: str = None)

# State
input.save_state() -> Dict[str, Any]
input.restore_state(state: Dict[str, Any])
```

**Messages Emitted:**

| Message | When | Attributes |
|---------|------|------------|
| `InputPanel.InputSubmitted` | Input submitted | `value`, `mode` |
| `InputPanel.InputCancelled` | Input cancelled | `mode` |
| `InputPanel.InputChanged` | Value changes | `value`, `mode` |
| `InputPanel.ValidationFailed` | Validation fails | `value`, `error` |

**Convenience Classes:**

```python
# Pre-configured for search
yield SearchInput(id="search")

# Pre-configured for tags with get_tags() helper
yield TagInput(id="tags")
tags = tag_input.get_tags()  # Returns List[str]
```

---

## Layout System

The layout system provides config-driven layouts for complex browsers.

### Quick Layout Example

```python
from emdx.ui.layout import ComposableBrowser, create_layout, SplitSpec, PanelSpec, SizeSpec

class MyBrowser(ComposableBrowser):
    def get_default_layout(self):
        return create_layout(
            "my-browser",
            SplitSpec(
                direction="horizontal",
                sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
                children=[
                    PanelSpec("table", "doc-list"),
                    PanelSpec("richlog", "preview"),
                ],
            ),
        )

    def configure_panels(self):
        table = self.get_panel("doc-list")
        if table:
            table.cursor_type = "row"
        self.set_focus_order(["doc-list", "preview"])
```

### Size Specifications

```python
from emdx.ui.layout import SizeSpec

SizeSpec.fraction(1)      # "1fr" - 1 fractional unit
SizeSpec.fraction(2)      # "2fr" - 2 fractional units
SizeSpec.percent(40)      # "40%" - 40% of parent
SizeSpec.fixed(20)        # "20" - 20 characters/cells
SizeSpec.auto()           # "auto" - auto-size

# Parse from string
SizeSpec.from_string("1fr")
SizeSpec.from_string("40%")
SizeSpec.from_string("20px")
```

### Panel Specifications

```python
from emdx.ui.layout import PanelSpec

PanelSpec(
    panel_type="table",           # Registered panel type
    panel_id="my-table",          # Unique ID
    config={"cursor_type": "row"}, # Panel-specific config
    size=SizeSpec.percent(50),    # Size in parent
    collapsible=True,             # Can be toggled
    collapsed=False,              # Initial state
    min_size=SizeSpec.fixed(10),  # Minimum when visible
    classes=["custom-class"],     # CSS classes
)
```

### Split Specifications

```python
from emdx.ui.layout import SplitSpec

SplitSpec(
    direction="horizontal",  # or "vertical"
    children=[
        PanelSpec("table", "list"),
        SplitSpec(
            direction="vertical",
            children=[
                PanelSpec("richlog", "preview"),
                PanelSpec("static", "status"),
            ],
            sizes=[SizeSpec.fraction(1), SizeSpec.fixed(1)],
        ),
    ],
    sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
    split_id="main-split",
)
```

### YAML Layout Files

Create `~/.config/emdx/layouts/my-layout.yaml`:

```yaml
name: my-layout
description: My custom layout
version: "1.0"

root:
  type: split
  direction: horizontal
  sizes: ["40%", "60%"]
  children:
    - type: table
      id: doc-list
      config:
        cursor_type: row
        show_header: true

    - type: split
      direction: vertical
      sizes: ["1fr", "1"]
      children:
        - type: richlog
          id: preview
          config:
            wrap: true
            markup: true

        - type: static
          id: status
          size: "1"
```

Load in browser:

```python
class MyBrowser(ComposableBrowser):
    LAYOUT_NAME = "my-layout"  # Loads from YAML
```

### Panel Registry

Register custom panel types:

```python
from emdx.ui.layout import panel_registry

# Simple registration
panel_registry.register(
    "my-widget",
    MyWidgetClass,
    description="My custom widget",
    default_config={"option": "value"},
)

# With factory
def create_custom_panel(config):
    widget = MyWidget(**config)
    widget.setup_something()
    return widget

panel_registry.register(
    "custom-panel",
    MyWidget,
    factory=create_custom_panel,
)

# Decorator style
@panel_registry.decorator("decorated-panel", description="A panel")
class DecoratedPanel(Widget):
    pass
```

### ComposableBrowser API

```python
class MyBrowser(ComposableBrowser):
    LAYOUT_NAME = "my-layout"  # Optional: load from YAML

    def get_layout_name(self) -> Optional[str]:
        """Override LAYOUT_NAME dynamically."""
        return "my-layout"

    def get_default_layout(self) -> Optional[LayoutConfig]:
        """Define layout in code when no YAML exists."""
        return create_layout(...)

    def configure_panels(self) -> None:
        """Called after panels are mounted."""
        table = self.get_panel("doc-table")
        self.set_focus_order(["doc-table", "preview"])

    def on_panel_focus(self, panel_id: str) -> None:
        """Called when focus changes between panels."""
        pass

# Focus management
browser.set_focus_order(["panel-1", "panel-2", "panel-3"])
browser.focus_panel("panel-id")
browser.focus_next()  # Tab
browser.focus_previous()  # Shift+Tab
browser.get_focused_panel() -> Optional[str]

# Visibility management
await browser.toggle_panel("panel-id")
browser.collapse_panel("panel-id")
browser.expand_panel("panel-id")
browser.is_panel_visible("panel-id") -> bool

# Layout access
browser.get_panel("panel-id") -> Optional[Widget]
browser.get_panels() -> Dict[str, Widget]
browser.get_layout_config() -> Optional[LayoutConfig]
await browser.reload_layout()
```

---

## Communication Patterns

### Message-Based Communication

Panels communicate through Textual messages, keeping them decoupled:

```python
class MyBrowser(Widget):
    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        """Handle selection change from ListPanel."""
        item = event.item
        preview = self.query_one("#preview", PreviewPanel)
        await preview.show_content(item.data.get("content", ""))

    async def on_list_panel_item_activated(self, event: ListPanel.ItemActivated) -> None:
        """Handle Enter key from ListPanel."""
        self.notify(f"Activated: {event.item.values[1]}")

    async def on_preview_panel_content_changed(self, event: PreviewPanel.ContentChanged) -> None:
        """Handle edit completion from PreviewPanel."""
        # Save the edited content
        await self.save_document(event.title, event.content)
```

### Protocol-Based Capabilities

Check panel capabilities before performing operations:

```python
from emdx.ui.panels import has_capability, PanelCapability

if has_capability(panel, PanelCapability.SEARCHABLE):
    panel.action_search()

if has_capability(panel, PanelCapability.REFRESHABLE):
    await panel.refresh()

# Common capability combinations
PanelCapability.LIST_PANEL  # NAVIGABLE | SELECTABLE | SCROLLABLE | FOCUSABLE
PanelCapability.PREVIEW_PANEL  # SCROLLABLE | TEXT_SELECTABLE | PREVIEWABLE | FOCUSABLE
PanelCapability.INPUT_PANEL  # FOCUSABLE | EDITABLE
```

### Base Panel Class

Create custom panels by extending `PanelBase`:

```python
from emdx.ui.panels import PanelBase, PanelCapability, KeyBinding

class MyCustomPanel(PanelBase):
    PANEL_ID = "my-custom-panel"
    CAPABILITIES = PanelCapability.NAVIGABLE | PanelCapability.FOCUSABLE
    HELP_TITLE = "My Custom Panel"

    KEYBINDINGS = [
        KeyBinding("j", "cursor_down", "Move down", category="Navigation"),
        KeyBinding("k", "cursor_up", "Move up", category="Navigation"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("My content")

    async def on_activate(self) -> None:
        """Called when panel becomes active."""
        await super().on_activate()
        # Start background tasks

    async def on_deactivate(self) -> None:
        """Called when panel loses active status."""
        await super().on_deactivate()
        # Pause background tasks

    def save_state(self) -> PanelState:
        """Save panel state."""
        state = super().save_state()
        state.extra["my_data"] = self._my_data
        return state

    def restore_state(self, state: PanelState) -> None:
        """Restore panel state."""
        super().restore_state(state)
        self._my_data = state.extra.get("my_data")
```

### Standard Panel Messages

```python
from emdx.ui.panels import (
    # Lifecycle
    PanelActivated,
    PanelDeactivated,
    PanelFocused,
    PanelBlurred,
    # Selection
    SelectionChanged,
    SelectionData,
    # Navigation
    NavigationRequested,
    NavigationDirection,
    # Content
    ContentRequested,
    ContentProvided,
    # Actions
    ActionRequested,
    ActionCompleted,
    # Errors
    ErrorOccurred,
    ErrorSeverity,
    # Status
    StatusUpdate,
)

# Filter messages for debugging/testing
from emdx.ui.panels import filter_messages_by_type, filter_messages_from_panel

selection_msgs = filter_messages_by_type(messages, SelectionChanged)
list_msgs = filter_messages_from_panel(messages, "my-list")
```

---

## Testing Guide

### Test Harness

```python
import pytest
from emdx.ui.testing import BrowserTestHarness
from myapp.browsers import MyBrowser

@pytest.fixture
def harness():
    browser = MyBrowser()
    return BrowserTestHarness(browser)

@pytest.mark.asyncio
async def test_navigation(harness):
    """Test vim-style navigation."""
    await harness.mount()
    items = [
        {"id": 1, "values": ["1", "First"]},
        {"id": 2, "values": ["2", "Second"]},
        {"id": 3, "values": ["3", "Third"]},
    ]
    harness._items = items

    # Navigate down
    await harness.press("j")
    harness.assert_selected(1)

    # Navigate up
    await harness.press("k")
    harness.assert_selected(0)

    # Jump to bottom
    await harness.press("G")
    harness.assert_selected(2)

    # Jump to top
    await harness.press("g")
    harness.assert_selected(0)

@pytest.mark.asyncio
async def test_selection_updates_preview(harness):
    """Test that selection updates preview panel."""
    await harness.mount()
    items = [
        {"id": 1, "values": ["1", "Test"], "data": {"content": "# Hello"}},
    ]
    harness._items = items

    await harness.press("j")
    harness.assert_preview_contains("Hello")

@pytest.mark.asyncio
async def test_search(harness):
    """Test search functionality."""
    await harness.mount()

    # Enter search mode
    await harness.press("/")

    # Type search query
    await harness.type_text("test")
    await harness.press("enter")

    # Verify search message
    harness.assert_message_posted(ListPanel.SearchSubmitted)
```

### Harness API Reference

```python
# Mounting
await harness.mount(items: Optional[List[Dict]] = None)

# Key simulation
await harness.press(key: str)  # "j", "k", "enter", "escape", etc.
await harness.type_text(text: str)

# State access
harness.get_selected_index() -> int
harness.get_selected_item() -> Optional[Dict]
harness.get_items() -> List[Dict]
harness.get_preview_content() -> str
harness.get_status_text() -> str

# Message access
harness.get_messages(message_type: Optional[type] = None) -> List[Any]
harness.clear_messages()

# Assertions
harness.assert_item_count(expected: int)
harness.assert_selected(index: int)
harness.assert_preview_contains(text: str)
harness.assert_status_contains(text: str)
harness.assert_message_posted(message_type: type)
harness.assert_no_message(message_type: type)
```

### Mock Panels

For unit testing without Textual:

```python
from emdx.ui.testing import MockListPanel, MockPreviewPanel, MockStatusPanel

def test_list_operations():
    mock = MockListPanel(columns=["ID", "Name"])

    # Set items
    mock.set_items([{"id": 1, "name": "Test"}])
    assert mock.get_selected()["id"] == 1
    assert len(mock.set_items_calls) == 1

    # Navigation
    mock.cursor_down()
    assert mock.cursor_row == 0  # No more items

def test_preview_operations():
    mock = MockPreviewPanel()

    # Show content
    await mock.show_content("# Hello World")
    assert mock.get_content() == "# Hello World"
    assert mock.mode == "VIEWING"
    assert len(mock.show_content_calls) == 1

def test_status_operations():
    mock = MockStatusPanel()

    mock.set_text("5 items loaded")
    assert mock.get_text() == "5 items loaded"
    assert len(mock.set_text_calls) == 1
```

### Interactive Testing

Run the test app to manually test ListPanel:

```bash
poetry run python -m emdx.ui.panels.test_list_panel
```

This launches an interactive app with:

- Sample data loading
- Event logging
- Navigation testing
- Search testing
- Performance testing (1000 items)

---

## Migration Guide

### From Custom DataTable to ListPanel

**Before (manual DataTable setup):**

```python
class OldBrowser(Widget):
    def compose(self):
        yield DataTable(id="table")

    async def on_mount(self):
        table = self.query_one("#table", DataTable)
        table.add_column("ID", width=5)
        table.add_column("Name", width=40)
        table.cursor_type = "row"
        table.show_header = True

        # Load data
        for item in data:
            table.add_row(item.id, item.name)

    async def on_data_table_row_highlighted(self, event):
        row_key = event.row_key
        # Handle selection...
```

**After (using ListPanel):**

```python
class NewBrowser(Widget):
    def compose(self):
        yield ListPanel(
            columns=[
                ColumnDef("ID", 5),
                ColumnDef("Name", 40),
            ],
            id="list",
        )

    async def on_mount(self):
        items = [ListItem(id=item.id, values=[str(item.id), item.name]) for item in data]
        self.query_one("#list", ListPanel).set_items(items)

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected):
        item = event.item  # Full ListItem with data
```

### From Static Preview to PreviewPanel

**Before:**

```python
class OldBrowser(Widget):
    def compose(self):
        with ScrollableContainer():
            yield RichLog(id="preview")

    async def show_preview(self, content):
        preview = self.query_one("#preview", RichLog)
        preview.clear()
        markdown = Markdown(content)
        preview.write(markdown)
```

**After:**

```python
class NewBrowser(Widget):
    def compose(self):
        yield PreviewPanel(id="preview")

    async def show_preview(self, content):
        preview = self.query_one("#preview", PreviewPanel)
        await preview.show_content(content)
```

### From Hardcoded Layout to ComposableBrowser

**Before:**

```python
class OldBrowser(Widget):
    CSS = """
    OldBrowser { layout: horizontal; }
    #list-container { width: 40%; }
    #preview-container { width: 60%; }
    """

    def compose(self):
        with Vertical(id="list-container"):
            yield DataTable(id="table")
            yield Static(id="details")
        with Vertical(id="preview-container"):
            yield RichLog(id="preview")
```

**After:**

```python
class NewBrowser(ComposableBrowser):
    LAYOUT_NAME = "document-browser"  # Load from YAML

    def configure_panels(self):
        self.set_focus_order(["doc-table", "details-panel", "preview-container"])

# Or define in code:
class NewBrowser(ComposableBrowser):
    def get_default_layout(self):
        return create_layout(
            "document-browser",
            SplitSpec(
                direction="horizontal",
                sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
                children=[
                    SplitSpec(
                        direction="vertical",
                        children=[
                            PanelSpec("table", "doc-table"),
                            PanelSpec("richlog", "details-panel"),
                        ],
                    ),
                    PanelSpec("container", "preview-container"),
                ],
            ),
        )
```

---

## Troubleshooting

### Common Issues

**Panel not receiving focus:**

```python
# Ensure panel is focusable
yield ListPanel(..., id="list")

# Explicitly focus after mount
async def on_mount(self):
    list_panel = self.query_one("#list", ListPanel)
    list_panel.focus_table()
```

**Selection events not firing:**

```python
# Handler method name must match exactly
async def on_list_panel_item_selected(self, event):  # Correct
async def on_item_selected(self, event):  # Wrong - won't be called
```

**Preview not updating:**

```python
# Make sure to await async methods
await preview.show_content(content)  # Correct
preview.show_content(content)  # Wrong - won't complete
```

**Layout not loading from YAML:**

```python
# Check file location
# User: ~/.config/emdx/layouts/my-layout.yaml
# Or use programmatic fallback:
class MyBrowser(ComposableBrowser):
    LAYOUT_NAME = "my-layout"

    def get_default_layout(self):
        # Fallback if YAML not found
        return create_layout(...)
```

**Panel type not found in layout:**

```python
# Register custom panels before creating browser
from emdx.ui.layout import panel_registry, register_builtin_panels

# Register built-ins
register_builtin_panels()

# Register custom
panel_registry.register("my-panel", MyPanelClass)
```

### Debugging Tips

**Enable logging:**

```python
import logging
logging.getLogger("emdx.ui.panels").setLevel(logging.DEBUG)
logging.getLogger("emdx.ui.layout").setLevel(logging.DEBUG)
```

**Message tracing:**

```python
# In your browser
def on_message(self, message):
    if hasattr(message, "source_panel_id"):
        self.log(f"Message: {type(message).__name__} from {message.source_panel_id}")
    return super().on_message(message)
```

**Layout validation:**

```python
from emdx.ui.layout import LayoutManager

manager = LayoutManager()
config = manager.load_layout("my-layout")
errors = manager.validate_layout(config)
if errors:
    for error in errors:
        print(f"Layout error: {error}")
```

### Performance Tips

**Large lists:**

```python
# Use lazy loading
config = ListPanelConfig(lazy_load_threshold=20)

# Handle load more
async def on_list_panel_load_more_requested(self, event):
    more_items = await self.fetch_more(offset=event.total_count)
    self.query_one("#list", ListPanel).append_items(more_items, has_more=True)
```

**Preview truncation:**

```python
# Limit preview content
config = PreviewPanelConfig(truncate_preview=50000)
```

**Avoid frequent updates:**

```python
# Batch item updates
list_panel.set_items(all_items)  # Good: one update

# Avoid:
for item in items:
    list_panel.append_items([item])  # Bad: many updates
```

---

## Additional Resources

- [ExampleBrowser](/emdx/ui/browsers/example_browser.py) - Minimal working example
- [Layout Examples](/emdx/ui/layout/examples.py) - Programmatic layout examples
- [Test Application](/emdx/ui/panels/test_list_panel.py) - Interactive testing
- [Testing Utilities](/emdx/ui/testing/) - Test harness and mocks
