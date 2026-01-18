"""
Panel Protocol and Base Classes for EMDX UI.

This module defines the standard interface for all UI panels in EMDX.
It provides:

1. PanelProtocol - The interface all panels must implement
2. PanelBase - Abstract base class with default implementations
3. Concrete panel types - ListPanel, PreviewPanel, StatusPanel, InputPanel
4. Panel messages - Standard communication between panels

Design Principles:
- Panels are composable, reusable UI components
- Message-based communication (no tight coupling)
- Declarative keybinding registration
- State save/restore for session management
- Lifecycle hooks for clean resource management

Quick Start:
    from emdx.ui.panels import ListPanel, PreviewPanel, StatusPanel

    class MyBrowser(Widget):
        def compose(self):
            yield ListPanel(columns=[("ID", 5), ("Name", 40)], id="list")
            yield PreviewPanel(id="preview")
            yield StatusPanel(id="status")

        async def on_list_panel_item_selected(self, event):
            preview = self.query_one("#preview", PreviewPanel)
            await preview.show_content(event.item.data["content"])
"""

# Protocol and capabilities
from .protocol import (
    PanelProtocol,
    PanelCapability,
    PanelRequirement,
    KeyBinding,
    PanelState,
    has_capability,
    is_panel,
    get_panel_keybindings,
)

# Base class
from .base import PanelBase

# Messages
from .messages import (
    PanelMessage,
    PanelActivated,
    PanelDeactivated,
    PanelFocused,
    PanelBlurred,
    SelectionChanged,
    SelectionData,
    NavigationRequested,
    NavigationDirection,
    ContentRequested,
    ContentProvided,
    ActionRequested,
    ActionCompleted,
    ErrorOccurred,
    ErrorSeverity,
    StatusUpdate,
    filter_messages_by_type,
    filter_messages_from_panel,
)

# List panel
from .list_panel import (
    ListPanel,
    ListItem,
    ColumnDef,
    ListPanelConfig,
    SimpleBrowser,
    DocumentListBrowser,
)

# Preview panel
from .preview_panel import (
    PreviewPanel,
    PreviewMode,
    PreviewPanelConfig,
    TextAreaHost,
)

# Status panel
from .status_panel import (
    StatusPanel,
    StatusSection,
    StatusAlign,
    StatusPanelConfig,
    SimpleStatusBar,
)

# Input panel
from .input_panel import (
    InputPanel,
    InputMode,
    InputPanelConfig,
    SearchInput,
    TagInput,
)

__all__ = [
    # Protocol and capabilities
    "PanelProtocol",
    "PanelCapability",
    "PanelRequirement",
    "KeyBinding",
    "PanelState",
    "has_capability",
    "is_panel",
    "get_panel_keybindings",
    # Base class
    "PanelBase",
    # Messages
    "PanelMessage",
    "PanelActivated",
    "PanelDeactivated",
    "PanelFocused",
    "PanelBlurred",
    "SelectionChanged",
    "SelectionData",
    "NavigationRequested",
    "NavigationDirection",
    "ContentRequested",
    "ContentProvided",
    "ActionRequested",
    "ActionCompleted",
    "ErrorOccurred",
    "ErrorSeverity",
    "StatusUpdate",
    "filter_messages_by_type",
    "filter_messages_from_panel",
    # List panel
    "ListPanel",
    "ListItem",
    "ColumnDef",
    "ListPanelConfig",
    "SimpleBrowser",
    "DocumentListBrowser",
    # Preview panel
    "PreviewPanel",
    "PreviewMode",
    "PreviewPanelConfig",
    "TextAreaHost",
    # Status panel
    "StatusPanel",
    "StatusSection",
    "StatusAlign",
    "StatusPanelConfig",
    "SimpleStatusBar",
    # Input panel
    "InputPanel",
    "InputMode",
    "InputPanelConfig",
    "SearchInput",
    "TagInput",
]
