"""Knowledge event recording for emdx.

Append-only event log for tracking KB interactions: searches, views,
creates, updates, deletes, and asks.
"""

from __future__ import annotations

import json
import logging
import os

from emdx.database.connection import db_connection

logger = logging.getLogger(__name__)

# Valid event types
EVENT_TYPES = frozenset({"search", "view", "create", "update", "delete", "ask"})


def record_event(
    event_type: str,
    doc_id: int | None = None,
    query: str | None = None,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> int | None:
    """Record a knowledge event to the append-only event log.

    Args:
        event_type: One of 'search', 'view', 'create', 'update',
                    'delete', 'ask'.
        doc_id: Optional document ID associated with the event.
        query: Optional search query (for search/ask events).
        metadata: Optional dict of extra context (serialised as JSON).

    Returns:
        The event row ID, or None if recording failed.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown event type: %s", event_type)
        return None

    session_id = os.environ.get("EMDX_EXECUTION_ID")
    metadata_json: str | None = None
    if metadata:
        metadata_json = json.dumps(metadata)

    try:
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO knowledge_events "
                "(event_type, doc_id, query, session_id, metadata_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_type, doc_id, query, session_id, metadata_json),
            )
            conn.commit()
            return cursor.lastrowid
    except Exception:
        # Event recording is non-critical — never break the caller
        logger.debug(
            "Failed to record event %s (table may not exist yet)",
            event_type,
            exc_info=True,
        )
        return None
