"""Group service facade for the UI layer.

Provides a clean import boundary between UI code and the database layer
for group operations.
"""

from emdx.database.groups import (
    create_group,
    get_child_groups,
    get_group_members,
    list_groups,
)

__all__ = [
    "create_group",
    "get_child_groups",
    "get_group_members",
    "list_groups",
]
