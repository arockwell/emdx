"""
Panel registry for the layout system.

Panels register themselves with type names that can be referenced
in layout configurations. The registry validates panel configs and
provides panel class lookup.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Type, TypeVar

from textual.app import ComposeResult
from textual.widget import Widget

logger = logging.getLogger(__name__)


class PanelProtocol(Protocol):
    """Protocol that panel widgets should implement."""

    def compose(self) -> ComposeResult:
        """Compose the panel's widget tree."""
        ...


# Type variable for panel classes
P = TypeVar("P", bound=Widget)


@dataclass
class PanelRegistration:
    """Registration information for a panel type.

    Attributes:
        panel_type: Unique type name for this panel
        panel_class: The widget class to instantiate
        factory: Optional factory function for complex construction
        config_schema: Optional schema for validating panel config
        description: Human-readable description
        default_config: Default configuration values
        required_config: List of required config keys
    """

    panel_type: str
    panel_class: Type[Widget]
    factory: Optional[Callable[[Dict[str, Any]], Widget]] = None
    config_schema: Optional[Dict[str, Any]] = None
    description: str = ""
    default_config: Dict[str, Any] = field(default_factory=dict)
    required_config: List[str] = field(default_factory=list)

    def create_instance(
        self, panel_id: str, config: Optional[Dict[str, Any]] = None
    ) -> Widget:
        """Create an instance of this panel.

        Args:
            panel_id: The ID to assign to the widget
            config: Panel-specific configuration

        Returns:
            Instantiated widget
        """
        # Merge default config with provided config
        merged_config = {**self.default_config, **(config or {})}

        # Validate required config
        for key in self.required_config:
            if key not in merged_config:
                raise ValueError(
                    f"Panel '{self.panel_type}' requires config key '{key}'"
                )

        # Use factory if provided, otherwise direct instantiation
        if self.factory:
            widget = self.factory(merged_config)
            # Set ID if not already set by factory
            if widget.id is None:
                widget.id = panel_id
        else:
            # Try to pass config as kwargs, fall back to no args
            try:
                widget = self.panel_class(id=panel_id, **merged_config)
            except TypeError:
                widget = self.panel_class(id=panel_id)

        return widget

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate panel configuration.

        Args:
            config: Configuration to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check required fields
        for key in self.required_config:
            if key not in config:
                errors.append(f"Missing required config key: {key}")

        # Validate against schema if provided
        if self.config_schema:
            errors.extend(self._validate_schema(config, self.config_schema))

        return errors

    def _validate_schema(
        self, config: Dict[str, Any], schema: Dict[str, Any]
    ) -> List[str]:
        """Validate config against a schema."""
        errors = []

        for key, spec in schema.items():
            if key not in config:
                if spec.get("required", False):
                    errors.append(f"Missing required field: {key}")
                continue

            value = config[key]
            expected_type = spec.get("type")

            if expected_type:
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{key}' must be a string")
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{key}' must be a number")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{key}' must be a boolean")
                elif expected_type == "array" and not isinstance(value, list):
                    errors.append(f"Field '{key}' must be an array")
                elif expected_type == "object" and not isinstance(value, dict):
                    errors.append(f"Field '{key}' must be an object")

            # Check allowed values
            if "enum" in spec and value not in spec["enum"]:
                errors.append(
                    f"Field '{key}' must be one of: {spec['enum']}, got: {value}"
                )

            # Check range for numbers
            if isinstance(value, (int, float)):
                if "min" in spec and value < spec["min"]:
                    errors.append(f"Field '{key}' must be >= {spec['min']}")
                if "max" in spec and value > spec["max"]:
                    errors.append(f"Field '{key}' must be <= {spec['max']}")

        return errors


