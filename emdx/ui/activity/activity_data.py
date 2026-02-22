"""Activity data loading — flat list of documents.

Loads recent documents (excluding superseded) and sorts by timestamp descending.
"""

import logging
from datetime import datetime

from emdx.utils.datetime_utils import parse_datetime

from .activity_items import (
    ActivityItem,
    DocumentItem,
)

logger = logging.getLogger(__name__)

try:
    from emdx.services import document_service as doc_svc

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

        Args:
            doc_type_filter: Filter documents by type: "user", "wiki", or "all".

        Returns:
            Sorted list of document items.
        """
        docs: list[ActivityItem] = []
        if HAS_DOCS:
            docs = await self._load_documents(doc_type_filter=doc_type_filter)

        docs.sort(key=lambda item: -item.timestamp.timestamp())
        return docs

    async def _load_documents(self, doc_type_filter: str = "all") -> list[ActivityItem]:
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

        for doc in docs:
            try:
                doc_id = doc["id"]
                created = doc.get("created_at")
                title = doc.get("title", "")
                doc_type = doc.get("doc_type", "user") or "user"

                # Apply doc_type filter
                if doc_type_filter != "all" and doc_type != doc_type_filter:
                    continue

                item = DocumentItem(
                    item_id=doc_id,
                    title=title or "Untitled",
                    status="completed",
                    timestamp=parse_datetime(created) or datetime.now(),
                    doc_id=doc_id,
                    doc_type=doc_type,
                )

                items.append(item)

            except Exception as e:
                logger.error(
                    f"Error loading document {doc.get('id', '?')}: {e}",
                    exc_info=True,
                )

        return items
