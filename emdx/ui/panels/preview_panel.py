"""
PreviewPanel - A reusable content preview panel with mode switching.

This panel extracts the preview functionality from DocumentBrowser into a
standalone, configurable component that can be used by any browser widget.

Features:
- Multiple preview modes (viewing, editing, selecting)
- Markdown rendering with RichLog
- Vim-style text editing integration
- Text selection mode for copying
- State save/restore
- Mode-specific keybindings

Example usage:
    class MyBrowser(Widget):
        def compose(self):
            yield PreviewPanel(id="my-preview")

        async def on_list_panel_item_selected(self, event):
            preview = self.query_one("#my-preview", PreviewPanel)
            await preview.show_content(event.item.data["content"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

if TYPE_CHECKING:
    from ..text_areas import SelectionTextArea
    from ..vim_editor import VimEditor

logger = logging.getLogger(__name__)


class PreviewMode(Enum):
    """Preview panel modes."""

    VIEWING = auto()  # Showing content (read-only)
    EDITING = auto()  # Editing content with vim bindings
    SELECTING = auto()  # Text selection mode for copying
    EMPTY = auto()  # No content to show


class TextAreaHost(Protocol):
    """Protocol for widgets that can host editing text areas."""

    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode."""
        ...

    def _update_vim_status(self, message: str = "") -> None:
        """Update status with vim mode information."""
        ...

    def action_toggle_selection_mode(self) -> None:
        """Toggle selection mode."""
        ...


@dataclass
class PreviewPanelConfig:
    """Configuration for PreviewPanel behavior.

    Attributes:
        enable_editing: Whether editing mode is available
        enable_selection: Whether text selection mode is available
        show_title_in_edit: Whether to show title input when editing
        markdown_rendering: Whether to render content as markdown
        empty_message: Message to show when no content
        truncate_preview: Max chars before truncating (0 = no limit)
    """

    enable_editing: bool = True
    enable_selection: bool = True
    show_title_in_edit: bool = True
    markdown_rendering: bool = True
    empty_message: str = "[dim]No content to display[/dim]"
    truncate_preview: int = 50000


