"""
Git utility functions for emdx
"""

import logging
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def create_worktree(base_branch: str = "main") -> tuple[str, str]:
    """Create a unique git worktree for isolated execution.

    Args:
        base_branch: Branch to base the worktree on

    Returns:
        Tuple of (worktree_path, branch_name)
    """
    # Get the repo root
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True
    )
    repo_root = result.stdout.strip()

    # Create unique branch and worktree names with timestamp + random + pid
    timestamp = int(time.time())
    random_suffix = random.randint(1000, 9999)
    pid = os.getpid()
    unique_id = f"{timestamp}-{pid}-{random_suffix}"
    branch_name = f"worktree-{unique_id}"
    worktree_dir = Path(repo_root).parent / f"emdx-worktree-{unique_id}"

    # Create the worktree
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_branch],
        capture_output=True, text=True, check=True
    )

    return str(worktree_dir), branch_name


def cleanup_worktree(worktree_path: str):
    """Clean up a worktree after completion.

    Args:
        worktree_path: Path to the worktree to clean up
    """
    try:
        subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"],
            capture_output=True, text=True
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Could not clean up worktree %s: %s", worktree_path, e)


def get_git_project(path: Optional[Path] = None) -> Optional[str]:
    """
    Get the git repository name for a given path.

    Args:
        path: The path to check. If None, uses current directory.

    Returns:
        The repository name if in a git repo, None otherwise.
    """
    if path is None:
        path = Path.cwd()

    cwd = str(path)

    try:
        # Check if we're in a git repo and get the repo root
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode != 0:
            # Not in a git repository
            return None

        repo_root = result.stdout.strip()

        # Try to get the remote origin URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if result.returncode == 0:
            url = result.stdout.strip()

            # Extract repo name from URL
            # Handle different URL formats:
            # - https://github.com/user/repo.git
            # - git@github.com:user/repo.git
            # - https://github.com/user/repo

            if url.endswith(".git"):
                url = url[:-4]

            # Get the last part of the URL
            repo_name = url.split("/")[-1]
            if ":" in repo_name:  # Handle SSH format
                repo_name = repo_name.split(":")[-1]

            return repo_name

        # If no origin remote, use the repository directory name
        return Path(repo_root).name

    except (OSError, FileNotFoundError):
        # git not found or path doesn't exist
        return None
    except Exception as e:
        # Any other error, just return None
        logger.debug("Error getting git project: %s", e)
        return None
