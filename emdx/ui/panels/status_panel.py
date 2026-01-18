"""
StatusPanel - A configurable status bar panel for EMDX browsers.

This panel provides a flexible status bar that can display:
- Status messages (persistent and temporary)
- Key hints (keybindings for current context)
- Mode indicators
- Progress information
- Custom sections

Features:
- Multiple display sections with custom content
- Temporary messages with auto-dismiss
- Key hint generation from bindings
- Mode-aware status updates
- Theme integration

Example usage:
    class MyBrowser(Widget):
        def compose(self):
            yield StatusPanel(
                sections=[
                    StatusSection("mode", width=10, align="left"),
                    StatusSection("message", width="auto", align="left"),
                    StatusSection("hints", width=40, align="right"),
                ],
                id="status-bar",
            )

        def on_mount(self):
            status = self.query_one("#status-bar", StatusPanel)
            status.set_section("mode", "NORMAL")
            status.set_hints(["j/k=nav", "q=quit"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

logger = logging.getLogger(__name__)


class StatusAlign(Enum):
    """Alignment for status sections."""

    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


@dataclass
class StatusSection:
    """Definition for a section in the StatusPanel.

    Attributes:
        key: Unique key for this section
        width: Width in characters, or "auto" for flexible
        align: Text alignment within section
        default: Default content for this section
        style: Optional Rich style string
    """

    key: str
    width: Union[int, str] = "auto"
    align: StatusAlign = StatusAlign.LEFT
    default: str = ""
    style: str = ""


@dataclass
class StatusPanelConfig:
    """Configuration for StatusPanel behavior.

    Attributes:
        height: Height of the status bar
        show_mode: Whether to show mode indicator
        show_hints: Whether to show key hints
        hint_separator: Separator between key hints
        temporary_timeout: Default timeout for temporary messages (seconds)
        background: Background color/style
    """

    height: int = 1
    show_mode: bool = True
    show_hints: bool = True
    hint_separator: str = " | "
    temporary_timeout: float = 3.0
    background: str = "$boost"


class StatusPanel(Widget):
    """Configurable status bar panel.

    This widget provides a flexible status bar with multiple sections
    that can be independently updated. It supports:

    - Multiple named sections with custom widths
    - Temporary messages that auto-dismiss
    - Key hint generation from keybinding lists
    - Mode indicator integration

    Messages:
        StatusClicked: Fired when status bar is clicked
    """

    DEFAULT_CSS = """
    StatusPanel {
        layout: horizontal;
        height: 1;
        background: $boost;
        color: $text;
        padding: 0;
        width: 100%;
    }

    StatusPanel .status-section {
        height: 100%;
        padding: 0 1;
    }

    StatusPanel .status-section.left {
        text-align: left;
    }

    StatusPanel .status-section.center {
        text-align: center;
    }

    StatusPanel .status-section.right {
        text-align: right;
    }

    StatusPanel .status-section.auto {
        width: 1fr;
    }

    StatusPanel .status-section.mode {
        color: $accent;
        text-style: bold;
    }

    StatusPanel .status-section.hints {
        color: $text-muted;
    }

    StatusPanel .status-section.error {
        color: $error;
    }

    StatusPanel .status-section.success {
        color: $success;
    }
    """

    # Reactive properties
    mode: reactive[str] = reactive("NORMAL")
    message: reactive[str] = reactive("")

    # Messages
    class StatusClicked(Message):
        """Fired when status bar is clicked."""

        def __init__(self, section_key: str) -> None:
            self.section_key = section_key
            super().__init__()

    def __init__(
        self,
        sections: Optional[Sequence[StatusSection]] = None,
        config: Optional[StatusPanelConfig] = None,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the StatusPanel.

        Args:
            sections: Section definitions. If None, uses default layout.
            config: Optional configuration object
            *args, **kwargs: Passed to Widget
        """
        super().__init__(*args, **kwargs)

        self._config = config or StatusPanelConfig()

        # Set up default sections if none provided
        if sections is None:
            self._sections = [
                StatusSection("mode", width=10, align=StatusAlign.LEFT),
                StatusSection("message", width="auto", align=StatusAlign.LEFT),
                StatusSection("hints", width=40, align=StatusAlign.RIGHT),
            ]
        else:
            self._sections = list(sections)

        # Section content storage
        self._section_content: Dict[str, str] = {}
        for section in self._sections:
            self._section_content[section.key] = section.default

        # Timer for temporary messages
        self._message_timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        """Compose the status panel UI."""
        with Horizontal():
            for section in self._sections:
                # Build CSS classes
                classes = ["status-section"]

                # Alignment class
                if section.align == StatusAlign.LEFT:
                    classes.append("left")
                elif section.align == StatusAlign.CENTER:
                    classes.append("center")
                else:
                    classes.append("right")

                # Width handling
                if section.width == "auto":
                    classes.append("auto")

                # Special section classes
                if section.key == "mode":
                    classes.append("mode")
                elif section.key == "hints":
                    classes.append("hints")

                widget = Static(
                    section.default,
                    id=f"status-{section.key}",
                    classes=" ".join(classes),
                )

                # Set explicit width if not auto
                if isinstance(section.width, int):
                    widget.styles.width = section.width

                yield widget

    async def on_mount(self) -> None:
        """Initialize the status panel."""
        # Apply initial mode if show_mode is enabled
        if self._config.show_mode:
            self.set_section("mode", f"[bold]{self.mode}[/bold]")

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def set_section(self, key: str, content: str) -> None:
        """Set content for a specific section.

        Args:
            key: Section key
            content: Content to display (Rich markup supported)
        """
        self._section_content[key] = content
        try:
            widget = self.query_one(f"#status-{key}", Static)
            widget.update(content)
        except Exception as e:
            logger.debug(f"Could not update section {key}: {e}")

    def get_section(self, key: str) -> str:
        """Get current content of a section.

        Args:
            key: Section key

        Returns:
            Current content, or empty string if section not found
        """
        return self._section_content.get(key, "")

    def set_message(
        self,
        message: str,
        temporary: bool = True,
        timeout: Optional[float] = None,
        style: str = "",
    ) -> None:
        """Set the main status message.

        Args:
            message: Message to display
            temporary: Whether message should auto-dismiss
            timeout: Custom timeout (uses config default if None)
            style: Optional style class ("error", "success", etc.)
        """
        # Cancel any existing timer
        if self._message_timer:
            self._message_timer.stop()
            self._message_timer = None

        # Update content
        content = message
        if style:
            content = f"[{style}]{message}[/{style}]"

        self.message = message
        self.set_section("message", content)

        # Apply style class to widget
        try:
            widget = self.query_one("#status-message", Static)
            # Remove previous style classes
            widget.remove_class("error", "success")
            if style:
                widget.add_class(style)
        except Exception:
            pass

        # Set up auto-dismiss timer
        if temporary:
            timeout = timeout or self._config.temporary_timeout
            self._message_timer = self.set_timer(timeout, self._clear_message)

    def _clear_message(self) -> None:
        """Clear the temporary message."""
        self.message = ""
        self.set_section("message", "")
        try:
            widget = self.query_one("#status-message", Static)
            widget.remove_class("error", "success")
        except Exception:
            pass

    def set_mode(self, mode: str) -> None:
        """Set the mode indicator.

        Args:
            mode: Mode name (e.g., "NORMAL", "SEARCH", "EDIT")
        """
        self.mode = mode
        if self._config.show_mode:
            self.set_section("mode", f"[bold]{mode}[/bold]")

    def set_hints(self, hints: List[str]) -> None:
        """Set key hints.

        Args:
            hints: List of hint strings (e.g., ["j/k=nav", "q=quit"])
        """
        if self._config.show_hints:
            content = self._config.hint_separator.join(hints)
            self.set_section("hints", content)

    def set_hints_from_bindings(
        self,
        bindings: List[tuple],
        max_hints: int = 5,
    ) -> None:
        """Generate hints from a list of key bindings.

        Args:
            bindings: List of (key, action, description) tuples
            max_hints: Maximum number of hints to show
        """
        hints = []
        for binding in bindings[:max_hints]:
            if len(binding) >= 3:
                key, action, desc = binding[:3]
                # Format key for display
                key_display = self._format_key(key)
                hints.append(f"{key_display}={desc.lower()}")

        self.set_hints(hints)

    def show_error(self, message: str, timeout: Optional[float] = None) -> None:
        """Show an error message.

        Args:
            message: Error message
            timeout: Custom timeout (longer default for errors)
        """
        self.set_message(
            message,
            temporary=True,
            timeout=timeout or 5.0,
            style="error",
        )

    def show_success(self, message: str, timeout: Optional[float] = None) -> None:
        """Show a success message.

        Args:
            message: Success message
            timeout: Custom timeout
        """
        self.set_message(
            message,
            temporary=True,
            timeout=timeout or self._config.temporary_timeout,
            style="success",
        )

    def clear(self) -> None:
        """Clear all sections to their defaults."""
        for section in self._sections:
            self._section_content[section.key] = section.default
            self.set_section(section.key, section.default)

    def save_state(self) -> Dict[str, Any]:
        """Save panel state for restoration."""
        return {
            "mode": self.mode,
            "sections": dict(self._section_content),
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        self.mode = state.get("mode", "NORMAL")
        sections = state.get("sections", {})
        for key, content in sections.items():
            self.set_section(key, content)

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _format_key(self, key: str) -> str:
        """Format a key name for display.

        Args:
            key: Raw key name

        Returns:
            Formatted key string
        """
        replacements = {
            "question_mark": "?",
            "escape": "Esc",
            "enter": "Enter",
            "tab": "Tab",
            "shift+tab": "S-Tab",
            "space": "Space",
            "ctrl+": "C-",
        }

        result = key
        for old, new in replacements.items():
            result = result.replace(old, new)

        return result

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def watch_mode(self, old_mode: str, new_mode: str) -> None:
        """React to mode changes."""
        if self._config.show_mode:
            self.set_section("mode", f"[bold]{new_mode}[/bold]")


class SimpleStatusBar(StatusPanel):
    """Simplified status bar with just message and hints.

    A convenience class for common use cases where you just need
    a message area and key hints without mode indicator.

    Example:
        yield SimpleStatusBar(id="status")
        status = self.query_one("#status", SimpleStatusBar)
        status.set("Ready | j/k=nav | /=search | q=quit")
    """

    def __init__(self, *args, **kwargs) -> None:
        sections = [
            StatusSection("message", width="auto", align=StatusAlign.LEFT),
        ]
        config = StatusPanelConfig(show_mode=False, show_hints=False)
        super().__init__(sections=sections, config=config, *args, **kwargs)

    def set(self, message: str) -> None:
        """Set the status bar message.

        Args:
            message: Full status message
        """
        self.set_section("message", message)

    def update(self, message: str) -> None:
        """Alias for set() for compatibility."""
        self.set(message)
