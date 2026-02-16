"""Activity data loading — extracts DB queries from activity_view.py.

Produces typed ActivityItem subclasses from activity_items.py.
"""

import logging
from datetime import datetime, timedelta
from typing import cast

from emdx.ui.types import GroupDict
from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    AgentExecutionItem,
    DocumentItem,
    GroupItem,
)

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_svc
    from emdx.services import group_service as group_svc

    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_svc = None  # type: ignore[assignment]
    group_svc = None  # type: ignore[assignment]
    HAS_DOCS = False
    HAS_GROUPS = False


class ActivityDataLoader:
    """Loads activity data from DB and returns typed ActivityItem instances."""

    def __init__(self) -> None:
        pass

    async def load_all(self, zombies_cleaned: bool = True) -> list[ActivityItem]:
        """Load all activity items, sorted.

        Args:
            zombies_cleaned: Whether zombie cleanup has already been done.

        Returns:
            Sorted list of typed ActivityItem instances.
        """
        items: list[ActivityItem] = []

        if HAS_GROUPS:
            items.extend(await self._load_groups())

        if HAS_DOCS:
            items.extend(await self._load_direct_saves())

        items.extend(await self._load_agent_executions())

        # Sort: running items first (pinned), then by timestamp descending
        def sort_key(item: ActivityItem) -> tuple:
            is_running = item.item_type == "agent_execution" and item.status == "running"
            return (
                0 if is_running else 1,
                -item.timestamp.timestamp() if item.timestamp else 0,
            )

        items.sort(key=sort_key)
        return items

    async def _load_groups(self) -> list[ActivityItem]:
        """Load document groups into typed GroupItem instances.

        Uses a single batched query instead of N+1 per-group lookups.
        """
        items: list[ActivityItem] = []
        try:
            top_groups = group_svc.list_top_groups_with_counts()
        except Exception as e:
            logger.error(f"Error listing groups: {e}", exc_info=True)
            return items

        for group in top_groups:
            try:
                group_id = group["id"]
                created = parse_datetime(group.get("created_at")) or datetime.now()

                item = GroupItem(
                    item_id=group_id,
                    title=group["name"],
                    timestamp=created,
                    group=cast(GroupDict, dict(group)),
                    doc_count=group["doc_count"],
                    total_cost=group["total_cost_usd"] or 0,
                    total_tokens=group["total_tokens"],
                    child_group_count=group["child_group_count"],
                    cost=group["total_cost_usd"] or 0,
                )

                items.append(item)

            except Exception as e:
                logger.error(f"Error loading group {group.get('id', '?')}: {e}", exc_info=True)

        return items

    async def _load_direct_saves(self) -> list[ActivityItem]:
        """Load documents not added to groups (standalone saves)."""
        items: list[ActivityItem] = []
        grouped_doc_ids: set[int] = set()
        if HAS_GROUPS:
            try:
                grouped_doc_ids = group_svc.get_all_grouped_document_ids()
            except Exception as e:
                logger.debug(f"Error getting grouped doc IDs: {e}")

        try:
            docs = doc_svc.list_recent_documents(limit=100, days=7)
        except Exception as e:
            logger.error(f"Error listing recent documents: {e}", exc_info=True)
            return items

        for doc in docs:
            try:
                doc_id = doc["id"]
                if doc_id in grouped_doc_ids:
                    continue

                created = doc.get("created_at")
                title = doc.get("title", "")
                children_docs = doc_svc.get_children(doc_id)
                has_children = len(children_docs) > 0

                item = DocumentItem(
                    item_id=doc_id,
                    title=title or "Untitled",
                    status="completed",
                    timestamp=parse_datetime(created) or datetime.now(),
                    doc_id=doc_id,
                    has_children=has_children,
                )

                items.append(item)

            except Exception as e:
                logger.error(f"Error loading document {doc.get('id', '?')}: {e}", exc_info=True)

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
                # already shows in the activity feed (standalone or grouped).
                # Only keep running/failed executions for visibility.
                if status == "completed" and doc_id:
                    continue

                timestamp = parse_datetime(started_at) or datetime.now()

                cli_tool = "claude"
                if log_file and "cursor" in log_file.lower():
                    cli_tool = "cursor"

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
                    cli_tool=cli_tool,
                    cost=row.get("cost_usd", 0.0),
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error loading agent executions: {e}", exc_info=True)

        return items
