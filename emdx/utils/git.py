"""
Git utility functions for emdx
"""

import hashlib
import logging
import os
import random
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def slugify_for_branch(text: str, max_length: int = 40) -> str:
    """Convert text to a git branch-safe slug.

    Examples:
        "Gameplan #1: Contextual Save" -> "contextual-save"
        "Smart Priming (context-aware)" -> "smart-priming-context-aware"
        "Fix the auth bug in login.py" -> "fix-the-auth-bug-in-login-py"
    """
    # Remove common prefixes like "Gameplan #1:", "Feature:", etc.
    slug = re.sub(
        r"^(?:gameplan|feature|plan|doc(?:ument)?|fix|feat)\s*#?\d*[:\s—-]*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    # Keep only alphanumeric, spaces, and hyphens
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
    # Collapse whitespace to hyphens, lowercase
    slug = re.sub(r"\s+", "-", slug).strip("-").lower()
    # Truncate to max_length
    return slug[:max_length].rstrip("-") or "task"


def generate_delegate_branch_name(task_title: str) -> str:
    """Generate a consistent branch name for delegate tasks.

    All delegate-created branches follow the pattern:
        delegate/{slugified-title}-{short-hash}

    The short hash is a 5-char hash derived from the full title + timestamp,
    ensuring uniqueness even for similar task titles.

    Args:
        task_title: The task title or description

    Returns:
        Branch name like "delegate/fix-auth-bug-a1b2c"
    """
    slug = slugify_for_branch(task_title, max_length=40)

    # Generate short hash from title + timestamp for collision resistance
    hash_input = f"{task_title}-{time.time()}"
    short_hash = hashlib.sha1(hash_input.encode()).hexdigest()[:5]

    return f"delegate/{slug}-{short_hash}"


def create_worktree(
    base_branch: str = "main",
    task_title: str | None = None,
) -> tuple[str, str]:
    """Create a unique git worktree for isolated execution.

    Args:
        base_branch: Branch to base the worktree on
        task_title: Optional task title for meaningful branch naming.
                    If provided, branch follows delegate/{slug}-{hash} pattern.
                    If not provided, uses legacy worktree-{timestamp} pattern.

    Returns:
        Tuple of (worktree_path, branch_name)
    """
    # Get the repo root
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    repo_root = result.stdout.strip()

    # Generate branch name - use task title if provided, else legacy pattern
    if task_title:
        branch_name = generate_delegate_branch_name(task_title)
    else:
        # Legacy fallback for non-delegate worktree usage
        timestamp = int(time.time())
        random_suffix = random.randint(1000, 9999)
        pid = os.getpid()
        unique_id = f"{timestamp}-{pid}-{random_suffix}"
        branch_name = f"worktree-{unique_id}"

    # Worktree directory uses a unique ID for filesystem safety
    timestamp = int(time.time())
    random_suffix = random.randint(1000, 9999)
    pid = os.getpid()
    unique_id = f"{timestamp}-{pid}-{random_suffix}"
    worktree_dir = Path(repo_root).parent / f"emdx-worktree-{unique_id}"

    # Create the worktree
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_branch],
        capture_output=True,
        text=True,
        check=True,
    )

    return str(worktree_dir), branch_name


def cleanup_worktree(worktree_path: str) -> None:
    """Clean up a worktree after completion.

    Args:
        worktree_path: Path to the worktree to clean up
    """
    try:
        subprocess.run(
            ["git", "worktree", "remove", worktree_path, "--force"], capture_output=True, text=True
        )
    except Exception as e:
        logger.warning("Could not clean up worktree %s: %s", worktree_path, e)


def get_git_project(path: Path | None = None) -> str | None:
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
