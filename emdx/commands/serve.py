"""
JSON-RPC server for emdx — persistent process for IDE integrations.

Reads JSON requests from stdin (one per line), writes JSON responses to stdout.
This avoids the ~700ms Python cold-start overhead per CLI invocation.

Protocol:
  Request:  {"id": 1, "method": "find.recent", "params": {"limit": 20}}
  Response: {"id": 1, "result": [...]}
  Error:    {"id": 1, "error": {"code": -1, "message": "..."}}

Start with: emdx serve
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

import typer

from emdx.database import db
from emdx.database.documents import (
    get_document,
    get_recent_documents,
    save_document,
)
from emdx.database.search import search_documents
from emdx.models.tags import (
    list_all_tags,
    search_by_tags,
)
from emdx.models.tasks import (
    get_task_log,
    list_tasks,
    log_progress,
    update_task,
)


def _serialize(obj: Any) -> Any:
    """JSON serializer that handles datetime objects."""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ---------------------------------------------------------------------------
# RPC method handlers
# ---------------------------------------------------------------------------


def _find_recent(params: dict[str, Any]) -> list[dict[str, Any]]:
    limit = params.get("limit", 20)
    rows = get_recent_documents(limit=limit)
    return [dict(r) for r in rows]


def _find_search(params: dict[str, Any]) -> list[dict[str, Any]]:
    query = params["query"]
    limit = params.get("limit", 10)
    rows = search_documents(query, limit=limit)
    return [dict(r) for r in rows]


def _find_by_tags(params: dict[str, Any]) -> list[dict[str, Any]]:
    tags = params["tags"]
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    mode = params.get("mode", "all")
    limit = params.get("limit", 20)
    rows = search_by_tags(tags, mode=mode, limit=limit)
    return [dict(r) for r in rows]


def _view_document(params: dict[str, Any]) -> dict[str, Any] | None:
    doc_id = params["id"]
    row = get_document(doc_id)
    if row is None:
        return None
    result = dict(row)
    # Get tags for the document
    from emdx.models.tags import get_document_tags

    result["tags"] = get_document_tags(doc_id)
    # Get linked docs
    from emdx.database.document_links import get_links_for_document

    links = get_links_for_document(doc_id)
    # Map to the shape the extension expects: {doc_id, title, similarity_score, method}
    linked_docs = []
    for link in links:
        is_source = link["source_doc_id"] == doc_id
        other_id = link["target_doc_id"] if is_source else link["source_doc_id"]
        other_title = link["target_title"] if is_source else link["source_title"]
        linked_docs.append(
            {
                "doc_id": other_id,
                "title": other_title,
                "similarity_score": link["similarity_score"],
                "method": link["link_type"],
            }
        )
    result["linked_docs"] = linked_docs
    return result


def _save_document(params: dict[str, Any]) -> dict[str, Any]:
    title = params["title"]
    content = params["content"]
    tags = params.get("tags")
    doc_id = save_document(title=title, content=content, tags=tags)
    return {"id": doc_id, "title": title}


def _tag_list(params: dict[str, Any]) -> list[dict[str, Any]]:
    sort_by = params.get("sort_by", "usage")
    rows = list_all_tags(sort_by=sort_by)
    return [dict(r) for r in rows]


def _task_list(params: dict[str, Any]) -> list[dict[str, Any]]:
    status = params.get("status")
    epic_key = params.get("epic_key")
    limit = params.get("limit", 200)
    status_list = [status] if status else None
    rows = list_tasks(status=status_list, epic_key=epic_key, limit=limit)
    return [dict(r) for r in rows]


def _task_log(params: dict[str, Any]) -> list[dict[str, Any]]:
    task_id = params["id"]
    limit = params.get("limit", 50)
    rows = get_task_log(task_id, limit=limit)
    return [dict(r) for r in rows]


def _task_update(params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["id"]
    status = params.get("status")
    if status:
        update_task(task_id, status=status)
    return {"ok": True}


def _task_log_progress(params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["id"]
    message = params["message"]
    entry_id = log_progress(task_id, message)
    return {"id": entry_id}


def _status(params: dict[str, Any]) -> dict[str, Any]:
    tasks = list_tasks(limit=20)
    return {
        "tasks": [dict(t) for t in tasks],
    }


# Method dispatch table
METHODS: dict[str, Any] = {
    "find.recent": _find_recent,
    "find.search": _find_search,
    "find.by_tags": _find_by_tags,
    "view": _view_document,
    "save": _save_document,
    "tag.list": _tag_list,
    "task.list": _task_list,
    "task.log": _task_log,
    "task.update": _task_update,
    "task.log_progress": _task_log_progress,
    "status": _status,
}


def _handle_request(request: dict[str, Any]) -> dict[str, Any]:
    """Process a single JSON-RPC request and return a response."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    handler = METHODS.get(method)
    if handler is None:
        return {
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }

    try:
        result = handler(params)
        return {"id": req_id, "result": result}
    except Exception as e:
        return {
            "id": req_id,
            "error": {"code": -1, "message": str(e)},
        }


def serve() -> None:
    """Start a JSON-RPC server over stdin/stdout for IDE integrations.

    Reads one JSON request per line from stdin.
    Writes one JSON response per line to stdout.
    Runs until stdin is closed (EOF).
    """
    # Ensure schema is up to date
    db.ensure_schema()

    # Signal readiness
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        response = _handle_request(request)
        sys.stdout.write(json.dumps(response, default=_serialize) + "\n")
        sys.stdout.flush()


app = typer.Typer()


@app.command()
def serve_command() -> None:
    """JSON-RPC server over stdin/stdout for IDE integrations."""
    serve()