class PreviewPanel(Widget):
    """Reusable preview panel with mode switching.

    This widget provides a flexible content preview area that can:
    - Display content as rendered markdown or plain text
    - Switch to editing mode with vim bindings
    - Switch to text selection mode for copying

    Messages:
        ContentChanged: Fired when content is modified in edit mode
        EditRequested: Fired when user requests edit mode
        SelectionCopied: Fired when text is copied in selection mode
        ModeChanged: Fired when preview mode changes
    """

    DEFAULT_CSS = """
    PreviewPanel {
        layout: vertical;
        height: 100%;
        layers: base overlay;
    }

    PreviewPanel #preview-scroll {
        height: 1fr;
        layer: base;
    }

    PreviewPanel #preview-content {
        padding: 0 1;
    }

    PreviewPanel #preview-empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    PreviewPanel #edit-container {
        height: 100%;
        layer: base;
    }

    PreviewPanel #title-input {
        height: 3;
        margin: 0 0 1 0;
    }

    PreviewPanel #vim-editor-container {
        height: 1fr;
    }

    PreviewPanel #selection-area {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("e", "enter_edit", "Edit", show=False),
        Binding("s", "enter_selection", "Select", show=False),
        Binding("escape", "exit_mode", "Exit", show=False),
    ]

    # Reactive properties
    mode: reactive[PreviewMode] = reactive(PreviewMode.EMPTY)
    has_content: reactive[bool] = reactive(False)

    # Messages
    class ContentChanged(Message):
        """Fired when content is modified."""

        def __init__(self, title: str, content: str) -> None:
            self.title = title
            self.content = content
            super().__init__()

    class EditRequested(Message):
        """Fired when user requests edit mode."""

        def __init__(self) -> None:
            super().__init__()

    class SelectionCopied(Message):
        """Fired when text is copied."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class ModeChanged(Message):
        """Fired when preview mode changes."""

        def __init__(self, old_mode: PreviewMode, new_mode: PreviewMode) -> None:
            self.old_mode = old_mode
            self.new_mode = new_mode
            super().__init__()

    def __init__(
        self,
        config: Optional[PreviewPanelConfig] = None,
        host: Optional[TextAreaHost] = None,
        *args,
        **kwargs,
    ) -> None:
        """Initialize the PreviewPanel.

        Args:
            config: Optional configuration object
            host: Optional host widget for text area callbacks
            *args, **kwargs: Passed to Widget
        """
        super().__init__(*args, **kwargs)
        self._config = config or PreviewPanelConfig()
        self._host = host
        self._content: str = ""
        self._title: str = ""
        self._original_content: str = ""  # For cancel/restore

    def compose(self) -> ComposeResult:
        """Compose the preview panel UI."""
        # Main preview container (shown in VIEWING mode)
        with ScrollableContainer(id="preview-scroll"):
            yield RichLog(
                id="preview-content",
                wrap=True,
                highlight=True,
                markup=True,
                auto_scroll=False,
            )

        # Empty state (shown when no content)
        yield Static(self._config.empty_message, id="preview-empty")

    async def on_mount(self) -> None:
        """Initialize the preview panel."""
        # Set initial visibility
        self._update_visibility()

        # Disable focus on preview content
        try:
            preview = self.query_one("#preview-content", RichLog)
            preview.can_focus = False
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def show_content(
        self,
        content: str,
        title: str = "",
        render_markdown: bool = True,
    ) -> None:
        """Display content in viewing mode.

        Args:
            content: Content to display
            title: Optional title for the content
            render_markdown: Whether to render as markdown
        """
        self._content = content
        self._title = title
        self._original_content = content
        self.has_content = bool(content.strip())

        if not self.has_content:
            self.mode = PreviewMode.EMPTY
            self._update_visibility()
            return

        self.mode = PreviewMode.VIEWING
        self._update_visibility()

        try:
            preview = self.query_one("#preview-content", RichLog)
            preview.clear()

            # Truncate if needed
            display_content = content
            if (
                self._config.truncate_preview > 0
                and len(content) > self._config.truncate_preview
            ):
                display_content = (
                    content[: self._config.truncate_preview]
                    + "\n\n[dim]... (truncated for preview)[/dim]"
                )

            # Render content
            if render_markdown and self._config.markdown_rendering:
                try:
                    from ..markdown_config import MarkdownConfig

                    markdown = MarkdownConfig.create_markdown(display_content)
                    preview.write(markdown)
                except Exception as e:
                    logger.warning(f"Markdown render failed: {e}")
                    preview.write(display_content)
            else:
                preview.write(display_content)

        except Exception as e:
            logger.error(f"Error showing content: {e}")

    async def show_empty(self, message: Optional[str] = None) -> None:
        """Show empty state.

        Args:
            message: Optional custom empty message
        """
        self._content = ""
        self._title = ""
        self.has_content = False
        self.mode = PreviewMode.EMPTY

        if message:
            try:
                empty_widget = self.query_one("#preview-empty", Static)
                empty_widget.update(message)
            except Exception:
                pass

        self._update_visibility()

    async def enter_edit_mode(
        self,
        title: str = "",
        content: str = "",
        is_new: bool = False,
    ) -> Optional[Tuple[Input, "VimEditor"]]:
        """Enter editing mode.

        Args:
            title: Title to edit (or empty for new)
            content: Content to edit
            is_new: Whether this is creating new content

        Returns:
            Tuple of (TitleInput, VimEditor) or None if editing disabled
        """
        if not self._config.enable_editing:
            return None

        old_mode = self.mode
        self.mode = PreviewMode.EDITING
        self._title = title
        self._content = content
        self._original_content = content

        # Clear existing content
        await self._clear_preview_widgets()

        # Import editing components
        try:
            from ..inputs import TitleInput
            from ..vim_editor import VimEditor

            # Create edit container
            edit_container = Vertical(id="edit-container")
            await self.mount(edit_container)

            # Create editing widgets
            host = self._host or self._create_default_host()

            if self._config.show_title_in_edit:
                title_input = TitleInput(
                    host,
                    value=title,
                    placeholder="Enter title...",
                    id="title-input",
                )
                await edit_container.mount(title_input)
            else:
                title_input = None

            vim_editor = VimEditor(host, content=content, id="vim-editor-container")
            await edit_container.mount(vim_editor)

            self._update_visibility()
            self.post_message(self.ModeChanged(old_mode, self.mode))

            return title_input, vim_editor

        except ImportError as e:
            logger.error(f"Could not import editing components: {e}")
            self.mode = old_mode
            return None
        except Exception as e:
            logger.error(f"Error entering edit mode: {e}")
            self.mode = old_mode
            return None

    async def exit_edit_mode(self, save: bool = False) -> None:
        """Exit editing mode.

        Args:
            save: Whether to save changes (triggers ContentChanged message)
        """
        if self.mode != PreviewMode.EDITING:
            return

        if save:
            # Get edited content
            try:
                vim_editor = self.query_one("#vim-editor-container")
                content = vim_editor.text_area.text

                title = self._title
                if self._config.show_title_in_edit:
                    try:
                        title_input = self.query_one("#title-input", Input)
                        title = title_input.value.strip()
                    except Exception:
                        pass

                self._content = content
                self._title = title
                self.post_message(self.ContentChanged(title, content))

            except Exception as e:
                logger.error(f"Error saving content: {e}")

        # Restore viewing mode
        await self._clear_edit_widgets()
        await self._restore_preview_widgets()
        await self.show_content(self._content, self._title)

    async def enter_selection_mode(self, content: str = "") -> Optional["SelectionTextArea"]:
        """Enter text selection mode.

        Args:
            content: Content to show in selection mode (uses current if empty)

        Returns:
            SelectionTextArea widget or None if selection disabled
        """
        if not self._config.enable_selection:
            return None

        old_mode = self.mode
        self.mode = PreviewMode.SELECTING

        content = content or self._content

        try:
            from ..text_areas import SelectionTextArea

            # Clear preview widgets
            await self._clear_preview_widgets()

            # Create selection area
            host = self._host or self._create_default_host()
            selection_area = SelectionTextArea(
                host, content, id="selection-area", read_only=True
            )
            await self.mount(selection_area)

            self._update_visibility()
            self.post_message(self.ModeChanged(old_mode, self.mode))

            return selection_area

        except ImportError as e:
            logger.error(f"Could not import selection components: {e}")
            self.mode = old_mode
            return None
        except Exception as e:
            logger.error(f"Error entering selection mode: {e}")
            self.mode = old_mode
            return None

    async def exit_selection_mode(self) -> None:
        """Exit selection mode and return to viewing."""
        if self.mode != PreviewMode.SELECTING:
            return

        # Remove selection widget
        try:
            selection_area = self.query_one("#selection-area")
            await selection_area.remove()
        except Exception:
            pass

        # Restore viewing mode
        await self._restore_preview_widgets()
        await self.show_content(self._content, self._title)

    def get_content(self) -> str:
        """Get current content."""
        return self._content

    def get_title(self) -> str:
        """Get current title."""
        return self._title

    def save_state(self) -> Dict[str, Any]:
        """Save panel state for restoration."""
        return {
            "mode": self.mode.name,
            "content": self._content,
            "title": self._title,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore panel state."""
        import asyncio

        mode_name = state.get("mode", "EMPTY")
        self._content = state.get("content", "")
        self._title = state.get("title", "")

        try:
            self.mode = PreviewMode[mode_name]
        except KeyError:
            self.mode = PreviewMode.EMPTY

        # Restore content display
        if self._content:
            asyncio.create_task(self.show_content(self._content, self._title))
        else:
            asyncio.create_task(self.show_empty())

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _update_visibility(self) -> None:
        """Update widget visibility based on current mode."""
        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            empty_widget = self.query_one("#preview-empty", Static)

            if self.mode == PreviewMode.VIEWING:
                preview_scroll.display = True
                empty_widget.display = False
            elif self.mode == PreviewMode.EMPTY:
                preview_scroll.display = False
                empty_widget.display = True
            else:
                # EDITING or SELECTING - hide default preview widgets
                preview_scroll.display = False
                empty_widget.display = False

        except Exception as e:
            logger.debug(f"Could not update visibility: {e}")

    async def _clear_preview_widgets(self) -> None:
        """Clear the default preview widgets for mode switch."""
        try:
            preview_scroll = self.query_one("#preview-scroll", ScrollableContainer)
            preview_scroll.display = False
        except Exception:
            pass

        try:
            empty_widget = self.query_one("#preview-empty", Static)
            empty_widget.display = False
        except Exception:
            pass

    async def _restore_preview_widgets(self) -> None:
        """Restore the default preview widgets."""
        # Widgets should already exist, just update visibility
        self._update_visibility()

    async def _clear_edit_widgets(self) -> None:
        """Remove edit mode widgets."""
        try:
            edit_container = self.query_one("#edit-container", Vertical)
            await edit_container.remove()
        except Exception:
            pass

    def _create_default_host(self) -> TextAreaHost:
        """Create a default host implementation."""

        class DefaultHost:
            def __init__(self, panel: PreviewPanel):
                self.panel = panel

            def action_save_and_exit_edit(self) -> None:
                import asyncio

                asyncio.create_task(self.panel.exit_edit_mode(save=True))

            def _update_vim_status(self, message: str = "") -> None:
                pass  # No-op

            def action_toggle_selection_mode(self) -> None:
                import asyncio

                asyncio.create_task(self.panel.exit_selection_mode())

        return DefaultHost(self)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_enter_edit(self) -> None:
        """Enter edit mode via keybinding."""
        if self._config.enable_editing and self.has_content:
            self.post_message(self.EditRequested())

    def action_enter_selection(self) -> None:
        """Enter selection mode via keybinding."""
        if self._config.enable_selection and self.has_content:
            import asyncio

            asyncio.create_task(self.enter_selection_mode())

    def action_exit_mode(self) -> None:
        """Exit current mode back to viewing."""
        import asyncio

        if self.mode == PreviewMode.EDITING:
            asyncio.create_task(self.exit_edit_mode(save=False))
        elif self.mode == PreviewMode.SELECTING:
            asyncio.create_task(self.exit_selection_mode())

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def watch_mode(self, old_mode: PreviewMode, new_mode: PreviewMode) -> None:
        """React to mode changes."""
        self._update_visibility()
