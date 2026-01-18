#!/usr/bin/env python3
"""
Git operations and utilities for EMDX TUI.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class GitWorktree:
    """Represents a git worktree."""
    path: str
    branch: str
    commit: str
    is_current: bool = False

    @property
    def name(self) -> str:
        """Get a display name for the worktree."""
        return Path(self.path).name


@dataclass
class GitProject:
    """Represents a git project with its worktrees."""
    name: str
    main_path: str
    worktrees: List['GitWorktree'] = None

    def __post_init__(self):
        if self.worktrees is None:
            self.worktrees = []

    @property
    def worktree_count(self) -> int:
        """Get the number of worktrees."""
        return len(self.worktrees)

    @property
    def display_name(self) -> str:
        """Get a display name for the project."""
        return f"{self.name} ({self.worktree_count} worktrees)"


@dataclass
class GitFileStatus:
    """Represents a file's git status."""
    path: str
    status: str  # M, A, D, ??, etc.
    staged: bool
    
    @property
    def status_icon(self) -> str:
        """Get icon for file status."""
        icons = {
            'M': '📝',  # Modified
            'A': '➕',  # Added
            'D': '🗑️',  # Deleted
            'R': '🔄',  # Renamed
            'C': '📋',  # Copied
            '??': '❓',  # Untracked
        }
        return icons.get(self.status, '❓')
    
    @property
    def status_description(self) -> str:
        """Get human-readable status description."""
        descriptions = {
            'M': 'Modified',
            'A': 'Added',
            'D': 'Deleted',
            'R': 'Renamed',
            'C': 'Copied',
            '??': 'Untracked',
        }
        return descriptions.get(self.status, 'Unknown')


def extract_project_name_from_worktree(worktree_path: str) -> str:
    """
    Extract project name from worktree path.

    Examples:
        clauding-main -> clauding
        emdx-feature-agents -> emdx
        gopher-survivors-main -> gopher-survivors
    """
    name = Path(worktree_path).name

    # Common suffixes that indicate branch names
    branch_indicators = [
        '-main', '-master', '-develop', '-dev',
        '-feature-', '-fix-', '-hotfix-',
        '-release-', '-staging-', '-prod-'
    ]

    # Try to find project name by removing branch suffix
    for indicator in branch_indicators:
        if indicator in name:
            # Find the first occurrence and take everything before it
            idx = name.find(indicator)
            if idx > 0:
                return name[:idx]

    # If no indicator found, try to split on last dash and see if remainder looks like a branch
    parts = name.rsplit('-', 1)
    if len(parts) == 2:
        potential_project, potential_branch = parts
        # If it looks like a valid project name, use it
        if len(potential_project) > 2:
            return potential_project

    # Fallback: return the whole name
    return name


def discover_projects_from_main_repos() -> List[GitProject]:
    """
    Discover projects by scanning ~/dev/ for main repos.

    This is faster and more reliable than scanning worktrees:
    - Scans ~/dev/* for git repositories (skips worktrees subdir)
    - Uses git worktree list to get each repo's worktrees
    - More reliable than parsing worktree names

    Returns:
        List of GitProject objects with worktrees pre-loaded
    """
    dev_dir = Path.home() / "dev"
    projects = []

    if not dev_dir.exists():
        logger.warning(f"Dev directory not found: {dev_dir}")
        return projects

    logger.info(f"Scanning {dev_dir} for git repositories")

    for item in dev_dir.iterdir():
        # Skip the worktrees directory itself
        if item.name == "worktrees":
            continue

        if not item.is_dir():
            continue

        # Check if it's a git repository
        git_dir = item / ".git"
        if git_dir.exists() and git_dir.is_file():
            # This is a worktree, not a main repo - skip it
            continue

        if git_dir.exists() and git_dir.is_dir():
            # Found a main repo!
            project_name = item.name
            main_path = str(item)

            try:
                # Get worktrees from this repo
                worktrees = get_worktrees(main_path)

                projects.append(GitProject(
                    name=project_name,
                    main_path=main_path,
                    worktrees=worktrees
                ))

                logger.debug(f"Found project '{project_name}' with {len(worktrees)} worktrees")

            except Exception as e:
                logger.warning(f"Failed to get worktrees for {project_name}: {e}")
                # Still add the project even if we can't get worktrees
                projects.append(GitProject(
                    name=project_name,
                    main_path=main_path,
                    worktrees=[]
                ))

    # Sort projects by name
    projects.sort(key=lambda p: p.name.lower())
    logger.info(f"Discovered {len(projects)} projects from main repos")
    return projects


