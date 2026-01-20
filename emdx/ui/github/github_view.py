"""GitHub PR browser view widget."""

import asyncio
import logging
from typing import Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListItem, ListView, Markdown, Static

from emdx.services.github_service import FilterMode
from .github_items import PRItem, PRStateVM
from .github_presenter import GitHubPresenter

logger = logging.getLogger(__name__)


class PRListItem(ListItem):
    """A single PR item in the list."""

    def __init__(self, pr: PRItem, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pr = pr

    def compose(self) -> ComposeResult:
        """Compose the PR item."""
        status = self.pr.status_icon
        title = self.pr.title[:50] + "..." if len(self.pr.title) > 50 else self.pr.title
        author = self.pr.author
        content = f"{status} #{self.pr.number} {title}  ({author})"
        yield Static(content, classes="pr-item-content", markup=False)


class PRPreview(Vertical):
    """PR preview panel."""

    DEFAULT_CSS = """
    PRPreview {
        width: 55%;
        height: 100%;
        border-left: solid $primary;
        padding: 1;
    }

    PRPreview #pr-preview-title {
        text-style: bold;
        margin-bottom: 1;
    }

    PRPreview #pr-preview-meta {
        color: $text-muted;
        margin-bottom: 1;
    }

    PRPreview #pr-preview-stats {
        margin-bottom: 1;
    }

    PRPreview #pr-preview-body {
        height: 100%;
        overflow-y: auto;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose preview panel."""
        yield Static("Select a PR to view details", id="pr-preview-title", markup=False)
        yield Static("", id="pr-preview-meta", markup=False)
        yield Static("", id="pr-preview-stats", markup=False)
        yield Markdown("", id="pr-preview-body")

    def update_pr(self, pr: Optional[PRItem]) -> None:
        """Update the preview with PR details."""
        if not pr:
            self.query_one("#pr-preview-title", Static).update("Select a PR to view details")
            self.query_one("#pr-preview-meta", Static).update("")
            self.query_one("#pr-preview-stats", Static).update("")
            self.query_one("#pr-preview-body", Markdown).update("")
            return

        title = f"PR #{pr.number}: {pr.title}"
        self.query_one("#pr-preview-title", Static).update(title)

        meta = f"{pr.author} → {pr.base_branch}"
        if pr.is_draft:
            meta += " (Draft)"
        self.query_one("#pr-preview-meta", Static).update(meta)

        stats_parts = []
        stats_parts.append(f"+{pr.additions} -{pr.deletions}")
        stats_parts.append(f"{pr.changed_files} files")
        if pr.comments_count:
            stats_parts.append(f"{pr.comments_count} comments")

        review_status = ""
        if pr.review_decision.value:
            review_status = f" | {pr.review_decision.value.replace('_', ' ').title()}"

        checks_status = ""
        if pr.checks_status.value != "none":
            icon = "✓" if pr.checks_status.value == "passing" else "✗" if pr.checks_status.value == "failing" else "○"
            checks_status = f" | {icon} Checks"

        stats = " | ".join(stats_parts) + review_status + checks_status
        self.query_one("#pr-preview-stats", Static).update(stats)

        body = pr.body if pr.body else "*No description provided*"
        self.query_one("#pr-preview-body", Markdown).update(body)


class GitHubView(Widget):
    """Main GitHub PR browser view."""

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=True),
        Binding("k", "cursor_up", "Up", show=True),
        Binding("f", "view_files", "Files", show=True),
        Binding("enter", "view_diff", "Diff", show=False),
        Binding("M", "merge", "Merge", show=True),
        Binding("A", "approve", "Approve", show=True),
        Binding("o", "checkout", "Checkout", show=True),
        Binding("b", "open_browser", "Browser", show=True),
        Binding("r", "refresh", "Refresh", show=True),
    ]

    DEFAULT_CSS = """
    GitHubView {
        layout: vertical;
        height: 100%;
    }

    GitHubView #github-status {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    GitHubView #github-main {
        height: 1fr;
    }

    GitHubView #pr-list-container {
        width: 45%;
        height: 100%;
    }

    GitHubView ListView {
        height: 100%;
    }

    GitHubView .pr-item-content {
        width: 100%;
    }
    """

    class ViewDocument(Message):
        """Request to view an EMDX document."""

        def __init__(self, doc_id: int) -> None:
            self.doc_id = doc_id
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._presenter = GitHubPresenter(on_state_changed=self._on_state_changed)
        self._initialized = False

    def compose(self) -> ComposeResult:
        """Compose the view."""
        yield Static("Loading PRs...", id="github-status")
        with Horizontal(id="github-main"):
            with Vertical(id="pr-list-container"):
                yield ListView(id="pr-list")
            yield PRPreview(id="pr-preview")

    async def on_mount(self) -> None:
        """Initialize on mount."""
        # Focus the PR list immediately
        self.call_later(self._focus_list)
        # Load PRs in background (non-blocking)
        if not self._initialized:
            self._initialized = True
            asyncio.create_task(self._presenter.initialize())

    def _focus_list(self) -> None:
        """Focus the PR list."""
        try:
            list_view = self.query_one("#pr-list", ListView)
            list_view.focus()
        except Exception:
            pass

    def _on_state_changed(self, state: PRStateVM) -> None:
        """Handle state changes from presenter."""
        self.call_later(lambda: self._do_state_update(state))

    def _do_state_update(self, state: PRStateVM) -> None:
        """Actually perform the state update."""
        if not self.is_mounted:
            return

        try:
            # Update status bar - simple format
            status = self.query_one("#github-status", Static)
            if state.loading:
                status.update("Loading PRs...")
            elif state.error:
                status.update(f"Error: {state.error}")
            elif not state.gh_available:
                status.update(state.gh_error or "GitHub CLI not available")
            else:
                pr_count = len(state.filtered_prs)
                status.update(f"{pr_count} PRs | Enter=Diff | M=Merge | A=Approve | o=Checkout | b=Browser | r=Refresh")

            # Update PR list
            list_view = self.query_one("#pr-list", ListView)
            current_count = len(list_view.children)
            new_count = len(state.filtered_prs)

            needs_rebuild = current_count != new_count
            if not needs_rebuild and current_count > 0:
                first_child = list_view.children[0]
                if isinstance(first_child, PRListItem):
                    if state.filtered_prs and first_child.pr.number != state.filtered_prs[0].number:
                        needs_rebuild = True

            if needs_rebuild:
                self._update_pr_list(state)
            elif state.filtered_prs and 0 <= state.selected_index < len(list_view.children):
                list_view.index = state.selected_index

            # Update preview
            preview = self.query_one("#pr-preview", PRPreview)
            preview.update_pr(state.selected_pr)

            self.refresh()
        except Exception as e:
            logger.error(f"Error updating GitHub view: {e}", exc_info=True)

    def _update_pr_list(self, state: PRStateVM) -> None:
        """Update the PR list widget."""
        list_view = self.query_one("#pr-list", ListView)

        list_view.clear()
        for pr in state.filtered_prs:
            item = PRListItem(pr, id=f"pr-{pr.number}")
            list_view.append(item)

        if state.filtered_prs and 0 <= state.selected_index < len(list_view.children):
            list_view.index = state.selected_index

        list_view.refresh()

    @on(ListView.Selected)
    async def on_list_selected(self, event: ListView.Selected) -> None:
        """Handle list selection - opens diff view."""
        if isinstance(event.item, PRListItem):
            list_view = self.query_one("#pr-list", ListView)
            for i, item in enumerate(list_view.children):
                if item == event.item:
                    self._presenter.select_index(i)
                    break
            await self.action_view_diff()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        self._presenter.select_next()
        list_view = self.query_one("#pr-list", ListView)
        if list_view.index is not None:
            list_view.index = self._presenter.state.selected_index

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        self._presenter.select_previous()
        list_view = self.query_one("#pr-list", ListView)
        if list_view.index is not None:
            list_view.index = self._presenter.state.selected_index

    async def action_refresh(self) -> None:
        """Refresh PR list."""
        self._presenter.invalidate_cache()
        await self._presenter.refresh()

    async def action_merge(self) -> None:
        """Merge selected PR."""
        success, message = await self._presenter.merge_selected()
        self.notify(message, severity="information" if success else "error")

    async def action_approve(self) -> None:
        """Approve selected PR."""
        success, message = await self._presenter.approve_selected()
        self.notify(message, severity="information" if success else "error")

    async def action_checkout(self) -> None:
        """Checkout selected PR branch."""
        success, message = await self._presenter.checkout_selected()
        self.notify(message, severity="information" if success else "error")

    async def action_open_browser(self) -> None:
        """Open selected PR in browser."""
        success, message = await self._presenter.open_selected_in_browser()
        self.notify(message, severity="information" if success else "error")

    async def action_view_diff(self) -> None:
        """View diff for selected PR."""
        pr = self._presenter.state.selected_pr
        if not pr:
            self.notify("No PR selected", severity="warning")
            return

        self.notify(f"Loading diff for PR #{pr.number}...")
        success, result = await self._presenter.get_selected_diff()

        if success:
            from .diff_modal import DiffModal
            self.app.push_screen(DiffModal(pr.number, pr.title, result))
        else:
            self.notify(f"Failed to load diff: {result}", severity="error")

    async def action_view_files(self) -> None:
        """View files changed in selected PR."""
        pr = self._presenter.state.selected_pr
        if not pr:
            self.notify("No PR selected", severity="warning")
            return

        success, files = await self._presenter.get_selected_files()

        if success and files:
            lines = [f"Files changed in PR #{pr.number}:", ""]
            for f in files:
                path = f.get("path", "unknown")
                adds = f.get("additions", 0)
                dels = f.get("deletions", 0)
                lines.append(f"  {path} (+{adds} -{dels})")

            from .diff_modal import DiffModal
            self.app.push_screen(DiffModal(pr.number, f"{pr.title} - Files", "\n".join(lines)))
        else:
            self.notify("No files found or failed to load", severity="warning")
