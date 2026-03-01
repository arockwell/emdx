"""Tests for emdx find --wander (serendipity search)."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from emdx.services.embedding_service import EmbeddingStats

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)


@pytest.fixture
def seed_embedding() -> np.ndarray:
    """Create a normalized seed embedding vector."""
    rng = np.random.default_rng(42)
    vec = rng.random(384).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return vec


def _make_doc_embedding(seed: np.ndarray, target_similarity: float) -> bytes:
    """Create a document embedding with approximately the target similarity.

    For normalized vectors, cosine similarity = dot product.
    We create a vector that has `target_similarity` component along seed
    and a random orthogonal component.
    """
    rng = np.random.default_rng(hash(str(target_similarity)) % (2**31))
    random_vec = rng.random(384).astype(np.float32)
    # Make orthogonal to seed
    random_vec -= np.dot(random_vec, seed) * seed
    random_vec /= np.linalg.norm(random_vec)

    # Compose: target_similarity * seed + sqrt(1-t^2) * orthogonal
    t = target_similarity
    ortho_weight = np.sqrt(max(0, 1 - t * t))
    composed: np.ndarray = (t * seed + ortho_weight * random_vec).astype(np.float32)
    composed /= np.linalg.norm(composed)
    return bytes(composed.tobytes())


def _mock_db_context(mock_db: Any, mock_conn: Any) -> None:
    """Wire up mock_db.get_connection() as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = lambda s: mock_conn
    ctx.__exit__ = lambda s, *a: None
    mock_db.get_connection.return_value = ctx


def _make_service_mock(stats_indexed: int = 50) -> MagicMock:
    """Create a mock EmbeddingService with standard config."""
    mock_service = MagicMock()
    mock_service.MODEL_NAME = "all-MiniLM-L6-v2"
    mock_service.stats.return_value = EmbeddingStats(
        total_documents=stats_indexed,
        indexed_documents=stats_indexed,
        coverage_percent=100.0,
        model_name="all-MiniLM-L6-v2",
        index_size_bytes=stats_indexed * 1000,
    )
    return mock_service


