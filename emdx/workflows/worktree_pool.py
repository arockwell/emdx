"""Worktree pool for managing parallel git worktrees in dynamic workflows."""

import asyncio
import json
import logging
import os
import random
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Registry file for tracking worktrees across process restarts
REGISTRY_FILE = Path.home() / ".config" / "emdx" / "worktree_registry.json"


def _load_registry() -> Dict[str, Dict]:
    """Load worktree registry from disk."""
    try:
        if REGISTRY_FILE.exists():
            return json.loads(REGISTRY_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Could not load worktree registry: %s", e)
    return {}


def _save_registry(registry: Dict[str, Dict]) -> None:
    """Save worktree registry to disk."""
    try:
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_FILE.write_text(json.dumps(registry, indent=2))
    except OSError as e:
        logger.debug("Could not save worktree registry: %s", e)


def _register_worktree(worktree_path: str, branch: str, repo_root: str) -> None:
    """Register a worktree in the persistent registry."""
    registry = _load_registry()
    registry[worktree_path] = {
        "created_at": time.time(),
        "pid": os.getpid(),
        "branch": branch,
        "repo_root": repo_root,
    }
    _save_registry(registry)


def _unregister_worktree(worktree_path: str) -> None:
    """Remove a worktree from the registry."""
    registry = _load_registry()
    registry.pop(worktree_path, None)
    _save_registry(registry)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 = check existence only
        return True
    except OSError:
        return False


def cleanup_orphaned_worktrees(max_age_hours: int = 24) -> int:
    """Clean up orphaned worktrees from previous crashed runs.

    Worktrees are considered orphaned if:
    - The PID that created them no longer exists
    - They are older than max_age_hours

    Args:
        max_age_hours: Maximum age in hours before a worktree is considered orphaned

    Returns:
        Number of worktrees cleaned up
    """
    registry = _load_registry()
    cleaned = 0
    now = time.time()

    for path, info in list(registry.items()):
        should_remove = False
        reason = ""

        # Check if PID is dead
        pid = info.get("pid", 0)
        if pid and not _is_pid_alive(pid):
            should_remove = True
            reason = f"PID {pid} is dead"

        # Check age
        created_at = info.get("created_at", 0)
        age_hours = (now - created_at) / 3600
        if age_hours > max_age_hours:
            should_remove = True
            reason = f"older than {max_age_hours}h (age: {age_hours:.1f}h)"

        if should_remove:
            worktree_path = Path(path)
            repo_root = info.get("repo_root", ".")

            # Try to remove the worktree via git
            if worktree_path.exists():
                try:
                    result = subprocess.run(
                        ["git", "worktree", "remove", path, "--force"],
                        cwd=repo_root,
                        capture_output=True,
                        check=False,
                    )
                    if result.returncode == 0:
                        logger.info("Cleaned up orphaned worktree %s (%s)", path, reason)
                        cleaned += 1
                    else:
                        logger.debug(
                            "Could not remove worktree %s: %s",
                            path,
                            result.stderr.decode() if result.stderr else "unknown error"
                        )
                except Exception as e:
                    logger.debug("Error removing worktree %s: %s", path, e)

            # Remove from registry regardless of git success
            registry.pop(path, None)

    _save_registry(registry)
    return cleaned


# Track whether orphan cleanup has run this session
_orphan_cleanup_done = False


@dataclass
class Worktree:
    """Represents a git worktree."""
    path: str
    branch: str
    repo_root: str

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, Worktree):
            return False
        return self.path == other.path

    async def reset_to_branch(self, branch: str):
        """Reset the worktree to a clean state on the given branch."""
        # Fetch latest
        await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "origin", branch],
            cwd=self.path,
            capture_output=True,
            check=False,
        )

        # Hard reset to origin/branch
        await asyncio.to_thread(
            subprocess.run,
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=self.path,
            capture_output=True,
            check=False,
        )

        # Clean untracked files
        await asyncio.to_thread(
            subprocess.run,
            ["git", "clean", "-fd"],
            cwd=self.path,
            capture_output=True,
            check=False,
        )

    async def checkout_branch(self, branch: str):
        """Checkout a specific branch in this worktree."""
        # Fetch the branch first
        await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "origin", branch],
            cwd=self.path,
            capture_output=True,
            check=False,
        )

        # Checkout the branch
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "checkout", branch],
            cwd=self.path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            # Try checking out as a tracking branch
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "checkout", "-b", branch, f"origin/{branch}"],
                cwd=self.path,
                capture_output=True,
                text=True,
            )

        return result.returncode == 0

    async def remove(self):
        """Remove this worktree and unregister it."""
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "remove", self.path, "--force"],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
            # Unregister from persistent registry
            _unregister_worktree(self.path)
        except Exception as e:
            logger.debug("Best effort worktree cleanup failed for %s: %s", self.path, e)