class PanelRegistry:
    """Registry for panel types.

    Panels register themselves by type name, allowing layout configs
    to reference them by string identifier.

    Usage:
        # Register a panel class
        panel_registry.register("list", DataTablePanel)

        # Register with factory
        panel_registry.register("preview", PreviewPanel, factory=create_preview)

        # Look up and create
        panel = panel_registry.create("list", "doc-list", {"columns": 4})
    """

    def __init__(self) -> None:
        self._panels: Dict[str, PanelRegistration] = {}

    def register(
        self,
        panel_type: str,
        panel_class: Type[Widget],
        *,
        factory: Optional[Callable[[Dict[str, Any]], Widget]] = None,
        config_schema: Optional[Dict[str, Any]] = None,
        description: str = "",
        default_config: Optional[Dict[str, Any]] = None,
        required_config: Optional[List[str]] = None,
    ) -> None:
        """Register a panel type.

        Args:
            panel_type: Unique type name for this panel
            panel_class: The widget class to instantiate
            factory: Optional factory function for complex construction
            config_schema: Optional schema for validating panel config
            description: Human-readable description
            default_config: Default configuration values
            required_config: List of required config keys
        """
        if panel_type in self._panels:
            logger.warning(f"Overwriting existing panel registration: {panel_type}")

        self._panels[panel_type] = PanelRegistration(
            panel_type=panel_type,
            panel_class=panel_class,
            factory=factory,
            config_schema=config_schema,
            description=description,
            default_config=default_config or {},
            required_config=required_config or [],
        )
        logger.debug(f"Registered panel type: {panel_type}")

    def unregister(self, panel_type: str) -> bool:
        """Unregister a panel type.

        Args:
            panel_type: The type name to unregister

        Returns:
            True if panel was unregistered, False if not found
        """
        if panel_type in self._panels:
            del self._panels[panel_type]
            return True
        return False

    def get(self, panel_type: str) -> Optional[PanelRegistration]:
        """Get registration info for a panel type.

        Args:
            panel_type: The type name to look up

        Returns:
            PanelRegistration or None if not found
        """
        return self._panels.get(panel_type)

    def create(
        self,
        panel_type: str,
        panel_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Widget:
        """Create a panel instance.

        Args:
            panel_type: The type of panel to create
            panel_id: Unique ID for the panel
            config: Panel-specific configuration

        Returns:
            Instantiated widget

        Raises:
            ValueError: If panel type is not registered
        """
        registration = self._panels.get(panel_type)
        if not registration:
            raise ValueError(f"Unknown panel type: {panel_type}")

        return registration.create_instance(panel_id, config)

    def validate_config(
        self, panel_type: str, config: Dict[str, Any]
    ) -> List[str]:
        """Validate configuration for a panel type.

        Args:
            panel_type: The type of panel
            config: Configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        registration = self._panels.get(panel_type)
        if not registration:
            return [f"Unknown panel type: {panel_type}"]

        return registration.validate_config(config)

    def list_types(self) -> List[str]:
        """List all registered panel types.

        Returns:
            Sorted list of panel type names
        """
        return sorted(self._panels.keys())

    def list_registrations(self) -> List[PanelRegistration]:
        """List all panel registrations.

        Returns:
            List of all PanelRegistration objects
        """
        return list(self._panels.values())

    def has(self, panel_type: str) -> bool:
        """Check if a panel type is registered.

        Args:
            panel_type: The type name to check

        Returns:
            True if registered
        """
        return panel_type in self._panels

    def decorator(
        self,
        panel_type: str,
        *,
        config_schema: Optional[Dict[str, Any]] = None,
        description: str = "",
        default_config: Optional[Dict[str, Any]] = None,
        required_config: Optional[List[str]] = None,
    ) -> Callable[[Type[P]], Type[P]]:
        """Decorator for registering panel classes.

        Usage:
            @panel_registry.decorator("list", description="Document list panel")
            class DocumentListPanel(Widget):
                ...

        Args:
            panel_type: The type name to register
            config_schema: Optional validation schema
            description: Human-readable description
            default_config: Default config values
            required_config: Required config keys

        Returns:
            Decorator function
        """

        def wrapper(cls: Type[P]) -> Type[P]:
            self.register(
                panel_type,
                cls,
                config_schema=config_schema,
                description=description,
                default_config=default_config,
                required_config=required_config,
            )
            return cls

        return wrapper


# Global panel registry instance
panel_registry = PanelRegistry()


def register_builtin_panels() -> None:
    """Register built-in panel types.

    This function registers the standard EMDX panels that are
    commonly used in layouts. Called during application startup.
    """
    from textual.containers import ScrollableContainer, Vertical
    from textual.widgets import DataTable, RichLog, Static

    # Basic container types
    panel_registry.register(
        "container",
        Vertical,
        description="Basic vertical container",
    )

    panel_registry.register(
        "scroll",
        ScrollableContainer,
        description="Scrollable container",
    )

    # Common widget types
    panel_registry.register(
        "table",
        DataTable,
        description="Data table for lists",
        default_config={"cursor_type": "row", "show_header": True},
    )

    panel_registry.register(
        "richlog",
        RichLog,
        description="Rich text log/preview",
        default_config={"wrap": True, "highlight": True, "markup": True},
    )

    panel_registry.register(
        "static",
        Static,
        description="Static text/status",
    )

    logger.debug("Registered built-in panel types")
