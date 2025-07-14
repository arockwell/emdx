#!/usr/bin/env python3
"""
Git diff browser and operations for EMDX TUI.
"""

import logging
import os
from pathlib import Path
from textual.widgets import Button, DataTable, Input, Label, RichLog
from textual.screen import ModalScreen  
from textual.containers import Grid

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


class CommitMessageScreen(ModalScreen):
    """Modal screen for entering git commit messages."""
    
    def __init__(self):
        super().__init__()
        self.commit_message = ""
    
    def compose(self):
        with Grid(id="commit-dialog"):
            yield Label("📝 Enter commit message:", id="commit-label")
            yield Input(placeholder="feat: add new feature", id="commit-input")
            yield Button("Commit", variant="primary", id="commit-btn")
            yield Button("Cancel", variant="default", id="cancel-btn")
    
    CSS = """
    CommitMessageScreen {
        align: center middle;
    }
    #commit-dialog {
        width: 60%;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1;
        grid-size: 1 4;
        grid-rows: auto auto auto auto;
    }
    #commit-input {
        width: 100%;
        margin: 1 0;
    }
    """
    
    def on_button_pressed(self, event):
        if event.button.id == "commit-btn":
            commit_input = self.query_one("#commit-input", Input)
            self.commit_message = commit_input.value.strip()
            if self.commit_message:
                self.dismiss(self.commit_message)
            else:
                # Show error for empty message
                label = self.query_one("#commit-label", Label)
                label.update("[red]⚠️ Commit message cannot be empty[/red]")
        else:
            self.dismiss(None)
    
    def on_mount(self):
        commit_input = self.query_one("#commit-input", Input)
        commit_input.focus()


