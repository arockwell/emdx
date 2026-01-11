"""
Presenters for UI components.

Presenters contain the business logic that transforms data from
the model layer into ViewModels for display. They decouple UI
widgets from database access and business logic.
"""

from .document_browser_presenter import DocumentBrowserPresenter

__all__ = [
    "DocumentBrowserPresenter",
]
