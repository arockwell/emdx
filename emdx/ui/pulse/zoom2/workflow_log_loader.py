"""Workflow log loader - handles loading logs from workflow runs."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from emdx.models.executions import get_execution

if TYPE_CHECKING:
    from .log_content_writer import LogContentWriter

logger = logging.getLogger(__name__)

# Import workflow components
try:
    from emdx.workflows import database as wf_db
    HAS_WORKFLOWS = True
except ImportError:
    wf_db = None
    HAS_WORKFLOWS = False


class WorkflowLogLoader:
    """Handles loading logs from workflow runs."""

    def __init__(self, writer: 'LogContentWriter'):
        self.writer = writer

    async def load_workflow_run(
        self, run: Dict[str, Any], stage_name: Optional[str] = None
    ) -> bool:
        """Load logs from a workflow run's context or individual execution logs.

        Returns True if logs were successfully loaded.
        """
        self.writer.clear()

        try:
            # Try to load individual run execution logs (for dynamic mode)
            if HAS_WORKFLOWS and wf_db:
                loaded = await self._load_individual_run_logs(run, stage_name)
                if loaded:
                    return True

            # Fallback: Get context from run
            return self._load_context_logs(run, stage_name)

        except Exception as e:
            logger.error(f"Error loading workflow run logs: {e}", exc_info=True)
            self.writer.write_error(str(e))
            return False

    async def _load_individual_run_logs(
        self, run: Dict[str, Any], stage_name: Optional[str]
    ) -> bool:
        """Load logs from individual run execution files (for dynamic mode).

        Returns True if any logs were loaded.
        """
        # Get stage runs for this workflow run
        stage_runs = wf_db.list_stage_runs(run['id'])

        # Collect all log files to load
        logs_to_load = []

        for stage_run in stage_runs:
            # Skip if filtering by stage name and this isn't the one
            if stage_name and stage_run.get('stage_name') != stage_name:
                continue

            # Get individual runs for this stage
            individual_runs = wf_db.list_individual_runs(stage_run['id'])

            if not individual_runs:
                continue

            for ind_run in individual_runs:
                exec_id = ind_run.get('agent_execution_id')
                if not exec_id:
                    continue

                # Get the execution to find the log file
                execution = get_execution(str(exec_id))
                if not execution:
                    continue

                log_path = execution.log_path
                if not log_path.exists():
                    continue

                branch_name = ind_run.get(
                    'input_context', f"Run #{ind_run.get('run_number', '?')}"
                )
                status = ind_run.get('status', 'unknown')
                logs_to_load.append((branch_name, status, log_path))

        if not logs_to_load:
            return False

        # Show summary header
        self.writer.write_raw(f"[bold]Loading {len(logs_to_load)} execution logs...[/bold]")

        # Load logs one at a time with yields to keep UI responsive
        for branch_name, status, log_path in logs_to_load:
            status_icon = self._get_status_icon(status)
            self.writer.write_header(f"{status_icon} {branch_name}")

            # Read file in a thread to avoid blocking
            try:
                content = await asyncio.to_thread(log_path.read_text)
                # Only show last 100 lines per log to avoid overwhelming the UI
                lines = content.strip().split('\n')
                if len(lines) > 100:
                    self.writer.write_info(f"... ({len(lines) - 100} lines omitted) ...")
                    lines = lines[-100:]
                for line in lines:
                    self.writer.write_raw(line)
            except Exception as e:
                self.writer.write_error(f"Error reading log: {e}")

            # Yield to let UI update
            await asyncio.sleep(0)

        return True

    def _load_context_logs(
        self, run: Dict[str, Any], stage_name: Optional[str]
    ) -> bool:
        """Load logs from run context (fallback method).

        Returns True if logs were loaded.
        """
        context = run.get('context_json')
        if isinstance(context, str):
            context = json.loads(context)

        if not context:
            self.writer.write_info("No log data in this run")
            return False

        # Find stage outputs in context
        output_keys = [k for k in context.keys() if k.endswith('.output')]

        if stage_name:
            # Show specific stage
            output_key = f"{stage_name}.output"
            if output_key in context:
                self.writer.write_content(context[output_key])
                return True
            else:
                self.writer.write_info(f"No output for stage '{stage_name}'")
                return False
        else:
            # Show all stage outputs
            if not output_keys:
                self.writer.write_info("No stage outputs found in context")
                return False

            for key in sorted(output_keys):
                stage = key.replace('.output', '')
                self.writer.write_header(f"STAGE: {stage}")
                output = context[key]
                if isinstance(output, str):
                    self.writer.write_content(output)
                else:
                    self.writer.write_content(str(output))

            return True

    @staticmethod
    def _get_status_icon(status: str) -> str:
        """Get status icon for a given status."""
        if status == 'completed':
            return "✅"
        elif status == 'running':
            return "🔄"
        else:
            return "❌"