class GitBrowserMixin:
    """Mixin class to add git browser functionality to the main browser."""
    
    def setup_git_diff_browser(self):
        """Set up the git diff browser interface."""
        try:
            # Get current worktree info (only set if not already set for worktree switching)
            if not hasattr(self, 'current_worktree_path'):
                self.current_worktree_path = os.getcwd()

            current_branch = get_current_branch(self.current_worktree_path)

            # Get list of all worktrees for switching
            from emdx.utils.git_ops import get_worktrees
            self.worktrees = get_worktrees()

            # Find current worktree in the list (based on current_worktree_path, not os.getcwd())
            if not hasattr(self, 'current_worktree_index'):
                self.current_worktree_index = 0
                for i, wt in enumerate(self.worktrees):
                    if wt.path == self.current_worktree_path:
                        self.current_worktree_index = i
                        break

            # Load git status for current worktree
            self.git_files = get_git_status(self.current_worktree_path)
            logger.info(f"📁 Git files from {self.current_worktree_path}: {len(self.git_files)} files")
            for f in self.git_files:
                logger.info(f"  {f.status} {f.path} (staged: {f.staged})")

            # Replace the documents table with git files table
            table = self.query_one("#doc-table", DataTable)
            table.clear(columns=True)
            table.add_columns("Status", "File", "Type")
            logger.info("🔄 Table cleared and columns added")

            # Clear preview first to remove document content
            try:
                preview = self.query_one("#preview-content")
                preview.clear()
            except Exception:
                pass

            if not self.git_files:
                # No files but still set up empty table and allow worktree switching
                preview.write("[dim]No git changes in this worktree[/dim]")
                preview.write("")
                preview.write("[yellow]Press 'w' to switch to another worktree[/yellow]")

                # Update status
                self.cancel_refresh_timer()
                status = self.query_one("#status", Label)
                worktree_name = Path(self.current_worktree_path).name
                status.update(f"📄 GIT DIFF [{worktree_name}:{current_branch}]: No changes ('w' switch worktree, 'q' exit)")
                return

            # Populate git files table
            logger.info(f"📋 Populating table with {len(self.git_files)} files")
            for i, file_status in enumerate(self.git_files):
                # Create more descriptive status display
                if file_status.status == '??':
                    status_display = f"{file_status.status_icon} Untracked"
                    file_type = "New"
                elif file_status.staged:
                    status_display = f"{file_status.status_icon} {file_status.status_description}"
                    file_type = "Staged"
                else:
                    status_display = f"{file_status.status_icon} {file_status.status_description}"
                    file_type = "Modified"

                row_data = (
                    status_display,
                    file_status.path,
                    file_type
                )
                table.add_row(*row_data)
                logger.info(f"  Added row {i}: {row_data}")

            logger.info(f"🎯 Table now has {table.row_count} rows")

            # Start with the first file
            self.current_file_index = 0

            # Select first row and load its diff
            table.move_cursor(row=0)
            logger.info(f"🔍 About to load git diff for index 0, git_files length: {len(self.git_files)}")
            if self.git_files:
                logger.info(f"  First file: {self.git_files[0].path} ({self.git_files[0].status})")
            self.load_git_diff(0)

            # Update status with instructions
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            worktree_name = Path(self.current_worktree_path).name
            status.update(f"📄 GIT DIFF [{worktree_name}:{current_branch}]: {len(self.git_files)} changes (j/k nav, a=stage, u=unstage, c=commit, R=discard, w=worktree, q=exit)")

        except Exception as e:
            self.cancel_refresh_timer()
            status = self.query_one("#status", Label)
            status.update(f"Error setting up git diff browser: {e}")

    def load_git_diff(self, index: int):
        """Load the git diff for the file at the given index."""
        logger.info(f"🔍 load_git_diff called with index {index}, git_files length: {len(self.git_files)}")
        if index < 0 or index >= len(self.git_files):
            logger.warning(f"❌ Index {index} out of range for {len(self.git_files)} files")
            return

        try:
            file_status = self.git_files[index]
            self.current_file_index = index

            # Clear preview and load diff content
            try:
                from textual.widgets import RichLog
                preview = self.query_one("#preview-content", RichLog)
            except Exception:
                # Widget doesn't exist (different screen) - cannot load diff
                return

            preview.clear()

            # Show file header
            preview.write(f"[bold cyan]=== {file_status.path} ===[/bold cyan]")
            preview.write(f"[yellow]Status:[/yellow] {file_status.status_description} ({file_status.status})")
            preview.write(f"[yellow]Type:[/yellow] {'Staged' if file_status.staged else 'Unstaged'}")
            preview.write(f"[yellow]Worktree:[/yellow] {Path(self.current_worktree_path).name}")
            preview.write("[bold cyan]=== Diff Content ===[/bold cyan]")
            preview.write("")

            # Load comprehensive git diff content (both staged and unstaged)
            logger.info(f"🔍 Getting comprehensive diff for {file_status.path} from {self.current_worktree_path}")

            if file_status.status == '??':
                # For untracked files, show file content instead of diff
                preview.write("[yellow]📄 UNTRACKED FILE CONTENT[/yellow]")
                preview.write("")
                try:
                    file_path = Path(self.current_worktree_path) / file_status.path
                    if file_path.exists() and file_path.is_file():
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if content.strip():
                                preview.write(content)
                            else:
                                preview.write("[dim](Empty file)[/dim]")
                    else:
                        preview.write("[dim](File not found)[/dim]")
                except Exception as e:
                    preview.write(f"[red]Error reading file: {e}[/red]")
            else:
                # For tracked files, show comprehensive diff with both staged and unstaged changes
                diff_content = get_comprehensive_git_diff(file_status.path, self.current_worktree_path)
                logger.info(f"📄 Comprehensive diff content length: {len(diff_content)} chars")
                if diff_content.strip():
                    preview.write(diff_content)
                    logger.info("✅ Comprehensive diff content written to preview")
                else:
                    preview.write("[dim](No changes found - file may be binary or identical)[/dim]")
                    logger.warning("⚠️ No diff content available")

            # Highlight current row in table
            table = self.query_one("#doc-table", DataTable)
            table.move_cursor(row=index)

        except Exception as e:
            logger.error(f"Error loading git diff: {e}")
            try:
                status = self.query_one("#status", Label)
                status.update(f"Error loading git diff: {e}")
            except Exception:
                pass

    def action_git_stage_file(self):
        """Stage the currently selected file."""
        if self.mode != "GIT_DIFF_BROWSER" or not hasattr(self, 'git_files') or not self.git_files:
            return

        try:
            current_file = self.git_files[self.current_file_index]

            # Don't stage files that are already staged
            if current_file.staged:
                status = self.query_one("#status", Label)
                status.update(f"📦 {current_file.path} is already staged")
                return

            # Stage the file
            success = git_stage_file(current_file.path, self.current_worktree_path)
            status = self.query_one("#status", Label)

            if success:
                status.update(f"✅ Staged {current_file.path}")
                # Refresh the git status and reload the diff browser
                self.setup_git_diff_browser()
            else:
                status.update(f"❌ Failed to stage {current_file.path}")

        except Exception as e:
            status = self.query_one("#status", Label)
            status.update(f"❌ Error staging file: {e}")

    def action_git_unstage_file(self):
        """Unstage the currently selected file."""
        if self.mode != "GIT_DIFF_BROWSER" or not hasattr(self, 'git_files') or not self.git_files:
            return

        try:
            current_file = self.git_files[self.current_file_index]

            # Don't unstage files that aren't staged
            if not current_file.staged:
                status = self.query_one("#status", Label)
                status.update(f"📝 {current_file.path} is not staged")
                return

            # Unstage the file
            success = git_unstage_file(current_file.path, self.current_worktree_path)
            status = self.query_one("#status", Label)

            if success:
                status.update(f"✅ Unstaged {current_file.path}")
                # Refresh the git status and reload the diff browser
                self.setup_git_diff_browser()
            else:
                status.update(f"❌ Failed to unstage {current_file.path}")

        except Exception as e:
            status = self.query_one("#status", Label)
            status.update(f"❌ Error unstaging file: {e}")

    def action_git_commit(self):
        """Commit all staged changes with a message."""
        if self.mode != "GIT_DIFF_BROWSER":
            return

        def handle_commit_message(message):
            if message:
                try:
                    success, result = git_commit(message, self.current_worktree_path)
                    status = self.query_one("#status", Label)

                    if success:
                        status.update(f"✅ Committed: {message[:30]}...")
                        # Refresh the git status and reload the diff browser
                        self.setup_git_diff_browser()
                    else:
                        status.update(f"❌ Commit failed: {result}")

                except Exception as e:
                    status = self.query_one("#status", Label)
                    status.update(f"❌ Error committing: {e}")

        # Show the commit message modal
        self.push_screen(CommitMessageScreen(), handle_commit_message)

    def action_git_discard_changes(self):
        """Discard changes to the currently selected file."""
        if self.mode != "GIT_DIFF_BROWSER" or not hasattr(self, 'git_files') or not self.git_files:
            return

        try:
            current_file = self.git_files[self.current_file_index]

            # Don't discard staged files (they need to be unstaged first)
            if current_file.staged:
                status = self.query_one("#status", Label)
                status.update(f"⚠️ Unstage {current_file.path} first (press 'u')")
                return

            # Only discard if file has unstaged changes
            if current_file.status == '??':
                status = self.query_one("#status", Label)
                status.update(f"⚠️ Cannot discard untracked file {current_file.path}")
                return

            # Discard the changes
            success = git_discard_changes(current_file.path, self.current_worktree_path)
            status = self.query_one("#status", Label)

            if success:
                status.update(f"✅ Discarded changes to {current_file.path}")
                # Refresh the git status and reload the diff browser
                self.setup_git_diff_browser()
            else:
                status.update(f"❌ Failed to discard changes to {current_file.path}")

        except Exception as e:
            status = self.query_one("#status", Label)
            status.update(f"❌ Error discarding changes: {e}")

    def navigate_git_diff(self, direction: int):
        """Navigate between git files in diff browser."""
        if self.mode != "GIT_DIFF_BROWSER" or not hasattr(self, 'git_files') or not self.git_files:
            return
            
        # Calculate new index
        new_index = self.current_file_index + direction
        
        # Wrap around if needed
        if new_index < 0:
            new_index = len(self.git_files) - 1
        elif new_index >= len(self.git_files):
            new_index = 0
            
        # Load the new file
        self.load_git_diff(new_index)