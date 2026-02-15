"""
Presenter for the command palette.

Handles search logic, result ranking, and action dispatch.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .palette_commands import CommandContext, PaletteCommand, get_command_registry

logger = logging.getLogger(__name__)

class ResultType(Enum):
    """Types of results in the palette."""

    DOCUMENT = "document"
    COMMAND = "command"
    SCREEN = "screen"
    TAG = "tag"
    RECENT = "recent"

@dataclass
class PaletteResultItem:
    """A single result in the command palette."""

    id: str  # Unique identifier
    type: ResultType
    title: str  # Primary display text
    subtitle: str  # Secondary info (project, description)
    icon: str  # Emoji or symbol
    score: float  # Relevance score for sorting
    data: dict[str, Any] = field(default_factory=dict)  # Type-specific payload

@dataclass
class PaletteState:
    """Current state of the palette."""

    query: str = ""
    results: list[PaletteResultItem] = field(default_factory=list)
    selected_index: int = 0
    is_searching: bool = False
    recent_items: list[PaletteResultItem] = field(default_factory=list)

class PalettePresenter:
    """
    Handles command palette business logic.

    Routes queries based on prefix:
    - (none) → Document search (fuzzy title + FTS)
    - > → Commands
    - @ → Tag filter
    - # → Document ID or semantic search
    - : → Screen navigation
    """

    def __init__(
        self,
        on_state_update: Callable[[PaletteState], None] | None = None,
        context: CommandContext | None = None,
    ):
        self.on_state_update = on_state_update
        self.context = context or CommandContext.GLOBAL
        self._state = PaletteState()
        self._command_registry = get_command_registry()
        self._search_service = None  # Lazy load
        self._history: list[PaletteResultItem] = []
        self._max_history = 10

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
    def state(self) -> PaletteState:
        """Get current state."""
        return self._state

    def _notify_update(self) -> None:
        """Notify listeners of state change."""
        if self.on_state_update:
            self.on_state_update(self._state)

    async def load_initial_state(self) -> None:
        """Load initial state (recent items, suggestions)."""
        self._state.recent_items = self._get_recent_items()
        self._state.results = self._state.recent_items.copy()
        self._notify_update()

    def _get_recent_items(self) -> list[PaletteResultItem]:
        """Get recent items from history and recent documents."""
        items: list[PaletteResultItem] = []

        # Add history items first
        for item in self._history:
            items.append(item)

        # Add recent documents if we have the search service
        if self.search_service:
            try:
                recent_docs = self.search_service.get_recent_documents(limit=5)
                for doc in recent_docs:
                    if not any(i.id == f"doc:{doc.doc_id}" for i in items):
                        items.append(
                            PaletteResultItem(
                                id=f"doc:{doc.doc_id}",
                                type=ResultType.RECENT,
                                title=doc.title,
                                subtitle=doc.project or "No project",
                                icon="📄",
                                score=1.0,
                                data={"doc_id": doc.doc_id},
                            )
                        )
            except Exception as e:
                logger.debug(f"Could not load recent documents: {e}")

        return items[:self._max_history]

    async def search(self, query: str) -> None:
        """
        Execute search based on query and prefix.

        Routing:
        - > → Commands
        - @ → Tags
        - # → Document ID or semantic
        - : → Navigation
        - (none) → Document search
        """
        self._state.query = query
        self._state.is_searching = True
        self._notify_update()

        query = query.strip()

        if not query:
            # Show recent items when empty
            self._state.results = self._get_recent_items()
        elif query.startswith(">"):
            # Command search
            self._state.results = self._search_commands(query[1:].strip())
        elif query.startswith("@"):
            # Tag search
            self._state.results = await self._search_tags(query[1:].strip())
        elif query.startswith("#"):
            # Document ID or semantic search
            self._state.results = await self._search_by_id_or_semantic(query[1:].strip())
        elif query.startswith(":"):
            # Navigation/screen search
            self._state.results = self._search_navigation(query[1:].strip())
        else:
            # Default: document search
            self._state.results = await self._search_documents(query)

        self._state.is_searching = False
        self._state.selected_index = 0
        self._notify_update()

    def _search_commands(self, query: str) -> list[PaletteResultItem]:
        """Search registered commands."""
        commands = self._command_registry.search(query, context=self.context, limit=10)

        return [
            PaletteResultItem(
                id=f"cmd:{cmd.id}",
                type=ResultType.COMMAND,
                title=cmd.name,
                subtitle=cmd.description,
                icon="▶",
                score=1.0,
                data={"command": cmd},
            )
            for cmd in commands
        ]

    async def _search_tags(self, query: str) -> list[PaletteResultItem]:
        """Search by tags or suggest tags."""
        if not self.search_service:
            return []

        # Parse tags from query (comma or space separated)
        tags = [t.strip() for t in query.replace(",", " ").split() if t.strip()]

        if not tags:
            # No tags yet - show popular tags as suggestions
            try:
                popular = self.search_service.get_popular_tags(limit=10)
                return [
                    PaletteResultItem(
                        id=f"tag:{tag['name']}",
                        type=ResultType.TAG,
                        title=f"@{tag['name']}",
                        subtitle=f"Used {tag['count']} times",
                        icon="🏷️",
                        score=1.0,
                        data={"tag": tag["name"]},
                    )
                    for tag in popular
                ]
            except Exception as e:
                logger.debug(f"Could not load popular tags: {e}")
                return []

        # Search documents with these tags
        try:
            from emdx.services.unified_search import SearchQuery

            search_query = SearchQuery(tags=tags, tag_mode="all", limit=10)
            results = await self.search_service.search(search_query)

            return [
                PaletteResultItem(
                    id=f"doc:{r.doc_id}",
                    type=ResultType.DOCUMENT,
                    title=r.title,
                    subtitle=f"Tags: {' '.join(r.tags[:3])}" if r.tags else r.project or "",
                    icon="📄",
                    score=r.score,
                    data={"doc_id": r.doc_id},
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Tag search failed: {e}")
            return []

    async def _search_by_id_or_semantic(self, query: str) -> list[PaletteResultItem]:
        """Search by document ID or semantic similarity."""
        if not self.search_service:
            return []

        # Check if query is a number (document ID)
        try:
            doc_id = int(query)
            result = self.search_service.get_document_by_id(doc_id)
            if result:
                return [
                    PaletteResultItem(
                        id=f"doc:{result.doc_id}",
                        type=ResultType.DOCUMENT,
                        title=result.title,
                        subtitle=f"#{result.doc_id} | {result.project or 'No project'}",
                        icon="📄",
                        score=1.0,
                        data={"doc_id": result.doc_id},
                    )
                ]
            return []
        except ValueError:
            pass

        # Check for similar: prefix
        if query.startswith("similar:"):
            try:
                doc_id = int(query[8:])
                if self.search_service.embedding_service:
                    matches = self.search_service.embedding_service.find_similar(doc_id, limit=10)
                    return [
                        PaletteResultItem(
                            id=f"doc:{m.doc_id}",
                            type=ResultType.DOCUMENT,
                            title=m.title,
                            subtitle=f"{m.similarity:.0%} similar",
                            icon="🧠",
                            score=m.similarity,
                            data={"doc_id": m.doc_id},
                        )
                        for m in matches
                    ]
            except (ValueError, Exception) as e:
                logger.debug(f"Similar search failed: {e}")
            return []

        # Otherwise, semantic search
        if self.search_service.has_embeddings():
            try:
                from emdx.services.unified_search import SearchQuery

                search_query = SearchQuery(text=query, semantic=True, limit=10)
                results = await self.search_service.search(search_query)

                return [
                    PaletteResultItem(
                        id=f"doc:{r.doc_id}",
                        type=ResultType.DOCUMENT,
                        title=r.title,
                        subtitle=f"🧠 {r.score:.0%} match",
                        icon="📄",
                        score=r.score,
                        data={"doc_id": r.doc_id},
                    )
                    for r in results
                ]
            except Exception as e:
                logger.error(f"Semantic search failed: {e}")

        return []

    def _search_navigation(self, query: str) -> list[PaletteResultItem]:
        """Search for screens/navigation targets."""
        # Filter commands to navigation category
        nav_commands = [
            cmd
            for cmd in self._command_registry.get_all(self.context)
            if cmd.category == "Navigation"
        ]

        if query:
            # Fuzzy filter
            from difflib import SequenceMatcher

            query_lower = query.lower()
            scored = []
            for cmd in nav_commands:
                name_lower = cmd.name.lower()
                score = SequenceMatcher(None, query_lower, name_lower).ratio()
                if query_lower in name_lower:
                    score += 0.5
                if score > 0.3:
                    scored.append((score, cmd))
            scored.sort(key=lambda x: -x[0])
            nav_commands = [cmd for _, cmd in scored]

        return [
            PaletteResultItem(
                id=f"nav:{cmd.id}",
                type=ResultType.SCREEN,
                title=cmd.name,
                subtitle=cmd.shortcut or "",
                icon="📂",
                score=1.0,
                data={"command": cmd},
            )
            for cmd in nav_commands[:10]
        ]

    async def _search_documents(self, query: str) -> list[PaletteResultItem]:
        """Search documents by title and content."""
        if not self.search_service:
            return []

        results: list[PaletteResultItem] = []
        seen_ids: set[int] = set()

        try:
            # Fuzzy title search first (fast)
            fuzzy_results = self.search_service.fuzzy_search_titles(query, limit=5)
            for r in fuzzy_results:
                if r.doc_id not in seen_ids:
                    results.append(
                        PaletteResultItem(
                            id=f"doc:{r.doc_id}",
                            type=ResultType.DOCUMENT,
                            title=r.title,
                            subtitle=r.project or "No project",
                            icon="📄",
                            score=r.score,
                            data={"doc_id": r.doc_id},
                        )
                    )
                    seen_ids.add(r.doc_id)
        except Exception as e:
            logger.debug(f"Fuzzy search failed: {e}")

        # FTS search for content matches
        try:
            from emdx.services.unified_search import SearchQuery

            search_query = SearchQuery(text=query, limit=10)
            fts_results = await self.search_service.search(search_query)

            for r in fts_results:
                if r.doc_id not in seen_ids:
                    results.append(
                        PaletteResultItem(
                            id=f"doc:{r.doc_id}",
                            type=ResultType.DOCUMENT,
                            title=r.title,
                            subtitle=r.snippet[:50] + "..." if r.snippet else (r.project or ""),
                            icon="📄",
                            score=r.score * 0.9,  # Slightly lower than fuzzy matches
                            data={"doc_id": r.doc_id},
                        )
                    )
                    seen_ids.add(r.doc_id)
        except Exception as e:
            logger.debug(f"FTS search failed: {e}")

        # Sort by score
        results.sort(key=lambda r: -r.score)

        return results[:10]

    def move_selection(self, delta: int) -> None:
        """Move selection up or down."""
        if not self._state.results:
            return

        new_index = self._state.selected_index + delta
        new_index = max(0, min(new_index, len(self._state.results) - 1))
        self._state.selected_index = new_index
        self._notify_update()

    def get_selected_result(self) -> PaletteResultItem | None:
        """Get the currently selected result."""
        if not self._state.results:
            return None
        if 0 <= self._state.selected_index < len(self._state.results):
            return self._state.results[self._state.selected_index]
        return None

    def add_to_history(self, item: PaletteResultItem) -> None:
        """Add an item to the history."""
        # Remove if already in history
        self._history = [h for h in self._history if h.id != item.id]
        # Add at front
        self._history.insert(0, item)
        # Trim
        self._history = self._history[: self._max_history]

    async def execute_selected(self, app) -> dict[str, Any] | None:
        """
        Execute the selected result.

        Returns action info for the caller to handle, or None if handled internally.
        """
        result = self.get_selected_result()
        if not result:
            return None

        # Add to history
        self.add_to_history(result)

        if result.type == ResultType.COMMAND:
            cmd: PaletteCommand = result.data.get("command")
            if cmd:
                return {"action": "command", "command_id": cmd.id}

        elif result.type in (ResultType.DOCUMENT, ResultType.RECENT):
            doc_id = result.data.get("doc_id")
            if doc_id:
                return {"action": "view_document", "doc_id": doc_id}

        elif result.type == ResultType.SCREEN:
            cmd: PaletteCommand = result.data.get("command")
            if cmd:
                return {"action": "command", "command_id": cmd.id}

        elif result.type == ResultType.TAG:
            tag = result.data.get("tag")
            if tag:
                return {"action": "search_tag", "tag": tag}

        return None
