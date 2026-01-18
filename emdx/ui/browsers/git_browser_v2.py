"""
GitBrowserV2 - Git diff browser using the panel system.

Uses ListPanel for file listing and PreviewPanel for colorized diff display.
Provides stage/unstage/commit/discard operations with vim-style navigation.
"""

import logging
import os
from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widget import Widget

from emdx.utils.git_ops import (
    get_comprehensive_git_diff,
    get_current_branch,
    get_git_status,
    git_commit,
    git_discard_changes,
    git_stage_file,
    git_unstage_file,
)
from ..panels import (
    ColumnDef, ListItem, ListPanel, ListPanelConfig,
    PreviewPanel, PreviewPanelConfig,
)

logger = logging.getLogger(__name__)

STATUS_ICONS = {"M": "M", "A": "A", "D": "D", "R": "R", "C": "C", "U": "?", "??": "?"}


class GitBrowserV2(Widget):
    """Git diff browser with file list and colorized diff preview."""

    DEFAULT_CSS = """
    GitBrowserV2 { layout: horizontal; height: 100%; }
    GitBrowserV2 #git-list { width: 45%; min-width: 30; }
    GitBrowserV2 #git-preview { width: 55%; min-width: 40; border-left: solid $primary; }
    """

    BINDINGS = [
        Binding("a", "stage_file", "Stage", show=True),
        Binding("u", "unstage_file", "Unstage", show=True),
        Binding("c", "commit", "Commit", show=True),
        Binding("R", "discard_changes", "Discard", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, worktree_path: Optional[str] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.worktree_path = worktree_path or os.getcwd()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield ListPanel(
                columns=[ColumnDef("St", width=3), ColumnDef("File", width=50)],
                config=ListPanelConfig(
                    show_search=True, search_placeholder="Search files...",
                    status_format="{filtered}/{total} files",
                ),
                show_status=True, id="git-list",
            )
            yield PreviewPanel(
                config=PreviewPanelConfig(
                    enable_editing=False, enable_selection=True,
                    empty_message="Select a file to view diff", markdown_rendering=False,
                ),
                id="git-preview",
            )

    async def on_mount(self) -> None:
        await self._refresh_git_status()

    async def _refresh_git_status(self) -> None:
        try:
            git_files = get_git_status(self.worktree_path)
            branch = get_current_branch(self.worktree_path)
            items = [
                ListItem(
                    id=f.path,
                    values=[STATUS_ICONS.get(f.status, "."), f.path],
                    data={"path": f.path, "status": f.status},
                )
                for f in git_files
            ]
            list_panel = self.query_one("#git-list", ListPanel)
            list_panel.set_items(items)
            list_panel.update_status(f"{branch} | {len(items)} changes")
        except Exception as e:
            logger.error(f"Error refreshing git status: {e}")
            self.notify(f"Error: {e}", severity="error")

    async def on_list_panel_item_selected(self, event: ListPanel.ItemSelected) -> None:
        item = event.item
        if not item.data:
            return
        file_path = item.data["path"]
        diff_content = get_comprehensive_git_diff(file_path, self.worktree_path)
        preview = self.query_one("#git-preview", PreviewPanel)
        if diff_content:
            colorized = self._colorize_diff(diff_content)
            await preview.show_content(colorized, title=file_path, render_markdown=False)
        else:
            await preview.show_empty(f"No diff available for {file_path}")

    def _colorize_diff(self, diff: str) -> str:
        lines = []
        for line in diff.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines.append(f"[green]{line}[/green]")
            elif line.startswith("-") and not line.startswith("---"):
                lines.append(f"[red]{line}[/red]")
            elif line.startswith("@@"):
                lines.append(f"[cyan]{line}[/cyan]")
            elif line.startswith("diff ") or line.startswith("index "):
                lines.append(f"[dim]{line}[/dim]")
            else:
                lines.append(line)
        return "\n".join(lines)

    def _get_selected_file(self) -> Optional[str]:
        list_panel = self.query_one("#git-list", ListPanel)
        item = list_panel.get_selected_item()
        return item.data["path"] if item and item.data else None

    async def action_stage_file(self) -> None:
        if file_path := self._get_selected_file():
            git_stage_file(file_path, self.worktree_path)
            await self._refresh_git_status()
            self.notify(f"Staged: {file_path}")

    async def action_unstage_file(self) -> None:
        if file_path := self._get_selected_file():
            git_unstage_file(file_path, self.worktree_path)
            await self._refresh_git_status()
            self.notify(f"Unstaged: {file_path}")

    async def action_discard_changes(self) -> None:
        if file_path := self._get_selected_file():
            git_discard_changes(file_path, self.worktree_path)
            await self._refresh_git_status()
            self.notify(f"Discarded: {file_path}")

    async def action_commit(self) -> None:
        from emdx.ui.git_browser import CommitMessageScreen
        result = await self.app.push_screen_wait(CommitMessageScreen())
        if result:
            success, message = git_commit(result, self.worktree_path)
            if success:
                await self._refresh_git_status()
                self.notify("Committed successfully")
            else:
                self.notify(f"Commit failed: {message}", severity="error")

    async def action_refresh(self) -> None:
        await self._refresh_git_status()
        self.notify("Refreshed")

    def action_quit(self) -> None:
        self.app.exit()
