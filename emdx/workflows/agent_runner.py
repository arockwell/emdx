"""Agent execution for workflow runs.

Handles running Claude agents as part of workflow execution.
Uses the UnifiedExecutor service for consistent execution behavior
across all EMDX execution paths (agent, workflow, cascade).
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..services.unified_executor import (
    UnifiedExecutor,
    ExecutionConfig,
    ExecutionResult,
    DEFAULT_ALLOWED_TOOLS,
)
from . import database as wf_db
from emdx.database.documents import record_document_source

logger = logging.getLogger(__name__)

# Instruction appended to prompts to have agents save their output
OUTPUT_INSTRUCTION = """

IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"

Report the document ID that was created."""


async def run_agent(
    individual_run_id: int,
    agent_id: Optional[int],
    prompt: str,
    context: Dict[str, Any],
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Run an agent with the given prompt using the UnifiedExecutor.

    Args:
        individual_run_id: Individual run ID for tracking
        agent_id: Optional agent ID (not currently used, reserved for future)
        prompt: The prompt to send
        context: Execution context (must include '_working_dir')

    Returns:
        Dict with:
        - success: bool
        - output_doc_id: Optional[int]
        - tokens_used: int
        - input_tokens: int
        - output_tokens: int
        - cost_usd: float
        - execution_time_ms: int
        - execution_id: int
        - error_message: Optional[str] (on failure)
    """
    wf_db.update_individual_run(
        individual_run_id,
        status='running',
        started_at=datetime.now(),
    )

    try:
        # Get working directory from context (set by execute_workflow)
        working_dir = context.get('_working_dir', str(Path.cwd()))

        # Configure execution
        config = ExecutionConfig(
            prompt=prompt,
            output_instruction=OUTPUT_INSTRUCTION,
            working_dir=working_dir,
            title=title or f"Workflow Agent Run #{individual_run_id}",
            doc_id=context.get('input_doc_id'),
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS", "Task", "TodoWrite", "WebFetch", "WebSearch"],
            cli_tool=context.get('_cli_tool', 'claude'),
            model=context.get('_model'),
        )

        # Run execution in thread pool to not block async
        executor = UnifiedExecutor()
        loop = asyncio.get_event_loop()
        result: ExecutionResult = await loop.run_in_executor(
            None,
            lambda: executor.execute(config)
        )

        # Link execution to individual run so TUI can show logs
        wf_db.update_individual_run(
            individual_run_id,
            agent_execution_id=result.execution_id,
        )

        if result.success:
            output_doc_id = result.output_doc_id

            if not output_doc_id:
                # If no document was created, save the log content as output
                from .services import document_service
                log_content = result.log_file.read_text() if result.log_file.exists() else "No output captured"
                output_doc_id = document_service.save_document(
                    title=f"Workflow Agent Output - {datetime.now().isoformat()}",
                    content=f"# Agent Execution Log\n\n{log_content}",
                    tags=['workflow-output'],
                )

            # Record document source for efficient querying (for all outputs)
            _record_output_source(individual_run_id, output_doc_id, "individual_output")

            wf_db.update_individual_run(
                individual_run_id,
                status='completed',
                output_doc_id=output_doc_id,
                agent_execution_id=result.execution_id,
                tokens_used=result.tokens_used,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                execution_time_ms=result.execution_time_ms,
                completed_at=datetime.now(),
            )

            return {
                'success': True,
                'output_doc_id': output_doc_id,
                'tokens_used': result.tokens_used,
                'input_tokens': result.input_tokens,
                'output_tokens': result.output_tokens,
                'cost_usd': result.cost_usd,
                'execution_time_ms': result.execution_time_ms,
                'execution_id': result.execution_id,
            }
        else:
            error_msg = result.error_message or f"Claude execution failed with exit code {result.exit_code}"
            wf_db.update_individual_run(
                individual_run_id,
                status='failed',
                agent_execution_id=result.execution_id,
                error_message=error_msg,
                tokens_used=result.tokens_used,
                execution_time_ms=result.execution_time_ms,
                completed_at=datetime.now(),
            )
            return {
                'success': False,
                'error_message': error_msg,
                'tokens_used': result.tokens_used,
                'execution_time_ms': result.execution_time_ms,
                'execution_id': result.execution_id,
            }

    except Exception as e:
        wf_db.update_individual_run(
            individual_run_id,
            status='failed',
            error_message=str(e),
            completed_at=datetime.now(),
        )
        return {
            'success': False,
            'error_message': str(e),
        }


def _record_output_source(
    individual_run_id: int,
    output_doc_id: int,
    source_type: str,
) -> None:
    """Record document source for efficient querying.

    Links the output document to the workflow run hierarchy.

    Args:
        individual_run_id: The individual run that created this document
        output_doc_id: The document ID to link
        source_type: Type of source (e.g., "individual_output", "synthesis")
    """
    try:
        ir = wf_db.get_individual_run(individual_run_id)
        if ir:
            sr = wf_db.get_stage_run(ir["stage_run_id"])
            if sr:
                record_document_source(
                    document_id=output_doc_id,
                    workflow_run_id=sr.get("workflow_run_id"),
                    workflow_stage_run_id=ir["stage_run_id"],
                    workflow_individual_run_id=individual_run_id,
                    source_type=source_type,
                )
    except Exception as e:
        logger.debug(f"Failed to record document source: {e}")