def discover_projects_from_worktrees(worktree_dirs: Optional[List[str]] = None) -> List[GitProject]:
    """
    Discover projects by grouping worktrees.

    This is optimized for the common pattern where worktrees are named like:
    project-branch (e.g., clauding-main, gopher-survivors-feature-xyz)

    Returns projects with their worktrees already loaded.
    """
    if worktree_dirs is None:
        worktree_dirs = []
        # Check ~/dev/worktrees
        home_worktrees = Path.home() / "dev" / "worktrees"
        if home_worktrees.exists():
            worktree_dirs.append(str(home_worktrees))

    # Map of project_name -> (main_path, [worktrees])
    projects_map = {}

    for worktree_dir in worktree_dirs:
        try:
            wt_path = Path(worktree_dir)
            if not wt_path.exists():
                continue

            # Scan for worktrees
            for item in wt_path.iterdir():
                if not item.is_dir():
                    continue

                git_dir = item / ".git"
                if not git_dir.exists():
                    continue

                # This is a worktree - extract project name
                project_name = extract_project_name_from_worktree(str(item))

                # Get worktree info
                try:
                    # Get the main repo path from this worktree
                    result = subprocess.run(
                        ['git', 'rev-parse', '--show-toplevel'],
                        capture_output=True,
                        text=True,
                        cwd=str(item),
                        check=True
                    )
                    main_path = result.stdout.strip()

                    # Get branch info
                    result = subprocess.run(
                        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                        capture_output=True,
                        text=True,
                        cwd=str(item),
                        check=True
                    )
                    branch = result.stdout.strip()

                    # Get commit hash
                    result = subprocess.run(
                        ['git', 'rev-parse', 'HEAD'],
                        capture_output=True,
                        text=True,
                        cwd=str(item),
                        check=True
                    )
                    commit = result.stdout.strip()

                    # Create worktree object
                    worktree = GitWorktree(
                        path=str(item),
                        branch=branch,
                        commit=commit,
                        is_current=(str(item) == os.getcwd())
                    )

                    # Add to project map
                    if project_name not in projects_map:
                        projects_map[project_name] = (main_path, [])
                    projects_map[project_name][1].append(worktree)

                except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
                    # Skip worktrees we can't read
                    logger.debug(f"Could not read worktree {item}: {e}")
                    continue

        except (OSError, PermissionError) as e:
            logger.debug(f"Could not scan directory {worktree_dir}: {e}")
            continue

    # Convert to GitProject list
    projects = []
    for project_name, (main_path, worktrees) in projects_map.items():
        # Sort worktrees by branch name
        worktrees.sort(key=lambda w: w.branch)
        projects.append(GitProject(
            name=project_name,
            main_path=main_path,
            worktrees=worktrees
        ))

    # Sort projects by name
    projects.sort(key=lambda p: p.name.lower())
    return projects


def discover_git_projects(search_paths: Optional[List[str]] = None, max_depth: int = 1) -> List[GitProject]:
    """
    Discover git projects in common locations.

    Args:
        search_paths: Optional list of paths to search. Defaults to ~/dev/worktrees and parent of current dir.
        max_depth: Maximum directory depth to search (default 1 = only immediate children)

    Returns:
        List of GitProject objects
    """
    projects = []
    seen_paths = set()

    if search_paths is None:
        # Default search paths - focus on worktree directories
        search_paths = []

        # Add ~/dev/worktrees if it exists (most likely location)
        home_worktrees = Path.home() / "dev" / "worktrees"
        if home_worktrees.exists():
            search_paths.append(str(home_worktrees))

        # Add parent of current directory (for current project)
        cwd_parent = Path.cwd().parent
        if cwd_parent.exists() and str(cwd_parent) not in search_paths:
            search_paths.append(str(cwd_parent))

    for search_path in search_paths:
        try:
            search_dir = Path(search_path)
            if not search_dir.exists():
                continue

            # Look for directories with .git folder (only immediate children for speed)
            for item in search_dir.iterdir():
                if not item.is_dir():
                    continue

                # Skip if we've already seen this project
                resolved_path = str(item.resolve())
                if resolved_path in seen_paths:
                    continue

                git_dir = item / ".git"
                if git_dir.exists():
                    # This is a git repository
                    seen_paths.add(resolved_path)
                    try:
                        # Count worktrees (quick check)
                        worktrees = get_worktrees(str(item))
                        projects.append(GitProject(
                            name=item.name,
                            main_path=str(item),
                            worktree_count=len(worktrees)
                        ))
                    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
                        # Failed to get worktrees, but it's still a git repo
                        logger.debug(f"Could not get worktrees for {item.name}: {e}")
                        projects.append(GitProject(
                            name=item.name,
                            main_path=str(item),
                            worktree_count=0
                        ))
        except (OSError, PermissionError) as e:
            # Skip directories we can't read
            logger.debug(f"Could not scan directory {search_path}: {e}")
            continue

    # Sort by name
    projects.sort(key=lambda p: p.name.lower())
    return projects


