"""Output synthesis for parallel workflow runs.

Combines multiple agent outputs into a single synthesized result.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .output_parser import extract_output_doc_id
from .template import resolve_template
from .services import document_service, execution_service, claude_service
from . import database as wf_db
from emdx.database.documents import record_document_source

logger = logging.getLogger(__name__)

# Default synthesis prompt when none is provided
DEFAULT_SYNTHESIS_PROMPT = "Synthesize these outputs into a coherent summary:\n\n{{outputs}}"

# Instruction for synthesis agent to save output
SYNTHESIS_INSTRUCTION = """

IMPORTANT: After synthesizing, save your synthesis as a document using:
echo "YOUR SYNTHESIS HERE" | emdx save --title "Synthesis" --tags "workflow-synthesis"

Report the document ID that was created."""


async def synthesize_outputs(
    stage_run_id: int,
    output_doc_ids: List[int],
    synthesis_prompt: Optional[str],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Synthesize multiple outputs into one using Claude.

    Gathers content from all output documents, combines them with a
    synthesis prompt, and runs Claude to produce a unified result.

    Args:
        stage_run_id: Stage run ID for tracking
        output_doc_ids: List of output document IDs to synthesize
        synthesis_prompt: Prompt template for synthesis (uses default if None)
        context: Execution context (must include '_working_dir')

    Returns:
        Dict with:
        - output_doc_id: The synthesized document ID
        - tokens_used: int
        - execution_id: Optional[int]
    """
    # Gather all outputs
    outputs = []
    for doc_id in output_doc_ids:
        doc = document_service.get_document(doc_id)
        if doc:
            outputs.append(doc.get('content', ''))

    # Build synthesis context
    synth_context = dict(context)
    synth_context['outputs'] = '\n\n---\n\n'.join(outputs)
    synth_context['output_count'] = len(outputs)

    base_prompt = resolve_template(
        synthesis_prompt or DEFAULT_SYNTHESIS_PROMPT,
        synth_context,
    )

    # Add instruction to save output
    full_prompt = base_prompt + SYNTHESIS_INSTRUCTION

    try:
        # Set up log file
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        log_file = log_dir / f"workflow-synthesis-{stage_run_id}-{timestamp}.log"

        # Get working directory from context
        working_dir = context.get('_working_dir', str(Path.cwd()))

        # Create execution record
        input_doc_id = context.get('input_doc_id')
        if input_doc_id == 0:
            input_doc_id = None

        exec_id = execution_service.create_execution(
            doc_id=input_doc_id,
            doc_title=f"Workflow Synthesis #{stage_run_id}",
            log_file=str(log_file),
            working_dir=working_dir,
        )

        # Run Claude
        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(
            None,
            lambda: claude_service.execute_with_claude(
                task=full_prompt,
                execution_id=exec_id,
                log_file=log_file,
                allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
                verbose=False,
                working_dir=working_dir,
                doc_id=str(context.get('input_doc_id', 0)),
                context=None,
            )
        )

        execution_service.update_execution_status(
            exec_id,
            'completed' if exit_code == 0 else 'failed',
            exit_code,
        )

        if exit_code == 0:
            # Try to extract output document ID
            output_doc_id = extract_output_doc_id(log_file)

            if not output_doc_id:
                # Fallback: save log content
                output_doc_id = _save_fallback_synthesis(
                    stage_run_id, log_file, outputs, "Log"
                )
            else:
                # Record document source so synthesis doc doesn't appear
                # as a duplicate "direct save" in the activity view
                try:
                    sr = wf_db.get_stage_run(stage_run_id)
                    if sr:
                        record_document_source(
                            document_id=output_doc_id,
                            workflow_run_id=sr.get("workflow_run_id"),
                            workflow_stage_run_id=stage_run_id,
                            source_type="synthesis",
                        )
                except Exception as e:
                    logger.debug(f"Failed to record synthesis source: {e}")

            return {
                'output_doc_id': output_doc_id,
                'tokens_used': 0,
                'execution_id': exec_id,
            }
        else:
            # Fallback on failure: just combine outputs manually
            output_doc_id = _save_fallback_synthesis(
                stage_run_id, None, outputs, "fallback - Claude failed"
            )

            return {
                'output_doc_id': output_doc_id,
                'tokens_used': 0,
            }

    except Exception as e:
        # Fallback: manual combination
        output_doc_id = _save_fallback_synthesis(
            stage_run_id, None, outputs, f"error: {e}"
        )

        return {
            'output_doc_id': output_doc_id,
            'tokens_used': 0,
        }


def _save_fallback_synthesis(
    stage_run_id: int,
    log_file: Optional[Path],
    outputs: List[str],
    reason: str,
) -> int:
    """Save a fallback synthesis when Claude fails.

    Combines outputs manually and saves as a document.

    Args:
        stage_run_id: Stage run ID for recording source
        log_file: Optional log file to include content from
        outputs: List of output strings to combine
        reason: Reason for fallback (included in title)

    Returns:
        Document ID of the saved synthesis
    """
    if log_file and log_file.exists():
        log_content = log_file.read_text()
        combined = f"# Synthesis {reason}\n\n{log_content}"
    else:
        combined = f"# Synthesis of {len(outputs)} outputs ({reason})\n\n"
        for i, output in enumerate(outputs, 1):
            combined += f"## Output {i}\n{output}\n\n"

    doc_id = document_service.save_document(
        title=f"Synthesis ({reason}) - {datetime.now().isoformat()}",
        content=combined,
        tags=['workflow-synthesis'],
    )

    # Record document source for efficient querying
    try:
        sr = wf_db.get_stage_run(stage_run_id)
        if sr:
            record_document_source(
                document_id=doc_id,
                workflow_run_id=sr.get("workflow_run_id"),
                workflow_stage_run_id=stage_run_id,
                source_type="synthesis",
            )
    except Exception as e:
        logger.debug(f"Failed to record synthesis source: {e}")

    return doc_id
