"""
ComposableBrowser base class for layout-driven browsers.

Provides a base class for browsers that use the LayoutManager
system to define their layouts via configuration rather than
hardcoding the widget tree.
"""

import logging
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget

from .config import LayoutConfig, PanelSpec, SizeSpec, SplitSpec
from .manager import LayoutManager, create_layout
from .registry import PanelRegistry, panel_registry

logger = logging.getLogger(__name__)


class PanelFocused(Message):
    """Message sent when a panel receives focus."""

    def __init__(self, panel_id: str) -> None:
        self.panel_id = panel_id
        super().__init__()


class PanelToggled(Message):
    """Message sent when a panel is toggled (collapsed/expanded)."""

    def __init__(self, panel_id: str, visible: bool) -> None:
        self.panel_id = panel_id
        self.visible = visible
        super().__init__()


class ComposableBrowser(Widget):
    """Base class for browsers with config-driven layouts.

    ComposableBrowser provides:
    - Layout loading from YAML or Python definitions
    - Panel focus management and routing
    - Visibility toggling for collapsible panels
    - Hooks for panel configuration

    Subclasses should:
    1. Define get_layout_name() or get_default_layout()
    2. Override configure_panels() to customize panel behavior
    3. Optionally override on_panel_focus() for focus handling

    Example:
        class MyBrowser(ComposableBrowser):
            def get_layout_name(self) -> str:
                return "my-browser"

            def configure_panels(self) -> None:
                table = self.get_panel("doc-table")
                if table:
                    table.cursor_type = "row"

            def on_panel_focus(self, panel_id: str) -> None:
                self.update_status(f"Focused: {panel_id}")
    """

    # Subclasses can override
    LAYOUT_NAME: Optional[str] = None

    # Focus management
    _focus_order: List[str] = []  # Panel IDs in focus order
    _current_focus_index: int = 0

    def __init__(
        self,
        layout_manager: Optional[LayoutManager] = None,
        layout_config: Optional[LayoutConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the composable browser.

        Args:
            layout_manager: LayoutManager to use (defaults to new instance)
            layout_config: Optional pre-loaded layout config
            **kwargs: Additional Widget arguments
        """
        super().__init__(**kwargs)

        self._layout_manager = layout_manager or LayoutManager()
        self._layout_config = layout_config
        self._panels: Dict[str, Widget] = {}
        self._collapsed_panels: Set[str] = set()
        self._panel_callbacks: Dict[str, List[Callable]] = {}

    def compose(self) -> ComposeResult:
        """Compose the browser using its layout configuration.

        Loads the layout (from name or default), builds the widget
        tree, and yields all widgets.
        """
        # Get layout config
        config = self._get_layout_config()
        if not config:
            from textual.widgets import Static

            yield Static("[red]No layout configuration found[/red]")
            return

        # Validate layout
        errors = self._layout_manager.validate_layout(config)
        if errors:
            logger.warning(f"Layout validation errors: {errors}")

        # Build and yield layout
        yield from self._layout_manager.build_layout(config)

    def _get_layout_config(self) -> Optional[LayoutConfig]:
        """Get the layout configuration for this browser.

        Order of precedence:
        1. Layout config passed to constructor
        2. Load from LAYOUT_NAME or get_layout_name()
        3. Build from get_default_layout()

        Returns:
            LayoutConfig or None
        """
        # Use provided config
        if self._layout_config:
            return self._layout_config

        # Try loading by name
        layout_name = self.get_layout_name()
        if layout_name:
            try:
                return self._layout_manager.load_layout(layout_name)
            except FileNotFoundError:
                logger.debug(f"Layout '{layout_name}' not found, using default")
            except Exception as e:
                logger.error(f"Failed to load layout '{layout_name}': {e}")

        # Fall back to default layout
        return self.get_default_layout()

    def get_layout_name(self) -> Optional[str]:
        """Get the name of the layout to load.

        Override this to specify a YAML layout file name.

        Returns:
            Layout name or None to use default
        """
        return self.LAYOUT_NAME

    def get_default_layout(self) -> Optional[LayoutConfig]:
        """Get the default layout configuration.

        Override this to define a layout in Python when no
        YAML layout is available.

        Returns:
            LayoutConfig or None
        """
        return None

    async def on_mount(self) -> None:
        """Handle mount event - configure panels after mounting."""
        # Store panel references
        self._panels = self._layout_manager.get_all_panels()

        # Configure panels
        self.configure_panels()

        # Set initial focus
        if self._focus_order:
            self.focus_panel(self._focus_order[0])

    def configure_panels(self) -> None:
        """Configure panels after they are mounted.

        Override this to customize panel behavior, set up
        event handlers, configure appearance, etc.

        Example:
            def configure_panels(self) -> None:
                table = self.get_panel("doc-table")
                if table and isinstance(table, DataTable):
                    table.cursor_type = "row"
                    table.add_column("ID", width=4)
                    table.add_column("Title", width=50)

                self.set_focus_order(["doc-table", "preview"])
        """
        pass

    def get_panel(self, panel_id: str) -> Optional[Widget]:
        """Get a panel by ID.

        Args:
            panel_id: The panel ID

        Returns:
            Widget or None if not found
        """
        return self._panels.get(panel_id)

    def get_panels(self) -> Dict[str, Widget]:
        """Get all panels.

        Returns:
            Dictionary mapping panel IDs to widgets
        """
        return dict(self._panels)

    # Focus management

    def set_focus_order(self, panel_ids: List[str]) -> None:
        """Set the order for Tab/Shift-Tab focus cycling.

        Args:
            panel_ids: List of panel IDs in focus order
        """
        # Filter to only existing panels
        self._focus_order = [pid for pid in panel_ids if pid in self._panels]
        self._current_focus_index = 0

    def focus_panel(self, panel_id: str) -> bool:
        """Focus a specific panel.

        Args:
            panel_id: The panel to focus

        Returns:
            True if panel was focused
        """
        panel = self._panels.get(panel_id)
        if not panel or panel_id in self._collapsed_panels:
            return False

        panel.focus()
        self.post_message(PanelFocused(panel_id))
        self.on_panel_focus(panel_id)

        # Update focus index
        if panel_id in self._focus_order:
            self._current_focus_index = self._focus_order.index(panel_id)

        return True

    def focus_next(self) -> None:
        """Focus the next panel in the focus order."""
        if not self._focus_order:
            return

        # Find next non-collapsed panel
        start = self._current_focus_index
        for _ in range(len(self._focus_order)):
            self._current_focus_index = (
                self._current_focus_index + 1
            ) % len(self._focus_order)
            panel_id = self._focus_order[self._current_focus_index]
            if panel_id not in self._collapsed_panels:
                self.focus_panel(panel_id)
                return

        # All panels collapsed, restore original
        self._current_focus_index = start

    def focus_previous(self) -> None:
        """Focus the previous panel in the focus order."""
        if not self._focus_order:
            return

        start = self._current_focus_index
        for _ in range(len(self._focus_order)):
            self._current_focus_index = (
                self._current_focus_index - 1
            ) % len(self._focus_order)
            panel_id = self._focus_order[self._current_focus_index]
            if panel_id not in self._collapsed_panels:
                self.focus_panel(panel_id)
                return

        self._current_focus_index = start

    def get_focused_panel(self) -> Optional[str]:
        """Get the ID of the currently focused panel.

        Returns:
            Panel ID or None
        """
        if self._focus_order and 0 <= self._current_focus_index < len(self._focus_order):
            return self._focus_order[self._current_focus_index]
        return None

    def on_panel_focus(self, panel_id: str) -> None:
        """Called when a panel receives focus.

        Override this to handle focus changes.

        Args:
            panel_id: The ID of the focused panel
        """
        pass

    # Visibility management

    async def toggle_panel(self, panel_id: str) -> bool:
        """Toggle a panel's visibility.

        Args:
            panel_id: The panel to toggle

        Returns:
            True if panel is now visible, False if collapsed
        """
        panel = self._panels.get(panel_id)
        if not panel:
            return False

        if panel_id in self._collapsed_panels:
            # Expand
            self._collapsed_panels.remove(panel_id)
            panel.display = True
            self.post_message(PanelToggled(panel_id, visible=True))
            return True
        else:
            # Collapse
            self._collapsed_panels.add(panel_id)
            panel.display = False

            # Move focus if this panel was focused
            if self.get_focused_panel() == panel_id:
                self.focus_next()

            self.post_message(PanelToggled(panel_id, visible=False))
            return False

    def collapse_panel(self, panel_id: str) -> None:
        """Collapse a panel."""
        panel = self._panels.get(panel_id)
        if panel and panel_id not in self._collapsed_panels:
            self._collapsed_panels.add(panel_id)
            panel.display = False
            self.post_message(PanelToggled(panel_id, visible=False))

    def expand_panel(self, panel_id: str) -> None:
        """Expand a collapsed panel."""
        panel = self._panels.get(panel_id)
        if panel and panel_id in self._collapsed_panels:
            self._collapsed_panels.remove(panel_id)
            panel.display = True
            self.post_message(PanelToggled(panel_id, visible=True))

    def is_panel_visible(self, panel_id: str) -> bool:
        """Check if a panel is visible.

        Args:
            panel_id: The panel ID

        Returns:
            True if visible
        """
        return panel_id not in self._collapsed_panels

    # Panel callbacks

    def on_panel_event(
        self, panel_id: str, callback: Callable[[Widget, Any], None]
    ) -> None:
        """Register a callback for panel events.

        Args:
            panel_id: The panel to watch
            callback: Function to call with (widget, event)
        """
        if panel_id not in self._panel_callbacks:
            self._panel_callbacks[panel_id] = []
        self._panel_callbacks[panel_id].append(callback)

    def _dispatch_panel_event(self, panel_id: str, event: Any) -> None:
        """Dispatch an event to panel callbacks.

        Args:
            panel_id: The source panel
            event: The event to dispatch
        """
        callbacks = self._panel_callbacks.get(panel_id, [])
        panel = self._panels.get(panel_id)
        if panel:
            for callback in callbacks:
                try:
                    callback(panel, event)
                except Exception as e:
                    logger.error(f"Panel callback error: {e}")

    # Layout introspection

    def get_layout_config(self) -> Optional[LayoutConfig]:
        """Get the current layout configuration.

        Returns:
            LayoutConfig or None
        """
        return self._layout_manager.get_current_layout()

    async def reload_layout(self) -> None:
        """Reload the layout from configuration.

        This clears the current layout and rebuilds it from
        the configuration. Useful for hot-reloading.
        """
        # Clear current state
        await self.remove_children()
        self._panels.clear()
        self._collapsed_panels.clear()
        self._layout_config = None
        self._layout_manager.clear_cache()

        # Remount
        await self.recompose()

    # Utility methods for subclasses

    def create_simple_split_layout(
        self,
        name: str,
        panels: List[Dict[str, Any]],
        direction: str = "horizontal",
        sizes: Optional[List[str]] = None,
    ) -> LayoutConfig:
        """Create a simple split layout programmatically.

        Convenience method for defining basic layouts in Python.

        Args:
            name: Layout name
            panels: List of panel dicts with 'type', 'id', and optional 'config'
            direction: Split direction
            sizes: Optional list of size specs (e.g., ["40%", "60%"])

        Returns:
            LayoutConfig instance

        Example:
            layout = self.create_simple_split_layout(
                "my-layout",
                [
                    {"type": "list", "id": "doc-list"},
                    {"type": "preview", "id": "doc-preview"},
                ],
                direction="horizontal",
                sizes=["40%", "60%"],
            )
        """
        panel_specs = [
            PanelSpec(
                panel_type=p["type"],
                panel_id=p["id"],
                config=p.get("config", {}),
            )
            for p in panels
        ]

        size_specs = None
        if sizes:
            size_specs = [SizeSpec.from_string(s) for s in sizes]

        return create_layout(
            name,
            SplitSpec(
                direction=direction,  # type: ignore
                children=panel_specs,
                sizes=size_specs,
            ),
        )

    def create_nested_split_layout(
        self,
        name: str,
        structure: Dict[str, Any],
    ) -> LayoutConfig:
        """Create a nested split layout from a dictionary structure.

        Args:
            name: Layout name
            structure: Nested dict defining the layout

        Returns:
            LayoutConfig instance

        Example:
            layout = self.create_nested_split_layout(
                "my-layout",
                {
                    "direction": "horizontal",
                    "sizes": ["40%", "60%"],
                    "children": [
                        {
                            "direction": "vertical",
                            "sizes": ["66%", "34%"],
                            "children": [
                                {"type": "list", "id": "doc-list"},
                                {"type": "details", "id": "doc-details"},
                            ],
                        },
                        {"type": "preview", "id": "doc-preview"},
                    ],
                },
            )
        """
        root = self._parse_structure(structure)
        return create_layout(name, root)

    def _parse_structure(
        self, structure: Dict[str, Any]
    ) -> Union[SplitSpec, PanelSpec]:
        """Parse a structure dict into layout specs."""
        if "children" in structure:
            # It's a split
            children = [self._parse_structure(c) for c in structure["children"]]
            sizes = None
            if "sizes" in structure:
                sizes = [SizeSpec.from_string(s) for s in structure["sizes"]]

            return SplitSpec(
                direction=structure.get("direction", "horizontal"),
                children=children,
                sizes=sizes,
                split_id=structure.get("id"),
            )
        else:
            # It's a panel
            return PanelSpec(
                panel_type=structure["type"],
                panel_id=structure["id"],
                config=structure.get("config", {}),
            )
