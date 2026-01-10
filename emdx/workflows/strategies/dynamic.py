"""Dynamic execution strategy - discover items at runtime and process in parallel."""

import asyncio
import subprocess
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import ExecutionStrategy, StageResult

if TYPE_CHECKING:
    from ..base import StageConfig


class DynamicStrategy(ExecutionStrategy):
    """Execute dynamic mode: discover items and process each in parallel.

    Dynamic mode:
    1. Runs discovery_command to get a list of items
    2. Creates a worktree for each item (up to max_concurrent)
    3. Processes items in parallel, respecting concurrency limits
    4. Optionally synthesizes results at the end

    Useful for batch processing discovered files, branches, etc.
    """

    async def execute(
        self,
        stage_run_id: int,
        stage: "StageConfig",
        context: Dict[str, Any],
        stage_input: Optional[str],
    ) -> StageResult:
        """Execute dynamic mode: discover items and process each in parallel.

        Args:
            stage_run_id: Stage run ID
            stage: Stage configuration
            context: Execution context
            stage_input: Resolved input for this stage

        Returns:
            StageResult with all outputs
        """
        from ..worktree_pool import WorktreePool

        # Get discovery command (CLI override takes precedence)
        discovery_command = context.get("_discovery_override") or stage.discovery_command

        # Validate configuration
        if not discovery_command:
            return StageResult(
                success=False, error_message="Dynamic mode requires discovery_command"
            )

        # Get max_concurrent (CLI override takes precedence)
        max_concurrent = context.get("_max_concurrent_override") or stage.max_concurrent

        # Step 1: Run discovery
        try:
            items = await self._run_discovery(discovery_command, context)
        except Exception as e:
            return StageResult(success=False, error_message=f"Discovery failed: {e}")

        if not items:
            return StageResult(success=True, error_message="No items discovered")

        # Update target_runs to reflect discovered item count
        self._update_stage_run(stage_run_id, target_runs=len(items))

        # Step 2: Set up worktree pool
        base_branch = context.get("base_branch", "main")
        pool = WorktreePool(
            max_size=max_concurrent,
            base_branch=base_branch,
            repo_root=context.get("_working_dir"),
        )

        output_doc_ids: List[int] = []
        total_tokens = 0
        errors: List[str] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_item(item_index: int, item: str) -> Dict[str, Any]:
            """Process a single discovered item."""
            async with semaphore:
                async with pool.acquire(target_branch=item) as worktree:
                    # Build item-specific context
                    item_context = dict(context)
                    item_context[stage.item_variable] = item
                    item_context["_working_dir"] = worktree.path
                    item_context["item_index"] = item_index
                    item_context["total_items"] = len(items)

                    # Resolve prompt with item context
                    prompt = (
                        self._resolve_template(stage.prompt, item_context)
                        if stage.prompt
                        else item
                    )

                    # Create individual run record
                    individual_run_id = self._create_individual_run(
                        stage_run_id=stage_run_id,
                        run_number=item_index + 1,
                        prompt_used=prompt,
                        input_context=item,
                    )

                    # Execute agent
                    result = await self._run_agent(
                        individual_run_id=individual_run_id,
                        agent_id=stage.agent_id,
                        prompt=prompt,
                        context=item_context,
                    )

                    return {"item": item, "index": item_index, **result}

        try:
            # Step 3: Process all items in parallel
            tasks = [process_item(i, item) for i, item in enumerate(items)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            successful_items = 0
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
                    if not stage.continue_on_failure:
                        break
                elif result.get("success"):
                    successful_items += 1
                    if result.get("output_doc_id"):
                        output_doc_ids.append(result["output_doc_id"])
                    total_tokens += result.get("tokens_used", 0)
                else:
                    error_msg = f"Item '{result.get('item')}' failed: {result.get('error_message', 'Unknown error')}"
                    errors.append(error_msg)
                    if not stage.continue_on_failure:
                        break

            # Update stage progress
            self._update_stage_run(stage_run_id, runs_completed=successful_items)

            # Step 4: Optional synthesis
            synthesis_doc_id = None
            if output_doc_ids and stage.synthesis_prompt:
                synthesis_result = await self._synthesize_outputs(
                    stage_run_id=stage_run_id,
                    output_doc_ids=output_doc_ids,
                    synthesis_prompt=stage.synthesis_prompt,
                    context=context,
                )
                synthesis_doc_id = synthesis_result.get("output_doc_id")
                total_tokens += synthesis_result.get("tokens_used", 0)

            # Determine overall success
            if not stage.continue_on_failure and errors:
                return StageResult(
                    success=False,
                    error_message=f"Dynamic execution failed: {'; '.join(errors)}",
                    individual_outputs=output_doc_ids,
                    tokens_used=total_tokens,
                )

            # Success if at least one item succeeded
            success = successful_items > 0

            return StageResult(
                success=success,
                output_doc_id=(
                    synthesis_doc_id or (output_doc_ids[-1] if output_doc_ids else None)
                ),
                synthesis_doc_id=synthesis_doc_id,
                individual_outputs=output_doc_ids,
                tokens_used=total_tokens,
                error_message=(
                    f"Processed {successful_items}/{len(items)} items. Errors: {'; '.join(errors)}"
                    if errors
                    else None
                ),
            )

        finally:
            # Clean up worktree pool
            await pool.cleanup()

    async def _run_discovery(
        self,
        command: str,
        context: Dict[str, Any],
    ) -> List[str]:
        """Run discovery command and return list of items.

        Args:
            command: Shell command that outputs items (one per line)
            context: Execution context for template resolution

        Returns:
            List of discovered items (strings)
        """
        # Resolve any templates in the command
        resolved_command = self._resolve_template(command, context)

        # Run command
        result = await asyncio.to_thread(
            subprocess.run,
            resolved_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=context.get("_working_dir"),
        )

        if result.returncode != 0:
            raise ValueError(f"Discovery command failed: {result.stderr}")

        # Parse output - one item per line, strip whitespace
        items = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        return items