class TestFindWander:
    """Tests for the _find_wander helper function."""

    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_too_few_documents(self, mock_es_class: Any, capsys: Any) -> None:
        """Should show helpful message when <10 docs have embeddings."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock(stats_indexed=5)
        mock_es_class.return_value = mock_service

        _find_wander("", limit=5, project=None, json_output=False)

        captured = capsys.readouterr()
        out = _strip_ansi(captured.out)
        assert "Serendipity works better with 50+ documents" in out
        assert "You have 5" in out

    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_too_few_documents_json(self, mock_es_class: Any, capsys: Any) -> None:
        """JSON mode should also report the error."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock(stats_indexed=3)
        mock_es_class.return_value = mock_service

        _find_wander("", limit=5, project=None, json_output=True)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert "error" in result
        assert "Serendipity works better" in result["error"]

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_with_query_seed(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """--wander with a query uses the query as embedding seed."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        # Create mock DB rows with various similarities
        mock_rows = [
            # In Goldilocks band (0.2-0.4)
            (
                1,
                _make_doc_embedding(seed_embedding, 0.35),
                "Related Doc A",
                "proj1",
                "Content about related topic A",
            ),
            (
                2,
                _make_doc_embedding(seed_embedding, 0.25),
                "Related Doc B",
                "proj1",
                "Content about related topic B",
            ),
            # Outside band - too similar
            (
                3,
                _make_doc_embedding(seed_embedding, 0.9),
                "Very Similar Doc",
                "proj1",
                "Almost the same content",
            ),
            # Outside band - too different
            (
                4,
                _make_doc_embedding(seed_embedding, 0.05),
                "Unrelated Doc",
                "proj1",
                "Completely different content",
            ),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander(
            "machine learning",
            limit=5,
            project=None,
            json_output=True,
        )

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert result["seed"] == "machine learning"
        # Should only include docs in Goldilocks band
        assert len(result["results"]) == 2
        # Should be sorted by similarity descending
        sims = [r["similarity"] for r in result["results"]]
        assert sims == sorted(sims, reverse=True)

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_without_query_picks_random_seed(
        self,
        mock_es_class: Any,
        mock_db: Any,
        capsys: Any,
        seed_embedding: Any,
    ) -> None:
        """--wander without query picks a random recent doc as seed."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_document.return_value = seed_embedding

        # Two DB calls: recent IDs, then all embeddings
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        recent_ids_result = [(10,), (11,), (12,)]
        all_docs_result = [
            (
                10,
                seed_embedding.tobytes(),
                "Seed Doc",
                "proj1",
                "The seed document",
            ),
            (
                20,
                _make_doc_embedding(seed_embedding, 0.3),
                "Goldilocks Doc",
                None,
                "In the sweet spot",
            ),
            (
                30,
                _make_doc_embedding(seed_embedding, 0.8),
                "Too Similar",
                "proj1",
                "Way too close",
            ),
        ]

        mock_cursor.fetchall.side_effect = [
            recent_ids_result,
            all_docs_result,
        ]
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander("", limit=5, project=None, json_output=True)

        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert result["seed"].startswith("doc #")
        # embed_document was called with one of the recent IDs
        call_args = mock_service.embed_document.call_args
        assert call_args[0][0] in [10, 11, 12]

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_no_goldilocks_results(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """Should show message when no docs in Goldilocks band."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        # All docs are too similar or too different
        mock_rows = [
            (
                1,
                _make_doc_embedding(seed_embedding, 0.9),
                "Very Similar",
                "proj1",
                "Almost identical",
            ),
            (
                2,
                _make_doc_embedding(seed_embedding, 0.05),
                "Very Different",
                "proj1",
                "Totally unrelated",
            ),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander("test", limit=5, project=None, json_output=False)

        captured = capsys.readouterr()
        assert "No surprising connections found" in _strip_ansi(captured.out)

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_respects_limit(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """--wander should respect --limit but cap at 5."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        # Create 10 docs in the Goldilocks band
        mock_rows = []
        for i in range(10):
            sim = 0.2 + (i * 0.02)  # 0.2 to 0.38
            mock_rows.append(
                (
                    i + 1,
                    _make_doc_embedding(seed_embedding, sim),
                    f"Doc {i}",
                    "proj1",
                    f"Content {i}",
                )
            )

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        # limit=3 should return 3
        _find_wander(
            "test",
            limit=3,
            project=None,
            json_output=True,
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert len(result["results"]) == 3

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_caps_at_five(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """--wander should cap results at 5 even with higher limit."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        mock_rows = []
        for i in range(10):
            sim = 0.2 + (i * 0.02)
            mock_rows.append(
                (
                    i + 1,
                    _make_doc_embedding(seed_embedding, sim),
                    f"Doc {i}",
                    "proj1",
                    f"Content {i}",
                )
            )

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander(
            "test",
            limit=20,
            project=None,
            json_output=True,
        )
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert len(result["results"]) <= 5

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_project_filter(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """--wander with --project should filter by project."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander(
            "test",
            limit=5,
            project="my-project",
            json_output=True,
        )

        # Verify the SQL was called with the project parameter
        execute_calls = mock_cursor.execute.call_args_list
        sql_call = execute_calls[0]
        sql_str = sql_call[0][0]
        sql_params = sql_call[0][1]
        assert "d.project = ?" in sql_str
        assert "my-project" in sql_params

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_human_readable_output(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """Human-readable output includes title, similarity, snippet."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_text.return_value = seed_embedding

        mock_rows = [
            (
                42,
                _make_doc_embedding(seed_embedding, 0.3),
                "Surprising Connection",
                "proj1",
                "This is a surprising but related doc",
            ),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_rows
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander(
            "topic",
            limit=5,
            project=None,
            json_output=False,
        )

        captured = capsys.readouterr()
        out = _strip_ansi(captured.out)
        assert "Wandering from 'topic'" in out
        assert "Surprising Connection" in out
        assert "#42" in out
        assert "surprising connections" in out

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_no_recent_docs_without_query(
        self, mock_es_class: Any, mock_db: Any, capsys: Any
    ) -> None:
        """Without query, if no recent docs have embeddings, show error."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # No recent docs
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander("", limit=5, project=None, json_output=False)

        captured = capsys.readouterr()
        assert "No documents with embeddings found" in _strip_ansi(captured.out)

    @patch("emdx.database.db")
    @patch(
        "emdx.services.embedding_service.EmbeddingService",
        autospec=True,
    )
    def test_wander_excludes_seed_doc(
        self, mock_es_class: Any, mock_db: Any, capsys: Any, seed_embedding: Any
    ) -> None:
        """The seed document itself should be excluded from results."""
        from emdx.commands.core import _find_wander

        mock_service = _make_service_mock()
        mock_es_class.return_value = mock_service
        mock_service.embed_document.return_value = seed_embedding

        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        seed_doc_id = 10
        mock_cursor.fetchall.side_effect = [
            [(seed_doc_id,)],  # recent IDs
            [
                # The seed doc itself (should be excluded)
                (
                    seed_doc_id,
                    _make_doc_embedding(seed_embedding, 0.3),
                    "Seed Doc",
                    "proj1",
                    "The seed",
                ),
                # Another doc in Goldilocks band
                (
                    20,
                    _make_doc_embedding(seed_embedding, 0.3),
                    "Other Doc",
                    "proj1",
                    "Other content",
                ),
            ],
        ]
        mock_conn.cursor.return_value = mock_cursor
        _mock_db_context(mock_db, mock_conn)

        _find_wander("", limit=5, project=None, json_output=True)

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        result_ids = [r["id"] for r in result["results"]]
        assert seed_doc_id not in result_ids
        assert 20 in result_ids
