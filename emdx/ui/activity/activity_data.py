"""Activity data loading — flat list of documents.

Loads recent documents (excluding superseded) and sorts by timestamp descending.
"""

import asyncio
import logging
from datetime import datetime

from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    DocumentItem,
)

logger = logging.getLogger(__name__)

try:
    from emdx.database import documents as doc_svc

    HAS_DOCS = True
except ImportError:
    doc_svc = None  # type: ignore[assignment]
    HAS_DOCS = False


class ActivityDataLoader:
    """Loads activity data from DB and returns typed ActivityItem instances."""

    async def load_all(
        self,
        doc_type_filter: str = "all",
    ) -> list[ActivityItem]:
        """Load all documents and sort by timestamp descending.

        The DB work is synchronous SQLite; run it in a thread so the awaiting
        TUI event loop isn't blocked for the duration of the queries.

        Args:
            doc_type_filter: Filter documents by type: "user", "wiki", or "all".

        Returns:
            Sorted list of document items.
        """
        return await asyncio.to_thread(self._load_all_sync, doc_type_filter)

    def _load_all_sync(self, doc_type_filter: str = "all") -> list[ActivityItem]:
        docs: list[ActivityItem] = []
        if HAS_DOCS:
            docs = self._load_documents(doc_type_filter=doc_type_filter)

        docs.sort(key=lambda item: -item.timestamp.timestamp())
        return docs

    def _load_documents(self, doc_type_filter: str = "all") -> list[ActivityItem]:
        """Load recent documents (top-level only, superseded are hidden).

        Args:
            doc_type_filter: Filter by doc_type: "user", "wiki", or "all".
        """
        items: list[ActivityItem] = []

        try:
            # list_recent_documents already filters parent_id IS NULL
            docs = doc_svc.list_recent_documents(limit=100, days=7)
        except Exception as e:
            logger.error(f"Error listing recent documents: {e}", exc_info=True)
            return items

        # Bulk-load tags for all docs in a single query (avoids N+1)
        doc_tags: dict[int, list[str]] = {}
        try:
            from emdx.models.tags import get_tags_for_documents

            doc_tags = get_tags_for_documents([doc.id for doc in docs])
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Error bulk-loading tags: {e}")

        for doc in docs:
            try:
                doc_id = doc.id
                created = doc.created_at
                title = doc.title
                doc_type = doc.doc_type or "user"

                # Apply doc_type filter
                if doc_type_filter != "all" and doc_type != doc_type_filter:
                    continue

                # Compute word count from content
                content = doc.content
                word_count = len(content.split()) if content else 0

                item = DocumentItem(
                    item_id=doc_id,
                    title=title or "Untitled",
                    status="completed",
                    timestamp=parse_datetime(created) or datetime.now(),
                    doc_id=doc_id,
                    doc_type=doc_type,
                    project=doc.project or "",
                    tags=doc_tags.get(doc_id),
                    access_count=doc.access_count or 0,
                    word_count=word_count,
                    updated_at=parse_datetime(doc.updated_at),
                    accessed_at=parse_datetime(doc.accessed_at),
                    parent_id=doc.parent_id,
                )

                items.append(item)

            except Exception as e:
                logger.error(
                    f"Error loading document {doc.id}: {e}",
                    exc_info=True,
                )

        return items
