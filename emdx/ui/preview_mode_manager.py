#!/usr/bin/env python3
"""
Preview mode manager for DocumentBrowser.

Centralizes all preview container widget state transitions.
Each switch_to_X method handles the complete lifecycle:
1. Clear existing widgets
2. Create new widget structure
3. Mount to container
4. Return widget for caller to manage (focus, etc.)
"""

import logging
from enum import Enum
from typing import TYPE_CHECKING

from textual.containers import ScrollableContainer, Vertical
from textual.widgets import RichLog

from emdx.ui.markdown_config import MarkdownConfig

if TYPE_CHECKING:
    from .inputs import TitleInput
    from .text_areas import SelectionTextArea
    from .vim_editor import VimEditor

logger = logging.getLogger(__name__)

class PreviewMode(Enum):
    """Preview container states."""

    VIEWING = "viewing"  # Showing document content
    EDITING = "editing"  # Editing existing document
    CREATING = "creating"  # Creating new document
    SELECTING = "selecting"  # Text selection mode

class PreviewModeManager:
    """Manages DocumentBrowser preview container state transitions.

    Centralizes all widget manipulation for the preview area.
    Makes adding new preview modes trivial - just add switch_to_X method.

    Design principles:
    1. Each switch_to_X method is self-contained
    2. Caller manages focus and status updates
    3. Returns created widgets for caller to interact with
    4. All Textual widget lifecycle complexity lives here
    """

    def __init__(self, container: Vertical):
        """Initialize manager.

        Args:
            container: The #preview-container Vertical widget
        """
        self.container = container
        self.mode = PreviewMode.VIEWING

    async def _clear_container(self) -> None:
        """Remove all children from preview container.

        Centralizes the widget cleanup pattern that was duplicated 5 times.
        Handles both clean removal and fallback for edge cases.
        """
        for child in list(self.container.children):
            try:
                await child.remove()
            except Exception as e:
                logger.warning(f"Error removing child widget: {e}")

    async def switch_to_viewing(self, content: str) -> RichLog:
        """Switch to document viewing mode.

        Creates the standard preview structure:
        - ScrollableContainer wrapping
        - RichLog for content display
        - Markdown rendering

        Args:
            content: Document content to display

        Returns:
            RichLog widget (for caller reference if needed)
        """
        await self._clear_container()

        # Create preview structure
        preview = ScrollableContainer(id="preview")
        preview_content = RichLog(
            id="preview-content",
            wrap=True,
            highlight=True,
            markup=True,
            auto_scroll=False,
        )
        preview_content.can_focus = False

        # Mount hierarchy
        await self.container.mount(preview)
        await preview.mount(preview_content)

        # Render content
        if content.strip():
            try:
                preview_content.write(MarkdownConfig.create_markdown(content))
            except Exception as e:
                logger.warning(f"Markdown render failed: {e}, using plain text")
                preview_content.write(content)
        else:
            preview_content.write("[dim]Empty document[/dim]")

        self.mode = PreviewMode.VIEWING
        return preview_content

    async def switch_to_editing(
        self, host, title: str, content: str, is_new: bool = False
    ) -> tuple["TitleInput", "VimEditor"]:
        """Switch to document editing mode.

        Creates the edit structure:
        - Vertical container for layout
        - TitleInput for title editing
        - VimEditor for content editing

        Args:
            host: Widget implementing TextAreaHost protocol (for callbacks)
            title: Document title (empty string for new documents)
            content: Document content
            is_new: True if creating new document, False if editing existing

        Returns:
            (TitleInput, VimEditor) tuple - caller decides which to focus
        """
        await self._clear_container()

        from .inputs import TitleInput
        from .vim_editor import VimEditor

        # Create edit container
        edit_container = Vertical(id="edit-container")
        await self.container.mount(edit_container)

        # Create editing widgets
        title_input = TitleInput(
            host, value=title, placeholder="Enter document title...", id="title-input"
        )
        vim_editor = VimEditor(host, content=content, id="vim-editor-container")

        # Mount both
        await edit_container.mount(title_input)
        await edit_container.mount(vim_editor)

        self.mode = PreviewMode.CREATING if is_new else PreviewMode.EDITING
        return title_input, vim_editor

    async def switch_to_selecting(self, host, content: str) -> "SelectionTextArea":
        """Switch to text selection mode.

        Args:
            host: Widget implementing TextAreaHost protocol
            content: Text content for selection

        Returns:
            SelectionTextArea widget for selection operations
        """
        await self._clear_container()

        from .text_areas import SelectionTextArea

        selection_area = SelectionTextArea(
            host, content, id="selection-area", read_only=True
        )
        await self.container.mount(selection_area)

        self.mode = PreviewMode.SELECTING
        return selection_area
