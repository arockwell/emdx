"""
Presenter for the Search Screen.

Handles search logic with debouncing, mode switching, and result management.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

class SearchMode(Enum):
    """Available search modes."""

    FTS = "fts"  # Full-text search
    TAGS = "tags"  # Tag-based search
    SEMANTIC = "semantic"  # AI-powered semantic search
    COMBINED = "combined"  # FTS + semantic

@dataclass
class SearchResultItem:
    """Single search result for display."""

    doc_id: int
    title: str
    snippet: str
    tags: list[str]
    tags_display: str  # Formatted tags for display
    score: float  # Normalized 0-1
    source: str  # "fts", "tags", "semantic"
    project: str | None = None
    updated_at: str | None = None
    is_selected: bool = False  # For multi-select

@dataclass
class SearchStateVM:
    """Complete search state for the UI."""

    query: str = ""
    results: list[SearchResultItem] = field(default_factory=list)
    total_count: int = 0
    mode: SearchMode = SearchMode.FTS
    is_searching: bool = False
    search_time_ms: int = 0
    recent_docs: list[SearchResultItem] = field(default_factory=list)
    popular_tags: list[dict[str, Any]] = field(default_factory=list)
    selected_indices: set[int] = field(default_factory=set)
    active_filters: list[str] = field(default_factory=list)
    status_text: str = ""

class SearchPresenter:
    """
    Handles search screen business logic.

    Features:
    - Mode-specific debouncing (FTS: 150ms, Tags: 100ms, Semantic: 500ms)
    - Result caching
    - Multi-select support
    - Filter management
    """

    # Debounce times by mode (milliseconds) - wait for user to stop typing
    DEBOUNCE_TIMES = {
        SearchMode.FTS: 300,
        SearchMode.TAGS: 300,
        SearchMode.SEMANTIC: 500,
        SearchMode.COMBINED: 400,
    }

    # Minimum query length before searching (avoids searching on every keystroke)
    MIN_QUERY_LENGTH = 2

    def __init__(
        self,
        on_state_update: Callable[[SearchStateVM], Awaitable[None]] | None = None,
    ):
        self.on_state_update = on_state_update
        self._state = SearchStateVM()
        self._search_service = None  # Lazy load
        self._cache: dict[str, list[SearchResultItem]] = {}
        self._cache_max_size = 20

    @property
    def search_service(self):
        """Lazy load the unified search service."""
        if self._search_service is None:
            try:
                from emdx.services.unified_search import UnifiedSearchService

                self._search_service = UnifiedSearchService()
            except ImportError:
                logger.warning("UnifiedSearchService not available")
        return self._search_service

    @property
    def state(self) -> SearchStateVM:
        """Get current state."""
        return self._state

    def get_debounce_time(self, mode: SearchMode | None = None) -> int:
        """Get debounce time for the given mode in milliseconds."""
        mode = mode or self._state.mode
        return self.DEBOUNCE_TIMES.get(mode, 150)

    async def _notify_update(self) -> None:
        """Notify listeners of state change."""
        if self.on_state_update:
            await self.on_state_update(self._state)

    async def load_initial_state(self) -> None:
        """Load initial state (recent docs, popular tags)."""
        import asyncio

        if not self.search_service:
            self._state.status_text = "Search service not available"
            await self._notify_update()
            return

        try:
            # Run blocking DB calls in thread pool to avoid blocking UI
            recent, popular_tags = await asyncio.to_thread(
                self._load_initial_data_sync
            )

            self._state.recent_docs = [
                SearchResultItem(
                    doc_id=r.doc_id,
                    title=r.title,
                    snippet="",
                    tags=r.tags,
                    tags_display=" ".join(r.tags[:3]),
                    score=1.0,
                    source="recent",
                    project=r.project,
                )
                for r in recent
            ]

            self._state.popular_tags = popular_tags

            # Show recent docs when empty
            self._state.results = self._state.recent_docs.copy()
            self._state.status_text = f"{len(self._state.recent_docs)} recent documents"

            await self._notify_update()

        except Exception as e:
            logger.error(f"Error loading initial state: {e}")
            self._state.status_text = f"Error: {e}"
            await self._notify_update()

    def _load_initial_data_sync(self):
        """Synchronous helper to load initial data (runs in thread pool)."""
        recent = self.search_service.get_recent_documents(limit=10)
        popular_tags = self.search_service.get_popular_tags(limit=15)
        return recent, popular_tags

    async def search(self, query: str, mode: SearchMode | None = None) -> None:
        """
        Execute search with the given query and mode.

        Args:
            query: Search query (may include special syntax)
            mode: Override the current mode, or None to use current
        """
        import time

        if mode:
            self._state.mode = mode

        self._state.query = query

        # Don't search for very short queries (just show recent)
        query_stripped = query.strip()
        if len(query_stripped) < self.MIN_QUERY_LENGTH and not query_stripped.startswith('@') and not query_stripped.startswith('tags:'):  # noqa: E501
            self._state.results = self._state.recent_docs.copy()
            self._state.total_count = len(self._state.results)
            self._state.search_time_ms = 0
            self._state.is_searching = False
            self._state.status_text = f"Type {self.MIN_QUERY_LENGTH}+ chars to search | {len(self._state.results)} recent"  # noqa: E501
            await self._notify_update()
            return

        self._state.is_searching = True
        await self._notify_update()

        if not query_stripped:
            # Show recent docs when empty
            self._state.results = self._state.recent_docs.copy()
            self._state.total_count = len(self._state.results)
            self._state.search_time_ms = 0
            self._state.is_searching = False
            self._state.status_text = f"{len(self._state.results)} recent documents"
            await self._notify_update()
            return

        # Check cache
        cache_key = f"{self._state.mode.value}:{query}"
        if cache_key in self._cache:
            self._state.results = self._cache[cache_key]
            self._state.total_count = len(self._state.results)
            self._state.is_searching = False
            self._state.status_text = f"{len(self._state.results)} results (cached)"
            await self._notify_update()
            return

        start_time = time.time()

        try:
            results = await self._execute_search(query)
            self._state.results = results
            self._state.total_count = len(results)
            self._state.search_time_ms = int((time.time() - start_time) * 1000)

            # Cache results
            self._cache[cache_key] = results
            if len(self._cache) > self._cache_max_size:
                # Remove oldest entry
                oldest = next(iter(self._cache))
                del self._cache[oldest]

            mode_label = self._state.mode.value.upper()
            self._state.status_text = (
                f"{len(results)} results | {mode_label} | {self._state.search_time_ms}ms"
            )

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self._state.results = []
            self._state.total_count = 0
            self._state.status_text = f"Search error: {e}"

        self._state.is_searching = False
        self._state.selected_indices.clear()
        await self._notify_update()

    async def _execute_search(self, query: str) -> list[SearchResultItem]:
        """Execute the actual search based on current mode."""
        if not self.search_service:
            return []

        from emdx.services.unified_search import SearchQuery

        # Build search query based on mode
        search_query = SearchQuery(limit=50)

        # Parse query for special syntax
        parsed = self.search_service.parse_query(query)

        if self._state.mode == SearchMode.FTS:
            # Use parsed text, NOT the original query (which may contain tags: syntax)
            search_query.text = parsed.text  # May be empty if query was only tags
            search_query.tags = parsed.tags
            search_query.tag_mode = parsed.tag_mode
            search_query.created_after = parsed.created_after
            search_query.created_before = parsed.created_before
            search_query.project = parsed.project

        elif self._state.mode == SearchMode.TAGS:
            # Tag mode: parse @tag syntax or comma-separated
            if query.startswith("@"):
                tags = [t.strip().lstrip("@") for t in query.split() if t.strip()]
            else:
                tags = [t.strip() for t in query.replace(",", " ").split() if t.strip()]
            search_query.tags = tags
            search_query.tag_mode = "all"

        elif self._state.mode == SearchMode.SEMANTIC:
            search_query.text = query
            search_query.semantic = True

        elif self._state.mode == SearchMode.COMBINED:
            search_query.text = query
            search_query.semantic = True
            search_query.tags = parsed.tags
            search_query.tag_mode = parsed.tag_mode

        # Execute search
        raw_results = await self.search_service.search(search_query)

        # Convert to display items
        results = []
        for r in raw_results:
            results.append(
                SearchResultItem(
                    doc_id=r.doc_id,
                    title=r.title,
                    snippet=r.snippet[:100] + "..." if len(r.snippet) > 100 else r.snippet,
                    tags=r.tags,
                    tags_display=" ".join(r.tags[:3]) if r.tags else "",
                    score=r.score,
                    source=r.source,
                    project=r.project,
                    updated_at=r.updated_at.isoformat() if r.updated_at else None,
                )
            )

        return results

    def set_mode(self, mode: SearchMode) -> None:
        """Change the search mode."""
        self._state.mode = mode
        # Clear cache when mode changes
        self._cache.clear()

    def cycle_mode(self) -> SearchMode:
        """Cycle to the next search mode, skipping semantic if no embeddings."""
        modes = list(SearchMode)
        current_idx = modes.index(self._state.mode)

        # Try up to len(modes) times to find a valid mode
        for _ in range(len(modes)):
            next_idx = (current_idx + 1) % len(modes)
            next_mode = modes[next_idx]

            # Skip semantic modes if no embeddings available
            if next_mode in (SearchMode.SEMANTIC, SearchMode.COMBINED):
                if not self.search_service.has_embeddings():
                    current_idx = next_idx
                    continue

            self._state.mode = next_mode
            self._cache.clear()
            return self._state.mode

        # Fallback to FTS if nothing else works
        self._state.mode = SearchMode.FTS
        self._cache.clear()
        return self._state.mode

    def toggle_selection(self, index: int) -> None:
        """Toggle selection of a result at the given index."""
        if index in self._state.selected_indices:
            self._state.selected_indices.discard(index)
        else:
            self._state.selected_indices.add(index)

        # Update is_selected on items
        for i, item in enumerate(self._state.results):
            item.is_selected = i in self._state.selected_indices

    def select_all(self) -> None:
        """Select all results."""
        self._state.selected_indices = set(range(len(self._state.results)))
        for item in self._state.results:
            item.is_selected = True

    def clear_selection(self) -> None:
        """Clear all selections."""
        self._state.selected_indices.clear()
        for item in self._state.results:
            item.is_selected = False

    def get_selected_doc_ids(self) -> list[int]:
        """Get document IDs of selected results."""
        return [
            self._state.results[i].doc_id
            for i in sorted(self._state.selected_indices)
            if i < len(self._state.results)
        ]

    def get_result_at_index(self, index: int) -> SearchResultItem | None:
        """Get result at the given index."""
        if 0 <= index < len(self._state.results):
            return self._state.results[index]
        return None

    def clear_results(self) -> None:
        """Clear search results and show recent docs."""
        self._state.query = ""
        self._state.results = self._state.recent_docs.copy()
        self._state.total_count = len(self._state.results)
        self._state.selected_indices.clear()
        self._state.status_text = f"{len(self._state.results)} recent documents"
