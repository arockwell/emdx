"""TypedDict definitions for the UI layer.

These types provide proper typing for dict-style data structures used
in UI components, replacing Any annotations.
"""

from __future__ import annotations

from typing import TypedDict


class GroupDict(TypedDict, total=False):
    """Document group data used by GroupItem in the activity view.

    Mirrors DocumentGroupWithCounts from database/types.py but with
    only the fields actually used by the UI layer.
    """

    id: int
    name: str
    description: str | None
    group_type: str
    created_at: str | None
    doc_count: int
    total_cost_usd: float | None
    total_tokens: int
    child_group_count: int
    project: str | None
    parent_group_id: int | None
    is_active: int


class AgentExecutionDict(TypedDict, total=False):
    """Agent execution data used by AgentExecutionItem in the activity view.

    Contains execution record fields plus derived display fields.
    """

    id: int
    doc_id: int | None
    doc_title: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    log_file: str | None
    exit_code: int | None
    working_dir: str | None
    cost_usd: float
    tokens_used: int
    output_text: str | None