class WorktreePool:
    """Manages a pool of reusable git worktrees for parallel execution.

    This pool creates worktrees on-demand up to max_size, reuses them when
    possible, and cleans them up when the pool is closed.
    """

    def __init__(
        self,
        max_size: int = 5,
        base_branch: str = "main",
        repo_root: Optional[str] = None,
    ):
        """Initialize the worktree pool.

        Args:
            max_size: Maximum number of concurrent worktrees
            base_branch: Default branch to base worktrees on
            repo_root: Git repository root (auto-detected if not provided)
        """
        self.max_size = max_size
        self.base_branch = base_branch
        self._repo_root = repo_root
        self._available: List[Worktree] = []
        self._in_use: Set[Worktree] = set()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._closed = False

        # Run orphan cleanup once per session on first pool creation
        global _orphan_cleanup_done
        if not _orphan_cleanup_done:
            _orphan_cleanup_done = True
            try:
                cleaned = cleanup_orphaned_worktrees()
                if cleaned > 0:
                    logger.info("Cleaned up %d orphaned worktrees from previous runs", cleaned)
            except Exception as e:
                logger.debug("Error during orphan worktree cleanup: %s", e)

    @property
    def repo_root(self) -> str:
        """Get the repository root, detecting it if needed."""
        if self._repo_root is None:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            self._repo_root = result.stdout.strip()
        return self._repo_root

    async def _create_worktree(self) -> Worktree:
        """Create a new worktree and register it."""
        timestamp = int(time.time())
        random_suffix = random.randint(1000, 9999)
        pid = os.getpid()
        unique_id = f"{timestamp}-{pid}-{random_suffix}"

        branch_name = f"workflow-pool-{unique_id}"
        worktree_dir = Path(self.repo_root).parent / f"emdx-pool-{unique_id}"

        await asyncio.to_thread(
            subprocess.run,
            ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), self.base_branch],
            cwd=self.repo_root,
            capture_output=True,
            check=True,
        )

        worktree_path = str(worktree_dir)

        # Register worktree in persistent registry for orphan cleanup
        _register_worktree(worktree_path, branch_name, self.repo_root)

        return Worktree(
            path=worktree_path,
            branch=branch_name,
            repo_root=self.repo_root,
        )

    @asynccontextmanager
    async def acquire(self, target_branch: Optional[str] = None):
        """Acquire a worktree from the pool.

        Args:
            target_branch: Optional branch to checkout in the worktree

        Yields:
            A Worktree instance ready for use
        """
        if self._closed:
            raise RuntimeError("WorktreePool is closed")

        worktree = None

        async with self._condition:
            while True:
                # Try to get an available worktree
                if self._available:
                    worktree = self._available.pop()
                    break
                # Or create a new one if under limit
                elif len(self._in_use) < self.max_size:
                    worktree = await self._create_worktree()
                    break
                # Otherwise wait for one to become available
                else:
                    await self._condition.wait()

            self._in_use.add(worktree)

        try:
            # Reset to clean state
            await worktree.reset_to_branch(self.base_branch)

            # Checkout target branch if specified
            if target_branch:
                await worktree.checkout_branch(target_branch)

            yield worktree
        finally:
            async with self._condition:
                self._in_use.discard(worktree)
                if not self._closed:
                    self._available.append(worktree)
                self._condition.notify()

    @property
    def stats(self) -> dict:
        """Get pool statistics."""
        return {
            "available": len(self._available),
            "in_use": len(self._in_use),
            "max_size": self.max_size,
            "total_created": len(self._available) + len(self._in_use),
        }

    async def cleanup(self):
        """Clean up all worktrees in the pool."""
        self._closed = True

        async with self._lock:
            all_worktrees = self._available + list(self._in_use)
            self._available.clear()
            self._in_use.clear()

        # Remove all worktrees in parallel
        await asyncio.gather(
            *[wt.remove() for wt in all_worktrees],
            return_exceptions=True,
        )

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup all worktrees."""
        await self.cleanup()
