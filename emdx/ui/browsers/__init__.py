"""
Browsers using the panel-based architecture.

This module contains browser implementations using the reusable panel
components (ListPanel, PreviewPanel, etc.).

For documentation, see: docs/browser-dx-design.md
"""

from .activity_browser_v2 import ActivityBrowserV2
from .document_browser_v2 import DocumentBrowserV2
from .example_browser import ExampleBrowser
from .file_browser_v2 import FileBrowserV2
from .git_browser_v2 import GitBrowserV2
from .log_browser_v2 import LogBrowserV2
from .task_browser_v2 import TaskBrowserV2
from .workflow_browser_v2 import WorkflowBrowserV2

__all__ = [
    "ActivityBrowserV2",
    "DocumentBrowserV2",
    "ExampleBrowser",
    "FileBrowserV2",
    "GitBrowserV2",
    "LogBrowserV2",
    "TaskBrowserV2",
    "WorkflowBrowserV2",
]

