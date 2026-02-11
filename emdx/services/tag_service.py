"""Tag service facade for the UI layer.

Provides a clean import boundary between UI code and the model layer
for tag operations.
"""

from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    get_tags_for_documents,
    remove_tags_from_document,
)

__all__ = [
    "add_tags_to_document",
    "get_document_tags",
    "get_tags_for_documents",
    "remove_tags_from_document",
]
