"""TypedDict definitions for the UI layer.

These types provide proper typing for dict-style data structures used
in UI components, replacing Any annotations.
"""

from __future__ import annotations

from typing import TypedDict


class CascadeRunDict(TypedDict, total=False):
    """Cascade run data used by CascadeRunItem in the activity view.

    Contains both database fields and display-derived fields.
    """

    id: int
    status: str
    started_at: str | None
    completed_at: str | None
    pipeline_name: str
    pipeline_display_name: str
    current_stage: str
    initial_doc_title: str | None
    doc_id: int | None
    error_message: str | None


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


class PipelineActivityDict(TypedDict, total=False):
    """Pipeline activity data used in cascade_view.py.

    Mirrors PipelineActivityItem from database/types.py.
    """

    exec_id: int
    input_id: int | None
    input_title: str | None
    output_id: int | None
    output_title: str | None
    output_stage: str | None
    from_stage: str
    status: str | None
    started_at: str | None
    completed_at: str | None
    log_file: str | None
    doc_title: str | None
