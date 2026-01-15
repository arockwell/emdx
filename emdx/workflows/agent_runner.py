"""Agent execution for workflow runs.

Handles running Claude agents as part of workflow execution, including:
- Setting up log files
- Creating execution records
- Calling Claude via execute_with_claude
- Extracting results and updating records
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from .output_parser import extract_output_doc_id, extract_token_usage_detailed
from .services import document_service, execution_service, claude_service
from . import database as wf_db
from emdx.database.documents import record_document_source, find_documents_created_between

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
) -> Dict[str, Any]:
    """Run an agent with the given prompt using the existing execution system.

    Uses execute_with_claude() from the existing exec system to actually
    call Claude and get results.

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
        # Set up log file for this agent run
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        log_file = log_dir / f"workflow-agent-{individual_run_id}-{timestamp}.log"

        # Get working directory from context (set by execute_workflow)
        working_dir = context.get('_working_dir', str(Path.cwd()))

        # Create execution record
        exec_id = execution_service.create_execution(
            doc_id=context.get('input_doc_id'),
            doc_title=f"Workflow Agent Run #{individual_run_id}",
            log_file=str(log_file),
            working_dir=working_dir,
        )

        # Link execution to individual run immediately so TUI can show logs
        wf_db.update_individual_run(
            individual_run_id,
            agent_execution_id=exec_id,
        )

        # Build the full prompt with instructions to save output
        full_prompt = prompt + OUTPUT_INSTRUCTION

        # Track execution start time
        exec_start_time = datetime.now()

        # Run Claude synchronously (in thread pool to not block async)
        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(
            None,
            lambda: claude_service.execute_with_claude(
                task=full_prompt,
                execution_id=exec_id,
                log_file=log_file,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS", "Task", "TodoWrite", "WebFetch", "WebSearch"],
                verbose=False,
                working_dir=working_dir,
                doc_id=str(context.get('input_doc_id', 0)),
                context=None,
            )
        )

        # Calculate execution time
        exec_end_time = datetime.now()
        execution_time_ms = int((exec_end_time - exec_start_time).total_seconds() * 1000)

        # Update execution status
        status = 'completed' if exit_code == 0 else 'failed'
        execution_service.update_execution_status(exec_id, status, exit_code)

        # Extract token usage from the log file
        token_usage = extract_token_usage_detailed(log_file)
        tokens_used = token_usage.get('total', 0)
        input_tokens = token_usage.get('input', 0) + token_usage.get('cache_in', 0) + token_usage.get('cache_create', 0)
        output_tokens = token_usage.get('output', 0)
        cost_usd = token_usage.get('cost_usd', 0.0)

        if exit_code == 0:
            # Find output document - try database query first (more reliable),
            # then fall back to log parsing
            output_doc_id = _find_workflow_output_doc(exec_start_time, exec_end_time)

            if not output_doc_id:
                # Fallback: try to extract from log
                output_doc_id = extract_output_doc_id(log_file)
                if output_doc_id:
                    logger.debug(f"Found output doc via log parsing: {output_doc_id}")

            if not output_doc_id:
                # Last resort: save the log content as output
                log_content = log_file.read_text() if log_file.exists() else "No output captured"
                output_doc_id = document_service.save_document(
                    title=f"Workflow Agent Output - {datetime.now().isoformat()}",
                    content=f"# Agent Execution Log\n\n{log_content}",
                    tags=['workflow-output'],
                )
                # Record document source for efficient querying
                _record_output_source(individual_run_id, output_doc_id, "individual_output")

            wf_db.update_individual_run(
                individual_run_id,
                status='completed',
                output_doc_id=output_doc_id,
                agent_execution_id=exec_id,
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                execution_time_ms=execution_time_ms,
                completed_at=exec_end_time,
            )

            return {
                'success': True,
                'output_doc_id': output_doc_id,
                'tokens_used': tokens_used,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': cost_usd,
                'execution_time_ms': execution_time_ms,
                'execution_id': exec_id,
            }
        else:
            error_msg = f"Claude execution failed with exit code {exit_code}"
            wf_db.update_individual_run(
                individual_run_id,
                status='failed',
                agent_execution_id=exec_id,
                error_message=error_msg,
                tokens_used=tokens_used,
                execution_time_ms=execution_time_ms,
                completed_at=exec_end_time,
            )
            return {
                'success': False,
                'error_message': error_msg,
                'tokens_used': tokens_used,
                'execution_time_ms': execution_time_ms,
                'execution_id': exec_id,
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


def _find_workflow_output_doc(
    start_time: datetime,
    end_time: datetime,
) -> Optional[int]:
    """Find a workflow output document created during execution.

    Queries the database for documents with the 'workflow-output' tag
    created between start_time and end_time. This is more reliable than
    log parsing because it doesn't depend on Claude's output format.

    Args:
        start_time: Execution start time
        end_time: Execution end time

    Returns:
        Document ID if found, None otherwise
    """
    try:
        # Add a small buffer to account for timing differences
        # (document might be saved slightly before/after execution boundaries)
        buffer = timedelta(seconds=2)
        search_start = start_time - buffer
        search_end = end_time + buffer

        docs = find_documents_created_between(
            start_time=search_start,
            end_time=search_end,
            tags=['workflow-output'],
            limit=5,  # Get a few in case of duplicates
        )

        if docs:
            # Return the most recent one (first in list since ordered DESC)
            doc_id = docs[0]['id']
            logger.debug(f"Found workflow output doc via database query: {doc_id}")
            return doc_id

        return None

    except Exception as e:
        logger.debug(f"Database query for workflow output failed: {e}")
        return None
