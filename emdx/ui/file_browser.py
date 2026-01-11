"""Backward compatibility re-exports for file_browser module.

The FileBrowser component has been refactored into a package at emdx/ui/file_browser/
with the following structure:
- view.py: FileBrowserView (main widget)
- navigation.py: FileBrowserNavigation (mixin for movement/navigation)
- actions.py: FileBrowserActions (mixin for file operations/mode switching)

Import from emdx.ui.file_browser for the new modular structure.
"""

from .file_browser import (
    FileBrowser,
    FileBrowserView,
    FileBrowserNavigation,
    FileBrowserActions,
    FileEditTextArea,
    FileSelectionTextArea,
    FileBrowserVimApp,
)

__all__ = [
    "FileBrowser",
    "FileBrowserView",
    "FileBrowserNavigation",
    "FileBrowserActions",
    "FileEditTextArea",
    "FileSelectionTextArea",
    "FileBrowserVimApp",
]
