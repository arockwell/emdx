"""
Panel Messages - Standard communication between panels.

This module defines the message types that panels use to communicate
with each other and with their host container. Using messages instead
of direct method calls enables:

1. Loose coupling - panels don't need references to each other
2. Event-driven architecture - easy to add observers
3. Testability - messages can be captured and verified
4. Debugging - message flow can be logged and traced

Message Categories:
- Lifecycle: PanelActivated, PanelDeactivated, PanelFocused, PanelBlurred
- Selection: SelectionChanged
- Navigation: NavigationRequested
- Content: ContentRequested, ContentProvided
- Actions: ActionRequested, ActionCompleted
- Errors: ErrorOccurred
- Status: StatusUpdate
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Sequence, Type, Union

from textual.message import Message


class PanelMessage(Message):
    """
    Base class for all panel messages.

    Provides:
    - Source panel identification
    - Timestamp (inherited from Message)
    - Bubble behavior control

    All panel messages should inherit from this.
    """

    def __init__(
        self,
        source_panel_id: str = "",
        *,
        bubble: bool = True,
    ) -> None:
        """
        Initialize panel message.

        Args:
            source_panel_id: ID of the panel that sent this message
            bubble: Whether message should bubble up the DOM tree
        """
        super().__init__()
        self.source_panel_id = source_panel_id
        self._bubble = bubble

    @property
    def panel_id(self) -> str:
        """Alias for source_panel_id for convenience."""
        return self.source_panel_id


# =============================================================================
# LIFECYCLE MESSAGES
# =============================================================================


class PanelActivated(PanelMessage):
    """
    Sent when a panel becomes the active/focused panel.

    Host containers can listen to this to update UI state,
    enable panel-specific menus, etc.

    Attributes:
        source_panel_id: ID of the panel that was activated
        previous_panel_id: ID of the previously active panel (if any)
    """

    def __init__(
        self,
        source_panel_id: str,
        previous_panel_id: Optional[str] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.previous_panel_id = previous_panel_id


class PanelDeactivated(PanelMessage):
    """
    Sent when a panel loses active status.

    Attributes:
        source_panel_id: ID of the panel that was deactivated
        next_panel_id: ID of the panel being activated (if any)
    """

    def __init__(
        self,
        source_panel_id: str,
        next_panel_id: Optional[str] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.next_panel_id = next_panel_id


class PanelFocused(PanelMessage):
    """
    Sent when a panel receives keyboard focus.

    Distinct from PanelActivated - focus is about keyboard input,
    activation is about being the "current" panel.
    """

    pass


class PanelBlurred(PanelMessage):
    """
    Sent when a panel loses keyboard focus.
    """

    pass


# =============================================================================
# SELECTION MESSAGES
# =============================================================================


@dataclass
class SelectionData:
    """
    Data about a selection in a panel.

    Flexible structure that can represent:
    - Single item selection (list panels)
    - Multiple item selection (multi-select panels)
    - Text selection (preview panels)
    - Custom selection types
    """

    item_id: Optional[Any] = None
    item_ids: Sequence[Any] = field(default_factory=list)
    item_data: Optional[Dict[str, Any]] = None
    text_range: Optional[tuple] = None  # (start, end) for text selection
    metadata: Dict[str, Any] = field(default_factory=dict)


class SelectionChanged(PanelMessage):
    """
    Sent when panel selection changes.

    Other panels can listen to this to update their content.
    For example, a preview panel listens to selection changes
    from a list panel to show the selected item's content.

    Attributes:
        selection: Data about the new selection
        previous_selection: Data about the previous selection (for undo)
    """

    def __init__(
        self,
        source_panel_id: str,
        selection: SelectionData,
        previous_selection: Optional[SelectionData] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.selection = selection
        self.previous_selection = previous_selection

    @property
    def item_id(self) -> Optional[Any]:
        """Convenience accessor for single item selection."""
        return self.selection.item_id

    @property
    def item_data(self) -> Optional[Dict[str, Any]]:
        """Convenience accessor for item data."""
        return self.selection.item_data


# =============================================================================
# NAVIGATION MESSAGES
# =============================================================================


class NavigationDirection(Enum):
    """Direction for navigation requests."""

    NEXT = auto()  # Move to next item/panel
    PREVIOUS = auto()  # Move to previous item/panel
    UP = auto()  # Move up (parent in hierarchy)
    DOWN = auto()  # Move down (child in hierarchy)
    HOME = auto()  # Move to first item
    END = auto()  # Move to last item
    PAGE_UP = auto()  # Page up
    PAGE_DOWN = auto()  # Page down


class NavigationRequested(PanelMessage):
    """
    Request navigation from one panel/item to another.

    Panels emit this when they want the host container to handle
    navigation logic (e.g., switching panels, navigating hierarchy).

    Attributes:
        direction: Which direction to navigate
        target_panel_id: Specific panel to navigate to (optional)
        target_item_id: Specific item to navigate to (optional)
        metadata: Additional navigation context
    """

    def __init__(
        self,
        source_panel_id: str,
        direction: NavigationDirection,
        target_panel_id: Optional[str] = None,
        target_item_id: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.direction = direction
        self.target_panel_id = target_panel_id
        self.target_item_id = target_item_id
        self.metadata = metadata or {}


# =============================================================================
# CONTENT MESSAGES
# =============================================================================


class ContentRequested(PanelMessage):
    """
    Request content from a data source or another panel.

    Preview panels might emit this when they need content for
    a selected item. The host container or a data provider panel
    responds with ContentProvided.

    Attributes:
        content_id: Identifier for the requested content
        content_type: Type of content requested (e.g., "document", "preview")
        options: Additional options for content retrieval
    """

    def __init__(
        self,
        source_panel_id: str,
        content_id: Any,
        content_type: str = "default",
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.content_id = content_id
        self.content_type = content_type
        self.options = options or {}


class ContentProvided(PanelMessage):
    """
    Response to ContentRequested with the actual content.

    Attributes:
        content_id: Identifier for this content (matches request)
        content: The actual content (type depends on content_type)
        content_type: Type of content provided
        metadata: Additional metadata about the content
    """

    def __init__(
        self,
        source_panel_id: str,
        content_id: Any,
        content: Any,
        content_type: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.content_id = content_id
        self.content = content
        self.content_type = content_type
        self.metadata = metadata or {}


# =============================================================================
# ACTION MESSAGES
# =============================================================================


class ActionRequested(PanelMessage):
    """
    Request an action to be performed.

    Panels can request actions that should be handled by the host
    container or another panel. This enables loose coupling between
    action triggers and action handlers.

    Attributes:
        action: Name of the action (e.g., "delete", "edit", "save")
        target_id: Target of the action (e.g., document ID)
        parameters: Additional parameters for the action
    """

    def __init__(
        self,
        source_panel_id: str,
        action: str,
        target_id: Optional[Any] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.action = action
        self.target_id = target_id
        self.parameters = parameters or {}


class ActionCompleted(PanelMessage):
    """
    Notification that an action has completed.

    Sent after ActionRequested is handled, regardless of success/failure.

    Attributes:
        action: Name of the action that completed
        success: Whether the action succeeded
        result: Result of the action (if any)
        error: Error message if action failed
    """

    def __init__(
        self,
        source_panel_id: str,
        action: str,
        success: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        super().__init__(source_panel_id)
        self.action = action
        self.success = success
        self.result = result
        self.error = error


# =============================================================================
# ERROR MESSAGES
# =============================================================================


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    INFO = auto()  # Informational, not really an error
    WARNING = auto()  # Something might be wrong
    ERROR = auto()  # Something went wrong
    CRITICAL = auto()  # Something went very wrong


class ErrorOccurred(PanelMessage):
    """
    Notification that an error occurred in a panel.

    Host containers can display these errors in a status bar,
    notification area, or error log.

    Attributes:
        error: The exception or error message
        severity: How severe the error is
        context: Additional context about where/why the error occurred
        recoverable: Whether the panel can continue operating
    """

    def __init__(
        self,
        source_panel_id: str,
        error: Union[Exception, str],
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[str] = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(source_panel_id)
        self.error = error
        self.severity = severity
        self.context = context
        self.recoverable = recoverable

    @property
    def message(self) -> str:
        """Get error message as string."""
        if isinstance(self.error, Exception):
            return str(self.error)
        return self.error


# =============================================================================
# STATUS MESSAGES
# =============================================================================


class StatusUpdate(PanelMessage):
    """
    Request to update the status display.

    Panels emit this to update the global status bar or their
    own status area. The host container decides where to display it.

    Attributes:
        message: Status message to display
        persistent: Whether status should persist or be temporary
        timeout: How long to show temporary status (seconds)
    """

    def __init__(
        self,
        source_panel_id: str,
        message: str,
        persistent: bool = False,
        timeout: float = 3.0,
    ) -> None:
        super().__init__(source_panel_id)
        self.message = message
        self.persistent = persistent
        self.timeout = timeout


# =============================================================================
# MESSAGE HANDLER HELPERS
# =============================================================================


def message_handler(
    message_type: Type[PanelMessage],
) -> "Callable[[Any], Callable]":
    """
    Decorator for panel message handlers.

    This is a helper that works with Textual's message handling
    while providing type hints for IDE support.

    Usage:
        @message_handler(SelectionChanged)
        async def handle_selection(self, event: SelectionChanged) -> None:
            # Handle selection change
            pass

    Note: This is documentation-only. Actual handler registration
    uses Textual's on_* naming convention.
    """

    def decorator(func: "Callable") -> "Callable":
        func._handles_message = message_type
        return func

    return decorator


def filter_messages_from_panel(
    messages: Sequence[PanelMessage],
    panel_id: str,
) -> List[PanelMessage]:
    """
    Filter messages to only those from a specific panel.

    Useful for testing and debugging.

    Args:
        messages: Sequence of messages to filter
        panel_id: Panel ID to filter by

    Returns:
        List of messages from the specified panel
    """
    return [m for m in messages if m.source_panel_id == panel_id]


def filter_messages_by_type(
    messages: Sequence[PanelMessage],
    message_type: Type[PanelMessage],
) -> List[PanelMessage]:
    """
    Filter messages by type.

    Args:
        messages: Sequence of messages to filter
        message_type: Type to filter by

    Returns:
        List of messages of the specified type
    """
    return [m for m in messages if isinstance(m, message_type)]
