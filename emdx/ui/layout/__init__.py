"""
Layout management system for EMDX TUI.

Provides config-driven layout definitions with support for:
- Python and YAML layout definitions
- User customization via config files
- Nested layouts (splits within splits)
- Panel sizing (percentages, fractions, fixed)
- Visibility toggling (collapsible panels)

Example usage:
    from emdx.ui.layout import LayoutManager, LayoutConfig

    manager = LayoutManager()
    config = manager.load_layout("document-browser")
    widgets = manager.build_layout(config)

For creating layout-driven browsers:
    from emdx.ui.layout import ComposableBrowser

    class MyBrowser(ComposableBrowser):
        LAYOUT_NAME = "my-browser"

        def configure_panels(self) -> None:
            table = self.get_panel("my-table")
            if table:
                table.cursor_type = "row"
"""

from .config import (
    LayoutConfig,
    PanelSpec,
    SizeSpec,
    SizeUnit,
    SplitSpec,
)
from .manager import LayoutManager, create_layout
from .registry import (
    PanelRegistry,
    PanelRegistration,
    panel_registry,
    register_builtin_panels,
)
from .browser import (
    ComposableBrowser,
    PanelFocused,
    PanelToggled,
)

__all__ = [
    # Config classes
    "LayoutConfig",
    "PanelSpec",
    "SizeSpec",
    "SizeUnit",
    "SplitSpec",
    # Manager
    "LayoutManager",
    "create_layout",
    # Registry
    "PanelRegistry",
    "PanelRegistration",
    "panel_registry",
    "register_builtin_panels",
    # Browser base class
    "ComposableBrowser",
    "PanelFocused",
    "PanelToggled",
]
