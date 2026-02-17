"""Group service facade for the UI layer.

Provides a clean import boundary between UI code and the database layer
for group operations.
"""

from emdx.database.groups import (
    add_document_to_group,
    create_group,
    get_all_grouped_document_ids,
    get_child_groups,
    get_document_groups,
    get_group,
    get_group_members,
    get_recursive_doc_count,
    list_groups,
    list_top_groups_with_counts,
    remove_document_from_group,
    update_group,
)
from emdx.database.types import (
    DocumentGroup,
    DocumentGroupWithCounts,
    DocumentWithGroups,
    GroupMember,
)

__all__ = [
    # Functions
    "add_document_to_group",
    "create_group",
    "get_all_grouped_document_ids",
    "get_child_groups",
    "get_document_groups",
    "get_group",
    "get_group_members",
    "get_recursive_doc_count",
    "list_groups",
    "list_top_groups_with_counts",
    "remove_document_from_group",
    "update_group",
    # Types
    "DocumentGroup",
    "DocumentGroupWithCounts",
    "DocumentWithGroups",
    "GroupMember",
]
