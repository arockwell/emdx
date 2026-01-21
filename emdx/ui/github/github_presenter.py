"""GitHub PR presenter - manages state and coordinates with service."""

import asyncio
import logging
from typing import Callable, Optional

from emdx.services.github_service import (
    FilterMode,
    GitHubService,
    get_github_service,
)
from .github_items import PRItem, PRStateVM

logger = logging.getLogger(__name__)


class GitHubPresenter:
    """Presenter for GitHub PR browser.

    Manages state and coordinates between the view and service.
    """

    def __init__(self, on_state_changed: Optional[Callable[[PRStateVM], None]] = None):
        """Initialize the presenter.

        Args:
            on_state_changed: Callback when state changes
        """
        self._service: GitHubService = get_github_service()
        self._state = PRStateVM()
        self._on_state_changed = on_state_changed

    @property
    def state(self) -> PRStateVM:
        """Get current state."""
        return self._state

    def _notify(self) -> None:
        """Notify listeners of state change."""
        if self._on_state_changed:
            self._on_state_changed(self._state)

    async def initialize(self) -> None:
        """Initialize the presenter and check gh availability."""
        available, error = await self._service.check_gh_available()
        self._state.gh_available = available
        self._state.gh_error = error if not available else None

        if available:
            await self.refresh()
        else:
            self._notify()

    async def refresh(self) -> None:
        """Refresh the PR list."""
        if not self._state.gh_available:
            return

        self._state.loading = True
        self._state.error = None
        self._notify()

        try:
            # Fetch all PRs (filter locally for responsiveness)
            prs = await self._service.list_prs(FilterMode.ALL)
            self._state.prs = prs

            # Update filter counts
            self._state.filter_counts = self._service.get_filter_counts(prs)

            # Apply current filter
            self._apply_filter()

            self._state.loading = False
            self._state.error = None

            # Start prefetching diffs in background (first 5 PRs)
            if self._state.filtered_prs:
                pr_numbers = [pr.number for pr in self._state.filtered_prs[:5]]
                self._service.start_prefetch_diffs(pr_numbers)

        except Exception as e:
            logger.error(f"Failed to refresh PRs: {e}", exc_info=True)
            self._state.loading = False
            self._state.error = str(e)

        self._notify()

    def set_filter_mode(self, mode: FilterMode) -> None:
        """Set the filter mode."""
        if self._state.filter_mode != mode:
            self._state.filter_mode = mode
            self._apply_filter()
            self._notify()

    def _apply_filter(self) -> None:
        """Apply current filter to PR list."""
        prs = self._state.prs

        if self._state.filter_mode == FilterMode.ALL:
            self._state.filtered_prs = prs
        elif self._state.filter_mode == FilterMode.MINE:
            current_user = self._service._current_user
            self._state.filtered_prs = [
                pr for pr in prs if pr.author == current_user
            ]
        elif self._state.filter_mode == FilterMode.DRAFTS:
            self._state.filtered_prs = [pr for pr in prs if pr.is_draft]
        elif self._state.filter_mode == FilterMode.CONFLICTS:
            from emdx.services.github_service import MergeableState
            self._state.filtered_prs = [
                pr for pr in prs
                if pr.mergeable == MergeableState.CONFLICTING
            ]
        elif self._state.filter_mode == FilterMode.NEEDS_REVIEW:
            from emdx.services.github_service import ReviewDecision
            self._state.filtered_prs = [
                pr for pr in prs
                if pr.review_decision in (
                    ReviewDecision.REVIEW_REQUIRED,
                    ReviewDecision.CHANGES_REQUESTED
                )
                and not pr.is_draft
            ]
        elif self._state.filter_mode == FilterMode.READY:
            from emdx.services.github_service import (
                ReviewDecision, ChecksStatus, MergeableState
            )
            self._state.filtered_prs = [
                pr for pr in prs
                if pr.review_decision == ReviewDecision.APPROVED
                and pr.checks_status == ChecksStatus.PASSING
                and pr.mergeable == MergeableState.MERGEABLE
                and not pr.is_draft
            ]

        # Adjust selected index if needed
        if self._state.selected_index >= len(self._state.filtered_prs):
            self._state.selected_index = max(0, len(self._state.filtered_prs) - 1)

    def select_index(self, index: int) -> None:
        """Select a PR by index."""
        if 0 <= index < len(self._state.filtered_prs):
            self._state.selected_index = index
            self._notify()
            # Prefetch diffs for nearby PRs
            self._prefetch_nearby(index)

    def select_next(self) -> None:
        """Select next PR."""
        if self._state.selected_index < len(self._state.filtered_prs) - 1:
            self._state.selected_index += 1
            self._notify()
            self._prefetch_nearby(self._state.selected_index)

    def select_previous(self) -> None:
        """Select previous PR."""
        if self._state.selected_index > 0:
            self._state.selected_index -= 1
            self._notify()
            self._prefetch_nearby(self._state.selected_index)

    def _prefetch_nearby(self, index: int) -> None:
        """Prefetch diffs for PRs near the given index."""
        if not self._state.filtered_prs:
            return
        # Prefetch current + next 2 PRs
        start = max(0, index)
        end = min(len(self._state.filtered_prs), index + 3)
        pr_numbers = [self._state.filtered_prs[i].number for i in range(start, end)]
        if pr_numbers:
            self._service.start_prefetch_diffs(pr_numbers)

    async def merge_selected(self) -> tuple[bool, str]:
        """Merge the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        success, message = await self._service.merge_pr(pr.number)
        if success:
            await self.refresh()
        return success, message

    async def approve_selected(self) -> tuple[bool, str]:
        """Approve the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        success, message = await self._service.approve_pr(pr.number)
        if success:
            await self.refresh()
        return success, message

    async def request_changes_selected(self, body: str) -> tuple[bool, str]:
        """Request changes on the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        success, message = await self._service.request_changes(pr.number, body)
        if success:
            await self.refresh()
        return success, message

    async def close_selected(self) -> tuple[bool, str]:
        """Close the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        success, message = await self._service.close_pr(pr.number)
        if success:
            await self.refresh()
        return success, message

    async def checkout_selected(self) -> tuple[bool, str]:
        """Checkout the selected PR's branch."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        return await self._service.checkout_pr(pr.number)

    async def open_selected_in_browser(self) -> tuple[bool, str]:
        """Open the selected PR in browser."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        return await self._service.open_in_browser(pr.number)

    async def get_emdx_doc_for_selected(self) -> Optional[int]:
        """Get EMDX document ID linked to selected PR."""
        pr = self._state.selected_pr
        if not pr or not pr.url:
            return None

        return await self._service.find_emdx_doc_for_pr(pr.url)

    async def get_selected_diff(self) -> tuple[bool, str]:
        """Get the diff for the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, "No PR selected"

        return await self._service.get_pr_diff(pr.number)

    async def get_selected_files(self) -> tuple[bool, list]:
        """Get the files changed in the selected PR."""
        pr = self._state.selected_pr
        if not pr:
            return False, []

        return await self._service.get_pr_files(pr.number)

    def invalidate_cache(self) -> None:
        """Invalidate the service cache."""
        self._service.invalidate_cache()
