"""Patrol service - autonomous work item processing through cascade stages.

Patrols watch for ready work items and process them through Claude,
automatically advancing them to the next stage.
"""

import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..database import connection as db
from ..models.executions import create_execution, update_execution_status
from ..work import WorkService, WorkItem, Cascade
from ..utils.git import get_git_project
from .claude_executor import execute_claude_sync, DEFAULT_ALLOWED_TOOLS

logger = logging.getLogger(__name__)


@dataclass
class PatrolConfig:
    """Configuration for a patrol runner."""
    name: str = "patrol:worker"
    cascade: Optional[str] = None  # None = all cascades
    stage: Optional[str] = None  # None = all non-terminal stages
    poll_interval: int = 10  # seconds between polls
    max_items: int = 1  # max items to process per poll
    timeout: int = 300  # Claude execution timeout
    dry_run: bool = False  # If True, don't execute Claude


@dataclass
class PatrolStats:
    """Statistics for a patrol run."""
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    total_time: float = 0.0
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)


class PatrolRunner:
    """Runs a patrol loop that processes work items through stages."""

    def __init__(self, config: PatrolConfig):
        self.config = config
        self.service = WorkService()
        self.stats = PatrolStats()
        self._running = False
        self._stop_requested = False

    def process_one(self, item: WorkItem) -> bool:
        """Process a single work item through its current stage.

        Returns True if successful, False otherwise.
        """
        logger.info(f"Processing {item.id} at stage {item.stage}")

        # Get cascade and processor
        cascade = self.service.get_cascade(item.cascade)
        if not cascade:
            logger.error(f"Cascade not found: {item.cascade}")
            return False

        processor = cascade.get_processor(item.stage)
        if not processor:
            logger.warning(f"No processor for stage {item.stage}, advancing anyway")
            # No processor = just advance
            try:
                self.service.advance(item.id, transitioned_by=self.config.name)
                return True
            except ValueError as e:
                logger.error(f"Failed to advance {item.id}: {e}")
                return False

        # Build the full prompt
        content = item.content or item.title
        full_prompt = f"{processor}\n\n---\n\nWork Item: {item.title}\n\n{content}"

        if self.config.dry_run:
            logger.info(f"[DRY RUN] Would execute:\n{full_prompt[:200]}...")
            return True

        # Create execution record
        working_dir = get_git_project() or os.getcwd()
        log_dir = Path(working_dir) / ".emdx" / "logs" / "patrols"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{item.id}_{item.stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        exec_id = create_execution(
            doc_id=None,  # Work items don't have doc_id
            doc_title=f"Patrol: {item.title}",
            prompt=full_prompt[:500],  # Truncate for DB
            log_file=str(log_file),
            execution_type="patrol",
            working_dir=working_dir,
        )

        # Execute Claude
        try:
            result = execute_claude_sync(
                task=full_prompt,
                execution_id=exec_id,
                log_file=log_file,
                allowed_tools=DEFAULT_ALLOWED_TOOLS,
                working_dir=working_dir,
                timeout=self._get_timeout(item.stage),
            )
        except Exception as e:
            logger.error(f"Claude execution failed: {e}")
            update_execution_status(exec_id, "failed", error=str(e))
            return False

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"Processing failed for {item.id}: {error}")
            update_execution_status(exec_id, "failed", error=error)
            self.stats.errors.append(f"{item.id}: {error}")
            return False

        # Extract output
        output = result.get("output", "")

        # Check for PR URL in output (for planned/implementing stages)
        pr_number = self._extract_pr_number(output)

        # Advance to next stage with new content
        try:
            next_stage = cascade.get_next_stage(item.stage)
            if next_stage:
                self.service.set_stage(
                    item.id,
                    next_stage,
                    transitioned_by=self.config.name,
                    new_content=output,
                )
                logger.info(f"Advanced {item.id}: {item.stage} → {next_stage}")
            else:
                # Terminal stage reached
                self.service.done(item.id, pr_number=pr_number)
                logger.info(f"Completed {item.id} (terminal stage)")

            update_execution_status(exec_id, "completed")
            return True

        except ValueError as e:
            logger.error(f"Failed to advance {item.id}: {e}")
            update_execution_status(exec_id, "failed", error=str(e))
            return False

    def _get_timeout(self, stage: str) -> int:
        """Get timeout based on stage (implementing stages need more time)."""
        if stage in ("implementing", "planned", "draft"):
            return max(self.config.timeout, 1800)  # At least 30 min
        return self.config.timeout

    def _extract_pr_number(self, output: str) -> Optional[int]:
        """Extract PR number from output if present."""
        # Look for GitHub PR URLs
        patterns = [
            r'https://github\.com/[^/]+/[^/]+/pull/(\d+)',
            r'PR[:\s#]+(\d+)',
            r'pull request[:\s#]+(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def run_once(self) -> int:
        """Run one iteration: find and process ready items.

        Returns number of items processed.
        """
        # Find ready items
        ready = self.service.ready(
            cascade=self.config.cascade,
            stage=self.config.stage,
            limit=self.config.max_items,
        )

        if not ready:
            logger.debug("No ready items found")
            return 0

        processed = 0
        for item in ready:
            # Try to claim
            try:
                self.service.claim(item.id, self.config.name)
            except ValueError as e:
                logger.debug(f"Could not claim {item.id}: {e}")
                continue

            try:
                success = self.process_one(item)
                self.stats.items_processed += 1
                if success:
                    self.stats.items_succeeded += 1
                else:
                    self.stats.items_failed += 1
                processed += 1
            finally:
                # Always release the claim
                try:
                    self.service.release(item.id)
                except Exception:
                    pass

        return processed

    def run(self, max_iterations: Optional[int] = None):
        """Run the patrol loop continuously.

        Args:
            max_iterations: Stop after this many iterations (None = forever)
        """
        self._running = True
        self._stop_requested = False
        self.stats = PatrolStats(started_at=datetime.now())

        # Set up signal handlers
        def handle_stop(signum, frame):
            logger.info("Stop signal received, finishing current work...")
            self._stop_requested = True

        old_sigint = signal.signal(signal.SIGINT, handle_stop)
        old_sigterm = signal.signal(signal.SIGTERM, handle_stop)

        iteration = 0
        try:
            logger.info(f"Patrol {self.config.name} starting...")
            logger.info(f"  Cascade: {self.config.cascade or 'all'}")
            logger.info(f"  Stage: {self.config.stage or 'all'}")
            logger.info(f"  Poll interval: {self.config.poll_interval}s")

            while not self._stop_requested:
                if max_iterations and iteration >= max_iterations:
                    break

                start = time.time()
                processed = self.run_once()
                elapsed = time.time() - start
                self.stats.total_time += elapsed

                if processed > 0:
                    logger.info(f"Processed {processed} items in {elapsed:.1f}s")

                iteration += 1

                # Sleep unless we processed something (then check immediately)
                if processed == 0 and not self._stop_requested:
                    time.sleep(self.config.poll_interval)

        finally:
            self._running = False
            self.stats.stopped_at = datetime.now()
            signal.signal(signal.SIGINT, old_sigint)
            signal.signal(signal.SIGTERM, old_sigterm)
            logger.info(f"Patrol stopped. Processed: {self.stats.items_processed}, "
                       f"Succeeded: {self.stats.items_succeeded}, "
                       f"Failed: {self.stats.items_failed}")

    def stop(self):
        """Request the patrol to stop after current iteration."""
        self._stop_requested = True

    @property
    def is_running(self) -> bool:
        return self._running


def run_patrol(
    cascade: Optional[str] = None,
    stage: Optional[str] = None,
    poll_interval: int = 10,
    max_iterations: Optional[int] = None,
    dry_run: bool = False,
    name: str = "patrol:worker",
) -> PatrolStats:
    """Convenience function to run a patrol.

    Args:
        cascade: Filter to specific cascade (or None for all)
        stage: Filter to specific stage (or None for all)
        poll_interval: Seconds between polls
        max_iterations: Stop after N iterations (None = forever)
        dry_run: If True, don't execute Claude
        name: Patrol identity for claiming

    Returns:
        PatrolStats with run statistics
    """
    config = PatrolConfig(
        name=name,
        cascade=cascade,
        stage=stage,
        poll_interval=poll_interval,
        dry_run=dry_run,
    )
    runner = PatrolRunner(config)
    runner.run(max_iterations=max_iterations)
    return runner.stats