def get_worktrees(project_path: Optional[str] = None) -> List[GitWorktree]:
    """
    Get list of all git worktrees for a project.

    Args:
        project_path: Optional path to a git project. If None, uses current directory.

    Returns:
        List of GitWorktree objects
    """
    try:
        result = subprocess.run(
            ['git', 'worktree', 'list', '--porcelain'],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_path
        )
        
        worktrees = []
        current_worktree = {}
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                if current_worktree:
                    worktrees.append(GitWorktree(
                        path=current_worktree.get('worktree', ''),
                        branch=current_worktree.get('branch', 'detached'),
                        commit=current_worktree.get('HEAD', ''),
                        is_current=current_worktree.get('worktree') == os.getcwd()
                    ))
                current_worktree = {}
            elif line.startswith('worktree '):
                current_worktree['worktree'] = line[9:]
            elif line.startswith('HEAD '):
                current_worktree['HEAD'] = line[5:]
            elif line.startswith('branch '):
                current_worktree['branch'] = line[7:]
        
        # Handle last worktree
        if current_worktree:
            worktrees.append(GitWorktree(
                path=current_worktree.get('worktree', ''),
                branch=current_worktree.get('branch', 'detached'),
                commit=current_worktree.get('HEAD', ''),
                is_current=current_worktree.get('worktree') == os.getcwd()
            ))
        
        return worktrees
    except subprocess.CalledProcessError as e:
        logger.debug("Failed to get worktree list: %s", e)
        return []


def get_git_status(worktree_path: Optional[str] = None) -> List[GitFileStatus]:
    """Get git status for current directory or specified worktree."""
    try:
        cmd = ['git', 'status', '--porcelain']
        cwd = worktree_path if worktree_path else None
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        
        files = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
                
            # Parse git status format: XY filename where:
            # X = staged status, Y = unstaged status
            # Always expect 2 chars + space + filename
            if len(line) < 3:
                continue
                
            status_chars = line[:2]
            filename = line[2:].lstrip()  # Remove status chars and strip leading whitespace
            
            # Git status always uses 2 characters
            staged_char = status_chars[0]
            unstaged_char = status_chars[1]
            
            # Determine primary status and whether file has staged changes
            # Priority: staged changes > unstaged changes > untracked
            if staged_char != ' ' and staged_char != '?':
                # File has staged changes - show as staged
                files.append(GitFileStatus(
                    path=filename,
                    status=staged_char,
                    staged=True
                ))
            elif unstaged_char != ' ':
                # File has unstaged changes only
                files.append(GitFileStatus(
                    path=filename,
                    status=unstaged_char,
                    staged=False
                ))
        
        return files
    except subprocess.CalledProcessError as e:
        logger.debug("Failed to get git status: %s", e)
        return []


def get_comprehensive_git_diff(file_path: str, worktree_path: Optional[str] = None) -> str:
    """Get comprehensive diff showing both staged and unstaged changes."""
    staged_diff = get_git_diff(file_path, staged=True, worktree_path=worktree_path)
    unstaged_diff = get_git_diff(file_path, staged=False, worktree_path=worktree_path)
    
    output_parts = []
    
    # Add staged changes if they exist
    if staged_diff and not staged_diff.startswith("No staged changes") and not staged_diff.startswith("Error:"):
        output_parts.append("[bold green]📦 STAGED CHANGES[/bold green]")
        output_parts.append(staged_diff)
        output_parts.append("")
    
    # Add unstaged changes if they exist  
    if unstaged_diff and not unstaged_diff.startswith("No unstaged changes") and not unstaged_diff.startswith("Error:"):
        output_parts.append("[bold yellow]📝 UNSTAGED CHANGES[/bold yellow]")
        output_parts.append(unstaged_diff)
        output_parts.append("")
    
    # If no changes at all
    if not output_parts:
        return f"No changes found for {file_path}"
    
    return "\n".join(output_parts)


