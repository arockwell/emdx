"""Base class for execution strategies."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import StageConfig
from ..services import document_service, execution_service, claude_service
from .. import database as wf_db


@dataclass
class StageResult:
    """Result of executing a stage."""
    success: bool
    output_doc_id: Optional[int] = None
    synthesis_doc_id: Optional[int] = None
    individual_outputs: List[int] = field(default_factory=list)
    tokens_used: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None


class ExecutionStrategy(ABC):
    """Base class for stage execution strategies.

    Each execution mode (single, parallel, iterative, adversarial, dynamic)
    is implemented as a separate strategy class.
    """

    @abstractmethod
    async def execute(
        self,
        stage_run_id: int,
        stage: StageConfig,
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute the stage using this strategy.

        Args:
            stage_run_id: Stage run ID for tracking
            stage: Stage configuration
            context: Execution context with variables
            stage_input: Resolved input for this stage

        Returns:
            StageResult with execution results
        """
        pass

    def resolve_template(self, template: Optional[str], context: Dict[str, Any]) -> str:
        """Resolve {{variable}} templates in a string.

        Args:
            template: String with {{variable}} placeholders
            context: Dictionary of values to substitute

        Returns:
            Resolved string
        """
        if not template:
            return ""

        result = template

        # Handle indexed access like {{all_prev[0]}}
        indexed_pattern = r'\{\{(\w+)\[(\d+)\]\}\}'
        for match in re.finditer(indexed_pattern, template):
            var_name = match.group(1)
            index = int(match.group(2))
            if var_name in context and isinstance(context[var_name], list):
                if index < len(context[var_name]):
                    result = result.replace(match.group(0), str(context[var_name][index]))
                else:
                    result = result.replace(match.group(0), '')

        # Handle simple variables like {{input}}
        simple_pattern = r'\{\{(\w+(?:\.\w+)*)\}\}'
        for match in re.finditer(simple_pattern, result):
            var_name = match.group(1)
            # Handle dotted access like stage_name.output
            if '.' in var_name:
                value = context.get(var_name, '')
            else:
                value = context.get(var_name, '')
            result = result.replace(match.group(0), str(value))

        return result

    async def run_agent(
        self,
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
            agent_id: Optional agent ID to use
            prompt: The prompt to send
            context: Execution context

        Returns:
            Dict with success, output_doc_id, tokens_used, error_message
        """
        import asyncio

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
                doc_id=context.get('input_doc_id') or None,
                doc_title=f"Workflow Agent Run #{individual_run_id}",
                log_file=str(log_file),
                working_dir=working_dir,
            )

            # Link execution to individual run immediately so TUI can track it
            wf_db.update_individual_run(
                individual_run_id,
                agent_execution_id=exec_id,
            )

            # Build the full prompt with instructions to save output
            output_instruction = """

IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"

Report the document ID that was created."""

            full_prompt = prompt + output_instruction

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

            # Update execution status
            status = 'completed' if exit_code == 0 else 'failed'
            execution_service.update_execution_status(exec_id, status, exit_code)

            if exit_code == 0:
                # Try to extract output document ID from log
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # If no document was created, save the log content as output
                    log_content = log_file.read_text() if log_file.exists() else "No output captured"
                    output_doc_id = document_service.save_document(
                        title=f"Workflow Agent Output - {datetime.now().isoformat()}",
                        content=f"# Agent Execution Log\n\n{log_content}",
                        tags=['workflow-output'],
                    )

                wf_db.update_individual_run(
                    individual_run_id,
                    status='completed',
                    output_doc_id=output_doc_id,
                    agent_execution_id=exec_id,
                    tokens_used=0,  # Note: Token usage tracking not yet implemented
                    completed_at=datetime.now(),
                )

                return {
                    'success': True,
                    'output_doc_id': output_doc_id,
                    'tokens_used': 0,
                    'execution_id': exec_id,
                }
            else:
                error_msg = f"Claude execution failed with exit code {exit_code}"
                wf_db.update_individual_run(
                    individual_run_id,
                    status='failed',
                    agent_execution_id=exec_id,
                    error_message=error_msg,
                    completed_at=datetime.now(),
                )
                return {
                    'success': False,
                    'error_message': error_msg,
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

    def _extract_output_doc_id(self, log_file: Path) -> Optional[int]:
        """Extract output document ID from execution log.

        Looks for patterns like "Created document #123" or "Saved as #123"
        in the log file.

        Args:
            log_file: Path to the execution log

        Returns:
            Document ID if found, None otherwise
        """
        if not log_file.exists():
            return None

        try:
            content = log_file.read_text()
            # Look for document creation patterns
            patterns = [
                r'Created document #(\d+)',
                r'Saved as #(\d+)',
                r'document ID[:\s]+(\d+)',
                r'doc_id[:\s]+(\d+)',
                r'#(\d+)\s*\[green\]',  # Rich output format
            ]

            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            return None
        except (OSError, IOError) as e:
            # Log file read errors
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.debug(f"Could not read log file {log_file} for output doc ID extraction: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            # Log unexpected errors during parsing
            from emdx.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Unexpected error extracting output doc ID from {log_file}: {type(e).__name__}: {e}")
            return None

    async def synthesize_outputs(
        self,
        stage_run_id: int,
        output_doc_ids: List[int],
        synthesis_prompt: Optional[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Synthesize multiple outputs into one using Claude.

        Args:
            stage_run_id: Stage run ID
            output_doc_ids: List of output document IDs to synthesize
            synthesis_prompt: Prompt template for synthesis
            context: Execution context

        Returns:
            Dict with output_doc_id and tokens_used
        """
        import asyncio

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

        base_prompt = self.resolve_template(
            synthesis_prompt or "Synthesize these outputs into a coherent summary:\n\n{{outputs}}",
            synth_context,
        )

        # Add instruction to save output
        full_prompt = base_prompt + """

IMPORTANT: After synthesizing, save your synthesis as a document using:
echo "YOUR SYNTHESIS HERE" | emdx save --title "Synthesis" --tags "workflow-synthesis"

Report the document ID that was created."""

        try:
            # Set up log file
            log_dir = Path.home() / ".config" / "emdx" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            log_file = log_dir / f"workflow-synthesis-{stage_run_id}-{timestamp}.log"

            # Get working directory from context
            working_dir = context.get('_working_dir', str(Path.cwd()))

            # Create execution record
            exec_id = execution_service.create_execution(
                doc_id=context.get('input_doc_id') or None,
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

            execution_service.update_execution_status(exec_id, 'completed' if exit_code == 0 else 'failed', exit_code)

            if exit_code == 0:
                # Try to extract output document ID
                output_doc_id = self._extract_output_doc_id(log_file)

                if not output_doc_id:
                    # Fallback: save log content
                    log_content = log_file.read_text() if log_file.exists() else "No synthesis output"
                    output_doc_id = document_service.save_document(
                        title=f"Synthesis - {datetime.now().isoformat()}",
                        content=f"# Synthesis Log\n\n{log_content}",
                        tags=['workflow-synthesis'],
                    )

                return {
                    'output_doc_id': output_doc_id,
                    'tokens_used': 0,
                    'execution_id': exec_id,
                }
            else:
                # Fallback on failure: just combine outputs manually
                combined = f"# Synthesis of {len(outputs)} outputs (fallback - Claude failed)\n\n"
                for i, output in enumerate(outputs, 1):
                    combined += f"## Output {i}\n{output}\n\n"

                doc_id = document_service.save_document(
                    title=f"Synthesis (fallback) - {datetime.now().isoformat()}",
                    content=combined,
                    tags=['workflow-synthesis'],
                )

                return {
                    'output_doc_id': doc_id,
                    'tokens_used': 0,
                }

        except Exception as e:
            # Fallback: manual combination
            combined = f"# Synthesis of {len(outputs)} outputs (error: {e})\n\n"
            for i, output in enumerate(outputs, 1):
                combined += f"## Output {i}\n{output}\n\n"

            doc_id = document_service.save_document(
                title=f"Synthesis (error) - {datetime.now().isoformat()}",
                content=combined,
                tags=['workflow-synthesis'],
            )

            return {
                'output_doc_id': doc_id,
                'tokens_used': 0,
            }
