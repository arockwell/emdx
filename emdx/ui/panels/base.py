"""
Panel Base Class - Abstract base implementing the panel protocol.

This provides default implementations for common panel patterns:
- Lifecycle management (mount, unmount, activate, deactivate)
- State save/restore
- Keybinding registration
- Status updates
- Error handling

Subclasses only need to implement what they need to customize.
"""

import logging
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget

from .messages import (
    ActionCompleted,
    ActionRequested,
    ErrorOccurred,
    ErrorSeverity,
    PanelActivated,
    PanelBlurred,
    PanelDeactivated,
    PanelFocused,
    SelectionChanged,
    SelectionData,
    StatusUpdate,
)
from .protocol import (
    KeyBinding,
    PanelCapability,
    PanelProtocol,
    PanelRequirement,
    PanelState,
    has_capability,
)

logger = logging.getLogger(__name__)


class PanelBase(Widget):
    """
    Abstract base class for EMDX panels.

    Implements the PanelProtocol with sensible defaults. Subclasses
    should override only what they need to customize.

    Class Attributes:
        PANEL_ID: Override to set the panel's unique identifier
        CAPABILITIES: Override to declare panel capabilities
        KEYBINDINGS: Override to declare keybindings
        REQUIREMENTS: Override to declare dependencies
        HELP_TITLE: Override to set help dialog title

    Reactive Attributes:
        mode: Current panel mode (NORMAL, SEARCH, EDIT, etc.)
        is_active: Whether this panel is the active panel
        is_visible: Whether this panel is currently visible

    Example:
        class DocumentListPanel(PanelBase):
            PANEL_ID = "document-list"
            CAPABILITIES = PanelCapability.LIST_PANEL | PanelCapability.SEARCHABLE
            HELP_TITLE = "Document List"

            KEYBINDINGS = [
                KeyBinding("j", "cursor_down", "Move down", "Navigation"),
                KeyBinding("k", "cursor_up", "Move up", "Navigation"),
                KeyBinding("/", "search", "Search", "Search"),
            ]

            def compose(self) -> ComposeResult:
                yield DataTable(id="doc-table")
    """

    # ==========================================================================
    # CLASS ATTRIBUTES - Override in subclasses
    # ==========================================================================

    PANEL_ID: str = "base-panel"
    CAPABILITIES: PanelCapability = PanelCapability.NONE
    KEYBINDINGS: Sequence[KeyBinding] = ()
    REQUIREMENTS: Sequence[PanelRequirement] = ()
    HELP_TITLE: str = "Panel"

    # ==========================================================================
    # REACTIVE ATTRIBUTES
    # ==========================================================================

    mode: reactive[str] = reactive("NORMAL")
    is_active: reactive[bool] = reactive(False)
    is_visible: reactive[bool] = reactive(True)

    # ==========================================================================
    # INITIALIZATION
    # ==========================================================================

    def __init__(
        self,
        *args,
        panel_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Initialize the panel.

        Args:
            panel_id: Override the class PANEL_ID for this instance
            *args: Passed to Widget.__init__
            **kwargs: Passed to Widget.__init__
        """
        super().__init__(*args, **kwargs)
        self._panel_id = panel_id or self.PANEL_ID
        self._selection: Optional[SelectionData] = None
        self._mounted = False
        self._resources: List[Any] = []  # Resources to clean up on unmount

    # ==========================================================================
    # PROTOCOL IMPLEMENTATION - Properties
    # ==========================================================================

    @property
    def panel_id(self) -> str:
        """Unique identifier for this panel instance."""
        return self._panel_id

    @property
    def capabilities(self) -> PanelCapability:
        """What this panel can do."""
        return self.CAPABILITIES

    @property
    def keybindings(self) -> Sequence[KeyBinding]:
        """Keybindings this panel handles."""
        return self.KEYBINDINGS

    @property
    def requirements(self) -> Sequence[PanelRequirement]:
        """Dependencies this panel needs."""
        return self.REQUIREMENTS

    @property
    def help_title(self) -> str:
        """Title for help dialog."""
        return self.HELP_TITLE

    # ==========================================================================
    # TEXTUAL BINDINGS - Generated from KEYBINDINGS
    # ==========================================================================

    @classmethod
    def _generate_bindings(cls) -> List[Binding]:
        """Generate Textual bindings from KEYBINDINGS."""
        bindings = []
        for kb in cls.KEYBINDINGS:
            bindings.append(
                Binding(
                    key=kb.key,
                    action=kb.action,
                    description=kb.description,
                    show=kb.show,
                    priority=kb.priority,
                )
            )
        return bindings

    def __init_subclass__(cls, **kwargs):
        """Auto-generate BINDINGS from KEYBINDINGS when class is created."""
        super().__init_subclass__(**kwargs)
        if cls.KEYBINDINGS:
            # Merge with any existing BINDINGS
            existing = list(getattr(cls, "BINDINGS", []))
            generated = cls._generate_bindings()
            # Avoid duplicates by checking action names
            existing_actions = {
                b.action if hasattr(b, "action") else b[1] for b in existing
            }
            for binding in generated:
                if binding.action not in existing_actions:
                    existing.append(binding)
            cls.BINDINGS = existing

    # ==========================================================================
    # LIFECYCLE METHODS
    # ==========================================================================

    async def on_mount(self) -> None:
        """
        Called when panel is mounted to the DOM.

        Override to perform initialization that requires the DOM.
        Always call super().on_mount() first.
        """
        self._mounted = True
        logger.debug(f"Panel {self.panel_id} mounted")

    async def on_unmount(self) -> None:
        """
        Called when panel is removed from the DOM.

        Override to perform cleanup. Always call super().on_unmount() last.
        """
        await self._cleanup_resources()
        self._mounted = False
        logger.debug(f"Panel {self.panel_id} unmounted")

    async def on_activate(self) -> None:
        """
        Called when panel becomes the active panel.

        Override to start background processes, refresh data, etc.
        Emits PanelActivated message.
        """
        self.is_active = True
        self.post_message(PanelActivated(self.panel_id))
        logger.debug(f"Panel {self.panel_id} activated")

    async def on_deactivate(self) -> None:
        """
        Called when panel loses active status.

        Override to pause background processes, save state, etc.
        Emits PanelDeactivated message.
        """
        self.is_active = False
        self.post_message(PanelDeactivated(self.panel_id))
        logger.debug(f"Panel {self.panel_id} deactivated")

    async def on_show(self) -> None:
        """Called when panel becomes visible."""
        self.is_visible = True
        logger.debug(f"Panel {self.panel_id} shown")

    async def on_hide(self) -> None:
        """Called when panel becomes hidden."""
        self.is_visible = False
        logger.debug(f"Panel {self.panel_id} hidden")

    def on_focus(self) -> None:
        """Called when panel receives keyboard focus."""
        self.post_message(PanelFocused(self.panel_id))

    def on_blur(self) -> None:
        """Called when panel loses keyboard focus."""
        self.post_message(PanelBlurred(self.panel_id))

    # ==========================================================================
    # STATE MANAGEMENT
    # ==========================================================================

    def save_state(self) -> PanelState:
        """
        Save current panel state for later restoration.

        Override to save additional state. Call super().save_state()
        and update the returned state.

        Returns:
            PanelState with current state
        """
        return PanelState(
            panel_id=self.panel_id,
            mode=self.mode,
            selection=self._selection,
        )

    def restore_state(self, state: PanelState) -> None:
        """
        Restore panel state from a previous save.

        Override to restore additional state. Call super().restore_state()
        first.

        Args:
            state: Previously saved state
        """
        if state.panel_id != self.panel_id:
            logger.warning(
                f"State panel_id mismatch: {state.panel_id} != {self.panel_id}"
            )
        self.mode = state.mode
        self._selection = state.selection

    # ==========================================================================
    # SELECTION MANAGEMENT
    # ==========================================================================

    def get_selected_item(self) -> Optional[Any]:
        """
        Get the currently selected item.

        Override for panels with custom selection handling.

        Returns:
            The selected item, or None if nothing selected
        """
        if self._selection:
            return self._selection.item_id
        return None

    def get_selected_items(self) -> Sequence[Any]:
        """
        Get all selected items (for multi-select).

        Returns:
            Sequence of selected items
        """
        if self._selection and self._selection.item_ids:
            return self._selection.item_ids
        item = self.get_selected_item()
        return [item] if item is not None else []

    async def set_selection(self, item_id: Any) -> bool:
        """
        Select an item by its identifier.

        Override in subclasses to implement actual selection logic.

        Args:
            item_id: Identifier of item to select

        Returns:
            True if item was found and selected
        """
        previous = self._selection
        self._selection = SelectionData(item_id=item_id)
        self._emit_selection_changed(previous)
        return True

    def _emit_selection_changed(
        self, previous: Optional[SelectionData] = None
    ) -> None:
        """
        Emit a SelectionChanged message.

        Called automatically by set_selection. Can also be called
        directly when selection changes through other means.

        Args:
            previous: Previous selection data for undo support
        """
        if self._selection:
            self.post_message(
                SelectionChanged(
                    source_panel_id=self.panel_id,
                    selection=self._selection,
                    previous_selection=previous,
                )
            )

    # ==========================================================================
    # REFRESH AND UPDATE
    # ==========================================================================

    async def refresh(self) -> None:
        """
        Refresh panel content from data source.

        Override to implement refresh logic. This base implementation
        does nothing.
        """
        logger.debug(f"Panel {self.panel_id} refresh (no-op in base)")

    def update_status(self, message: str) -> None:
        """
        Update the panel's status display.

        Emits a StatusUpdate message. Override if panel has its own
        status display widget.

        Args:
            message: Status message to display
        """
        self.post_message(StatusUpdate(self.panel_id, message))

    # ==========================================================================
    # ACTION HANDLING
    # ==========================================================================

    def request_action(
        self,
        action: str,
        target_id: Optional[Any] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Request an action to be performed.

        Emits an ActionRequested message for the host container
        or another panel to handle.

        Args:
            action: Name of the action
            target_id: Target of the action
            parameters: Additional parameters
        """
        self.post_message(
            ActionRequested(
                source_panel_id=self.panel_id,
                action=action,
                target_id=target_id,
                parameters=parameters,
            )
        )

    def complete_action(
        self,
        action: str,
        success: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Signal that an action has completed.

        Emits an ActionCompleted message.

        Args:
            action: Name of the action
            success: Whether it succeeded
            result: Result if successful
            error: Error message if failed
        """
        self.post_message(
            ActionCompleted(
                source_panel_id=self.panel_id,
                action=action,
                success=success,
                result=result,
                error=error,
            )
        )

    # ==========================================================================
    # ERROR HANDLING
    # ==========================================================================

    def report_error(
        self,
        error: Exception | str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[str] = None,
        recoverable: bool = True,
    ) -> None:
        """
        Report an error that occurred in this panel.

        Emits an ErrorOccurred message and logs the error.

        Args:
            error: The exception or error message
            severity: How severe the error is
            context: Additional context
            recoverable: Whether the panel can continue
        """
        message = str(error) if isinstance(error, Exception) else error
        logger.log(
            logging.ERROR if severity in (ErrorSeverity.ERROR, ErrorSeverity.CRITICAL)
            else logging.WARNING,
            f"Panel {self.panel_id}: {message}",
            exc_info=isinstance(error, Exception),
        )

        self.post_message(
            ErrorOccurred(
                source_panel_id=self.panel_id,
                error=error,
                severity=severity,
                context=context,
                recoverable=recoverable,
            )
        )

    # ==========================================================================
    # CAPABILITY HELPERS
    # ==========================================================================

    def has_capability(self, capability: PanelCapability) -> bool:
        """
        Check if this panel has a specific capability.

        Args:
            capability: Capability to check

        Returns:
            True if panel has the capability
        """
        return has_capability(self, capability)

    # ==========================================================================
    # RESOURCE MANAGEMENT
    # ==========================================================================

    def register_resource(self, resource: Any) -> None:
        """
        Register a resource for cleanup on unmount.

        Use this for streams, subscriptions, timers, etc.
        Resources are cleaned up in reverse registration order.

        Args:
            resource: Resource to register
        """
        self._resources.append(resource)

    async def _cleanup_resources(self) -> None:
        """Clean up all registered resources."""
        for resource in reversed(self._resources):
            try:
                if hasattr(resource, "close"):
                    if hasattr(resource.close, "__await__"):
                        await resource.close()
                    else:
                        resource.close()
                elif hasattr(resource, "stop"):
                    if hasattr(resource.stop, "__await__"):
                        await resource.stop()
                    else:
                        resource.stop()
                elif hasattr(resource, "unsubscribe"):
                    resource.unsubscribe()
                elif callable(resource):
                    resource()
            except Exception as e:
                logger.warning(f"Error cleaning up resource: {e}")
        self._resources.clear()

    # ==========================================================================
    # HELP INTEGRATION
    # ==========================================================================

    def get_help_bindings(self) -> List[Tuple[str, str, str]]:
        """
        Get keybindings formatted for help display.

        Returns:
            List of (category, key, description) tuples
        """
        result = []
        for kb in self.keybindings:
            result.append((kb.category, kb.key, kb.description))
        return result

    def action_show_help(self) -> None:
        """Show help modal with this panel's keybindings."""
        try:
            from ..modals import KeybindingsHelpScreen
            bindings = self.get_help_bindings()
            self.app.push_screen(
                KeybindingsHelpScreen(bindings=bindings, title=self.help_title)
            )
        except Exception as e:
            logger.warning(f"Could not show help: {e}")

    # ==========================================================================
    # MODE MANAGEMENT
    # ==========================================================================

    def enter_mode(self, mode: str) -> None:
        """
        Enter a new mode.

        Args:
            mode: Mode to enter (e.g., "SEARCH", "EDIT")
        """
        previous = self.mode
        self.mode = mode
        logger.debug(f"Panel {self.panel_id}: {previous} -> {mode}")

    def exit_mode(self) -> None:
        """Exit current mode and return to NORMAL."""
        self.enter_mode("NORMAL")

    def is_in_mode(self, mode: str) -> bool:
        """Check if panel is in a specific mode."""
        return self.mode == mode

    # ==========================================================================
    # ABSTRACT METHODS - Must be implemented by subclasses
    # ==========================================================================

    @abstractmethod
    def compose(self) -> ComposeResult:
        """
        Compose the panel's widget structure.

        This is the standard Textual compose method. Subclasses MUST
        implement this to define their UI structure.

        Yields:
            Child widgets for this panel
        """
        ...
