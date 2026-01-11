"""
Presenter for DocumentBrowser widget.

This presenter handles business logic for document browsing:
- Loading documents from database with pagination
- Search/filter logic
- Tag operations
- Document CRUD operations
- Hierarchy navigation (expand/collapse children)

The presenter transforms raw database records into ViewModels
suitable for display.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from emdx.database import db
from emdx.database.documents import (
    count_documents,
    get_children_count,
    list_documents as db_list_documents,
)
from emdx.models.documents import (
    delete_document,
    get_document,
    save_document,
    update_document,
)
from emdx.models.tags import (
    add_tags_to_document,
    get_tags_for_documents,
    remove_tags_from_document,
)
from emdx.ui.formatting import format_tags, truncate_emoji_safe
from emdx.utils.git import get_git_project

from ..viewmodels import DocumentDetailVM, DocumentListItem, DocumentListVM

logger = logging.getLogger(__name__)


class DocumentBrowserPresenter:
    """Presenter for document browser business logic."""

    def __init__(
        self,
        on_list_update: Callable[[DocumentListVM], Awaitable[None]],
        on_detail_update: Optional[Callable[[DocumentDetailVM], Awaitable[None]]] = None,
    ):
        """Initialize the presenter.

        Args:
            on_list_update: Callback when the document list changes
            on_detail_update: Optional callback when document detail changes
        """
        self.on_list_update = on_list_update
        self.on_detail_update = on_detail_update

        # Internal state
        self._documents: List[DocumentListItem] = []
        self._filtered_documents: List[DocumentListItem] = []
        self._search_query: str = ""
        self._total_count: int = 0
        self._current_offset: int = 0
        self._has_more: bool = False
        self._loading_more: bool = False

        # Hierarchy state
        self._expanded_docs: Set[int] = set()  # Set of expanded parent doc IDs
        self._include_archived: bool = False  # Whether to show archived docs

        # Cache for tags (loaded in batch with documents)
        self._tags_cache: Dict[int, List[str]] = {}

        # LRU cache for full document content
        self._doc_cache: Dict[int, Dict[str, Any]] = {}
        self._doc_cache_max: int = 50

    def _create_list_vm(self) -> DocumentListVM:
        """Create current list ViewModel."""
        # Generate status text
        doc_count = len(self._filtered_documents)
        archived_indicator = " [+archived]" if self._include_archived else ""
        if self._has_more:
            status_text = (
                f"{doc_count}/{self._total_count} docs{archived_indicator} "
                "(scroll for more)"
            )
        else:
            status_text = f"{doc_count}/{self._total_count} docs{archived_indicator}"

        return DocumentListVM(
            documents=self._documents,
            filtered_documents=self._filtered_documents,
            search_query=self._search_query,
            total_count=self._total_count,
            filtered_count=len(self._filtered_documents),
            current_offset=self._current_offset,
            has_more=self._has_more,
            status_text=status_text,
        )

    def _raw_doc_to_view_model(
        self,
        doc: Dict[str, Any],
        tags: List[str],
        has_children: bool,
        depth: int = 0,
    ) -> DocumentListItem:
        """Convert a raw document dict to a DocumentListItem.

        Args:
            doc: Raw document dictionary from database
            tags: List of tags for this document
            has_children: Whether this document has children
            depth: Hierarchy depth (0 = top level)

        Returns:
            DocumentListItem view model
        """
        tags_display = " ".join(tags[:3]).ljust(8)

        # Calculate available title width based on depth
        # Base width is 74, reduce by 2 chars per depth level for tree indent
        title_width = max(40, 74 - (depth * 2))

        # Truncate title for display
        title, was_truncated = truncate_emoji_safe(doc["title"], title_width)
        if was_truncated:
            title += "..."

        return DocumentListItem(
            id=doc["id"],
            title=title,
            tags=tags,
            tags_display=tags_display,
            project=doc["project"] if doc["project"] else "default",
            access_count=doc["access_count"] or 0,
            created_at=doc["created_at"],
            accessed_at=doc.get("accessed_at"),
            parent_id=doc.get("parent_id"),
            has_children=has_children,
            depth=depth,
            is_archived=doc.get("archived_at") is not None,
            relationship=doc.get("relationship"),
        )

    async def load_documents(
        self, limit: int = 100, offset: int = 0, append: bool = False
    ) -> None:
        """Load documents from database with pagination.

        Loads only top-level documents initially. Children are loaded
        on-demand when a parent is expanded.

        Args:
            limit: Number of documents to fetch
            offset: Starting offset for pagination
            append: If True, append to existing docs instead of replacing
        """
        try:
            # Get total count for status display (top-level only by default)
            if not append:
                self._total_count = count_documents(
                    include_archived=self._include_archived,
                    parent_id=None,  # Top-level only
                )

            # Fetch paginated top-level documents
            raw_docs = db_list_documents(
                limit=limit,
                offset=offset,
                include_archived=self._include_archived,
                parent_id=None,  # Top-level only
            )

            # Batch load tags for efficiency
            doc_ids = [doc["id"] for doc in raw_docs]
            all_tags = get_tags_for_documents(doc_ids) if doc_ids else {}
            self._tags_cache.update(all_tags)

            # Batch check for children
            children_counts = get_children_count(
                doc_ids, include_archived=self._include_archived
            )

            # Convert to ViewModels
            new_items = []
            for doc in raw_docs:
                doc_tags = all_tags.get(doc["id"], [])
                has_children = children_counts.get(doc["id"], 0) > 0

                item = self._raw_doc_to_view_model(
                    doc=doc,
                    tags=doc_tags,
                    has_children=has_children,
                    depth=0,
                )
                new_items.append(item)

                # If this doc is expanded, load its children
                if doc["id"] in self._expanded_docs:
                    children = await self._load_children(doc["id"], depth=1)
                    new_items.extend(children)

            if append:
                self._documents = self._documents + new_items
            else:
                self._documents = new_items

            self._filtered_documents = self._documents
            self._current_offset = offset + len(raw_docs)
            self._has_more = len(raw_docs) == limit

            logger.info(
                f"Loaded {len(new_items)} documents "
                f"(total loaded: {len(self._documents)}, "
                f"total available: {self._total_count})"
            )

            # Notify view
            await self.on_list_update(self._create_list_vm())

        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _load_children(
        self, parent_id: int, depth: int, max_depth: int = 10
    ) -> List[DocumentListItem]:
        """Load children of a document recursively.

        Args:
            parent_id: Parent document ID
            depth: Current depth level
            max_depth: Maximum depth to prevent infinite recursion

        Returns:
            List of child DocumentListItem objects
        """
        if depth > max_depth:
            return []

        # Load children from database
        raw_children = db_list_documents(
            parent_id=parent_id,
            include_archived=self._include_archived,
            limit=100,  # Children are typically limited
        )

        # Batch load tags
        child_ids = [doc["id"] for doc in raw_children]
        if child_ids:
            child_tags = get_tags_for_documents(child_ids)
            self._tags_cache.update(child_tags)
            children_counts = get_children_count(
                child_ids, include_archived=self._include_archived
            )
        else:
            child_tags = {}
            children_counts = {}

        items = []
        for doc in raw_children:
            doc_tags = child_tags.get(doc["id"], [])
            has_children = children_counts.get(doc["id"], 0) > 0

            item = self._raw_doc_to_view_model(
                doc=doc,
                tags=doc_tags,
                has_children=has_children,
                depth=depth,
            )
            items.append(item)

            # Recursively load if this child is also expanded
            if doc["id"] in self._expanded_docs:
                grandchildren = await self._load_children(
                    doc["id"], depth + 1, max_depth
                )
                items.extend(grandchildren)

        return items

    async def expand_document(self, doc_id: int) -> bool:
        """Expand a document to show its children.

        Args:
            doc_id: Document ID to expand

        Returns:
            True if expansion was successful (doc had children)
        """
        # Find the document in our list
        doc_item = None
        for item in self._documents:
            if item.id == doc_id:
                doc_item = item
                break

        if doc_item is None or not doc_item.has_children:
            return False

        if doc_id in self._expanded_docs:
            return True  # Already expanded

        # Mark as expanded and reload
        self._expanded_docs.add(doc_id)
        await self.load_documents()
        return True

    async def collapse_document(self, doc_id: int) -> bool:
        """Collapse a document to hide its children.

        Args:
            doc_id: Document ID to collapse

        Returns:
            True if collapse was successful
        """
        if doc_id not in self._expanded_docs:
            return False

        # Remove from expanded set (and all descendants)
        self._expanded_docs.discard(doc_id)

        # Also remove any expanded children of this document
        children_to_remove = set()
        for expanded_id in self._expanded_docs:
            # Check if this expanded doc is a descendant
            for doc in self._documents:
                if doc.id == expanded_id and self._is_descendant_of(doc, doc_id):
                    children_to_remove.add(expanded_id)

        self._expanded_docs -= children_to_remove

        # Reload to update the list
        await self.load_documents()
        return True

    def _is_descendant_of(self, doc: DocumentListItem, ancestor_id: int) -> bool:
        """Check if a document is a descendant of another.

        Args:
            doc: Document to check
            ancestor_id: Potential ancestor ID

        Returns:
            True if doc is a descendant of ancestor_id
        """
        current_id = doc.parent_id
        visited = set()
        while current_id is not None and current_id not in visited:
            visited.add(current_id)
            if current_id == ancestor_id:
                return True
            # Find parent in our list
            parent = next((d for d in self._documents if d.id == current_id), None)
            if parent is None:
                break
            current_id = parent.parent_id
        return False

    async def toggle_expand(self, doc_id: int) -> bool:
        """Toggle expansion state of a document.

        Args:
            doc_id: Document ID to toggle

        Returns:
            True if toggle was successful
        """
        if doc_id in self._expanded_docs:
            return await self.collapse_document(doc_id)
        else:
            return await self.expand_document(doc_id)

    async def toggle_archived(self) -> None:
        """Toggle display of archived documents."""
        self._include_archived = not self._include_archived
        await self.load_documents()

    def is_expanded(self, doc_id: int) -> bool:
        """Check if a document is expanded.

        Args:
            doc_id: Document ID to check

        Returns:
            True if the document is expanded
        """
        return doc_id in self._expanded_docs

    @property
    def include_archived(self) -> bool:
        """Whether archived documents are being shown."""
        return self._include_archived

    async def load_more_documents(self) -> None:
        """Load more documents when user scrolls near the end."""
        if self._has_more and not self._loading_more:
            self._loading_more = True
            try:
                await self.load_documents(
                    limit=100, offset=self._current_offset, append=True
                )
            finally:
                self._loading_more = False

    async def apply_search(self, query: str) -> None:
        """Apply search filter to documents.

        Args:
            query: Search query string
        """
        self._search_query = query
        if not query:
            self._filtered_documents = self._documents
        else:
            # Simple title search
            self._filtered_documents = [
                doc
                for doc in self._documents
                if query.lower() in doc.title.lower()
            ]

        await self.on_list_update(self._create_list_vm())

    async def clear_search(self) -> None:
        """Clear the current search filter."""
        await self.apply_search("")

    async def delete_document(self, doc_id: int, hard_delete: bool = False) -> bool:
        """Delete a document.

        Args:
            doc_id: Document ID to delete
            hard_delete: If True, permanently delete; otherwise soft delete

        Returns:
            True if deletion was successful
        """
        try:
            delete_document(str(doc_id), hard_delete=hard_delete)
            # Reload documents
            await self.load_documents()
            return True
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False

    async def add_tags(self, doc_id: int, tags: List[str]) -> None:
        """Add tags to a document.

        Args:
            doc_id: Document ID
            tags: List of tags to add
        """
        if tags:
            add_tags_to_document(doc_id, tags)
            # Invalidate cache and refresh
            if doc_id in self._tags_cache:
                del self._tags_cache[doc_id]
            await self.load_documents()

    async def remove_tags(self, doc_id: int, tags: List[str]) -> None:
        """Remove tags from a document.

        Args:
            doc_id: Document ID
            tags: List of tags to remove
        """
        if tags:
            remove_tags_from_document(doc_id, tags)
            # Invalidate cache and refresh
            if doc_id in self._tags_cache:
                del self._tags_cache[doc_id]
            await self.load_documents()

    def get_document_detail(self, doc_id: int) -> Optional[DocumentDetailVM]:
        """Get full document details for preview.

        Args:
            doc_id: Document ID

        Returns:
            DocumentDetailVM or None if not found
        """
        # Check cache first
        if doc_id in self._doc_cache:
            full_doc = self._doc_cache[doc_id]
        else:
            full_doc = get_document(str(doc_id))
            if full_doc:
                # Add to cache, evict oldest if needed
                if len(self._doc_cache) >= self._doc_cache_max:
                    oldest_key = next(iter(self._doc_cache))
                    del self._doc_cache[oldest_key]
                self._doc_cache[doc_id] = full_doc

        if not full_doc:
            return None

        # Get tags from cache
        tags = self._tags_cache.get(doc_id, [])

        # Calculate content stats
        content = full_doc.get("content", "")
        word_count = len(content.split()) if content else 0
        char_count = len(content) if content else 0
        line_count = content.count("\n") + 1 if content else 0

        return DocumentDetailVM(
            id=full_doc["id"],
            title=full_doc["title"],
            content=content,
            project=full_doc.get("project", "default"),
            tags=tags,
            tags_formatted=format_tags(tags) if tags else "",
            created_at=full_doc.get("created_at"),
            updated_at=full_doc.get("updated_at"),
            accessed_at=full_doc.get("accessed_at"),
            access_count=full_doc.get("access_count", 0),
            word_count=word_count,
            char_count=char_count,
            line_count=line_count,
        )

    async def save_new_document(
        self, title: str, content: str, project: Optional[str] = None
    ) -> Optional[int]:
        """Save a new document.

        Args:
            title: Document title
            content: Document content
            project: Optional project name (auto-detects from git if not provided)

        Returns:
            New document ID or None if failed
        """
        if not title:
            return None

        try:
            proj = project or get_git_project() or "default"
            formatted_content = f"# {title}\n\n{content}"
            doc_id = save_document(
                title=title, content=formatted_content, project=proj
            )
            logger.info(f"Created new document with ID: {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Error saving new document: {e}")
            return None

    async def update_existing_document(
        self, doc_id: int, title: str, content: str
    ) -> bool:
        """Update an existing document.

        Args:
            doc_id: Document ID to update
            title: New title
            content: New content

        Returns:
            True if update was successful
        """
        if not title:
            return False

        try:
            formatted_content = f"# {title}\n\n{content}"
            update_document(str(doc_id), title=title, content=formatted_content)
            logger.info(f"Updated document ID: {doc_id}")

            # Invalidate cache
            if doc_id in self._doc_cache:
                del self._doc_cache[doc_id]

            return True
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return False

    def get_document_at_index(self, index: int) -> Optional[DocumentListItem]:
        """Get document at the given index in filtered list.

        Args:
            index: Row index

        Returns:
            DocumentListItem or None if out of range
        """
        if 0 <= index < len(self._filtered_documents):
            return self._filtered_documents[index]
        return None

    def get_parent_document(self, doc: DocumentListItem) -> Optional[DocumentListItem]:
        """Get the parent document of a given document.

        Args:
            doc: Document to find parent for

        Returns:
            Parent DocumentListItem or None if no parent
        """
        if doc.parent_id is None:
            return None
        return next((d for d in self._documents if d.id == doc.parent_id), None)

    def should_load_more(self, current_row: int, buffer: int = 20) -> bool:
        """Check if more documents should be loaded.

        Args:
            current_row: Current cursor row
            buffer: Number of rows from end to trigger load

        Returns:
            True if more documents should be loaded
        """
        return (
            self._has_more
            and not self._loading_more
            and current_row >= len(self._filtered_documents) - buffer
        )

    @property
    def has_more(self) -> bool:
        """Check if more documents are available."""
        return self._has_more

    @property
    def filtered_count(self) -> int:
        """Get count of filtered documents."""
        return len(self._filtered_documents)
