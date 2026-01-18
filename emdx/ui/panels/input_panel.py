"""
InputPanel - A modal input panel for search, tags, and other text entry.

This panel provides a flexible input mechanism that can be used for:
- Search/filter queries
- Tag entry
- General text prompts
- Multi-line input with confirmation

Features:
- Multiple input modes (search, tag, prompt)
- Overlay or inline display
- Input validation
- History support
- Autocomplete hooks

Example usage:
    class MyBrowser(Widget):
        def compose(self):
            yield InputPanel(id="search-input", mode=InputMode.SEARCH)

        def action_search(self):
            input_panel = self.query_one("#search-input", InputPanel)
            input_panel.show("Search:", callback=self.do_search)

        async def do_search(self, query: str):
            # Handle search
            pass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, Static

logger = logging.getLogger(__name__)


class InputMode(Enum):
    """Input panel modes."""

    SEARCH = auto()  # Search/filter input
    TAG = auto()  # Tag entry (space-separated)
    PROMPT = auto()  # General text prompt
    CONFIRM = auto()  # Yes/no confirmation


@dataclass
class InputPanelConfig:
    """Configuration for InputPanel behavior.

    Attributes:
        show_label: Whether to show input label
        show_hints: Whether to show key hints
        clear_on_submit: Clear input after submission
        clear_on_cancel: Clear input when cancelled
        history_enabled: Enable input history
        max_history: Maximum history entries
        validate_on_change: Validate input as user types
    """

    show_label: bool = True
    show_hints: bool = True
    clear_on_submit: bool = True
    clear_on_cancel: bool = True
    history_enabled: bool = True
    max_history: int = 50
    validate_on_change: bool = False


# Type alias for input callbacks
InputCallback = Callable[[str], Union[None, Awaitable[None]]]
ValidationCallback = Callable[[str], Union[bool, str]]


class InputPanel(Widget):
    """Modal input panel for text entry.

    This widget provides a flexible input mechanism that appears
    when activated and disappears after submission or cancellation.

    Messages:
        InputSubmitted: Fired when input is submitted (Enter)
        InputCancelled: Fired when input is cancelled (Escape)
        InputChanged: Fired when input value changes
        ValidationFailed: Fired when validation fails
    """

    DEFAULT_CSS = """
    InputPanel {
        layout: vertical;
        height: auto;
        display: none;
        padding: 0;
        margin: 0;
        layer: overlay;
    }

    InputPanel.visible {
        display: block;
    }

    InputPanel.overlay {
        dock: top;
        margin: 1;
        border: solid $primary;
        background: $surface;
        padding: 1;
    }

    InputPanel.inline {
        height: 3;
        border-bottom: solid $primary;
        background: $boost;
    }

    InputPanel #input-container {
        layout: horizontal;
        height: auto;
    }

    InputPanel #input-label {
        width: auto;
        padding: 0 1 0 0;
        color: $accent;
    }

    InputPanel #input-field {
        width: 1fr;
    }

    InputPanel #input-hints {
        height: 1;
        color: $text-muted;
        padding: 0;
        text-align: right;
    }

    InputPanel #input-error {
        height: 1;
        color: $error;
        padding: 0;
        display: none;
    }

    InputPanel #input-error.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "submit", "Submit", show=False),
        Binding("up", "history_prev", "Previous", show=False),
        Binding("down", "history_next", "Next", show=False),
    ]

    # Reactive properties
    is_active: reactive[bool] = reactive(False)
    current_mode: reactive[InputMode] = reactive(InputMode.SEARCH)
    error_message: reactive[str] = reactive("")

    # Messages
    class InputSubmitted(Message):
        """Fired when input is submitted."""

        def __init__(self, value: str, mode: InputMode) -> None:
            self.value = value
            self.mode = mode
            super().__init__()

    class InputCancelled(Message):
        """Fired when input is cancelled."""

        def __init__(self, mode: InputMode) -> None:
            self.mode = mode
            super().__init__()

    class InputChanged(Message):
        """Fired when input value changes."""

        def __init__(self, value: str, mode: InputMode) -> None:
            self.value = value
            self.mode = mode
            super().__init__()

    class ValidationFailed(Message):
        """Fired when validation fails."""

        def __init__(self, value: str, error: str) -> None:
            self.value = value
            self.error = error
            super().__init__()

    def __init__(
        self,
        mode: InputMode = InputMode.SEARCH,
        config: Optional[InputPanelConfig] = None,
        overlay: bool = True,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the InputPanel.

        Args:
            mode: Default input mode
            config: Optional configuration object
            overlay: Whether to display as overlay (True) or inline (False)
            *args, **kwargs: Passed to Widget
        """
        super().__init__(*args, **kwargs)
        self._config = config or InputPanelConfig()
        self._default_mode = mode
        self.current_mode = mode
        self._overlay = overlay

        # Callbacks
        self._submit_callback: Optional[InputCallback] = None
        self._cancel_callback: Optional[Callable[[], None]] = None
        self._validator: Optional[ValidationCallback] = None

        # History
        self._history: Dict[InputMode, List[str]] = {mode: [] for mode in InputMode}
        self._history_index: int = -1
        self._current_input: str = ""  # Saved input when navigating history

        # Mode-specific configuration
        self._mode_config: Dict[InputMode, Dict[str, str]] = {
            InputMode.SEARCH: {
                "label": "Search:",
                "placeholder": "Enter search query...",
                "hints": "Enter=search | Esc=cancel",
            },
            InputMode.TAG: {
                "label": "Tags:",
                "placeholder": "Enter tags (space-separated)...",
                "hints": "Enter=apply | Esc=cancel",
            },
            InputMode.PROMPT: {
                "label": "Input:",
                "placeholder": "Enter value...",
                "hints": "Enter=submit | Esc=cancel",
            },
            InputMode.CONFIRM: {
                "label": "Confirm:",
                "placeholder": "Type 'yes' to confirm...",
                "hints": "Type 'yes' + Enter | Esc=cancel",
            },
        }

    def compose(self) -> ComposeResult:
        """Compose the input panel UI."""
        # Apply overlay/inline class
        if self._overlay:
            self.add_class("overlay")
        else:
            self.add_class("inline")

        with Vertical():
            with Horizontal(id="input-container"):
                if self._config.show_label:
                    yield Label("", id="input-label")
                yield Input(placeholder="", id="input-field")

            if self._config.show_hints:
                yield Static("", id="input-hints")

            yield Static("", id="input-error")

    async def on_mount(self) -> None:
        """Initialize the input panel."""
        # Initially hidden
        self.display = False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def show(
        self,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        initial_value: str = "",
        callback: Optional[InputCallback] = None,
        cancel_callback: Optional[Callable[[], None]] = None,
        validator: Optional[ValidationCallback] = None,
        mode: Optional[InputMode] = None,
    ) -> None:
        """Show the input panel and activate it.

        Args:
            label: Custom label (uses mode default if None)
            placeholder: Custom placeholder (uses mode default if None)
            initial_value: Initial input value
            callback: Function to call on submission
            cancel_callback: Function to call on cancellation
            validator: Function to validate input
            mode: Input mode (uses default if None)
        """
        if mode is not None:
            self.current_mode = mode

        self._submit_callback = callback
        self._cancel_callback = cancel_callback
        self._validator = validator

        # Get mode-specific defaults
        mode_defaults = self._mode_config.get(self.current_mode, {})

        # Update label
        if self._config.show_label:
            try:
                label_widget = self.query_one("#input-label", Label)
                label_widget.update(label or mode_defaults.get("label", ""))
            except Exception:
                pass

        # Update input
        try:
            input_widget = self.query_one("#input-field", Input)
            input_widget.placeholder = placeholder or mode_defaults.get("placeholder", "")
            input_widget.value = initial_value
            input_widget.can_focus = True
        except Exception:
            pass

        # Update hints
        if self._config.show_hints:
            try:
                hints_widget = self.query_one("#input-hints", Static)
                hints_widget.update(mode_defaults.get("hints", ""))
            except Exception:
                pass

        # Clear error
        self.error_message = ""
        self._update_error_visibility()

        # Reset history navigation
        self._history_index = -1
        self._current_input = initial_value

        # Show and focus
        self.add_class("visible")
        self.display = True
        self.is_active = True

        # Focus input after display update
        self.call_later(self._focus_input)

    def _focus_input(self) -> None:
        """Focus the input field."""
        try:
            input_widget = self.query_one("#input-field", Input)
            input_widget.focus()
        except Exception:
            pass

    def hide(self, clear: bool = True) -> None:
        """Hide the input panel.

        Args:
            clear: Whether to clear the input value
        """
        if clear:
            try:
                input_widget = self.query_one("#input-field", Input)
                input_widget.value = ""
            except Exception:
                pass

        self.remove_class("visible")
        self.display = False
        self.is_active = False
        self.error_message = ""
        self._update_error_visibility()

    def get_value(self) -> str:
        """Get current input value."""
        try:
            input_widget = self.query_one("#input-field", Input)
            return input_widget.value
        except Exception:
            return ""

    def set_value(self, value: str) -> None:
        """Set input value.

        Args:
            value: Value to set
        """
        try:
            input_widget = self.query_one("#input-field", Input)
            input_widget.value = value
        except Exception:
            pass

    def set_error(self, message: str) -> None:
        """Set and display an error message.

        Args:
            message: Error message to display
        """
        self.error_message = message
        self._update_error_visibility()

    def clear_error(self) -> None:
        """Clear the error message."""
        self.error_message = ""
        self._update_error_visibility()

    def set_mode_config(
        self,
        mode: InputMode,
        label: Optional[str] = None,
        placeholder: Optional[str] = None,
        hints: Optional[str] = None,
    ) -> None:
        """Customize configuration for a specific mode.

        Args:
            mode: Mode to configure
            label: Custom label
            placeholder: Custom placeholder
            hints: Custom hints
        """
        if mode not in self._mode_config:
            self._mode_config[mode] = {}

        if label is not None:
            self._mode_config[mode]["label"] = label
        if placeholder is not None:
            self._mode_config[mode]["placeholder"] = placeholder
        if hints is not None:
            self._mode_config[mode]["hints"] = hints

    def save_state(self) -> Dict[str, Any]:
        """Save panel state for restoration."""
        return {
            "mode": self.current_mode.name,
            "history": {mode.name: list(hist) for mode, hist in self._history.items()},
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        try:
            self.current_mode = InputMode[state.get("mode", "SEARCH")]
        except KeyError:
            self.current_mode = InputMode.SEARCH

        history = state.get("history", {})
        for mode_name, hist in history.items():
            try:
                mode = InputMode[mode_name]
                self._history[mode] = list(hist)
            except KeyError:
                pass

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _update_error_visibility(self) -> None:
        """Update error message visibility."""
        try:
            error_widget = self.query_one("#input-error", Static)
            if self.error_message:
                error_widget.update(self.error_message)
                error_widget.add_class("visible")
            else:
                error_widget.update("")
                error_widget.remove_class("visible")
        except Exception:
            pass

    def _add_to_history(self, value: str) -> None:
        """Add value to history for current mode."""
        if not self._config.history_enabled or not value.strip():
            return

        history = self._history[self.current_mode]

        # Remove if already in history
        if value in history:
            history.remove(value)

        # Add to front
        history.insert(0, value)

        # Trim to max
        if len(history) > self._config.max_history:
            history.pop()

    def _validate(self, value: str) -> bool:
        """Validate input value.

        Args:
            value: Value to validate

        Returns:
            True if valid, False otherwise
        """
        if self._validator is None:
            return True

        result = self._validator(value)

        if isinstance(result, bool):
            if not result:
                self.set_error("Invalid input")
            else:
                self.clear_error()
            return result
        else:
            # Result is an error message
            self.set_error(result)
            return False

    async def _submit(self) -> None:
        """Handle submission."""
        value = self.get_value().strip()

        # Validate
        if not self._validate(value):
            self.post_message(self.ValidationFailed(value, self.error_message))
            return

        # Add to history
        self._add_to_history(value)

        # Hide panel
        self.hide(clear=self._config.clear_on_submit)

        # Post message
        self.post_message(self.InputSubmitted(value, self.current_mode))

        # Call callback
        if self._submit_callback:
            import asyncio

            result = self._submit_callback(value)
            if asyncio.iscoroutine(result):
                await result

    def _cancel(self) -> None:
        """Handle cancellation."""
        # Hide panel
        self.hide(clear=self._config.clear_on_cancel)

        # Post message
        self.post_message(self.InputCancelled(self.current_mode))

        # Call callback
        if self._cancel_callback:
            self._cancel_callback()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_submit(self) -> None:
        """Submit the input."""
        if self.is_active:
            import asyncio

            asyncio.create_task(self._submit())

    def action_cancel(self) -> None:
        """Cancel the input."""
        if self.is_active:
            self._cancel()

    def action_history_prev(self) -> None:
        """Navigate to previous history entry."""
        if not self._config.history_enabled or not self.is_active:
            return

        history = self._history[self.current_mode]
        if not history:
            return

        # Save current input if starting navigation
        if self._history_index == -1:
            self._current_input = self.get_value()

        # Move to previous
        if self._history_index < len(history) - 1:
            self._history_index += 1
            self.set_value(history[self._history_index])

    def action_history_next(self) -> None:
        """Navigate to next history entry."""
        if not self._config.history_enabled or not self.is_active:
            return

        if self._history_index > 0:
            self._history_index -= 1
            self.set_value(self._history[self.current_mode][self._history_index])
        elif self._history_index == 0:
            self._history_index = -1
            self.set_value(self._current_input)

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input value changes."""
        if event.input.id == "input-field":
            value = event.value

            # Validate on change if enabled
            if self._config.validate_on_change:
                self._validate(value)

            # Post message
            self.post_message(self.InputChanged(value, self.current_mode))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission via Enter key."""
        if event.input.id == "input-field":
            await self._submit()

    async def on_key(self, event) -> None:
        """Handle key events."""
        if not self.is_active:
            return

        # Escape to cancel
        if event.key == "escape":
            self._cancel()
            event.stop()


class SearchInput(InputPanel):
    """Convenience class for search input.

    Example:
        yield SearchInput(id="search")

        def action_search(self):
            search = self.query_one("#search", SearchInput)
            search.show(callback=self.do_search)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(mode=InputMode.SEARCH, *args, **kwargs)


class TagInput(InputPanel):
    """Convenience class for tag input.

    Example:
        yield TagInput(id="tag-input")

        def action_add_tags(self):
            tag_input = self.query_one("#tag-input", TagInput)
            tag_input.show(callback=self.apply_tags)
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(mode=InputMode.TAG, *args, **kwargs)

    def get_tags(self) -> List[str]:
        """Get tags as a list.

        Returns:
            List of tag strings (space-separated input)
        """
        value = self.get_value()
        return [tag.strip() for tag in value.split() if tag.strip()]
