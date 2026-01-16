"""
Presenter for DocumentBrowser widget.

This presenter handles business logic for document browsing:
- Loading documents from database with pagination
- Search/filter logic
- Tag operations
- Document CRUD operations

The presenter transforms raw database records into ViewModels
suitable for display.
"""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from emdx.database import (
    db,
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

        # Cache for tags (loaded in batch with documents)
        self._tags_cache: Dict[int, List[str]] = {}

        # LRU cache for full document content
        self._doc_cache: Dict[int, Dict[str, Any]] = {}
        self._doc_cache_max: int = 50

    def _create_list_vm(self) -> DocumentListVM:
        """Create current list ViewModel."""
        # Generate status text
        if self._has_more:
            status_text = f"{len(self._filtered_documents)}/{self._total_count} docs (scroll for more)"
        else:
            status_text = f"{len(self._filtered_documents)}/{self._total_count} docs"

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

    async def load_documents(
        self, limit: int = 100, offset: int = 0, append: bool = False
    ) -> None:
        """Load documents from database with pagination.

        Args:
            limit: Number of documents to fetch
            offset: Starting offset for pagination
            append: If True, append to existing docs instead of replacing
        """
        try:
            with db.get_connection() as conn:
                # Get total count for status display
                if not append:
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM documents WHERE is_deleted = 0"
                    )
                    self._total_count = cursor.fetchone()[0]

                # Fetch paginated documents
                cursor = conn.execute(
                    """
                    SELECT id, title, project, created_at, accessed_at, access_count
                    FROM documents
                    WHERE is_deleted = 0
                    ORDER BY id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )

                raw_docs = cursor.fetchall()

                # Batch load tags for efficiency
                doc_ids = [doc["id"] for doc in raw_docs]
                all_tags = get_tags_for_documents(doc_ids) if doc_ids else {}
                self._tags_cache.update(all_tags)

                # Convert to ViewModels
                new_items = []
                for doc in raw_docs:
                    doc_tags = all_tags.get(doc["id"], [])
                    tags_display = " ".join(doc_tags[:3]).ljust(8)

                    # Truncate title for display
                    title, was_truncated = truncate_emoji_safe(doc["title"], 74)
                    if was_truncated:
                        title += "..."

                    new_items.append(
                        DocumentListItem(
                            id=doc["id"],
                            title=title,
                            tags=doc_tags,
                            tags_display=tags_display,
                            project=doc["project"] if doc["project"] else "default",
                            access_count=doc["access_count"] or 0,
                            created_at=doc["created_at"],
                            accessed_at=doc["accessed_at"],
                        )
                    )

                if append:
                    self._documents = self._documents + new_items
                else:
                    self._documents = new_items

                self._filtered_documents = self._documents
                self._current_offset = offset + len(new_items)
                self._has_more = len(new_items) == limit

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
            doc_id = save_document(title=title, content=formatted_content, project=proj)
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
