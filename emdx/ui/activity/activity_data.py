"""Activity data loading — extracts DB queries from activity_view.py.

Produces typed ActivityItem subclasses from activity_items.py.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    WorkflowItem,
    DocumentItem,
    GroupItem,
    CascadeRunItem,
    CascadeStageItem,
    AgentExecutionItem,
    MailItem,
)

logger = logging.getLogger(__name__)

# Import services (same guards as activity_view)
try:
    from emdx.workflows import database as wf_db
    from emdx.workflows.registry import workflow_registry

    HAS_WORKFLOWS = True
except ImportError:
    wf_db = None
    workflow_registry = None
    HAS_WORKFLOWS = False

try:
    from emdx.database import documents as doc_db
    from emdx.database import groups as groups_db
    from emdx.database.documents import (
        get_workflow_document_ids,
        list_non_workflow_documents,
    )

    HAS_DOCS = True
    HAS_GROUPS = True
except ImportError:
    doc_db = None
    groups_db = None
    HAS_DOCS = False
    HAS_GROUPS = False

    def get_workflow_document_ids():
        return set()

    def list_non_workflow_documents(**kwargs):
        return []


class ActivityDataLoader:
    """Loads activity data from DB and returns typed ActivityItem instances."""

    def __init__(self) -> None:
        # Track workflow states for completion notifications
        self._last_workflow_states: Dict[int, str] = {}
        # Callbacks for notifications
        self.on_workflow_complete: Optional[callable] = None

    async def load_all(self, zombies_cleaned: bool = True) -> List[ActivityItem]:
        """Load all activity items, sorted.

        Args:
            zombies_cleaned: Whether zombie cleanup has already been done.

        Returns:
            Sorted list of typed ActivityItem instances.
        """
        items: List[ActivityItem] = []

        # Clean up zombie workflow runs on first load
        if HAS_WORKFLOWS and wf_db and not zombies_cleaned:
            try:
                cleaned = wf_db.cleanup_zombie_workflow_runs(max_age_hours=24.0)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} zombie workflow runs")
            except Exception as e:
                logger.debug(f"Could not cleanup zombies: {e}")

        if HAS_GROUPS and groups_db:
            items.extend(await self._load_groups())

        if HAS_WORKFLOWS and wf_db:
            items.extend(await self._load_workflows())

        if HAS_DOCS and doc_db:
            items.extend(await self._load_direct_saves())

        items.extend(await self._load_cascade_executions())
        items.extend(await self._load_agent_executions())
        items.extend(await self._load_mail_messages())

        # Sort: running items first (pinned), then by timestamp descending
        def sort_key(item: ActivityItem) -> Tuple:
            is_running = (
                (item.item_type == "workflow" and item.status == "running")
                or (item.item_type == "agent_execution" and item.status == "running")
                or (item.item_type == "mail" and not getattr(item, "is_read", True))
            )
            return (
                0 if is_running else 1,
                -item.timestamp.timestamp() if item.timestamp else 0,
            )

        items.sort(key=sort_key)
        return items

    async def _load_workflows(self) -> List[ActivityItem]:
        """Load workflow runs into typed WorkflowItem instances.

        Merges stage_runs + individual_runs into a single pass to halve DB calls.
        """
        items: List[ActivityItem] = []
        try:
            runs = wf_db.list_workflow_runs(limit=50)
        except Exception as e:
            logger.error(f"Error listing workflow runs: {e}", exc_info=True)
            return items

        for run in runs:
            try:
                started = parse_datetime(run.get("started_at")) or datetime.now()

                # Skip zombie running workflows (running for > 2 hours)
                if run.get("status") == "running":
                    age_hours = (datetime.now() - started).total_seconds() / 3600
                    if age_hours > 2:
                        continue

                # Get workflow name
                wf_name = "Workflow"
                if workflow_registry:
                    try:
                        wf = workflow_registry.get_workflow(run["workflow_id"])
                        if wf:
                            wf_name = wf.display_name
                    except Exception:
                        pass

                # Get task title from input variables
                task_title = ""
                try:
                    input_vars = run.get("input_variables")
                    if isinstance(input_vars, str):
                        input_vars = json.loads(input_vars)
                    if input_vars:
                        task_title = input_vars.get("task_title", "")
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

                title = task_title or wf_name

                # Single pass over stage_runs and individual_runs
                # (previously done twice: once for cost, once for outputs/progress)
                cost = run.get("total_cost_usd", 0) or 0
                has_outputs = False
                output_doc_id = None
                output_count = 0
                total_target = 0
                total_completed = 0
                current_stage = ""
                is_synthesizing = False
                total_input_tokens = 0
                total_output_tokens = 0
                cost_from_runs = 0.0

                try:
                    stage_runs = wf_db.list_stage_runs(run["id"])
                    for sr in stage_runs:
                        target = sr.get("target_runs", 1)
                        completed = sr.get("runs_completed", 0)
                        total_target += target
                        total_completed += completed

                        if sr.get("status") == "running":
                            current_stage = sr.get("stage_name", "")
                        elif sr.get("status") == "synthesizing":
                            current_stage = sr.get("stage_name", "")
                            is_synthesizing = True

                        if sr.get("synthesis_doc_id"):
                            output_count += 1
                            has_outputs = True
                            if not output_doc_id:
                                output_doc_id = sr["synthesis_doc_id"]

                        ind_runs = wf_db.list_individual_runs(sr["id"])
                        for ir in ind_runs:
                            total_input_tokens += ir.get("input_tokens", 0) or 0
                            total_output_tokens += ir.get("output_tokens", 0) or 0
                            ir_cost = ir.get("cost_usd", 0) or 0
                            cost_from_runs += ir_cost
                            if ir.get("output_doc_id"):
                                output_count += 1
                                has_outputs = True
                                if not output_doc_id:
                                    output_doc_id = ir["output_doc_id"]
                except Exception as e:
                    logger.debug(f"Error scanning workflow outputs for run {run['id']}: {e}")

                # Use summed cost from runs if top-level cost is missing
                if not cost:
                    cost = cost_from_runs

                # For completed workflows, use output document timestamp
                timestamp = started
                if output_doc_id and run.get("status") in ("completed", "failed") and HAS_DOCS:
                    try:
                        out_doc = doc_db.get_document(output_doc_id)
                        if out_doc:
                            doc_created = parse_datetime(out_doc.get("created_at"))
                            if doc_created:
                                timestamp = doc_created
                    except Exception:
                        pass

                item = WorkflowItem(
                    item_id=run["id"],
                    title=title,
                    timestamp=timestamp,
                    workflow_run=run,
                    status=run.get("status", "unknown"),
                    cost=cost,
                    tokens=0,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    progress_completed=total_completed if run.get("status") == "running" else 0,
                    progress_total=total_target if run.get("status") == "running" else 0,
                    progress_stage=current_stage if run.get("status") == "running" else "",
                    output_count=output_count,
                    doc_id=output_doc_id if run.get("status") in ("completed", "failed") else None,
                    has_workflow_outputs=has_outputs,
                )

                # Store synthesizing state for display
                if run.get("status") == "running" and is_synthesizing:
                    item._is_synthesizing = True

                # Track for notifications
                old_status = self._last_workflow_states.get(run["id"])
                new_status = run.get("status")
                if old_status == "running" and new_status in ("completed", "failed"):
                    if self.on_workflow_complete:
                        self.on_workflow_complete(run["id"], new_status == "completed")
                self._last_workflow_states[run["id"]] = new_status

                items.append(item)

            except Exception as e:
                logger.error(f"Error loading workflow run {run.get('id', '?')}: {e}", exc_info=True)

        return items

    async def _load_groups(self) -> List[ActivityItem]:
        """Load document groups into typed GroupItem instances."""
        items: List[ActivityItem] = []
        try:
            top_groups = groups_db.list_groups(top_level_only=True)
        except Exception as e:
            logger.error(f"Error listing groups: {e}", exc_info=True)
            return items

        for group in top_groups:
            try:
                group_id = group["id"]
                created = parse_datetime(group.get("created_at")) or datetime.now()
                child_groups = groups_db.get_child_groups(group_id)
                doc_count = groups_db.get_recursive_doc_count(group_id)

                item = GroupItem(
                    item_id=group_id,
                    title=group["name"],
                    timestamp=created,
                    group=group,
                    doc_count=doc_count,
                    total_cost=group.get("total_cost_usd", 0) or 0,
                    total_tokens=group.get("total_tokens", 0) or 0,
                    child_group_count=len(child_groups),
                    cost=group.get("total_cost_usd", 0) or 0,
                )

                items.append(item)

            except Exception as e:
                logger.error(f"Error loading group {group.get('id', '?')}: {e}", exc_info=True)

        return items

    async def _load_direct_saves(self) -> List[ActivityItem]:
        """Load documents not created by workflows or added to groups."""
        items: List[ActivityItem] = []
        grouped_doc_ids: Set[int] = set()
        if HAS_GROUPS and groups_db:
            try:
                grouped_doc_ids = groups_db.get_all_grouped_document_ids()
            except Exception as e:
                logger.debug(f"Error getting grouped doc IDs: {e}")

        try:
            docs = list_non_workflow_documents(limit=100, days=7, include_archived=False)
        except Exception as e:
            logger.error(f"Error listing non-workflow documents: {e}", exc_info=True)
            return items

        for doc in docs:
            try:
                doc_id = doc["id"]
                if doc_id in grouped_doc_ids:
                    continue

                created = doc.get("created_at")
                title = doc.get("title", "")
                children_docs = doc_db.get_children(doc_id, include_archived=False)
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

    async def _load_cascade_executions(self) -> List[ActivityItem]:
        """Load cascade executions into CascadeRunItem instances."""
        items: List[ActivityItem] = []
        try:
            from emdx.database.connection import db_connection
            from emdx.database import cascade as cascade_db

            cutoff = datetime.now() - timedelta(days=7)
            seen_run_ids: Set[int] = set()

            # Load cascade runs (grouped view)
            try:
                runs = cascade_db.list_cascade_runs(limit=30)

                for run in runs:
                    run_id = run.get("id")
                    if not run_id:
                        continue

                    seen_run_ids.add(run_id)
                    timestamp = parse_datetime(run.get("started_at")) or datetime.now()
                    title = run.get("initial_doc_title", f"Cascade Run #{run_id}")[:40]
                    executions = cascade_db.get_cascade_run_executions(run_id)

                    item = CascadeRunItem(
                        item_id=run_id,
                        title=title,
                        timestamp=timestamp,
                        cascade_run=run,
                        status=run.get("status", "running"),
                        pipeline_name=run.get("pipeline_name", "default"),
                        current_stage=run.get("current_stage", ""),
                        execution_count=len(executions),
                    )
                    items.append(item)

            except Exception as e:
                logger.debug(f"Could not load cascade runs (may not exist yet): {e}")

            # Backward-compat: individual executions not part of any run
            with db_connection.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at, e.completed_at,
                           d.stage, d.pr_url, e.cascade_run_id
                    FROM executions e
                    LEFT JOIN documents d ON e.doc_id = d.id
                    WHERE e.doc_id IS NOT NULL
                      AND e.started_at > ?
                      AND (e.cascade_run_id IS NULL OR e.cascade_run_id NOT IN (SELECT id FROM cascade_runs))
                      AND e.id = (
                          SELECT MAX(e2.id) FROM executions e2
                          WHERE e2.doc_id = e.doc_id
                      )
                    ORDER BY e.started_at DESC
                    LIMIT 50
                    """,
                    (cutoff.isoformat(),),
                )
                rows = cursor.fetchall()

            for row in rows:
                exec_id, doc_id, doc_title, status, started_at, completed_at, stage, pr_url, run_id = row

                if run_id and run_id in seen_run_ids:
                    continue

                timestamp = parse_datetime(started_at) or datetime.now()
                title = doc_title or f"Document #{doc_id}"
                if stage:
                    title = f"📋 {title}"
                if pr_url:
                    title = f"🔗 {title}"

                # Use CascadeStageItem for individual cascade executions (backward compat)
                item = CascadeStageItem(
                    item_id=exec_id,
                    title=title,
                    status=status or "unknown",
                    timestamp=timestamp,
                    doc_id=doc_id,
                    stage=stage or "",
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error loading cascade executions: {e}", exc_info=True)

        return items

    async def _load_agent_executions(self) -> List[ActivityItem]:
        """Load standalone agent executions."""
        items: List[ActivityItem] = []
        try:
            from emdx.database.connection import db_connection

            cutoff = datetime.now() - timedelta(days=7)

            with db_connection.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT e.id, e.doc_id, e.doc_title, e.status, e.started_at,
                           e.completed_at, e.log_file, e.exit_code, e.working_dir
                    FROM executions e
                    WHERE e.started_at > ?
                      AND (e.doc_title LIKE 'Agent:%' OR e.doc_title LIKE 'Delegate:%')
                      AND e.cascade_run_id IS NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM workflow_individual_runs ir
                          WHERE ir.agent_execution_id = e.id
                      )
                    ORDER BY e.started_at DESC
                    LIMIT 30
                    """,
                    (cutoff.isoformat(),),
                )
                rows = cursor.fetchall()

            for row in rows:
                exec_id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir = row

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
                    },
                    status=status or "unknown",
                    doc_id=doc_id,
                    log_file=log_file or "",
                    cli_tool=cli_tool,
                )
                items.append(item)

        except Exception as e:
            logger.error(f"Error loading agent executions: {e}", exc_info=True)

        return items

    async def _load_mail_messages(self) -> List[ActivityItem]:
        """Load mail messages."""
        items: List[ActivityItem] = []
        try:
            import asyncio
            from emdx.services.mail_service import get_mail_service, get_mail_config_repo

            if not get_mail_config_repo():
                return items

            service = get_mail_service()
            messages = await asyncio.to_thread(service.list_inbox, limit=20)

            for msg in messages:
                ts = parse_datetime(msg.created_at)
                timestamp = ts.replace(tzinfo=None) if ts and ts.tzinfo else (ts or datetime.now())

                item = MailItem(
                    item_id=msg.number,
                    title=msg.title,
                    timestamp=timestamp,
                    mail_message={
                        "body": msg.body,
                        "sender": msg.sender,
                        "recipient": msg.recipient,
                        "url": msg.url,
                        "comment_count": msg.comment_count,
                    },
                    sender=msg.sender,
                    recipient=msg.recipient,
                    is_read=msg.is_read,
                    comment_count=msg.comment_count,
                    url=msg.url,
                )
                items.append(item)

        except Exception as e:
            logger.debug(f"Could not load mail messages: {e}")

        return items
