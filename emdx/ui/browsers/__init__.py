"""
Browsers using the panel-based architecture.

This module contains browser implementations using the reusable panel
components (ListPanel, PreviewPanel, etc.).

For documentation, see: docs/browser-dx-design.md
"""

from .activity_browser import ActivityBrowser
from .document_browser import DocumentBrowser
from .example_browser import ExampleBrowser
from .file_browser import FileBrowser
from .git_browser import GitBrowser
from .log_browser import LogBrowser
from .task_browser import TaskBrowser
from .workflow_browser import WorkflowBrowser

__all__ = [
    "ActivityBrowser",
    "DocumentBrowser",
    "ExampleBrowser",
    "FileBrowser",
    "GitBrowser",
    "LogBrowser",
    "TaskBrowser",
    "WorkflowBrowser",
]
