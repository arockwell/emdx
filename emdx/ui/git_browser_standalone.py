#!/usr/bin/env python3
"""
Standalone git browser - extracted from the mixin.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Label, RichLog
from textual.widget import Widget
from textual import events

from .navigation_mixin import NavigationMixin, TableProvider
from .browser_types import BrowserState, BrowserMode, GitFileInfo

from emdx.utils.git_ops import (
    get_git_status,
    get_comprehensive_git_diff,
    get_current_branch,
    get_worktrees,
    git_stage_file,
    git_unstage_file,
    git_commit,
    git_discard_changes,
)

logger = logging.getLogger(__name__)


class GitBrowser(Widget, NavigationMixin):
    """Git diff browser widget with vim-style navigation."""
    
    BINDINGS = NavigationMixin.NAVIGATION_BINDINGS  # Include j/k/g/G navigation
    
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
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.git_files: list[dict[str, Any]] = []
        self.current_worktree_path: str = os.getcwd()
        self.current_worktree_index: int = 0
        self.worktrees: list[dict[str, str]] = []
        self.file_statuses: dict[str, str] = {}
    
    def get_primary_table(self) -> DataTable:
        """Return the git files table for navigation."""
        return self.query_one("#git-table", DataTable)
        
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
            except:
                pass  # Status update failed, continue
                
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
        except:
            pass
            
        return state
        
    def restore_state(self, state: dict) -> None:
        """Restore saved state."""
        self.current_worktree_path = state.get("worktree_path", os.getcwd())
        self.current_worktree_index = state.get("worktree_index", 0)
        
        if "cursor_position" in state:
            try:
                table: DataTable = self.query_one("#git-table", DataTable)
                table.cursor_coordinate = state["cursor_position"]
            except Exception:
                pass
    
    def save_state(self) -> BrowserState:
        """Save current git browser state."""
        try:
            table: DataTable = self.query_one("#git-table", DataTable)
            return BrowserState(
                mode="NORMAL",
                cursor_position=(table.cursor_row, table.cursor_column)
            )
        except Exception:
            return BrowserState(mode="NORMAL", cursor_position=(0, 0))
                
    async def on_key(self, event: events.Key) -> None:
        """Handle key events with navigation mixin and git-specific functionality."""
        key: str = event.key
        
        # Use navigation mixin for standard keys
        if self.handle_navigation_key(key):
            event.stop()
            return
        
        # Git-specific keys
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
            result: Optional[str] = await self.app.push_screen_wait(CommitMessageScreen())
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
        table: DataTable = self.query_one("#git-table", DataTable)
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