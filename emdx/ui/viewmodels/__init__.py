"""
ViewModels for UI components.

ViewModels are data transfer objects that contain display-ready data.
They decouple UI widgets from business logic and database access.
"""

from .document_list_vm import DocumentDetailVM, DocumentListItem, DocumentListVM

__all__ = [
    "DocumentListItem",
    "DocumentListVM",
    "DocumentDetailVM",
]
