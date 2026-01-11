"""Worktree pool for managing parallel git worktrees in dynamic workflows."""

import asyncio
import os
import random
import subprocess
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set


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
        """Remove this worktree."""
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "remove", self.path, "--force"],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
        except Exception:
            pass  # Best effort cleanup


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
        """Create a new worktree."""
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

        return Worktree(
            path=str(worktree_dir),
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