def get_git_diff(file_path: str, staged: bool = False, worktree_path: Optional[str] = None) -> str:
    """Get git diff for a specific file with beautiful formatting."""
    try:
        cmd = ['git', 'diff']
        if staged:
            cmd.append('--cached')
        cmd.append(file_path)
        
        cwd = worktree_path if worktree_path else None
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        
        raw_diff = result.stdout
        
        # If no diff content, return appropriate message
        if not raw_diff.strip():
            status = "staged" if staged else "unstaged"
            return f"No {status} changes for {file_path}"
        
        # Try to format with delta for beautiful output
        try:
            delta_result = subprocess.run(
                ['delta', 
                 '--no-gitconfig', 
                 '--side-by-side=never', 
                 '--width=70',
                 '--tabs=2',
                 '--wrap-max-lines=unlimited',
                 '--max-line-length=0'],
                input=raw_diff,
                capture_output=True,
                text=True,
                check=True
            )
            # Strip ANSI codes for better TUI display
            import re
            clean_output = re.sub(r'\x1b\[[0-9;]*m', '', delta_result.stdout)
            return clean_output
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to raw diff if delta fails or isn't available
            return raw_diff
            
    except subprocess.CalledProcessError:
        return f"Error: Could not get diff for {file_path}"


def is_git_repository(path: Optional[str] = None) -> bool:
    """Check if directory is a git repository."""
    try:
        cwd = path if path else None
        subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            check=True,
            cwd=cwd
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_current_branch(worktree_path: Optional[str] = None) -> str:
    """Get current git branch name."""
    try:
        cwd = worktree_path if worktree_path else None
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def get_repository_root(path: Optional[str] = None) -> Optional[str]:
    """Get the root directory of the git repository."""
    try:
        cwd = path if path else None
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def git_stage_file(file_path: str, worktree_path: Optional[str] = None) -> bool:
    """Stage a file for commit."""
    try:
        cwd = worktree_path if worktree_path else None
        subprocess.run(
            ['git', 'add', file_path],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_unstage_file(file_path: str, worktree_path: Optional[str] = None) -> bool:
    """Unstage a file (remove from staging area)."""
    try:
        cwd = worktree_path if worktree_path else None
        subprocess.run(
            ['git', 'reset', 'HEAD', file_path],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_commit(message: str, worktree_path: Optional[str] = None) -> Tuple[bool, str]:
    """Commit staged changes with a message."""
    try:
        cwd = worktree_path if worktree_path else None
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() if e.stderr else "Commit failed"


def git_discard_changes(file_path: str, worktree_path: Optional[str] = None) -> bool:
    """Discard unstaged changes to a file."""
    try:
        cwd = worktree_path if worktree_path else None
        subprocess.run(
            ['git', 'checkout', 'HEAD', '--', file_path],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return True
    except subprocess.CalledProcessError:
        return False


def create_worktree(branch_name: str, path: Optional[str] = None, base_branch: Optional[str] = None, repo_path: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    Create a new git worktree.

    Args:
        branch_name: Name for the new branch
        path: Optional path for the worktree (will be auto-generated if not provided)
        base_branch: Optional base branch to create from (defaults to current branch)
        repo_path: Optional path to the repository (defaults to current directory)

    Returns:
        Tuple of (success, worktree_path, error_message)
    """
    try:
        # Get repository root to create worktrees adjacent to it
        # Use provided repo_path or current directory
        repo_root = get_repository_root(repo_path)
        if not repo_root:
            return False, "", f"Not in a git repository (checked path: {repo_path or 'current directory'})"

        # Auto-generate path if not provided
        if not path:
            # Create worktree path: ../repo-name-worktrees/branch_name
            repo_name = Path(repo_root).name
            worktrees_dir = Path(repo_root).parent / f"{repo_name}-worktrees"
            worktrees_dir.mkdir(exist_ok=True)
            path = str(worktrees_dir / branch_name)

        # Build git worktree add command
        cmd = ['git', 'worktree', 'add', '-b', branch_name, path]
        if base_branch:
            cmd.append(base_branch)

        logger.info(f"Creating worktree in repo {repo_root}: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=repo_root
        )

        return True, path, ""

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else "Failed to create worktree"
        logger.error(f"Failed to create worktree: {error_msg}")
        return False, "", error_msg
    except Exception as e:
        logger.error(f"Exception creating worktree: {e}", exc_info=True)
        return False, "", str(e)


def remove_worktree(path: str, force: bool = False) -> Tuple[bool, str]:
    """
    Remove a git worktree.

    Args:
        path: Path to the worktree to remove
        force: Force removal even if worktree has modifications

    Returns:
        Tuple of (success, error_message)
    """
    try:
        cmd = ['git', 'worktree', 'remove', path]
        if force:
            cmd.append('--force')

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        return True, ""

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else "Failed to remove worktree"
        return False, error_msg
