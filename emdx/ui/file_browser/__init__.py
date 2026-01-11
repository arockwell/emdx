"""File browser package - modular file browser component.

This package contains:
- FileBrowserView: Main view widget combining all functionality
- FileBrowserNavigation: Mixin for navigation (movement, directories)
- FileBrowserActions: Mixin for file operations and mode switching

Helper classes (from actions.py):
- FileEditTextArea: TextArea for editing with ESC handling
- FileSelectionTextArea: TextArea for selection mode with ESC handling
- FileBrowserVimApp: Mock app for vim editor integration
"""

from .actions import (
    FileEditTextArea,
    FileSelectionTextArea,
    FileBrowserVimApp,
    FileBrowserActions,
)
from .navigation import FileBrowserNavigation
from .view import FileBrowser, FileBrowserView

__all__ = [
    # Main class and alias
    "FileBrowser",
    "FileBrowserView",
    # Mixins
    "FileBrowserNavigation",
    "FileBrowserActions",
    # Helper classes
    "FileEditTextArea",
    "FileSelectionTextArea",
    "FileBrowserVimApp",
]
