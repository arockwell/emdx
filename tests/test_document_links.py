"""Tests for the document_links database module and link_service."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from emdx.database.document_links import (
    batch_get_link_counts,
    create_link,
    create_links_batch,
    delete_link,
    delete_links_for_document,
    get_link_count,
    get_linked_doc_ids,
    get_links_for_document,
    link_exists,
)
from emdx.database.migrations import migration_043_add_document_links


class TestMigration043:
    """Test the document_links migration."""

    def test_creates_table(self):
        conn = sqlite3.connect(":memory:")
        # Need documents table for foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE documents ("
            "id INTEGER PRIMARY KEY, title TEXT, content TEXT, "
            "is_deleted INTEGER DEFAULT 0)"
        )
        migration_043_add_document_links(conn)

        cursor = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='document_links'"
        )
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_creates_indexes(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE documents ("
            "id INTEGER PRIMARY KEY, title TEXT, content TEXT, "
            "is_deleted INTEGER DEFAULT 0)"
        )
        migration_043_add_document_links(conn)

        cursor = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='index' AND name LIKE 'idx_doc_links_%'"
        )
        assert cursor.fetchone()[0] == 2
        conn.close()


class TestDocumentLinksCRUD:
    """Test document_links CRUD operations."""

    def test_create_link(self, isolate_test_database):
        from emdx.database import db

        # Create two documents
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (901, "Doc A", "Content A"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (902, "Doc B", "Content B"),
            )
            conn.commit()

        link_id = create_link(901, 902, similarity_score=0.85, method="auto")
        assert link_id is not None

    def test_create_link_self_returns_none(self, isolate_test_database):
        result = create_link(1, 1, similarity_score=0.99)
        assert result is None

    def test_create_duplicate_link_returns_none(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (903, "Doc C", "Content C"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (904, "Doc D", "Content D"),
            )
            conn.commit()

        first = create_link(903, 904, similarity_score=0.8)
        assert first is not None
        second = create_link(903, 904, similarity_score=0.9)
        assert second is None

    def test_link_exists(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (905, "Doc E", "Content E"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (906, "Doc F", "Content F"),
            )
            conn.commit()

        assert not link_exists(905, 906)
        create_link(905, 906, similarity_score=0.7)
        assert link_exists(905, 906)
        # Bidirectional check
        assert link_exists(906, 905)

    def test_delete_link(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (907, "Doc G", "Content G"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (908, "Doc H", "Content H"),
            )
            conn.commit()

        create_link(907, 908, similarity_score=0.6)
        assert link_exists(907, 908)

        deleted = delete_link(907, 908)
        assert deleted
        assert not link_exists(907, 908)

    def test_delete_link_reverse_direction(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (909, "Doc I", "Content I"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (910, "Doc J", "Content J"),
            )
            conn.commit()

        create_link(909, 910, similarity_score=0.6)
        # Delete using reverse order
        deleted = delete_link(910, 909)
        assert deleted
        assert not link_exists(909, 910)

    def test_get_linked_doc_ids(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            for i in range(911, 914):
                conn.execute(
                    "INSERT INTO documents (id, title, content) "
                    "VALUES (?, ?, ?)",
                    (i, f"Doc {i}", f"Content {i}"),
                )
            conn.commit()

        create_link(911, 912, similarity_score=0.8)
        create_link(913, 911, similarity_score=0.7)

        linked = get_linked_doc_ids(911)
        assert set(linked) == {912, 913}

    def test_get_link_count(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            for i in range(920, 924):
                conn.execute(
                    "INSERT INTO documents (id, title, content) "
                    "VALUES (?, ?, ?)",
                    (i, f"Doc {i}", f"Content {i}"),
                )
            conn.commit()

        create_link(920, 921, similarity_score=0.8)
        create_link(920, 922, similarity_score=0.7)
        create_link(923, 920, similarity_score=0.6)

        assert get_link_count(920) == 3
        assert get_link_count(921) == 1

    def test_batch_get_link_counts(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            for i in range(930, 934):
                conn.execute(
                    "INSERT INTO documents (id, title, content) "
                    "VALUES (?, ?, ?)",
                    (i, f"Doc {i}", f"Content {i}"),
                )
            conn.commit()

        create_link(930, 931, similarity_score=0.8)
        create_link(930, 932, similarity_score=0.7)

        counts = batch_get_link_counts([930, 931, 932, 933])
        assert counts[930] == 2
        assert counts[931] == 1
        assert counts[932] == 1
        assert counts[933] == 0

    def test_create_links_batch(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            for i in range(940, 944):
                conn.execute(
                    "INSERT INTO documents (id, title, content) "
                    "VALUES (?, ?, ?)",
                    (i, f"Doc {i}", f"Content {i}"),
                )
            conn.commit()

        links = [
            (940, 941, 0.8, "auto"),
            (940, 942, 0.7, "auto"),
            (940, 943, 0.6, "manual"),
        ]
        created = create_links_batch(links)
        assert created == 3
        assert get_link_count(940) == 3

    def test_create_links_batch_skips_self_links(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) "
                "VALUES (?, ?, ?)",
                (950, "Doc 950", "Content 950"),
            )
            conn.commit()

        links = [(950, 950, 0.99, "auto")]
        created = create_links_batch(links)
        assert created == 0

    def test_delete_links_for_document(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            for i in range(960, 964):
                conn.execute(
                    "INSERT INTO documents (id, title, content) "
                    "VALUES (?, ?, ?)",
                    (i, f"Doc {i}", f"Content {i}"),
                )
            conn.commit()

        create_link(960, 961, similarity_score=0.8)
        create_link(960, 962, similarity_score=0.7)
        create_link(963, 960, similarity_score=0.6)

        deleted_count = delete_links_for_document(960)
        assert deleted_count == 3
        assert get_link_count(960) == 0

    def test_get_links_for_document_with_titles(self, isolate_test_database):
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) "
                "VALUES (?, ?, ?)",
                (970, "Alpha Doc", "Content A"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) "
                "VALUES (?, ?, ?)",
                (971, "Beta Doc", "Content B"),
            )
            conn.commit()

        create_link(970, 971, similarity_score=0.9, method="auto")

        links = get_links_for_document(970)
        assert len(links) == 1
        link = links[0]
        assert link["source_doc_id"] == 970
        assert link["source_title"] == "Alpha Doc"
        assert link["target_doc_id"] == 971
        assert link["target_title"] == "Beta Doc"
        assert link["similarity_score"] == pytest.approx(0.9)
        assert link["method"] == "auto"

    def test_create_link_with_conn_param(self, isolate_test_database):
        """Test creating a link with explicit connection for atomicity."""
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content) "
                "VALUES (?, ?, ?)",
                (980, "Doc 980", "Content 980"),
            )
            conn.execute(
                "INSERT INTO documents (id, title, content) "
                "VALUES (?, ?, ?)",
                (981, "Doc 981", "Content 981"),
            )
            link_id = create_link(980, 981, similarity_score=0.75, conn=conn)
            conn.commit()

        assert link_id is not None
        assert link_exists(980, 981)


class TestLinkService:
    """Test the link_service auto-linking logic."""

    @patch("emdx.services.link_service.document_links")
    @patch("emdx.services.embedding_service.EmbeddingService")
    def test_auto_link_no_index(
        self, MockEmbedding, mock_links, isolate_test_database
    ):
        """auto_link_document returns empty when no index exists."""
        from emdx.services.link_service import auto_link_document

        mock_service = MagicMock()
        mock_stats = MagicMock()
        mock_stats.indexed_documents = 0
        mock_service.stats.return_value = mock_stats
        MockEmbedding.return_value = mock_service

        result = auto_link_document(1)

        assert result.links_created == 0
        assert result.linked_doc_ids == []

    @patch("emdx.services.link_service.document_links")
    @patch("emdx.services.embedding_service.EmbeddingService")
    def test_auto_link_creates_links(
        self, MockEmbedding, mock_links, isolate_test_database
    ):
        """auto_link_document creates links for similar docs above threshold."""
        from emdx.services.link_service import auto_link_document

        mock_service = MagicMock()
        mock_stats = MagicMock()
        mock_stats.indexed_documents = 10
        mock_service.stats.return_value = mock_stats

        mock_match1 = MagicMock()
        mock_match1.doc_id = 2
        mock_match1.similarity = 0.8

        mock_match2 = MagicMock()
        mock_match2.doc_id = 3
        mock_match2.similarity = 0.3  # Below threshold

        mock_service.find_similar.return_value = [mock_match1, mock_match2]
        MockEmbedding.return_value = mock_service

        mock_links.get_linked_doc_ids.return_value = []
        mock_links.create_links_batch.return_value = 1

        result = auto_link_document(1, threshold=0.5)

        assert result.links_created == 1
        mock_links.create_links_batch.assert_called_once()
        # Only the match above threshold should be in the batch
        call_args = mock_links.create_links_batch.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0][1] == 2  # target doc_id

    @patch("emdx.services.link_service.document_links")
    @patch("emdx.services.embedding_service.EmbeddingService")
    def test_auto_link_skips_existing(
        self, MockEmbedding, mock_links, isolate_test_database
    ):
        """auto_link_document skips already-linked documents."""
        from emdx.services.link_service import auto_link_document

        mock_service = MagicMock()
        mock_stats = MagicMock()
        mock_stats.indexed_documents = 10
        mock_service.stats.return_value = mock_stats

        mock_match = MagicMock()
        mock_match.doc_id = 2
        mock_match.similarity = 0.8

        mock_service.find_similar.return_value = [mock_match]
        MockEmbedding.return_value = mock_service

        # Document 2 is already linked
        mock_links.get_linked_doc_ids.return_value = [2]

        result = auto_link_document(1)

        assert result.links_created == 0
        mock_links.create_links_batch.assert_not_called()
