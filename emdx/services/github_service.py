"""GitHub service - wraps gh CLI commands with async execution and caching.

Provides methods for listing, viewing, and managing GitHub PRs.
Uses the `gh` CLI tool for GitHub API access.
"""

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FilterMode(Enum):
    """PR filter modes."""

    ALL = "all"
    MINE = "mine"
    NEEDS_REVIEW = "needs_review"
    DRAFTS = "drafts"
    CONFLICTS = "conflicts"
    READY = "ready"


class ReviewDecision(Enum):
    """PR review decision status."""

    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NONE = ""


class ChecksStatus(Enum):
    """PR checks status."""

    PASSING = "passing"
    FAILING = "failing"
    PENDING = "pending"
    NONE = "none"


class MergeableState(Enum):
    """PR mergeable state."""

    MERGEABLE = "MERGEABLE"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


@dataclass
class PRItem:
    """View model for a single PR in the list."""

    number: int
    title: str
    author: str
    branch: str
    base_branch: str
    is_draft: bool = False
    mergeable: MergeableState = MergeableState.UNKNOWN
    review_decision: ReviewDecision = ReviewDecision.NONE
    checks_status: ChecksStatus = ChecksStatus.NONE
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    reviewers: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)
    emdx_doc_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    url: str = ""
    body: str = ""
    comments_count: int = 0

    @property
    def status_icon(self) -> str:
        """Get status icon for display."""
        if self.is_draft:
            return "⛔"  # Draft
        if self.mergeable == MergeableState.CONFLICTING:
            return "❌"  # Conflicts
        if self.review_decision == ReviewDecision.CHANGES_REQUESTED:
            return "🔄"  # Changes requested
        if self.review_decision == ReviewDecision.REVIEW_REQUIRED:
            return "⚠"  # Needs review
        if self.checks_status == ChecksStatus.FAILING:
            return "🔴"  # Failing checks
        if self.checks_status == ChecksStatus.PENDING:
            return "🟡"  # Pending checks
        if (
            self.review_decision == ReviewDecision.APPROVED
            and self.checks_status == ChecksStatus.PASSING
            and self.mergeable == MergeableState.MERGEABLE
        ):
            return "✓"  # Ready to merge
        return "○"  # Unknown/other

    @classmethod
    def from_gh_json(cls, data: Dict[str, Any]) -> "PRItem":
        """Create PRItem from gh CLI JSON output."""
        # Parse review decision
        review_decision = ReviewDecision.NONE
        if data.get("reviewDecision"):
            try:
                review_decision = ReviewDecision(data["reviewDecision"])
            except ValueError:
                pass

        # Parse mergeable state
        mergeable = MergeableState.UNKNOWN
        if data.get("mergeable"):
            try:
                mergeable = MergeableState(data["mergeable"])
            except ValueError:
                pass
        # Also check mergeStateStatus for conflicts
        merge_state = data.get("mergeStateStatus", "")
        if merge_state == "DIRTY":
            mergeable = MergeableState.CONFLICTING

        # Parse checks status from statusCheckRollup
        checks_status = ChecksStatus.NONE
        status_rollup = data.get("statusCheckRollup", [])
        if status_rollup:
            # statusCheckRollup is a list of check contexts
            all_passing = True
            any_failing = False
            any_pending = False
            for check in status_rollup:
                conclusion = check.get("conclusion", "").upper()
                state = check.get("state", "").upper()
                if conclusion == "FAILURE" or state == "FAILURE":
                    any_failing = True
                    all_passing = False
                elif conclusion in ("", "PENDING") or state in ("PENDING", "EXPECTED"):
                    any_pending = True
                    all_passing = False
                elif conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                    all_passing = False

            if any_failing:
                checks_status = ChecksStatus.FAILING
            elif any_pending:
                checks_status = ChecksStatus.PENDING
            elif all_passing and status_rollup:
                checks_status = ChecksStatus.PASSING

        # Parse reviewers
        reviewers = []
        review_requests = data.get("reviewRequests", [])
        if review_requests:
            for req in review_requests:
                if isinstance(req, dict):
                    if req.get("login"):
                        reviewers.append(req["login"])
                    elif req.get("name"):
                        reviewers.append(req["name"])

        # Parse labels
        labels = []
        label_data = data.get("labels", [])
        if label_data:
            for label in label_data:
                if isinstance(label, dict) and label.get("name"):
                    labels.append(label["name"])
                elif isinstance(label, str):
                    labels.append(label)

        # Parse timestamps
        created_at = None
        if data.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(
                    data["createdAt"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        updated_at = None
        if data.get("updatedAt"):
            try:
                updated_at = datetime.fromisoformat(
                    data["updatedAt"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            author=data.get("author", {}).get("login", "")
            if isinstance(data.get("author"), dict)
            else str(data.get("author", "")),
            branch=data.get("headRefName", ""),
            base_branch=data.get("baseRefName", ""),
            is_draft=data.get("isDraft", False),
            mergeable=mergeable,
            review_decision=review_decision,
            checks_status=checks_status,
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
            changed_files=data.get("changedFiles", 0),
            reviewers=reviewers,
            labels=labels,
            created_at=created_at,
            updated_at=updated_at,
            url=data.get("url", ""),
            body=data.get("body", ""),
            comments_count=data.get("comments", {}).get("totalCount", 0)
            if isinstance(data.get("comments"), dict)
            else 0,
        )


@dataclass
class PRDetailVM:
    """Extended view model for PR detail view."""

    pr: PRItem
    description: str = ""
    commits: List[Dict[str, Any]] = field(default_factory=list)
    files: List[Dict[str, Any]] = field(default_factory=list)
    reviews: List[Dict[str, Any]] = field(default_factory=list)
    comments: List[Dict[str, Any]] = field(default_factory=list)
    checks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CacheEntry:
    """Cache entry with TTL."""

    data: Any
    timestamp: float
    ttl: float

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return time.time() - self.timestamp < self.ttl


class GitHubService:
    """Service for GitHub PR operations via gh CLI.

    Provides methods for:
    - Listing PRs with filtering
    - Getting PR details
    - PR actions (merge, approve, close, checkout)
    - Reverse lookup from PR URL to EMDX doc
    """

    # Cache TTLs in seconds
    PR_LIST_TTL = 30
    PR_DETAIL_TTL = 60
    DIFF_TTL = 300  # Diffs change less frequently

    def __init__(self):
        self._pr_list_cache: Optional[CacheEntry] = None
        self._pr_detail_cache: Dict[int, CacheEntry] = {}
        self._diff_cache: Dict[int, CacheEntry] = {}
        self._gh_available: Optional[bool] = None
        self._current_user: Optional[str] = None
        self._prefetch_task: Optional[asyncio.Task] = None

    async def _run_gh_command(
        self, args: List[str], timeout: int = 30
    ) -> Tuple[bool, str, str]:
        """Run a gh CLI command asynchronously.

        Args:
            args: Command arguments (without 'gh' prefix)
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            cmd = ["gh"] + args
            logger.debug(f"Running gh command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return False, "", f"Command timed out after {timeout}s"

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.warning(f"gh command failed: {stderr_str}")
                return False, stdout_str, stderr_str

            return True, stdout_str, stderr_str

        except FileNotFoundError:
            return False, "", "gh CLI not found. Install from https://cli.github.com/"
        except Exception as e:
            logger.error(f"Error running gh command: {e}")
            return False, "", str(e)

    async def check_gh_available(self) -> Tuple[bool, str]:
        """Check if gh CLI is available and authenticated.

        Returns:
            Tuple of (available, error_message)
        """
        if self._gh_available is not None:
            return self._gh_available, "" if self._gh_available else "gh CLI not available"

        # Check if gh is installed
        success, stdout, stderr = await self._run_gh_command(["--version"])
        if not success:
            self._gh_available = False
            return False, "gh CLI not installed. Install from https://cli.github.com/"

        # Check if authenticated
        success, stdout, stderr = await self._run_gh_command(["auth", "status"])
        if not success:
            self._gh_available = False
            return False, "Not authenticated with gh. Run 'gh auth login'"

        self._gh_available = True
        return True, ""

    async def get_current_user(self) -> Optional[str]:
        """Get the current authenticated GitHub user."""
        if self._current_user:
            return self._current_user

        success, stdout, stderr = await self._run_gh_command(
            ["api", "user", "--jq", ".login"]
        )
        if success and stdout.strip():
            self._current_user = stdout.strip()
            return self._current_user

        return None

    async def list_prs(
        self, filter_mode: FilterMode = FilterMode.ALL, limit: int = 50
    ) -> List[PRItem]:
        """List PRs with optional filtering.

        Args:
            filter_mode: How to filter the PR list
            limit: Maximum number of PRs to return

        Returns:
            List of PRItem objects
        """
        # Check cache first
        if (
            self._pr_list_cache
            and self._pr_list_cache.is_valid()
            and filter_mode == FilterMode.ALL
        ):
            return self._apply_filter(self._pr_list_cache.data, filter_mode)

        # Build gh command
        fields = [
            "number",
            "title",
            "author",
            "headRefName",
            "baseRefName",
            "isDraft",
            "mergeable",
            "mergeStateStatus",
            "reviewDecision",
            "statusCheckRollup",
            "additions",
            "deletions",
            "changedFiles",
            "reviewRequests",
            "labels",
            "createdAt",
            "updatedAt",
            "url",
            "body",
            "comments",
        ]

        args = [
            "pr",
            "list",
            "--json",
            ",".join(fields),
            "--limit",
            str(limit),
        ]

        # Add state filter for specific modes
        if filter_mode == FilterMode.DRAFTS:
            args.extend(["--draft"])
        elif filter_mode == FilterMode.MINE:
            user = await self.get_current_user()
            if user:
                args.extend(["--author", user])

        success, stdout, stderr = await self._run_gh_command(args)
        if not success:
            logger.error(f"Failed to list PRs: {stderr}")
            return []

        try:
            data = json.loads(stdout) if stdout.strip() else []
            prs = [PRItem.from_gh_json(pr_data) for pr_data in data]

            # Cache the full list
            self._pr_list_cache = CacheEntry(
                data=prs, timestamp=time.time(), ttl=self.PR_LIST_TTL
            )

            # Apply local filtering
            return self._apply_filter(prs, filter_mode)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PR list JSON: {e}")
            return []

    def _apply_filter(self, prs: List[PRItem], filter_mode: FilterMode) -> List[PRItem]:
        """Apply local filtering to PR list."""
        if filter_mode == FilterMode.ALL:
            return prs

        if filter_mode == FilterMode.DRAFTS:
            return [pr for pr in prs if pr.is_draft]

        if filter_mode == FilterMode.CONFLICTS:
            return [pr for pr in prs if pr.mergeable == MergeableState.CONFLICTING]

        if filter_mode == FilterMode.NEEDS_REVIEW:
            return [
                pr
                for pr in prs
                if pr.review_decision
                in (ReviewDecision.REVIEW_REQUIRED, ReviewDecision.CHANGES_REQUESTED)
                and not pr.is_draft
            ]

        if filter_mode == FilterMode.READY:
            return [
                pr
                for pr in prs
                if pr.review_decision == ReviewDecision.APPROVED
                and pr.checks_status == ChecksStatus.PASSING
                and pr.mergeable == MergeableState.MERGEABLE
                and not pr.is_draft
            ]

        if filter_mode == FilterMode.MINE:
            # Already filtered by gh command, but could add additional logic
            return prs

        return prs

    async def get_pr_detail(self, number: int) -> Optional[PRDetailVM]:
        """Get detailed information about a PR.

        Args:
            number: PR number

        Returns:
            PRDetailVM with full details or None if not found
        """
        # Check cache
        if number in self._pr_detail_cache:
            cache_entry = self._pr_detail_cache[number]
            if cache_entry.is_valid():
                return cache_entry.data

        # Get PR details
        fields = [
            "number",
            "title",
            "author",
            "headRefName",
            "baseRefName",
            "isDraft",
            "mergeable",
            "mergeStateStatus",
            "reviewDecision",
            "statusCheckRollup",
            "additions",
            "deletions",
            "changedFiles",
            "reviewRequests",
            "labels",
            "createdAt",
            "updatedAt",
            "url",
            "body",
            "comments",
            "commits",
            "files",
            "reviews",
        ]

        success, stdout, stderr = await self._run_gh_command(
            ["pr", "view", str(number), "--json", ",".join(fields)]
        )

        if not success:
            logger.error(f"Failed to get PR #{number}: {stderr}")
            return None

        try:
            data = json.loads(stdout)
            pr = PRItem.from_gh_json(data)

            # Parse commits
            commits = []
            for commit in data.get("commits", []):
                if isinstance(commit, dict):
                    commits.append(
                        {
                            "sha": commit.get("oid", "")[:8],
                            "message": commit.get("messageHeadline", ""),
                            "author": commit.get("authors", [{}])[0].get("name", "")
                            if commit.get("authors")
                            else "",
                        }
                    )

            # Parse files
            files = []
            for file in data.get("files", []):
                if isinstance(file, dict):
                    files.append(
                        {
                            "path": file.get("path", ""),
                            "additions": file.get("additions", 0),
                            "deletions": file.get("deletions", 0),
                        }
                    )

            # Parse reviews
            reviews = []
            for review in data.get("reviews", []):
                if isinstance(review, dict):
                    reviews.append(
                        {
                            "author": review.get("author", {}).get("login", ""),
                            "state": review.get("state", ""),
                            "body": review.get("body", ""),
                        }
                    )

            detail = PRDetailVM(
                pr=pr,
                description=data.get("body", ""),
                commits=commits,
                files=files,
                reviews=reviews,
            )

            # Cache the detail
            self._pr_detail_cache[number] = CacheEntry(
                data=detail, timestamp=time.time(), ttl=self.PR_DETAIL_TTL
            )

            return detail

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PR detail JSON: {e}")
            return None

    async def merge_pr(
        self,
        number: int,
        method: str = "squash",
        delete_branch: bool = True,
    ) -> Tuple[bool, str]:
        """Merge a PR.

        Args:
            number: PR number
            method: Merge method (merge, squash, rebase)
            delete_branch: Whether to delete the branch after merge

        Returns:
            Tuple of (success, message)
        """
        args = ["pr", "merge", str(number), f"--{method}"]
        if delete_branch:
            args.append("--delete-branch")

        success, stdout, stderr = await self._run_gh_command(args, timeout=60)

        if success:
            # Invalidate caches
            self._pr_list_cache = None
            self._pr_detail_cache.pop(number, None)
            return True, f"PR #{number} merged successfully"

        return False, stderr or "Failed to merge PR"

    async def approve_pr(self, number: int, body: str = "") -> Tuple[bool, str]:
        """Approve a PR.

        Args:
            number: PR number
            body: Optional review body

        Returns:
            Tuple of (success, message)
        """
        args = ["pr", "review", str(number), "--approve"]
        if body:
            args.extend(["--body", body])

        success, stdout, stderr = await self._run_gh_command(args)

        if success:
            # Invalidate detail cache
            self._pr_detail_cache.pop(number, None)
            return True, f"PR #{number} approved"

        return False, stderr or "Failed to approve PR"

    async def request_changes(self, number: int, body: str) -> Tuple[bool, str]:
        """Request changes on a PR.

        Args:
            number: PR number
            body: Review body (required)

        Returns:
            Tuple of (success, message)
        """
        if not body.strip():
            return False, "Review body is required when requesting changes"

        args = ["pr", "review", str(number), "--request-changes", "--body", body]

        success, stdout, stderr = await self._run_gh_command(args)

        if success:
            self._pr_detail_cache.pop(number, None)
            return True, f"Changes requested on PR #{number}"

        return False, stderr or "Failed to request changes"

    async def close_pr(self, number: int) -> Tuple[bool, str]:
        """Close a PR without merging.

        Args:
            number: PR number

        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = await self._run_gh_command(
            ["pr", "close", str(number)]
        )

        if success:
            self._pr_list_cache = None
            self._pr_detail_cache.pop(number, None)
            return True, f"PR #{number} closed"

        return False, stderr or "Failed to close PR"

    async def checkout_pr(self, number: int) -> Tuple[bool, str]:
        """Checkout a PR branch locally.

        Args:
            number: PR number

        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = await self._run_gh_command(
            ["pr", "checkout", str(number)]
        )

        if success:
            return True, f"Checked out PR #{number}"

        return False, stderr or "Failed to checkout PR"

    async def open_in_browser(self, number: int) -> Tuple[bool, str]:
        """Open PR in web browser.

        Args:
            number: PR number

        Returns:
            Tuple of (success, message)
        """
        success, stdout, stderr = await self._run_gh_command(
            ["pr", "view", str(number), "--web"]
        )

        if success:
            return True, f"Opened PR #{number} in browser"

        return False, stderr or "Failed to open PR in browser"

    async def find_emdx_doc_for_pr(self, pr_url: str) -> Optional[int]:
        """Find an EMDX document that links to the given PR URL.

        This performs a reverse lookup from PR URL to document.

        Args:
            pr_url: The GitHub PR URL

        Returns:
            Document ID if found, None otherwise
        """
        try:
            from emdx.database.search import search_documents

            # Search for documents containing the PR URL
            results = search_documents(pr_url, limit=5)
            for doc in results:
                content = doc.get("content", "")
                if pr_url in content:
                    return doc["id"]

            # Also try searching for just the PR number
            # e.g., "PR #123" or "#123"
            import re

            match = re.search(r"/pull/(\d+)", pr_url)
            if match:
                pr_num = match.group(1)
                results = search_documents(f"PR #{pr_num}", limit=5)
                for doc in results:
                    content = doc.get("content", "")
                    if f"PR #{pr_num}" in content or f"#{pr_num}" in content:
                        return doc["id"]

        except Exception as e:
            logger.warning(f"Error searching for EMDX doc: {e}")

        return None

    async def get_pr_diff(self, number: int) -> Tuple[bool, str]:
        """Get the diff for a PR.

        Args:
            number: PR number

        Returns:
            Tuple of (success, diff_content or error_message)
        """
        # Check cache first
        if number in self._diff_cache:
            cache_entry = self._diff_cache[number]
            if cache_entry.is_valid():
                return True, cache_entry.data

        success, stdout, stderr = await self._run_gh_command(
            ["pr", "diff", str(number)], timeout=60
        )

        if success:
            # Cache the diff
            self._diff_cache[number] = CacheEntry(
                data=stdout, timestamp=time.time(), ttl=self.DIFF_TTL
            )
            return True, stdout

        return False, stderr or "Failed to get PR diff"

    async def prefetch_diffs(self, pr_numbers: List[int], max_concurrent: int = 3) -> None:
        """Prefetch diffs for multiple PRs in parallel.

        Args:
            pr_numbers: List of PR numbers to prefetch
            max_concurrent: Max concurrent fetches
        """
        # Filter out already-cached PRs
        to_fetch = [
            n for n in pr_numbers
            if n not in self._diff_cache or not self._diff_cache[n].is_valid()
        ]

        if not to_fetch:
            return

        logger.debug(f"Prefetching diffs for {len(to_fetch)} PRs")

        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_one(number: int) -> None:
            async with semaphore:
                try:
                    await self.get_pr_diff(number)
                except Exception as e:
                    logger.debug(f"Failed to prefetch diff for PR #{number}: {e}")

        # Run all fetches concurrently (semaphore limits actual parallelism)
        await asyncio.gather(*[fetch_one(n) for n in to_fetch], return_exceptions=True)

    def start_prefetch_diffs(self, pr_numbers: List[int]) -> None:
        """Start prefetching diffs in the background (non-blocking).

        Args:
            pr_numbers: List of PR numbers to prefetch
        """
        # Cancel any existing prefetch task
        if self._prefetch_task and not self._prefetch_task.done():
            self._prefetch_task.cancel()

        # Start new prefetch task
        self._prefetch_task = asyncio.create_task(self.prefetch_diffs(pr_numbers))

    async def get_pr_files(self, number: int) -> Tuple[bool, List[Dict[str, Any]]]:
        """Get the list of changed files for a PR.

        Args:
            number: PR number

        Returns:
            Tuple of (success, files_list or empty list)
        """
        success, stdout, stderr = await self._run_gh_command(
            ["pr", "view", str(number), "--json", "files"]
        )

        if success:
            try:
                data = json.loads(stdout)
                files = data.get("files", [])
                return True, files
            except json.JSONDecodeError:
                return False, []

        return False, []

    def invalidate_cache(self) -> None:
        """Invalidate all caches."""
        self._pr_list_cache = None
        self._pr_detail_cache.clear()
        self._diff_cache.clear()

    def get_filter_counts(self, prs: List[PRItem]) -> Dict[FilterMode, int]:
        """Get counts for each filter mode.

        Args:
            prs: List of all PRs

        Returns:
            Dict mapping filter mode to count
        """
        return {
            FilterMode.ALL: len(prs),
            FilterMode.MINE: len(
                [pr for pr in prs if pr.author == self._current_user]
            ),
            FilterMode.NEEDS_REVIEW: len(
                [
                    pr
                    for pr in prs
                    if pr.review_decision
                    in (ReviewDecision.REVIEW_REQUIRED, ReviewDecision.CHANGES_REQUESTED)
                    and not pr.is_draft
                ]
            ),
            FilterMode.DRAFTS: len([pr for pr in prs if pr.is_draft]),
            FilterMode.CONFLICTS: len(
                [pr for pr in prs if pr.mergeable == MergeableState.CONFLICTING]
            ),
            FilterMode.READY: len(
                [
                    pr
                    for pr in prs
                    if pr.review_decision == ReviewDecision.APPROVED
                    and pr.checks_status == ChecksStatus.PASSING
                    and pr.mergeable == MergeableState.MERGEABLE
                    and not pr.is_draft
                ]
            ),
        }


# Singleton instance
_github_service: Optional[GitHubService] = None


def get_github_service() -> GitHubService:
    """Get the singleton GitHubService instance."""
    global _github_service
    if _github_service is None:
        _github_service = GitHubService()
    return _github_service
