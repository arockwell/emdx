#!/usr/bin/env python3
"""
Standalone git browser - extracted from the mixin.
"""

import logging
import os

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, RichLog

from emdx.utils.git_ops import (
    get_comprehensive_git_diff,
    get_current_branch,
    get_git_status,
    get_worktrees,
    git_commit,
    git_discard_changes,
    git_stage_file,
    git_unstage_file,
)

logger = logging.getLogger(__name__)


class GitBrowser(Widget):
    """Git diff browser widget."""
    
    CSS = """
    GitBrowser {
        layout: vertical;
        height: 100%;
    }
    
    #git-table {
        width: 45%;
        margin: 0;
    }
    
    #diff-container {
        width: 55%;
        padding: 0 1;
    }
    
    #sidebar {
        width: 45%;
    }
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.git_files = []
        self.current_worktree_path = os.getcwd()
        self.current_worktree_index = 0
        self.worktrees = []
        self.file_statuses = {}
        
    def compose(self) -> ComposeResult:
        """Compose the git browser UI."""
        with Horizontal():
            with Vertical(id="sidebar"):
                yield DataTable(id="git-table")
            with Vertical(id="diff-container"):
                with ScrollableContainer(id="diff-scroll"):
                    yield RichLog(id="diff-content", wrap=True, highlight=True, markup=True)
                    
    async def on_mount(self) -> None:
        """Initialize the git browser."""
        logger.info("GitBrowser mounted")
        
        # Setup table
        table = self.query_one("#git-table", DataTable)
        table.add_columns("Status", "File")
        table.cursor_type = "row"
        table.show_header = True
        
        # Load git status
        await self.refresh_git_status()
        
    async def refresh_git_status(self) -> None:
        """Refresh the git file list."""
        try:
            # Get git status
            self.git_files = get_git_status(self.current_worktree_path)
            self.worktrees = get_worktrees()
            
            # Find current worktree
            for i, wt in enumerate(self.worktrees):
                if wt.path == self.current_worktree_path:
                    self.current_worktree_index = i
                    break
                    
            # Build file status map
            self.file_statuses = {f.path: f.status for f in self.git_files}
            
            # Update table
            table = self.query_one("#git-table", DataTable)
            table.clear()
            
            for file in self.git_files:
                status_icon = self._get_status_icon(file.status)
                table.add_row(status_icon, file.path)
                
            # Update status - need to find the app instance
            try:
                app = self.app
                if hasattr(app, 'update_status'):
                    current_branch = get_current_branch(self.current_worktree_path)
                    status_text = f"Git: {current_branch} | {len(self.git_files)} changes"
                    status_text += " | a=stage | u=unstage | c=commit | q=back"
                    app.update_status(status_text)
            except Exception as e:
                logger.debug("Status update failed: %s", e)
                
        except Exception as e:
            logger.error(f"Error refreshing git status: {e}")
            
    def _get_status_icon(self, status: str) -> str:
        """Get icon for git status."""
        icons = {
            "M": "📝",  # Modified
            "A": "✅",  # Added/Staged
            "D": "🗑️",  # Deleted
            "R": "📛",  # Renamed
            "C": "📋",  # Copied
            "U": "❓",  # Untracked
            "??": "❓", # Untracked
        }
        return icons.get(status, "•")
        
    def save_state(self) -> dict:
        """Save current state."""
        state = {
            "worktree_path": self.current_worktree_path,
            "worktree_index": self.current_worktree_index,
        }
        
        try:
            table = self.query_one("#git-table", DataTable)
            state["cursor_position"] = table.cursor_coordinate
        except Exception as e:
            logger.debug("Could not save cursor position: %s", e)

        return state
        
    def restore_state(self, state: dict) -> None:
        """Restore saved state."""
        self.current_worktree_path = state.get("worktree_path", os.getcwd())
        self.current_worktree_index = state.get("worktree_index", 0)
        
        if "cursor_position" in state:
            try:
                table = self.query_one("#git-table", DataTable)
                table.cursor_coordinate = state["cursor_position"]
            except Exception as e:
                logger.debug("Could not restore cursor position: %s", e)
                
    async def on_key(self, event) -> None:
        """Handle key events."""
        key = event.key
        
        if key == "a":
            # Stage file
            await self.stage_current_file()
            event.stop()
        elif key == "u":
            # Unstage file
            await self.unstage_current_file()
            event.stop()
        elif key == "c":
            # Commit - quick and dirty for now
            from emdx.ui.git_browser import CommitMessageScreen
            result = await self.app.push_screen_wait(CommitMessageScreen())
            if result:
                git_commit(result, self.current_worktree_path)
                await self.refresh_git_status()
            event.stop()
        elif key == "R":
            # Discard changes
            await self.discard_current_file()
            event.stop()
            
    async def stage_current_file(self) -> None:
        """Stage the currently selected file."""
        table = self.query_one("#git-table", DataTable)
        if not table.cursor_row or table.cursor_row >= len(self.git_files):
            return
            
        file = self.git_files[table.cursor_row]
        git_stage_file(file.path, self.current_worktree_path)
        await self.refresh_git_status()
        
    async def unstage_current_file(self) -> None:
        """Unstage the currently selected file."""
        table = self.query_one("#git-table", DataTable)
        if not table.cursor_row or table.cursor_row >= len(self.git_files):
            return
            
        file = self.git_files[table.cursor_row]
        git_unstage_file(file.path, self.current_worktree_path)
        await self.refresh_git_status()
        
    async def discard_current_file(self) -> None:
        """Discard changes to current file."""
        table = self.query_one("#git-table", DataTable)
        if not table.cursor_row or table.cursor_row >= len(self.git_files):
            return
            
        file = self.git_files[table.cursor_row]
        git_discard_changes(file.path, self.current_worktree_path)
        await self.refresh_git_status()
        
    async def on_data_table_row_highlighted(self, event) -> None:
        """Show diff when row is highlighted."""
        row_idx = event.cursor_row
        if row_idx >= len(self.git_files):
            return
            
        file = self.git_files[row_idx]
        
        # Get diff for this file
        diff_content = get_comprehensive_git_diff(
            file_path=file.path,
            worktree_path=self.current_worktree_path
        )
        
        # Update diff view
        diff_view = self.query_one("#diff-content", RichLog)
        diff_view.clear()
        
        if diff_content:
            # Simple colorization
            for line in diff_content.split('\n'):
                if line.startswith('+') and not line.startswith('+++'):
                    diff_view.write(f"[green]{line}[/green]")
                elif line.startswith('-') and not line.startswith('---'):
                    diff_view.write(f"[red]{line}[/red]")
                elif line.startswith('@@'):
                    diff_view.write(f"[cyan]{line}[/cyan]")
                else:
                    diff_view.write(line)
