"""Activity data loading — flat list of documents, agent executions, and tasks.

Loads recent documents (excluding superseded), agent executions, and tasks,
then deduplicates and sorts into three tiers: running, tasks, recent history.
"""

import logging
from datetime import datetime, timedelta

from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    AgentExecutionItem,
    DocumentItem,
    TaskItem,
)

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_svc

    HAS_DOCS = True
except ImportError:
    doc_svc = None  # type: ignore[assignment]
    HAS_DOCS = False

# Tier boundaries for section headers
TIER_RUNNING = 0
TIER_TASKS = 1
TIER_RECENT = 2


class ActivityDataLoader:
    """Loads activity data from DB and returns typed ActivityItem instances."""

    async def load_all(self, zombies_cleaned: bool = True) -> list[ActivityItem]:
        """Load all activity items, deduplicate, and sort into three tiers.

        Tier 1 (top): Running executions — sorted by start time desc
        Tier 2: Ready/active tasks — sorted by priority then created_at
        Tier 3: Recent history (completed tasks, documents, completed executions)
                — sorted by timestamp desc

        Returns:
            Sorted list of activity items with tier metadata.
        """
        docs: list[ActivityItem] = []
        if HAS_DOCS:
            docs = await self._load_documents()

        executions = await self._load_agent_executions()
        tasks = await self._load_tasks()

        # Deduplicate: task with execution_id -> skip if exec already loaded
        exec_ids = {item.item_id for item in executions if item.item_type == "agent_execution"}
        # Deduplicate: task with output_doc_id -> remove the document
        task_output_doc_ids = set()
        deduped_tasks: list[ActivityItem] = []
        for item in tasks:
            if isinstance(item, TaskItem) and item.task_data:
                eid = item.task_data.get("execution_id")
                if eid and eid in exec_ids:
                    continue
                odid = item.task_data.get("output_doc_id")
                if odid:
                    task_output_doc_ids.add(odid)
            deduped_tasks.append(item)

        # Remove documents that are superseded by tasks
        deduped_docs = [item for item in docs if item.doc_id not in task_output_doc_ids]

        # Combine all items
        all_items = deduped_docs + executions + deduped_tasks

        # Three-tier sort
        def sort_key(item: ActivityItem) -> tuple[int, float, float]:
            # Tier 1: Running executions
            if item.item_type == "agent_execution" and item.status == "running":
                return (
                    TIER_RUNNING,
                    0,
                    -item.timestamp.timestamp(),
                )

            # Tier 2: Ready/active tasks
            if item.item_type == "task" and item.status in ("open", "active"):
                priority = 3.0
                if isinstance(item, TaskItem) and item.task_data:
                    priority = float(item.task_data.get("priority") or 3)
                return (
                    TIER_TASKS,
                    priority,
                    -item.timestamp.timestamp(),
                )

            # Tier 3: Everything else (recent history)
            return (
                TIER_RECENT,
                0,
                -item.timestamp.timestamp(),
            )

        all_items.sort(key=sort_key)
        return all_items

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

    async def _load_tasks(self) -> list[ActivityItem]:
        """Load ready, active, and recently completed tasks."""
        items: list[ActivityItem] = []
        try:
            from emdx.models.tasks import (
                get_recent_completed_tasks,
                list_tasks,
            )

            # Ready + active tasks
            open_active = list_tasks(
                status=["open", "active"],
                limit=50,
            )
            # Recently completed tasks (for the history tier)
            recent_done = get_recent_completed_tasks(limit=20)

            all_tasks = open_active + recent_done

            for task in all_tasks:
                task_id = task["id"]
                title = task["title"]
                status = task["status"]
                created_at = task.get("created_at")
                updated_at = task.get("updated_at")

                # Use updated_at if available, fall back to created_at
                ts_str = updated_at or created_at
                timestamp = parse_datetime(ts_str) or datetime.now()

                if len(title) > 50:
                    title = title[:47] + "..."

                item = TaskItem(
                    item_id=task_id,
                    title=title,
                    timestamp=timestamp,
                    status=status,
                    doc_id=task.get("output_doc_id"),
                    task_data=task,
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error loading tasks: {e}", exc_info=True)

        return items
