"""
Git utility functions for emdx
"""

from pathlib import Path
from typing import Optional

import git


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

    try:
        # Find the git repository
        repo = git.Repo(path, search_parent_directories=True)

        # Try to get the remote origin URL
        if repo.remotes:
            for remote in repo.remotes:
                if remote.name == "origin":
                    url = remote.url

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

        # If no remote, use the repository directory name
        return Path(repo.working_dir).name

    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        # Not in a git repository
        return None
    except Exception:
        # Any other error, just return None
        return None