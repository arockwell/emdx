"""
Presenter for DocumentBrowser widget (STUB MODULE).

This module was deleted in PR #300 but is still imported by document_browser.py.
This is a stub implementation that provides the interface without full implementation.

The original presenter handled:
- Loading documents from database with pagination
- Search/filter logic
- Tag operations
- Document CRUD operations
- Hierarchy navigation (expand/collapse children)
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from emdx.services.document_service import (
    count_documents,
    delete_document,
    get_children_count,
    get_document,
    save_document,
    update_document,
)
from emdx.services.document_service import (
    list_documents as db_list_documents,
)
from emdx.services.tag_service import (
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
        on_detail_update: Callable[[DocumentDetailVM], Awaitable[None]] | None = None,
    ):
        """Initialize the presenter."""
        self.on_list_update = on_list_update
        self.on_detail_update = on_detail_update

        # Internal state
        self._documents: list[DocumentListItem] = []
        self._filtered_documents: list[DocumentListItem] = []
        self._search_query: str = ""
        self._total_count: int = 0
        self._current_offset: int = 0
        self._has_more: bool = False
        self._loading_more: bool = False
        self._expanded_docs: set[int] = set()
        self._tags_cache: dict[int, list[str]] = {}
        self._tags_cache_max: int = 200  # Limit tags cache size
        self._doc_cache: dict[int, dict[str, Any]] = {}
        self._doc_cache_max: int = 50

    def _create_list_vm(self) -> DocumentListVM:
        """Create current list ViewModel."""
        doc_count = len(self._filtered_documents)
        if self._has_more:
            status_text = (
                f"{doc_count}/{self._total_count} docs "
                "(scroll for more)"
            )
        else:
            status_text = f"{doc_count}/{self._total_count} docs"

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

    def _update_tags_cache(self, tags_dict: dict[int, list[str]]) -> None:
        """Update tags cache with eviction when size limit exceeded.

        Uses FIFO eviction to keep the cache bounded.
        """
        for doc_id, tags in tags_dict.items():
            # Evict oldest entries if at capacity
            while len(self._tags_cache) >= self._tags_cache_max:
                oldest_key = next(iter(self._tags_cache))
                del self._tags_cache[oldest_key]
            self._tags_cache[doc_id] = tags

    def _raw_doc_to_view_model(
        self,
        doc: dict[str, Any],
        tags: list[str],
        has_children: bool,
        depth: int = 0,
    ) -> DocumentListItem:
        """Convert a raw document dict to a DocumentListItem."""
        tags_display = " ".join(tags[:3]).ljust(8)
        title_width = max(40, 74 - (depth * 2))
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
            relationship=doc.get("relationship"),
        )

    async def load_documents(
        self, limit: int = 100, offset: int = 0, append: bool = False
    ) -> None:
        """Load documents from database with pagination."""
        try:
            if not append:
                self._total_count = count_documents(
                    parent_id=None,
                )

            raw_docs = db_list_documents(
                limit=limit,
                offset=offset,
                parent_id=None,
            )

            doc_ids = [doc["id"] for doc in raw_docs]
            all_tags = get_tags_for_documents(doc_ids) if doc_ids else {}
            self._update_tags_cache(all_tags)

            children_counts = get_children_count(doc_ids)

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

            if append:
                self._documents.extend(new_items)
            else:
                self._documents = new_items

            self._filtered_documents = self._documents[:]
            self._current_offset = offset + len(raw_docs)
            self._has_more = len(raw_docs) == limit

            await self.on_list_update(self._create_list_vm())

        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            raise

    async def _load_children(
        self, parent_id: int, parent_depth: int
    ) -> list[DocumentListItem]:
        """Load children of a document."""
        try:
            raw_docs = db_list_documents(
                parent_id=parent_id,
            )

            doc_ids = [doc["id"] for doc in raw_docs]
            all_tags = get_tags_for_documents(doc_ids) if doc_ids else {}
            self._update_tags_cache(all_tags)

            children_counts = get_children_count(doc_ids)

            items = []
            for doc in raw_docs:
                doc_tags = all_tags.get(doc["id"], [])
                has_children = children_counts.get(doc["id"], 0) > 0

                item = self._raw_doc_to_view_model(
                    doc=doc,
                    tags=doc_tags,
                    has_children=has_children,
                    depth=parent_depth + 1,
                )
                items.append(item)

            return items

        except Exception as e:
            logger.error(f"Error loading children for doc {parent_id}: {e}")
            return []

    async def expand_document(self, doc_id: int) -> bool:
        """Expand a document to show its children."""
        if doc_id in self._expanded_docs:
            return True

        parent_idx = None
        parent_depth = 0
        for i, doc in enumerate(self._filtered_documents):
            if doc.id == doc_id:
                parent_idx = i
                parent_depth = doc.depth
                break

        if parent_idx is None:
            return False

        children = await self._load_children(doc_id, parent_depth)
        if not children:
            return False

        self._expanded_docs.add(doc_id)

        insert_pos = parent_idx + 1
        for child in children:
            self._filtered_documents.insert(insert_pos, child)
            insert_pos += 1

        await self.on_list_update(self._create_list_vm())
        return True

    async def collapse_document(self, doc_id: int) -> bool:
        """Collapse a document to hide its children."""
        if doc_id not in self._expanded_docs:
            return True

        self._expanded_docs.discard(doc_id)

        to_remove = []
        for i, doc in enumerate(self._filtered_documents):
            if doc.parent_id == doc_id or self._is_descendant_of(doc, doc_id):
                to_remove.append(i)
                if doc.id in self._expanded_docs:
                    self._expanded_docs.discard(doc.id)

        for idx in reversed(to_remove):
            self._filtered_documents.pop(idx)

        await self.on_list_update(self._create_list_vm())
        return True

    def _is_descendant_of(self, doc: DocumentListItem, ancestor_id: int) -> bool:
        """Check if a document is a descendant of another."""
        current = doc
        seen = set()
        while current.parent_id is not None:
            if current.parent_id in seen:
                break
            seen.add(current.parent_id)
            if current.parent_id == ancestor_id:
                return True
            parent = next(
                (d for d in self._filtered_documents if d.id == current.parent_id),
                None,
            )
            if parent is None:
                break
            current = parent
        return False

    async def toggle_expand(self, doc_id: int) -> bool:
        """Toggle expand/collapse state of a document."""
        if doc_id in self._expanded_docs:
            return await self.collapse_document(doc_id)
        else:
            return await self.expand_document(doc_id)

    def is_expanded(self, doc_id: int) -> bool:
        """Check if a document is expanded."""
        return doc_id in self._expanded_docs

    async def load_more_documents(self) -> None:
        """Load more documents for pagination."""
        if self._loading_more or not self._has_more:
            return

        self._loading_more = True
        try:
            await self.load_documents(
                limit=100,
                offset=self._current_offset,
                append=True,
            )
        finally:
            self._loading_more = False

    async def apply_search(self, query: str) -> None:
        """Apply a search filter to the document list."""
        self._search_query = query
        self._expanded_docs.clear()

        if not query.strip():
            await self.load_documents()
            return

        try:
            from emdx.services.document_service import search_documents
            raw_docs = search_documents(query, limit=100)

            doc_ids = [doc["id"] for doc in raw_docs]
            all_tags = get_tags_for_documents(doc_ids) if doc_ids else {}
            self._update_tags_cache(all_tags)

            children_counts = get_children_count(doc_ids)

            self._documents = []
            for doc in raw_docs:
                doc_tags = all_tags.get(doc["id"], [])
                has_children = children_counts.get(doc["id"], 0) > 0

                item = self._raw_doc_to_view_model(
                    doc=doc,
                    tags=doc_tags,
                    has_children=has_children,
                    depth=0,
                )
                self._documents.append(item)

            self._filtered_documents = self._documents[:]
            self._total_count = len(self._documents)
            self._has_more = False

            await self.on_list_update(self._create_list_vm())

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise

    async def search(self, query: str) -> None:
        """Alias for apply_search for backward compatibility."""
        await self.apply_search(query)

    async def clear_search(self) -> None:
        """Clear the search filter."""
        self._search_query = ""
        await self.load_documents()

    async def delete_document(self, doc_id: int, hard_delete: bool = False) -> bool:
        """Delete a document."""
        try:
            success = delete_document(doc_id, hard_delete=hard_delete)
            if success:
                self._filtered_documents = [
                    d for d in self._filtered_documents if d.id != doc_id
                ]
                self._documents = [d for d in self._documents if d.id != doc_id]
                self._total_count = max(0, self._total_count - 1)
                await self.on_list_update(self._create_list_vm())
            return success
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False

    async def add_tags(self, doc_id: int, tags: list[str]) -> None:
        """Add tags to a document."""
        try:
            add_tags_to_document(doc_id, tags)
            new_tags = self._tags_cache.get(doc_id, []) + tags
            self._update_tags_cache({doc_id: list(set(new_tags))})

            for doc in self._filtered_documents:
                if doc.id == doc_id:
                    doc.tags = self._tags_cache[doc_id]
                    doc.tags_display = " ".join(doc.tags[:3]).ljust(8)
                    break

            await self.on_list_update(self._create_list_vm())
        except Exception as e:
            logger.error(f"Error adding tags to document {doc_id}: {e}")

    async def remove_tags(self, doc_id: int, tags: list[str]) -> None:
        """Remove tags from a document."""
        try:
            remove_tags_from_document(doc_id, tags)
            current_tags = self._tags_cache.get(doc_id, [])
            self._update_tags_cache({doc_id: [t for t in current_tags if t not in tags]})

            for doc in self._filtered_documents:
                if doc.id == doc_id:
                    doc.tags = self._tags_cache[doc_id]
                    doc.tags_display = " ".join(doc.tags[:3]).ljust(8)
                    break

            await self.on_list_update(self._create_list_vm())
        except Exception as e:
            logger.error(f"Error removing tags from document {doc_id}: {e}")

    def get_document_detail(self, doc_id: int) -> DocumentDetailVM | None:
        """Get full document details for the detail panel."""
        try:
            if doc_id in self._doc_cache:
                doc = self._doc_cache[doc_id]
            else:
                doc = get_document(doc_id)
                if doc is None:
                    return None

                if len(self._doc_cache) >= self._doc_cache_max:
                    oldest_key = next(iter(self._doc_cache))
                    del self._doc_cache[oldest_key]
                self._doc_cache[doc_id] = doc

            tags = self._tags_cache.get(doc_id, [])
            content = doc.get("content", "")

            return DocumentDetailVM(
                id=doc["id"],
                title=doc["title"],
                content=content,
                project=doc.get("project", "default"),
                tags=tags,
                tags_formatted=format_tags(tags),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
                accessed_at=doc.get("accessed_at"),
                access_count=doc.get("access_count", 0),
                word_count=len(content.split()),
                char_count=len(content),
                line_count=content.count("\n") + 1,
            )
        except Exception as e:
            logger.error(f"Error getting document detail for {doc_id}: {e}")
            return None

    async def save_new_document(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> int:
        """Save a new document."""
        project = get_git_project()
        doc_id = save_document(title=title, content=content, project=project)

        if tags:
            add_tags_to_document(doc_id, tags)

        await self.load_documents()
        return doc_id

    async def update_existing_document(
        self,
        doc_id: int,
        title: str | None = None,
        content: str | None = None,
    ) -> bool:
        """Update an existing document."""
        try:
            updates = {}
            if title is not None:
                updates["title"] = title
            if content is not None:
                updates["content"] = content

            if updates:
                update_document(doc_id, **updates)
                if doc_id in self._doc_cache:
                    del self._doc_cache[doc_id]
                await self.load_documents()
            return True
        except Exception as e:
            logger.error(f"Error updating document {doc_id}: {e}")
            return False

    def get_document_at_index(self, index: int) -> DocumentListItem | None:
        """Get document at the given index in the filtered list."""
        if 0 <= index < len(self._filtered_documents):
            return self._filtered_documents[index]
        return None

    def get_parent_document(self, doc: DocumentListItem) -> DocumentListItem | None:
        """Get the parent document of a given document."""
        if doc.parent_id is None:
            return None
        return next(
            (d for d in self._filtered_documents if d.id == doc.parent_id),
            None,
        )

    def should_load_more(self, current_row: int, buffer: int = 20) -> bool:
        """Check if we should load more documents based on scroll position."""
        if not self._has_more or self._loading_more:
            return False
        return current_row >= len(self._filtered_documents) - buffer

    @property
    def has_more(self) -> bool:
        """Whether there are more documents to load."""
        return self._has_more

    @property
    def filtered_count(self) -> int:
        """Number of documents after filtering."""
        return len(self._filtered_documents)
