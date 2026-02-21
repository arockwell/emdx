"""Activity data loading — flat list of documents and agent executions.

No groups, no hierarchy. Just loads recent documents (excluding superseded)
and agent executions, sorted by timestamp.
"""

import logging
from datetime import datetime, timedelta

from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    AgentExecutionItem,
    DocumentItem,
)

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_svc

    HAS_DOCS = True
except ImportError:
    doc_svc = None  # type: ignore[assignment]
    HAS_DOCS = False


class ActivityDataLoader:
    """Loads activity data from DB and returns typed ActivityItem instances."""

    async def load_all(self, zombies_cleaned: bool = True) -> list[ActivityItem]:
        """Load all activity items, sorted.

        Returns:
            Sorted list of documents and agent executions.
        """
        items: list[ActivityItem] = []

        if HAS_DOCS:
            items.extend(await self._load_documents())

        items.extend(await self._load_agent_executions())

        # Sort: running items first (pinned), then by timestamp descending
        def sort_key(item: ActivityItem) -> tuple[int, float]:
            is_running = (
                item.item_type == "agent_execution" and item.status == "running"
            )
            return (
                0 if is_running else 1,
                -item.timestamp.timestamp() if item.timestamp else 0,
            )

        items.sort(key=sort_key)
        return items

    async def _load_documents(self) -> list[ActivityItem]:
        """Load recent documents (top-level only, superseded are hidden)."""
        items: list[ActivityItem] = []

        try:
            # list_recent_documents already filters parent_id IS NULL
            docs = doc_svc.list_recent_documents(limit=100, days=7)
        except Exception as e:
            logger.error(f"Error listing recent documents: {e}", exc_info=True)
            return items

        for doc in docs:
            try:
                doc_id = doc["id"]
                created = doc.get("created_at")
                title = doc.get("title", "")

                item = DocumentItem(
                    item_id=doc_id,
                    title=title or "Untitled",
                    status="completed",
                    timestamp=parse_datetime(created) or datetime.now(),
                    doc_id=doc_id,
                )

                items.append(item)

            except Exception as e:
                logger.error(
                    f"Error loading document {doc.get('id', '?')}: {e}",
                    exc_info=True,
                )

        return items

    async def _load_agent_executions(self) -> list[ActivityItem]:
        """Load standalone agent executions."""
        items: list[ActivityItem] = []
        try:
            from emdx.services.execution_service import get_agent_executions

            cutoff = datetime.now() - timedelta(days=7)
            rows = get_agent_executions(cutoff.isoformat(), limit=30)

            for row in rows:
                exec_id = row["id"]
                doc_id = row["doc_id"]
                doc_title = row["doc_title"]
                status = row["status"]
                started_at = row["started_at"]
                completed_at = row["completed_at"]
                log_file = row["log_file"]
                exit_code = row["exit_code"]
                working_dir = row["working_dir"]

                # Skip completed executions that produced a doc — the doc
                # already shows in the activity feed.
                if status == "completed" and doc_id:
                    continue

                timestamp = parse_datetime(started_at) or datetime.now()

                title = doc_title or f"Execution #{exec_id}"
                if title.startswith("Agent: "):
                    title = title[7:]
                elif title.startswith("Delegate: "):
                    title = title[10:]
                title = title[:50]

                item = AgentExecutionItem(
                    item_id=exec_id,
                    title=title,
                    timestamp=timestamp,
                    execution={
                        "id": exec_id,
                        "doc_id": doc_id,
                        "doc_title": doc_title,
                        "status": status,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "log_file": log_file,
                        "exit_code": exit_code,
                        "working_dir": working_dir,
                        "cost_usd": row.get("cost_usd", 0.0),
                        "tokens_used": row.get("tokens_used", 0),
                        "output_text": row.get("output_text"),
                    },
                    status=status or "unknown",
                    doc_id=doc_id,
                    log_file=log_file or "",
                    cli_tool="claude",
                    cost=row.get("cost_usd", 0.0),
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error loading agent executions: {e}", exc_info=True)

        return items
