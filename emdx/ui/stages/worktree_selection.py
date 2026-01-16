#!/usr/bin/env python3
"""
Worktree selection stage for agent execution overlay.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, ListView, ListItem, Label
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from ...utils.git_ops import get_worktrees, GitWorktree, create_worktree, is_git_repository, get_current_branch
from .base import OverlayStage

logger = get_logger(__name__)

import time


def format_worktree_display(worktree: GitWorktree, index: int) -> str:
    """Format worktree for display in ListView."""
    # Truncate path to show last 2 components for readability
    path_parts = Path(worktree.path).parts
    if len(path_parts) > 2:
        display_path = str(Path(*path_parts[-2:]))
    else:
        display_path = worktree.path

    # Truncate if still too long
    if len(display_path) > 40:
        display_path = "..." + display_path[-37:]

    # Format branch name
    branch = worktree.branch
    if len(branch) > 30:
        branch = branch[:27] + "..."

    # Truncate commit hash
    commit_short = worktree.commit[:8]

    # Current worktree indicator
    current_indicator = "→" if worktree.is_current else " "

    return f"{current_indicator} [{index}] {branch:<30} {commit_short} {display_path}"


class WorktreeSelectionStage(OverlayStage):
    """Worktree selection stage with git worktree list."""

    BINDINGS = [
        Binding("enter", "select_worktree", "Select Worktree"),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("n", "create_new_worktree", "Create New (Default)", show=True, priority=True),
        Binding("c", "use_current", "Use Current"),
        Binding("s", "skip_worktree", "Skip (Use Current)"),
        Binding("escape", "cancel", "Cancel"),
    ]

    DEFAULT_CSS = """
    WorktreeSelectionStage {
        height: 1fr;
        layout: vertical;
    }

    #worktree-info {
        height: 3;
        color: $text-muted;
        padding: 0 1 1 1;
    }

    #worktree-list-view {
        height: 1fr;
        border: solid $primary;
    }

    #worktree-help {
        height: 2;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }

    .worktree-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 1 1;
    }
    """

    class WorktreeSelected(Message):
        """Message sent when a worktree is selected."""
        def __init__(self, worktree_index: int, worktree_data: Dict[str, Any]) -> None:
            self.worktree_index = worktree_index
            self.worktree_data = worktree_data
            super().__init__()

    def __init__(self, host, **kwargs):
        super().__init__(host, "worktree", **kwargs)
        self.worktrees: List[GitWorktree] = []
        self.selected_worktree: Optional[GitWorktree] = None
        self.selected_index: Optional[int] = None
        self.current_worktree_index: Optional[int] = None

    def compose(self) -> ComposeResult:
        """Create the worktree selection UI."""
        yield Static("[bold yellow]🌳 Worktree Selection[/bold yellow]", classes="worktree-header")
        yield Static("[bold green]Press N to create new worktree (recommended)[/bold green] or select existing worktree below.", id="worktree-info")
        yield ListView(id="worktree-list-view")
        yield Static("N: Create New (Default) | Enter: Select | C/S: Use Current | Tab: Next", id="worktree-help")

    async def on_mount(self) -> None:
        """Load stage when mounted."""
        await super().on_mount()

    async def load_stage_data(self) -> None:
        """Load git worktrees data and auto-create new worktree for agent execution."""
        try:
            # Check if worktrees were already loaded from project selection
            preloaded_worktrees = self.host.data.get('project_worktrees')

            if preloaded_worktrees:
                # Use pre-loaded worktrees (much faster!)
                logger.info(f"Using pre-loaded worktrees from project selection: {len(preloaded_worktrees)} worktrees")
                self.worktrees = preloaded_worktrees
            else:
                # Fall back to loading worktrees
                project_path = self.host.data.get('project_path')

                # Check if we're in a git repository
                if not is_git_repository(project_path):
                    logger.info("Not in git repository - skipping worktree creation")
                    self.selected_index = 0
                    self.selected_worktree = None
                    self._is_valid = True
                    self.host.set_worktree_selection(0)
                    await asyncio.sleep(0.1)
                    await self.update_worktree_list()
                    return

                logger.info(f"Loading git worktrees for project: {project_path or 'current'}")
                self.worktrees = get_worktrees(project_path)
                logger.info(f"Loaded {len(self.worktrees)} worktrees")

            # Find current worktree
            for idx, wt in enumerate(self.worktrees):
                if wt.is_current:
                    self.current_worktree_index = idx
                    logger.info(f"Current worktree is index {idx}: {wt.branch}")
                    break

            # Ensure the UI is fully mounted before updating the list
            await asyncio.sleep(0.1)
            await self.update_worktree_list()

            # Don't auto-create - let user choose with N key
            # Focus is already on ListView for navigation

        except Exception as e:
            logger.error(f"Failed to load worktrees: {e}")
            # If we can't load worktrees, just use current directory
            await self.auto_select_current()

    async def auto_select_current(self) -> None:
        """Automatically select the current worktree."""
        if self.current_worktree_index is not None and self.worktrees:
            self.selected_index = self.current_worktree_index
            self.selected_worktree = self.worktrees[self.current_worktree_index]
        else:
            # No git repo or no worktrees - use index 0 (current directory)
            self.selected_index = 0
            self.selected_worktree = None

        self._is_valid = True
        self.host.set_worktree_selection(self.selected_index)
        self.update_selection(self.get_selection_data())

    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the list view."""
        try:
            list_view = self.query_one("#worktree-list-view", ListView)
            list_view.focus()
        except Exception as e:
            logger.warning(f"Could not focus list view: {e}")

    def validate_selection(self) -> bool:
        """Check if a worktree is selected."""
        return self.selected_index is not None

    def get_selection_data(self) -> Dict[str, Any]:
        """Return selected worktree data."""
        if self.selected_worktree:
            return {
                "worktree_index": self.selected_index,
                "worktree_path": self.selected_worktree.path,
                "worktree_branch": self.selected_worktree.branch,
                "worktree_commit": self.selected_worktree.commit,
            }
        else:
            # No git repo or no worktrees - use current directory
            return {
                "worktree_index": 0,
                "worktree_path": ".",
                "worktree_branch": "N/A",
                "worktree_commit": "N/A",
            }

    async def update_worktree_list(self) -> None:
        """Update the worktree list display."""
        try:
            list_view = self.query_one("#worktree-list-view", ListView)
            list_view.clear()

            if not self.worktrees:
                list_view.append(ListItem(Static("[yellow]Not in a git repository. Agent will execute in current directory.[/yellow]")))
                list_view.append(ListItem(Static("[dim]Press Tab to continue or Ctrl+C to cancel.[/dim]")))
                return

            # Add worktree items
            for idx, worktree in enumerate(self.worktrees):
                display_text = format_worktree_display(worktree, idx)
                list_view.append(ListItem(Static(display_text)))

            # Highlight current worktree if known
            if self.current_worktree_index is not None:
                list_view.index = self.current_worktree_index

        except Exception as e:
            logger.error(f"Failed to update worktree list: {e}")

    async def show_error(self, message: str) -> None:
        """Show error message."""
        try:
            list_view = self.query_one("#worktree-list-view", ListView)
            list_view.clear()
            list_view.append(ListItem(Static(f"[red]Error: {message}[/red]")))
        except Exception as e:
            logger.error(f"Could not show error in ListView: {e}")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle ListView selection (when user presses Enter on an item)."""
        if not self.worktrees:
            # No worktrees, just advance
            await self.auto_select_current()
            self.request_navigation("next")
            return

        selected_index = event.list_view.index

        if selected_index is not None and 0 <= selected_index < len(self.worktrees):
            worktree = self.worktrees[selected_index]
            self.selected_index = selected_index
            self.selected_worktree = worktree

            logger.info(f"Worktree selected via ListView: {selected_index} - {worktree.branch}")

            # Update host selection
            self.host.set_worktree_selection(selected_index)

            # Update selection data and mark as valid
            self.update_selection(self.get_selection_data())
            self._is_valid = True

            # Post selection message
            self.post_message(self.WorktreeSelected(selected_index, self.get_selection_data()))

            # Request navigation to next stage
            self.request_navigation("next")

    def action_select_worktree(self) -> None:
        """Select the current worktree."""
        logger.info("action_select_worktree called")

        if not self.worktrees:
            # No worktrees, just advance
            asyncio.create_task(self.auto_select_current())
            self.request_navigation("next")
            return

        try:
            list_view = self.query_one("#worktree-list-view", ListView)
            selected_index = list_view.index

            if selected_index is not None and 0 <= selected_index < len(self.worktrees):
                worktree = self.worktrees[selected_index]
                self.selected_index = selected_index
                self.selected_worktree = worktree

                logger.info(f"Worktree selected via action: {selected_index} - {worktree.branch}")

                # Update host selection
                self.host.set_worktree_selection(selected_index)

                # Update selection data and mark as valid
                self.update_selection(self.get_selection_data())
                self._is_valid = True

                # Post selection message
                self.post_message(self.WorktreeSelected(selected_index, self.get_selection_data()))

                # Request navigation to next stage
                self.request_navigation("next")
            else:
                logger.warning(f"Invalid selection index: {selected_index}")
        except Exception as e:
            logger.error(f"Error in action_select_worktree: {e}", exc_info=True)

    def action_use_current(self) -> None:
        """Use the current worktree."""
        asyncio.create_task(self.auto_select_current())
        self.request_navigation("next")

    def action_skip_worktree(self) -> None:
        """Skip worktree selection and use current directory."""
        asyncio.create_task(self.auto_select_current())
        self.request_navigation("next")

    def action_create_new_worktree(self) -> None:
        """Manually trigger new worktree creation."""
        asyncio.create_task(self.create_new_worktree_auto())

    async def create_new_worktree_auto(self) -> None:
        """Automatically create a new worktree for this agent execution."""
        try:
            # Get document ID and project path from host selections
            doc_id = self.host.data.get("document_id")
            project_path = self.host.data.get("project_path")

            logger.info(f"Worktree creation - doc_id: {doc_id}, project_path: {project_path}")
            logger.info(f"Full host.data: {self.host.data}")

            if not doc_id:
                logger.warning("No document ID available for worktree creation")
                await self.auto_select_current()
                return

            if not project_path:
                logger.warning("No project selected - using current directory")
                project_path = None

            # Generate unique branch name with timestamp to avoid conflicts
            # Format: agent-exec-doc<id>-<timestamp>
            timestamp = int(time.time())
            branch_name = f"agent-exec-doc{doc_id}-{timestamp}"

            # Get current branch from the selected project as base
            base_branch = get_current_branch(project_path)

            logger.info(f"Creating new worktree for project '{project_path}': {branch_name} from {base_branch}")

            # Update info display to show creation in progress
            try:
                info_widget = self.query_one("#worktree-info", Static)
                info_widget.update(f"[yellow]Creating new worktree: {branch_name}...[/yellow]")
            except Exception:
                pass

            # Create the worktree for the selected project
            success, worktree_path, error = create_worktree(branch_name, base_branch=base_branch, repo_path=project_path)

            if success:
                logger.info(f"Successfully created worktree at: {worktree_path}")

                # Update info display
                try:
                    info_widget = self.query_one("#worktree-info", Static)
                    info_widget.update(f"[green]✓ Created new worktree: {branch_name}[/green]")
                except Exception:
                    pass

                # Reload worktrees list for the selected project
                self.worktrees = get_worktrees(project_path)

                # Find and select the newly created worktree
                for idx, wt in enumerate(self.worktrees):
                    if branch_name in wt.branch or worktree_path == wt.path:
                        self.selected_index = idx
                        self.selected_worktree = wt
                        self._is_valid = True
                        self.host.set_worktree_selection(idx)
                        self.update_selection(self.get_selection_data())
                        logger.info(f"Selected newly created worktree at index {idx}")
                        break

                # Update list display
                await self.update_worktree_list()

                # Don't auto-advance - let user press Tab or Enter to continue
                # This allows them to review the created worktree

            else:
                logger.error(f"Failed to create worktree: {error}")
                # Update info display with error
                try:
                    info_widget = self.query_one("#worktree-info", Static)
                    info_widget.update(f"[red]Failed to create worktree: {error}[/red]\nPress C to use current worktree instead.")
                except Exception:
                    pass

                # Fall back to current worktree
                await asyncio.sleep(2)
                await self.auto_select_current()

        except Exception as e:
            logger.error(f"Error in create_new_worktree_auto: {e}", exc_info=True)
            await self.auto_select_current()

    def action_next_stage(self) -> None:
        """Navigate to next stage."""
        # Ensure we have a selection before advancing
        if not self.validate_selection():
            asyncio.create_task(self.auto_select_current())
        self.request_navigation("next")

    def action_prev_stage(self) -> None:
        """Navigate to previous stage."""
        self.request_navigation("prev")

    def get_help_text(self) -> str:
        """Get help text for this stage."""
        return "Select a worktree for agent execution. Use ↑↓ or j/k to navigate, Enter to select, C/S to use current, Tab to continue."
