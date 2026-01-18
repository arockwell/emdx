"""
Panel Protocol - The interface contract all EMDX panels must implement.

This defines what a panel IS and what it CAN DO using Python's Protocol
for structural subtyping. Panels that implement this protocol are guaranteed
to work with the panel management system.

Key Design Decisions:
1. Minimal required methods - only what's absolutely necessary
2. Optional methods via PanelCapability flags
3. Property-based introspection for keybindings and requirements
4. Async lifecycle hooks for clean resource management
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    TypeVar,
    Union,
    runtime_checkable,
)


class PanelCapability(Flag):
    """
    Capabilities a panel can declare.

    Used for:
    - Feature discovery by host containers
    - Enabling/disabling context-specific actions
    - Documentation and help generation

    Panels declare their capabilities via the `capabilities` property.
    """

    NONE = 0

    # Navigation capabilities
    NAVIGABLE = auto()  # Supports j/k cursor navigation
    SEARCHABLE = auto()  # Supports / search mode
    FILTERABLE = auto()  # Supports filtering content
    EXPANDABLE = auto()  # Supports h/l expand/collapse (hierarchical)
    SCROLLABLE = auto()  # Supports scrolling (g/G to top/bottom)

    # Selection capabilities
    SELECTABLE = auto()  # Supports item selection
    MULTI_SELECT = auto()  # Supports selecting multiple items
    TEXT_SELECTABLE = auto()  # Supports text selection mode

    # Content capabilities
    EDITABLE = auto()  # Content can be edited
    PREVIEWABLE = auto()  # Can show preview of content
    REFRESHABLE = auto()  # Can refresh its content

    # State capabilities
    STATEFUL = auto()  # Supports save/restore state
    FOCUSABLE = auto()  # Can receive focus

    # Common combinations
    LIST_PANEL = NAVIGABLE | SELECTABLE | SCROLLABLE | FOCUSABLE
    PREVIEW_PANEL = SCROLLABLE | TEXT_SELECTABLE | PREVIEWABLE | FOCUSABLE
    INPUT_PANEL = FOCUSABLE | EDITABLE


@dataclass(frozen=True)
class PanelRequirement:
    """
    A dependency requirement for a panel.

    Panels can declare requirements for services, data sources, or other
    panels they need to function. The host container is responsible for
    satisfying these requirements before mounting the panel.

    Examples:
        - PanelRequirement("database", required=True)
        - PanelRequirement("preview_panel", required=False, provides=["content"])
    """

    name: str  # Identifier for the requirement
    required: bool = True  # Whether the panel can function without it
    provides: Tuple[str, ...] = ()  # What the requirement provides
    description: str = ""  # Human-readable description

    def __hash__(self) -> int:
        return hash((self.name, self.required, self.provides))


@dataclass(frozen=True)
class KeyBinding:
    """
    Declaration of a keybinding for a panel.

    This is used for:
    - Registering bindings with the keybinding registry
    - Generating help documentation
    - Conflict detection at startup

    Attributes:
        key: The key or key combination (e.g., "j", "ctrl+s", "shift+tab")
        action: The action method name (e.g., "cursor_down", "save")
        description: Human-readable description for help
        category: Category for grouping in help (e.g., "Navigation", "Actions")
        show: Whether to show in help/footer
        priority: Textual priority flag for binding precedence
        modes: Set of modes where this binding is active (empty = all modes)
    """

    key: str
    action: str
    description: str
    category: str = "General"
    show: bool = True
    priority: bool = False
    modes: frozenset = field(default_factory=frozenset)

    def to_textual_binding(self) -> Tuple[str, str, str]:
        """Convert to Textual binding tuple format."""
        return (self.key, self.action, self.description)

    def __hash__(self) -> int:
        return hash((self.key, self.action, self.category))


@dataclass
class PanelState:
    """
    Serializable state of a panel for save/restore.

    Panels can extend this to add their own state fields.
    The base state includes common attributes all panels might need.
    """

    panel_id: str
    mode: str = "NORMAL"
    cursor_position: Optional[Tuple[int, int]] = None
    scroll_position: Optional[Tuple[int, int]] = None
    selection: Optional[Any] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state to dictionary."""
        return {
            "panel_id": self.panel_id,
            "mode": self.mode,
            "cursor_position": self.cursor_position,
            "scroll_position": self.scroll_position,
            "selection": self.selection,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PanelState":
        """Deserialize state from dictionary."""
        return cls(
            panel_id=data.get("panel_id", ""),
            mode=data.get("mode", "NORMAL"),
            cursor_position=tuple(data["cursor_position"])
            if data.get("cursor_position")
            else None,
            scroll_position=tuple(data["scroll_position"])
            if data.get("scroll_position")
            else None,
            selection=data.get("selection"),
            extra=data.get("extra", {}),
        )


@runtime_checkable
class PanelProtocol(Protocol):
    """
    The core protocol that all panels must implement.

    This uses Python's structural subtyping - any class that implements
    these methods/properties IS a Panel, regardless of inheritance.

    Required Methods (MUST implement):
    ---------------------------------
    - panel_id: Unique identifier for this panel instance
    - capabilities: What this panel can do
    - compose(): Textual's compose method for widget structure
    - on_mount(): Lifecycle hook when panel is mounted

    Optional Methods (implement based on capabilities):
    --------------------------------------------------
    - keybindings: Declared keybindings (if NAVIGABLE or similar)
    - requirements: Dependencies (if panel needs external services)
    - save_state/restore_state: State management (if STATEFUL)
    - on_activate/on_deactivate: Focus lifecycle (if FOCUSABLE)

    Example Implementation:
        class MyPanel(PanelBase):
            @property
            def panel_id(self) -> str:
                return "my-panel"

            @property
            def capabilities(self) -> PanelCapability:
                return PanelCapability.LIST_PANEL | PanelCapability.SEARCHABLE
    """

    # ==========================================================================
    # REQUIRED PROPERTIES - Every panel MUST implement these
    # ==========================================================================

    @property
    def panel_id(self) -> str:
        """
        Unique identifier for this panel instance.

        Used for:
        - Message routing between panels
        - State save/restore keying
        - Logging and debugging

        Should be unique within a container. Convention: lowercase-with-dashes
        Examples: "document-list", "preview", "search-input"
        """
        ...

    @property
    def capabilities(self) -> PanelCapability:
        """
        Declare what this panel can do.

        Host containers use this to:
        - Enable/disable actions in menus
        - Route appropriate messages
        - Generate accurate help

        Example:
            return PanelCapability.NAVIGABLE | PanelCapability.SELECTABLE
        """
        ...

    # ==========================================================================
    # OPTIONAL PROPERTIES - Implement based on capabilities
    # ==========================================================================

    @property
    def keybindings(self) -> Sequence[KeyBinding]:
        """
        Declare keybindings this panel handles.

        Return empty sequence if panel has no keybindings.
        Keybindings are registered with the central registry at startup.

        Example:
            return [
                KeyBinding("j", "cursor_down", "Move down", category="Navigation"),
                KeyBinding("k", "cursor_up", "Move up", category="Navigation"),
            ]
        """
        ...

    @property
    def requirements(self) -> Sequence[PanelRequirement]:
        """
        Declare dependencies this panel needs.

        The host container ensures requirements are satisfied before
        mounting the panel. Optional dependencies are provided if available.

        Example:
            return [
                PanelRequirement("database", required=True),
                PanelRequirement("preview_panel", required=False),
            ]
        """
        ...

    @property
    def mode(self) -> str:
        """
        Current mode of the panel (e.g., "NORMAL", "SEARCH", "EDIT").

        Used for:
        - Mode-specific keybinding activation
        - Status display
        - State save/restore
        """
        ...

    @property
    def help_title(self) -> str:
        """
        Title for the help dialog.

        Used when generating help documentation for this panel.
        """
        ...

    # ==========================================================================
    # LIFECYCLE METHODS - Called by host container
    # ==========================================================================

    async def on_activate(self) -> None:
        """
        Called when panel becomes the active/focused panel.

        Use for:
        - Starting background processes
        - Refreshing stale data
        - Subscribing to event streams
        """
        ...

    async def on_deactivate(self) -> None:
        """
        Called when panel loses active status.

        Use for:
        - Pausing background processes
        - Cleaning up resources
        - Unsubscribing from event streams
        """
        ...

    async def on_show(self) -> None:
        """
        Called when panel becomes visible.

        Distinct from on_activate - a panel can be visible but not active
        (e.g., in a split view where another panel has focus).
        """
        ...

    async def on_hide(self) -> None:
        """
        Called when panel becomes hidden.

        Use for pausing expensive rendering or animations.
        """
        ...

    # ==========================================================================
    # STATE MANAGEMENT - For STATEFUL capability
    # ==========================================================================

    def save_state(self) -> PanelState:
        """
        Save current panel state for later restoration.

        Called:
        - When switching away from this panel
        - Before app shutdown
        - On explicit save request

        Returns:
            PanelState with all necessary state to restore later
        """
        ...

    def restore_state(self, state: PanelState) -> None:
        """
        Restore panel state from a previous save.

        Called:
        - When switching back to this panel
        - After app startup with saved state
        - On explicit restore request

        Args:
            state: Previously saved state from save_state()
        """
        ...

    # ==========================================================================
    # CONTENT AND SELECTION - For SELECTABLE/PREVIEWABLE capabilities
    # ==========================================================================

    def get_selected_item(self) -> Optional[Any]:
        """
        Get the currently selected item.

        For list panels, this is typically the item at cursor position.
        For preview panels, this might be the current document.

        Returns:
            The selected item, or None if nothing selected
        """
        ...

    def get_selected_items(self) -> Sequence[Any]:
        """
        Get all selected items (for MULTI_SELECT capability).

        Returns:
            Sequence of selected items, empty if none selected
        """
        ...

    async def set_selection(self, item_id: Any) -> bool:
        """
        Select an item by its identifier.

        Args:
            item_id: Identifier of item to select

        Returns:
            True if item was found and selected, False otherwise
        """
        ...

    # ==========================================================================
    # REFRESH AND UPDATE - For REFRESHABLE capability
    # ==========================================================================

    async def refresh(self) -> None:
        """
        Refresh panel content from data source.

        Called:
        - On user request (r key)
        - When data source signals changes
        - After operations that might have changed data
        """
        ...

    def update_status(self, message: str) -> None:
        """
        Update the panel's status display.

        Panels can show status in their own status bar or emit
        a StatusUpdate message for the container to handle.

        Args:
            message: Status message to display
        """
        ...


# Type variable for generic panel operations
PanelT = TypeVar("PanelT", bound=PanelProtocol)


def is_panel(obj: Any) -> bool:
    """
    Check if an object implements the panel protocol.

    Uses runtime_checkable protocol for duck typing.

    Args:
        obj: Object to check

    Returns:
        True if object implements PanelProtocol
    """
    return isinstance(obj, PanelProtocol)


def has_capability(panel: PanelProtocol, capability: PanelCapability) -> bool:
    """
    Check if a panel has a specific capability.

    Args:
        panel: Panel to check
        capability: Capability to check for

    Returns:
        True if panel has the capability

    Example:
        if has_capability(panel, PanelCapability.SEARCHABLE):
            panel.action_search()
    """
    return bool(panel.capabilities & capability)


def get_panel_keybindings(panel: PanelProtocol) -> List[KeyBinding]:
    """
    Get keybindings from a panel, with safe fallback.

    Args:
        panel: Panel to get keybindings from

    Returns:
        List of keybindings, empty list if not implemented
    """
    try:
        bindings = panel.keybindings
        return list(bindings) if bindings else []
    except (AttributeError, NotImplementedError):
        return []
