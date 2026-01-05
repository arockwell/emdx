#!/usr/bin/env python3
"""
Project selection stage for cross-project agent execution.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static, ListView, ListItem, Label
from textual.message import Message
from textual.binding import Binding

from ...utils.logging import get_logger
from ...utils.git_ops import discover_projects_from_worktrees, GitProject, get_repository_root
from .base import OverlayStage, OverlayStageHost

logger = get_logger(__name__)


def format_project_display(project: GitProject, index: int, is_current: bool) -> str:
    """Format project for display in ListView."""
    # Truncate name if too long
    name = project.name
    if len(name) > 35:
        name = name[:32] + "..."

    # Current project indicator
    current_indicator = "→" if is_current else " "

    # Show worktree count
    wt_count = f"{project.worktree_count} wt" if project.worktree_count > 0 else "no wt"

    return f"{current_indicator} [{index}] {name:<35} {wt_count:>6}"


class ProjectSelectionStage(OverlayStage):
    """Project selection stage for choosing which git project to work with."""

    BINDINGS = [
        Binding("enter", "select_project", "Select Project"),
        Binding("tab", "next_stage", "Next Stage"),
        Binding("shift+tab", "prev_stage", "Previous Stage"),
        Binding("c", "use_current", "Use Current Project"),
    ]

    DEFAULT_CSS = """
    ProjectSelectionStage {
        height: 1fr;
        layout: vertical;
    }

    #project-info {
        height: 4;
        color: $text-muted;
        padding: 0 1 1 1;
    }

    #project-list-view {
        height: 1fr;
        border: solid $primary;
    }

    #project-help {
        height: 2;
        color: $text-muted;
        text-align: center;
        padding: 1 0 0 0;
    }

    .project-header {
        color: $warning;
        text-style: bold;
        padding: 0 1 1 1;
    }
    """

    class ProjectSelected(Message):
        """Message sent when a project is selected."""
        def __init__(self, project_index: int, project_data: Dict[str, Any]) -> None:
            self.project_index = project_index
            self.project_data = project_data
            super().__init__()

    def __init__(self, host: OverlayStageHost, **kwargs):
        super().__init__(host, "project", **kwargs)
        self.projects: List[GitProject] = []
        self.selected_project: Optional[GitProject] = None
        self.selected_index: Optional[int] = None
        self.current_project_index: Optional[int] = None
        self.current_project_path: Optional[str] = None

    def compose(self) -> ComposeResult:
        """Create the project selection UI."""
        yield Static("[bold yellow]📁 Project Selection[/bold yellow]", classes="project-header")
        yield Static(
            "[bold green]Select a git project to work with.[/bold green]\n"
            "This allows you to run agents on worktrees from any project (e.g., gopher-survivors, emdx).",
            id="project-info"
        )
        yield ListView(id="project-list-view")
        yield Static("Enter: Select | C: Use Current | Tab: Next", id="project-help")

    async def on_mount(self) -> None:
        """Load stage when mounted."""
        await super().on_mount()

    async def load_stage_data(self) -> None:
        """Discover git projects and populate list."""
        try:
            logger.info("Discovering git projects from worktrees")

            # Get current project path
            self.current_project_path = get_repository_root()
            logger.info(f"Current project path: {self.current_project_path}")

            # Discover projects (grouped from worktrees - much faster!)
            self.projects = discover_projects_from_worktrees()
            logger.info(f"Discovered {len(self.projects)} projects with worktrees already loaded")

            # Find current project in the list
            if self.current_project_path:
                for idx, proj in enumerate(self.projects):
                    if Path(proj.main_path).resolve() == Path(self.current_project_path).resolve():
                        self.current_project_index = idx
                        logger.info(f"Current project is index {idx}: {proj.name}")
                        break

            # Wait for UI to be ready
            await asyncio.sleep(0.1)
            await self.update_project_list()

            # Don't auto-select - let user explicitly choose
            # The list will highlight the current project by default

        except Exception as e:
            logger.error(f"Failed to discover projects: {e}", exc_info=True)

    async def auto_select_current(self) -> None:
        """Automatically select the current project."""
        if self.current_project_index is not None and self.projects:
            self.selected_index = self.current_project_index
            self.selected_project = self.projects[self.current_project_index]
            logger.info(f"Auto-selected current project: {self.selected_project.name}")
        else:
            # No current project found - select first one if available
            if self.projects:
                self.selected_index = 0
                self.selected_project = self.projects[0]
                logger.info(f"Auto-selected first project: {self.selected_project.name}")
            else:
                self.selected_index = None
                self.selected_project = None
                logger.warning("No projects found")

        if self.selected_project:
            self._is_valid = True
            self.host.set_project_selection(self.selected_index, self.selected_project.main_path)
            self.update_selection(self.get_selection_data())

    async def set_focus_to_primary_input(self) -> None:
        """Set focus to the list view."""
        try:
            list_view = self.query_one("#project-list-view", ListView)
            list_view.focus()
        except Exception as e:
            logger.warning(f"Could not focus list view: {e}")

    async def update_project_list(self) -> None:
        """Update the project list view."""
        try:
            list_view = self.query_one("#project-list-view", ListView)
            await list_view.clear()

            if not self.projects:
                await list_view.append(ListItem(Label("No git projects found")))
                return

            for idx, project in enumerate(self.projects):
                is_current = idx == self.current_project_index
                display_text = format_project_display(project, idx, is_current)
                await list_view.append(ListItem(Label(display_text)))

            # Select current project by default
            if self.current_project_index is not None:
                list_view.index = self.current_project_index

        except Exception as e:
            logger.error(f"Failed to update project list: {e}", exc_info=True)

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle project selection from list."""
        try:
            list_view = self.query_one("#project-list-view", ListView)
            selected_index = list_view.index

            if 0 <= selected_index < len(self.projects):
                self.selected_index = selected_index
                self.selected_project = self.projects[selected_index]
                self._is_valid = True

                logger.info(f"Selected project: {self.selected_project.name} with {len(self.selected_project.worktrees)} worktrees")
                # Store both project info AND worktrees
                self.host.set_project_selection(
                    self.selected_index,
                    self.selected_project.main_path,
                    self.selected_project.worktrees
                )
                self.update_selection(self.get_selection_data())

        except Exception as e:
            logger.error(f"Error selecting project: {e}", exc_info=True)

    def action_select_project(self) -> None:
        """Handle Enter key to select project."""
        try:
            list_view = self.query_one("#project-list-view", ListView)
            selected_index = list_view.index

            if 0 <= selected_index < len(self.projects):
                self.selected_index = selected_index
                self.selected_project = self.projects[selected_index]
                self._is_valid = True

                logger.info(f"Selected project: {self.selected_project.name} with {len(self.selected_project.worktrees)} worktrees")
                # Store both project info AND worktrees
                self.host.set_project_selection(
                    self.selected_index,
                    self.selected_project.main_path,
                    self.selected_project.worktrees
                )
                self.update_selection(self.get_selection_data())

        except Exception as e:
            logger.error(f"Error selecting project: {e}", exc_info=True)

    def action_use_current(self) -> None:
        """Use current project."""
        asyncio.create_task(self.auto_select_current())

    def get_selection_data(self) -> Dict[str, Any]:
        """Get current selection data."""
        if self.selected_project:
            return {
                "project_name": self.selected_project.name,
                "project_path": self.selected_project.main_path,
                "worktree_count": self.selected_project.worktree_count,
            }
        return {}

    def get_selection_summary(self) -> str:
        """Get a human-readable summary of the selection."""
        if self.selected_project:
            return f"📁 {self.selected_project.name}"
        return "No project selected"
