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
        "Fix the auth bug in login.py" -> "fix-the-auth-bug-in-loginpy"
    """
    slug = re.sub(
        r"^(?:gameplan|feature|plan|doc(?:ument)?|kink\s*\d*[:\s—-]*)\s*#?\d*[:\s—-]*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-").lower()
    return slug[:max_length].rstrip("-") or "task"


def generate_delegate_branch_name(task_title: str) -> str:
    """Generate a consistent delegate branch name.

    Pattern: delegate/{slug}-{short-hash}

    The 5-char hash (title + timestamp) prevents collisions for similar titles.
    """
    slug = slugify_for_branch(task_title)
    hash_input = f"{task_title}-{time.time()}"
    short_hash = hashlib.sha1(hash_input.encode()).hexdigest()[:5]  # noqa: S324
    return f"delegate/{slug}-{short_hash}"


def validate_pr_preconditions(
    working_dir: str | None = None,
    base_branch: str = "main",
) -> dict:
    """Check whether a branch is ready for PR creation.

    Returns dict with keys: has_commits, commit_count, is_pushed,
    branch_name, files_changed, error.
    """
    cwd_kwargs: dict = {"cwd": working_dir} if working_dir else {}
    try:
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            **cwd_kwargs,
        )
        branch_name = branch_result.stdout.strip()

        log_result = subprocess.run(
            ["git", "log", f"{base_branch}..HEAD", "--oneline"],
            capture_output=True,
            text=True,
            **cwd_kwargs,
        )
        commits = [ln for ln in log_result.stdout.strip().splitlines() if ln]

        remote_result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            capture_output=True,
            text=True,
            **cwd_kwargs,
        )
        is_pushed = branch_name in remote_result.stdout

        diff_result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True,
            **cwd_kwargs,
        )
        files = [ln for ln in diff_result.stdout.strip().splitlines() if ln]

        return {
            "has_commits": len(commits) > 0,
            "commit_count": len(commits),
            "is_pushed": is_pushed,
            "branch_name": branch_name,
            "files_changed": len(files),
            "error": None,
        }
    except Exception as e:
        return {
            "has_commits": False,
            "commit_count": 0,
            "is_pushed": False,
            "branch_name": None,
            "files_changed": 0,
            "error": str(e),
        }


def create_worktree(
    base_branch: str = "main",
    task_title: str | None = None,
) -> tuple[str, str]:
    """Create a unique git worktree for isolated execution.

    Args:
        base_branch: Branch to base the worktree on
        task_title: Optional title for meaningful branch naming.
                    Uses delegate/{slug}-{hash} when provided.

    Returns:
        Tuple of (worktree_path, branch_name)
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    repo_root = result.stdout.strip()

    if task_title:
        branch_name = generate_delegate_branch_name(task_title)
    else:
        timestamp = int(time.time())
        random_suffix = random.randint(1000, 9999)
        pid = os.getpid()
        branch_name = f"worktree-{timestamp}-{pid}-{random_suffix}"

    timestamp = int(time.time())
    random_suffix = random.randint(1000, 9999)
    pid = os.getpid()
    unique_id = f"{timestamp}-{pid}-{random_suffix}"
    worktree_dir = Path(repo_root).parent / f"emdx-worktree-{unique_id}"

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
