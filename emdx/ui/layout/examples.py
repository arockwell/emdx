"""
Example layouts and browser implementations.

This module provides examples of how to use the layout system:
1. Programmatic layout definitions
2. YAML-based layouts
3. ComposableBrowser implementations
"""

from textual.app import ComposeResult
from textual.widgets import DataTable, RichLog, Static

from .browser import ComposableBrowser
from .config import LayoutConfig, PanelSpec, SizeSpec, SplitSpec
from .manager import create_layout
from .registry import panel_registry


# =============================================================================
# Example 1: Programmatic Layout Definition
# =============================================================================

def create_document_browser_layout() -> LayoutConfig:
    """
    Create the document browser layout programmatically.

    This is equivalent to the document-browser.yaml file but defined in Python.
    Use this approach when you need dynamic layout generation or type checking.
    """
    return create_layout(
        name="document-browser",
        root=SplitSpec(
            direction="horizontal",
            sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
            children=[
                # Left sidebar with list and details
                SplitSpec(
                    direction="vertical",
                    split_id="sidebar",
                    sizes=[SizeSpec.percent(66), SizeSpec.percent(34)],
                    classes=["sidebar"],
                    children=[
                        # Document list table
                        PanelSpec(
                            panel_type="table",
                            panel_id="doc-table",
                            config={
                                "cursor_type": "row",
                                "show_header": True,
                                "cell_padding": 0,
                            },
                            classes=["table-section"],
                        ),
                        # Details panel
                        PanelSpec(
                            panel_type="richlog",
                            panel_id="details-panel",
                            config={
                                "wrap": True,
                                "highlight": True,
                                "markup": True,
                                "auto_scroll": False,
                            },
                            classes=["details-section", "details-richlog"],
                            collapsible=True,
                            min_size=SizeSpec.fixed(8),
                        ),
                    ],
                ),
                # Right preview panel
                PanelSpec(
                    panel_type="container",
                    panel_id="preview-container",
                    classes=["preview-section"],
                    collapsible=True,
                ),
            ],
        ),
        description="Classic document browser layout with list, details, and preview",
    )


# =============================================================================
# Example 2: Simple Browser with Layout Name
# =============================================================================

class SimpleDocumentBrowser(ComposableBrowser):
    """
    Simple document browser that loads its layout from YAML.

    This browser loads the 'document-browser' layout from:
    1. ~/.config/emdx/layouts/document-browser.yaml (user customization)
    2. Built-in layouts directory (default)

    Users can customize the layout by creating their own YAML file.
    """

    LAYOUT_NAME = "document-browser"

    def configure_panels(self) -> None:
        """Configure panels after they are mounted."""
        # Get the document table and configure it
        table = self.get_panel("doc-table")
        if table and isinstance(table, DataTable):
            table.add_column("ID", width=4)
            table.add_column("Tags", width=8)
            table.add_column(" ", width=1)
            table.add_column("Title", width=74)
            table.cursor_type = "row"

        # Set focus order for Tab navigation
        self.set_focus_order(["doc-table", "details-panel", "preview-container"])

    def on_panel_focus(self, panel_id: str) -> None:
        """Handle panel focus changes."""
        # Update status based on focused panel
        if panel_id == "doc-table":
            self.update_status("Navigate with j/k, Enter to view")
        elif panel_id == "preview-container":
            self.update_status("Preview mode - Tab to return to list")

    def update_status(self, message: str) -> None:
        """Update the status bar."""
        # Implementation would update a status widget
        pass


# =============================================================================
# Example 3: Browser with Programmatic Default Layout
# =============================================================================

class ActivityDashboard(ComposableBrowser):
    """
    Activity dashboard with programmatic layout definition.

    This browser defines its layout in Python code rather than YAML.
    Useful for layouts that need dynamic generation or when you want
    full type safety.
    """

    def get_layout_name(self) -> str | None:
        """Return None to skip YAML loading."""
        return None

    def get_default_layout(self) -> LayoutConfig:
        """Define the layout programmatically."""
        return create_layout(
            name="activity-dashboard",
            root=SplitSpec(
                direction="vertical",
                children=[
                    # Status bar at top
                    PanelSpec(
                        panel_type="static",
                        panel_id="status-bar",
                        size=SizeSpec.fixed(1),
                        classes=["status-bar"],
                    ),
                    # Main content area
                    SplitSpec(
                        direction="horizontal",
                        split_id="main-content",
                        sizes=[SizeSpec.percent(50), SizeSpec.percent(50)],
                        children=[
                            # Activity table
                            PanelSpec(
                                panel_type="table",
                                panel_id="activity-table",
                                config={"cursor_type": "row"},
                            ),
                            # Preview panel
                            PanelSpec(
                                panel_type="richlog",
                                panel_id="preview-content",
                                config={"wrap": True, "markup": True},
                            ),
                        ],
                    ),
                    # Help bar at bottom
                    PanelSpec(
                        panel_type="static",
                        panel_id="help-bar",
                        size=SizeSpec.fixed(1),
                        classes=["help-bar"],
                    ),
                ],
            ),
            description="Activity monitoring dashboard",
        )

    def configure_panels(self) -> None:
        """Configure the dashboard panels."""
        # Set initial status
        status = self.get_panel("status-bar")
        if status and isinstance(status, Static):
            status.update("Activity Dashboard - Ready")

        # Set help text
        help_bar = self.get_panel("help-bar")
        if help_bar and isinstance(help_bar, Static):
            help_bar.update("j/k: navigate | Enter: expand | q: quit")

        # Set focus order
        self.set_focus_order(["activity-table", "preview-content"])


