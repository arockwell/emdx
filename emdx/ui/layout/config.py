"""
Layout configuration dataclasses.

Defines the structure for layout specifications that can be
loaded from YAML or defined in Python code.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


class SizeUnit(Enum):
    """Units for specifying panel sizes."""

    FRACTION = "fr"  # Fractional units (like CSS fr)
    PERCENT = "%"  # Percentage of parent
    FIXED = "px"  # Fixed character/cell count
    AUTO = "auto"  # Auto-size based on content


@dataclass(frozen=True)
class SizeSpec:
    """Specification for panel sizing.

    Supports multiple sizing strategies:
    - Fractions: SizeSpec(1, "fr") or SizeSpec(2, "fr")
    - Percentages: SizeSpec(40, "%")
    - Fixed: SizeSpec(20, "px") (characters/cells)
    - Auto: SizeSpec.auto()

    Examples:
        >>> SizeSpec(1, "fr")  # 1 fractional unit
        >>> SizeSpec(40, "%")  # 40% of parent
        >>> SizeSpec(20, "px") # 20 characters wide
        >>> SizeSpec.auto()    # Auto-size
    """

    value: float
    unit: str = "fr"

    def __post_init__(self) -> None:
        """Validate the size specification."""
        valid_units = {"fr", "%", "px", "auto"}
        if self.unit not in valid_units:
            raise ValueError(f"Invalid unit '{self.unit}'. Must be one of: {valid_units}")
        if self.unit != "auto" and self.value < 0:
            raise ValueError("Size value must be non-negative")

    @classmethod
    def auto(cls) -> "SizeSpec":
        """Create an auto-size specification."""
        return cls(0, "auto")

    @classmethod
    def fraction(cls, value: float = 1) -> "SizeSpec":
        """Create a fractional size specification."""
        return cls(value, "fr")

    @classmethod
    def percent(cls, value: float) -> "SizeSpec":
        """Create a percentage size specification."""
        return cls(value, "%")

    @classmethod
    def fixed(cls, value: int) -> "SizeSpec":
        """Create a fixed size specification (in characters)."""
        return cls(value, "px")

    @classmethod
    def from_string(cls, spec: str) -> "SizeSpec":
        """Parse a size specification from a string.

        Args:
            spec: Size string like "1fr", "40%", "20px", or "auto"

        Returns:
            SizeSpec instance

        Examples:
            >>> SizeSpec.from_string("1fr")
            SizeSpec(value=1.0, unit='fr')
            >>> SizeSpec.from_string("40%")
            SizeSpec(value=40.0, unit='%')
        """
        spec = spec.strip().lower()
        if spec == "auto":
            return cls.auto()

        for unit in ("fr", "%", "px"):
            if spec.endswith(unit):
                value = float(spec[: -len(unit)])
                return cls(value, unit)

        # Default to fraction if no unit
        try:
            return cls(float(spec), "fr")
        except ValueError:
            raise ValueError(f"Invalid size specification: {spec}")

    def to_css(self) -> str:
        """Convert to Textual CSS-compatible size string."""
        if self.unit == "auto":
            return "auto"
        elif self.unit == "fr":
            return f"{int(self.value)}fr"
        elif self.unit == "%":
            return f"{int(self.value)}%"
        elif self.unit == "px":
            return f"{int(self.value)}"
        return f"{int(self.value)}fr"


@dataclass
class PanelSpec:
    """Specification for a panel within a layout.

    A panel is a leaf node in the layout tree that contains
    an actual widget (list, preview, status bar, etc.).

    Attributes:
        panel_type: Type of panel ("list", "preview", "status", etc.)
        panel_id: Unique ID for this panel instance
        config: Panel-specific configuration options
        size: Size specification for this panel
        collapsible: Whether the panel can be collapsed
        collapsed: Initial collapsed state
        min_size: Minimum size when visible
        classes: CSS classes to apply
    """

    panel_type: str
    panel_id: str
    config: Dict[str, Any] = field(default_factory=dict)
    size: SizeSpec = field(default_factory=lambda: SizeSpec.fraction(1))
    collapsible: bool = False
    collapsed: bool = False
    min_size: Optional[SizeSpec] = None
    classes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Process size field if it's a string."""
        if isinstance(self.size, str):
            object.__setattr__(self, "size", SizeSpec.from_string(self.size))
        if isinstance(self.min_size, str):
            object.__setattr__(self, "min_size", SizeSpec.from_string(self.min_size))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PanelSpec":
        """Create a PanelSpec from a dictionary (e.g., from YAML).

        Args:
            data: Dictionary with panel configuration

        Returns:
            PanelSpec instance
        """
        # Handle size conversion
        size = data.get("size", "1fr")
        if isinstance(size, str):
            size = SizeSpec.from_string(size)
        elif isinstance(size, dict):
            size = SizeSpec(size["value"], size.get("unit", "fr"))

        min_size = data.get("min_size")
        if isinstance(min_size, str):
            min_size = SizeSpec.from_string(min_size)
        elif isinstance(min_size, dict):
            min_size = SizeSpec(min_size["value"], min_size.get("unit", "fr"))

        return cls(
            panel_type=data["type"],
            panel_id=data["id"],
            config=data.get("config", {}),
            size=size,
            collapsible=data.get("collapsible", False),
            collapsed=data.get("collapsed", False),
            min_size=min_size,
            classes=data.get("classes", []),
        )


