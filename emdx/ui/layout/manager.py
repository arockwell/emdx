"""
Layout manager for building and managing TUI layouts.

The LayoutManager is responsible for:
- Loading layout configurations from YAML files
- Building Textual widget trees from layout configs
- Saving layout configurations
- Introspecting running layouts
"""

import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget

from .config import LayoutConfig, PanelSpec, SizeSpec, SplitSpec
from .registry import PanelRegistry, panel_registry

logger = logging.getLogger(__name__)

# Default layouts directory
DEFAULT_LAYOUTS_DIR = Path.home() / ".config" / "emdx" / "layouts"

# Built-in layouts directory (in package)
BUILTIN_LAYOUTS_DIR = Path(__file__).parent / "builtin_layouts"


class LayoutBuilder:
    """Builds Textual widget trees from layout configurations.

    This class handles the recursive construction of the widget
    hierarchy from SplitSpec and PanelSpec definitions.
    """

    def __init__(self, registry: PanelRegistry) -> None:
        self.registry = registry
        self._built_panels: Dict[str, Widget] = {}

    def build(self, config: LayoutConfig) -> ComposeResult:
        """Build the complete widget tree from a layout config.

        Args:
            config: The layout configuration

        Yields:
            Widgets in compose order
        """
        self._built_panels.clear()
        yield from self._build_node(config.root)

    def _build_node(
        self, node: Union[SplitSpec, PanelSpec]
    ) -> Generator[Widget, None, None]:
        """Recursively build a node in the layout tree.

        Args:
            node: The node to build

        Yields:
            Widgets for this node
        """
        if isinstance(node, PanelSpec):
            yield from self._build_panel(node)
        elif isinstance(node, SplitSpec):
            yield from self._build_split(node)
        else:
            raise ValueError(f"Unknown node type: {type(node)}")

    def _build_panel(self, spec: PanelSpec) -> Generator[Widget, None, None]:
        """Build a panel from its specification.

        Args:
            spec: The panel specification

        Yields:
            The panel widget
        """
        if spec.collapsed:
            # Don't yield collapsed panels
            return

        try:
            widget = self.registry.create(spec.panel_type, spec.panel_id, spec.config)

            # Apply CSS classes
            for css_class in spec.classes:
                widget.add_class(css_class)

            # Store reference for later access
            self._built_panels[spec.panel_id] = widget

            yield widget

        except ValueError as e:
            logger.error(f"Failed to build panel '{spec.panel_id}': {e}")
            # Yield a placeholder
            from textual.widgets import Static

            yield Static(f"[red]Error: {e}[/red]", id=spec.panel_id)

    def _build_split(self, spec: SplitSpec) -> Generator[Widget, None, None]:
        """Build a split container from its specification.

        Args:
            spec: The split specification

        Yields:
            The split container widget
        """
        if spec.collapsed:
            return

        # Choose container type based on direction
        ContainerClass = Horizontal if spec.direction == "horizontal" else Vertical

        # Create container with optional ID
        container_kwargs: Dict[str, Any] = {}
        if spec.split_id:
            container_kwargs["id"] = spec.split_id

        container = ContainerClass(**container_kwargs)

        # Apply CSS classes
        for css_class in spec.classes:
            container.add_class(css_class)

        # Build children with their sizes
        sizes = spec.get_child_sizes()
        children: List[Widget] = []

        for child, size in zip(spec.children, sizes):
            # Build child widgets
            child_widgets = list(self._build_node(child))

            for widget in child_widgets:
                # Apply size to widget
                self._apply_size(widget, size, spec.direction)
                children.append(widget)

        # Mount children to container
        # Note: Actual mounting happens in compose() via Textual's mechanism
        # We use a wrapper that holds the children
        wrapper = _SplitContainer(
            container_class=ContainerClass,
            children=children,
            container_id=spec.split_id,
            classes=spec.classes,
        )

        yield wrapper

    def _apply_size(
        self, widget: Widget, size: SizeSpec, direction: str
    ) -> None:
        """Apply size specification to a widget.

        Args:
            widget: The widget to size
            size: The size specification
            direction: Parent split direction
        """
        css_value = size.to_css()

        if direction == "horizontal":
            # Width for horizontal splits
            if size.unit == "fr":
                widget.styles.width = css_value
            elif size.unit == "%":
                widget.styles.width = f"{int(size.value)}%"
            elif size.unit == "px":
                widget.styles.width = int(size.value)
        else:
            # Height for vertical splits
            if size.unit == "fr":
                widget.styles.height = css_value
            elif size.unit == "%":
                widget.styles.height = f"{int(size.value)}%"
            elif size.unit == "px":
                widget.styles.height = int(size.value)

    def get_panel(self, panel_id: str) -> Optional[Widget]:
        """Get a built panel by ID.

        Args:
            panel_id: The panel ID

        Returns:
            Widget or None if not found
        """
        return self._built_panels.get(panel_id)

    def get_all_panels(self) -> Dict[str, Widget]:
        """Get all built panels.

        Returns:
            Dictionary mapping panel IDs to widgets
        """
        return dict(self._built_panels)


