"""Document service facade for the UI layer.

Provides a clean import boundary between UI code and the database/model
layer for document operations. All document-related UI imports should
come through this module.
"""

from emdx.database.documents import (
    count_documents,
    get_children,
    get_children_count,
    get_document,
    get_document_source,
    get_recent_documents,
    get_workflow_document_ids,
    list_documents,
    list_non_workflow_documents,
    save_document,
    update_document,
)
from emdx.database.search import search_documents
from emdx.models.documents import delete_document

__all__ = [
    "count_documents",
    "delete_document",
    "get_children",
    "get_children_count",
    "get_document",
    "get_document_source",
    "get_recent_documents",
    "get_workflow_document_ids",
    "list_documents",
    "list_non_workflow_documents",
    "save_document",
    "search_documents",
    "update_document",
]