@dataclass
class SplitSpec:
    """Specification for a split container in the layout.

    A split divides space between children either horizontally
    or vertically. Children can be either panels or nested splits.

    Attributes:
        direction: Split direction ("horizontal" or "vertical")
        children: List of child specs (PanelSpec or SplitSpec)
        sizes: Size distribution for children (overrides child sizes)
        split_id: Optional unique ID for this split
        collapsible: Whether the entire split can be collapsed
        collapsed: Initial collapsed state
        classes: CSS classes to apply
    """

    direction: Literal["horizontal", "vertical"]
    children: List[Union[PanelSpec, "SplitSpec"]]
    sizes: Optional[List[SizeSpec]] = None
    split_id: Optional[str] = None
    collapsible: bool = False
    collapsed: bool = False
    classes: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and process the split specification."""
        if not self.children:
            raise ValueError("SplitSpec must have at least one child")

        # Process sizes if they're strings
        if self.sizes:
            processed_sizes = []
            for size in self.sizes:
                if isinstance(size, str):
                    processed_sizes.append(SizeSpec.from_string(size))
                elif isinstance(size, SizeSpec):
                    processed_sizes.append(size)
                else:
                    raise ValueError(f"Invalid size type: {type(size)}")
            self.sizes = processed_sizes

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitSpec":
        """Create a SplitSpec from a dictionary (e.g., from YAML).

        Args:
            data: Dictionary with split configuration

        Returns:
            SplitSpec instance
        """
        children = []
        for child_data in data.get("children", []):
            child_type = child_data.get("type", "")
            if child_type == "split":
                children.append(cls.from_dict(child_data))
            else:
                children.append(PanelSpec.from_dict(child_data))

        # Parse sizes
        sizes = None
        if "sizes" in data:
            sizes = [SizeSpec.from_string(s) if isinstance(s, str) else s for s in data["sizes"]]
        elif "ratio" in data:
            # Legacy support for ratio format like [40, 60]
            ratio = data["ratio"]
            total = sum(ratio)
            sizes = [SizeSpec.percent(r / total * 100) for r in ratio]

        return cls(
            direction=data.get("direction", "horizontal"),
            children=children,
            sizes=sizes,
            split_id=data.get("id"),
            collapsible=data.get("collapsible", False),
            collapsed=data.get("collapsed", False),
            classes=data.get("classes", []),
        )

    def get_child_sizes(self) -> List[SizeSpec]:
        """Get sizes for all children, using defaults if not specified.

        Returns:
            List of SizeSpec, one per child
        """
        if self.sizes and len(self.sizes) == len(self.children):
            return self.sizes

        # Fall back to child-specified sizes or equal fractions
        result = []
        for i, child in enumerate(self.children):
            if self.sizes and i < len(self.sizes):
                result.append(self.sizes[i])
            elif hasattr(child, "size"):
                result.append(child.size)
            else:
                result.append(SizeSpec.fraction(1))
        return result


@dataclass
class LayoutConfig:
    """Complete layout configuration.

    Represents a full layout that can be loaded, saved, and built.

    Attributes:
        name: Unique name for this layout
        root: The root split or panel specification
        theme: Optional theme name to apply
        description: Human-readable description
        version: Layout schema version for compatibility
        metadata: Additional metadata (author, created, etc.)
    """

    name: str
    root: Union[SplitSpec, PanelSpec]
    theme: Optional[str] = None
    description: str = ""
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "LayoutConfig":
        """Create a LayoutConfig from a dictionary (e.g., from YAML).

        Args:
            name: Layout name
            data: Dictionary with layout configuration

        Returns:
            LayoutConfig instance
        """
        root_data = data.get("root", data)

        # Determine if root is a split or panel
        if root_data.get("type") == "split" or "children" in root_data:
            root = SplitSpec.from_dict(root_data)
        else:
            root = PanelSpec.from_dict(root_data)

        return cls(
            name=name,
            root=root,
            theme=data.get("theme"),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert layout config to a dictionary for serialization.

        Returns:
            Dictionary representation suitable for YAML/JSON
        """
        return {
            "name": self.name,
            "theme": self.theme,
            "description": self.description,
            "version": self.version,
            "metadata": self.metadata,
            "root": self._node_to_dict(self.root),
        }

    def _node_to_dict(self, node: Union[SplitSpec, PanelSpec]) -> Dict[str, Any]:
        """Convert a layout node to a dictionary."""
        if isinstance(node, PanelSpec):
            result: Dict[str, Any] = {
                "type": node.panel_type,
                "id": node.panel_id,
            }
            if node.config:
                result["config"] = node.config
            if node.size.unit != "fr" or node.size.value != 1:
                result["size"] = f"{node.size.value}{node.size.unit}"
            if node.collapsible:
                result["collapsible"] = True
            if node.collapsed:
                result["collapsed"] = True
            if node.min_size:
                result["min_size"] = f"{node.min_size.value}{node.min_size.unit}"
            if node.classes:
                result["classes"] = node.classes
            return result
        elif isinstance(node, SplitSpec):
            result = {
                "type": "split",
                "direction": node.direction,
                "children": [self._node_to_dict(child) for child in node.children],
            }
            if node.sizes:
                result["sizes"] = [f"{s.value}{s.unit}" for s in node.sizes]
            if node.split_id:
                result["id"] = node.split_id
            if node.collapsible:
                result["collapsible"] = True
            if node.collapsed:
                result["collapsed"] = True
            if node.classes:
                result["classes"] = node.classes
            return result
        else:
            raise ValueError(f"Unknown node type: {type(node)}")