class _SplitContainer(Widget):
    """Internal container widget that holds split children.

    This is a helper class that wraps the actual split layout
    to work with Textual's compose pattern.
    """

    def __init__(
        self,
        container_class: type,
        children: List[Widget],
        container_id: Optional[str] = None,
        classes: Optional[List[str]] = None,
    ) -> None:
        super().__init__(id=container_id)
        self._container_class = container_class
        self._children = children
        self._extra_classes = classes or []

    def compose(self) -> ComposeResult:
        """Compose the split container."""
        container = self._container_class()
        for css_class in self._extra_classes:
            container.add_class(css_class)

        with container:
            for child in self._children:
                yield child


class LayoutManager:
    """Manages layout loading, building, and saving.

    The main entry point for the layout system. Handles:
    - Loading layouts from YAML files
    - Building widget trees from configs
    - Saving layouts to files
    - Introspecting running layouts

    Usage:
        manager = LayoutManager()
        config = manager.load_layout("document-browser")

        # In a Widget.compose() method:
        yield from manager.build_layout(config)
    """

    def __init__(
        self,
        registry: Optional[PanelRegistry] = None,
        layouts_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the layout manager.

        Args:
            registry: Panel registry to use (defaults to global)
            layouts_dir: Directory for user layout files
        """
        self.registry = registry or panel_registry
        self.layouts_dir = layouts_dir or DEFAULT_LAYOUTS_DIR
        self._builder = LayoutBuilder(self.registry)
        self._current_config: Optional[LayoutConfig] = None
        self._layout_cache: Dict[str, LayoutConfig] = {}

    def load_layout(self, name: str) -> LayoutConfig:
        """Load a layout configuration by name.

        Searches in order:
        1. User layouts directory (~/.config/emdx/layouts/)
        2. Built-in layouts directory

        Args:
            name: Layout name (without .yaml extension)

        Returns:
            LayoutConfig instance

        Raises:
            FileNotFoundError: If layout file not found
            ValueError: If layout file is invalid
        """
        # Check cache first
        if name in self._layout_cache:
            return self._layout_cache[name]

        # Search for layout file
        layout_path = self._find_layout_file(name)
        if not layout_path:
            raise FileNotFoundError(f"Layout not found: {name}")

        # Load and parse
        config = self._load_layout_file(layout_path, name)
        self._layout_cache[name] = config
        return config

    def _find_layout_file(self, name: str) -> Optional[Path]:
        """Find a layout file by name.

        Args:
            name: Layout name

        Returns:
            Path to layout file or None
        """
        # Check user layouts first
        user_path = self.layouts_dir / f"{name}.yaml"
        if user_path.exists():
            return user_path

        # Check built-in layouts
        builtin_path = BUILTIN_LAYOUTS_DIR / f"{name}.yaml"
        if builtin_path.exists():
            return builtin_path

        return None

    def _load_layout_file(self, path: Path, name: str) -> LayoutConfig:
        """Load a layout from a YAML file.

        Args:
            path: Path to the YAML file
            name: Layout name

        Returns:
            LayoutConfig instance
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for loading layout files")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty layout file: {path}")

        # Handle layouts file with multiple layouts
        if "layouts" in data:
            if name not in data["layouts"]:
                raise ValueError(f"Layout '{name}' not found in {path}")
            layout_data = data["layouts"][name]
        else:
            layout_data = data

        return LayoutConfig.from_dict(name, layout_data)

    def build_layout(self, config: LayoutConfig) -> ComposeResult:
        """Build a Textual widget tree from a layout config.

        Args:
            config: The layout configuration

        Yields:
            Widgets in compose order

        Example:
            def compose(self) -> ComposeResult:
                config = layout_manager.load_layout("my-layout")
                yield from layout_manager.build_layout(config)
        """
        self._current_config = config
        yield from self._builder.build(config)

    def save_layout(self, name: str, config: LayoutConfig) -> Path:
        """Save a layout configuration to a YAML file.

        Args:
            name: Layout name (becomes filename)
            config: Layout configuration to save

        Returns:
            Path to saved file
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for saving layout files")

        # Ensure directory exists
        self.layouts_dir.mkdir(parents=True, exist_ok=True)

        # Write layout file
        path = self.layouts_dir / f"{name}.yaml"
        with open(path, "w") as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved layout to {path}")
        return path

    def get_current_layout(self) -> Optional[LayoutConfig]:
        """Get the currently active layout configuration.

        Returns:
            Current LayoutConfig or None if no layout is active
        """
        return self._current_config

    def get_panel(self, panel_id: str) -> Optional[Widget]:
        """Get a panel by ID from the current layout.

        Args:
            panel_id: The panel ID to look up

        Returns:
            Widget or None if not found
        """
        return self._builder.get_panel(panel_id)

    def get_all_panels(self) -> Dict[str, Widget]:
        """Get all panels from the current layout.

        Returns:
            Dictionary mapping panel IDs to widgets
        """
        return self._builder.get_all_panels()

    def list_layouts(self) -> List[Tuple[str, str]]:
        """List available layout names and their locations.

        Returns:
            List of (name, location) tuples where location is
            "user" or "builtin"
        """
        layouts = []

        # User layouts
        if self.layouts_dir.exists():
            for path in self.layouts_dir.glob("*.yaml"):
                layouts.append((path.stem, "user"))

        # Built-in layouts
        if BUILTIN_LAYOUTS_DIR.exists():
            for path in BUILTIN_LAYOUTS_DIR.glob("*.yaml"):
                # Don't add if user has override
                if not any(name == path.stem for name, _ in layouts):
                    layouts.append((path.stem, "builtin"))

        return sorted(layouts)

    def clear_cache(self) -> None:
        """Clear the layout cache."""
        self._layout_cache.clear()

    def validate_layout(self, config: LayoutConfig) -> List[str]:
        """Validate a layout configuration.

        Args:
            config: Layout to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        errors.extend(self._validate_node(config.root, set()))
        return errors

    def _validate_node(
        self, node: Union[SplitSpec, PanelSpec], seen_ids: set
    ) -> List[str]:
        """Validate a layout node recursively.

        Args:
            node: Node to validate
            seen_ids: Set of already-seen panel IDs

        Returns:
            List of validation errors
        """
        errors = []

        if isinstance(node, PanelSpec):
            # Check for duplicate IDs
            if node.panel_id in seen_ids:
                errors.append(f"Duplicate panel ID: {node.panel_id}")
            seen_ids.add(node.panel_id)

            # Check panel type exists
            if not self.registry.has(node.panel_type):
                errors.append(
                    f"Unknown panel type '{node.panel_type}' "
                    f"for panel '{node.panel_id}'"
                )

            # Validate panel config
            config_errors = self.registry.validate_config(
                node.panel_type, node.config
            )
            for err in config_errors:
                errors.append(f"Panel '{node.panel_id}': {err}")

        elif isinstance(node, SplitSpec):
            # Validate split ID if present
            if node.split_id:
                if node.split_id in seen_ids:
                    errors.append(f"Duplicate split ID: {node.split_id}")
                seen_ids.add(node.split_id)

            # Validate children
            for child in node.children:
                errors.extend(self._validate_node(child, seen_ids))

        return errors


# Convenience function for creating layouts programmatically
def create_layout(
    name: str,
    root: Union[SplitSpec, PanelSpec],
    theme: Optional[str] = None,
    description: str = "",
) -> LayoutConfig:
    """Create a layout configuration programmatically.

    Args:
        name: Layout name
        root: Root node (split or panel)
        theme: Optional theme name
        description: Layout description

    Returns:
        LayoutConfig instance

    Example:
        layout = create_layout(
            "my-layout",
            SplitSpec(
                direction="horizontal",
                children=[
                    PanelSpec("list", "doc-list"),
                    PanelSpec("preview", "doc-preview"),
                ],
                sizes=[SizeSpec(40, "%"), SizeSpec(60, "%")],
            ),
        )
    """
    return LayoutConfig(
        name=name,
        root=root,
        theme=theme,
        description=description,
    )
