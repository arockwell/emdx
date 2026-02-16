"""TypedDicts for CLI executor stream messages and environment info."""

from __future__ import annotations

from typing import Any, TypedDict


class SystemMessage(TypedDict, total=False):
    type: str  # "system"
    subtype: str | None
    session_id: str | None
    model: str | None
    cwd: str | None
    tools: list[str]


class AssistantMessage(TypedDict, total=False):
    type: str  # "assistant"
    text: str
    tool_uses: list[dict[str, Any]]  # genuinely polymorphic per-tool JSON
    usage: dict[str, int]


class ToolCallMessage(TypedDict, total=False):
    type: str  # "tool_call"
    subtype: str | None  # "started" | "completed"
    call_id: str | None
    tool_call: dict[str, Any]  # genuinely polymorphic per-tool JSON


class ResultMessage(TypedDict, total=False):
    type: str  # "result"
    success: bool
    result: str | None
    duration_ms: int
    cost_usd: float
    usage: dict[str, int]
    session_id: str | None
    raw_line: str  # original JSON line for __RAW_RESULT_JSON__ embedding


class ThinkingMessage(TypedDict, total=False):
    type: str  # "thinking"
    subtype: str | None  # "completed" | delta
    text: str


class ErrorMessage(TypedDict, total=False):
    type: str  # "error"
    error: dict[str, str]  # {"message": "..."}


StreamMessage = (
    SystemMessage
    | AssistantMessage
    | ToolCallMessage
    | ResultMessage
    | ThinkingMessage
    | ErrorMessage
)


class EnvironmentInfo(TypedDict, total=False):
    cli: str
    errors: list[str]
    warnings: list[str]
    binary_path: str
    version: str
    config_path: str


class ContentItem(TypedDict, total=False):
    type: str
    text: str
