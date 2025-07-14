#!/usr/bin/env python3
"""
Git operations and utilities for EMDX TUI.
"""

import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


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


def get_worktrees() -> List[GitWorktree]:
    """Get list of all git worktrees."""
    try:
        result = subprocess.run(
            ['git', 'worktree', 'list', '--porcelain'],
            capture_output=True,
            text=True,
            check=True
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
    except subprocess.CalledProcessError:
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
    except subprocess.CalledProcessError:
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