# =============================================================================
# Example 4: Browser with Dynamic Nested Layout
# =============================================================================

class FlexibleBrowser(ComposableBrowser):
    """
    Browser demonstrating the convenience methods for layout creation.

    Uses create_nested_split_layout() for cleaner layout definition.
    """

    def get_default_layout(self) -> LayoutConfig:
        """Create a nested layout using the convenience method."""
        return self.create_nested_split_layout(
            "flexible-browser",
            {
                "direction": "horizontal",
                "sizes": ["30%", "70%"],
                "children": [
                    # Left sidebar with navigation
                    {
                        "direction": "vertical",
                        "sizes": ["1fr", "1fr", "1fr"],
                        "children": [
                            {"type": "table", "id": "nav-tree"},
                            {"type": "table", "id": "bookmarks"},
                            {"type": "richlog", "id": "metadata"},
                        ],
                    },
                    # Right content area
                    {
                        "direction": "vertical",
                        "sizes": ["auto", "1fr", "auto"],
                        "children": [
                            {"type": "static", "id": "breadcrumb"},
                            {"type": "richlog", "id": "content"},
                            {"type": "static", "id": "status"},
                        ],
                    },
                ],
            },
        )


# =============================================================================
# Example 5: Custom Panel Types
# =============================================================================

def register_custom_panels() -> None:
    """
    Register custom panel types for use in layouts.

    Call this during application startup to make custom panel types
    available in YAML layouts.
    """
    from textual.containers import ScrollableContainer

    # Register a scrollable preview panel
    panel_registry.register(
        "scrollable-preview",
        ScrollableContainer,
        description="Scrollable container for large content",
        default_config={},
    )

    # Register with a factory for complex setup
    def create_rich_preview(config: dict):
        """Factory for creating rich preview panels."""
        log = RichLog(
            wrap=config.get("wrap", True),
            highlight=config.get("highlight", True),
            markup=config.get("markup", True),
        )
        log.can_focus = config.get("focusable", True)
        return log

    panel_registry.register(
        "rich-preview",
        RichLog,
        factory=create_rich_preview,
        description="Rich text preview with syntax highlighting",
        default_config={
            "wrap": True,
            "highlight": True,
            "markup": True,
            "focusable": True,
        },
    )

    # Register with validation schema
    panel_registry.register(
        "validated-table",
        DataTable,
        description="Data table with validated configuration",
        config_schema={
            "cursor_type": {
                "type": "string",
                "enum": ["row", "column", "cell", "none"],
            },
            "show_header": {"type": "boolean"},
            "zebra_stripes": {"type": "boolean"},
        },
        default_config={
            "cursor_type": "row",
            "show_header": True,
            "zebra_stripes": False,
        },
    )


# =============================================================================
# Example YAML layout file (for reference)
# =============================================================================

EXAMPLE_YAML = """
# Example custom layout file
# Save to: ~/.config/emdx/layouts/my-custom-layout.yaml

name: my-custom-layout
description: My customized document browser layout
version: "1.0"

root:
  type: split
  direction: horizontal
  sizes: ["35%", "65%"]
  children:
    # Narrower left sidebar
    - type: split
      id: sidebar
      direction: vertical
      sizes: ["80%", "20%"]
      children:
        - type: table
          id: doc-table
          config:
            cursor_type: row
            show_header: true
            zebra_stripes: true
        - type: richlog
          id: details-panel
          config:
            wrap: true
          collapsible: true
          collapsed: false

    # Wider preview area
    - type: split
      id: right-panel
      direction: vertical
      sizes: ["1fr", "auto"]
      children:
        - type: container
          id: preview-container
        - type: static
          id: preview-status
          size: "1"
"""
