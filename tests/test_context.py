"""Tests for the context command — graph-aware context assembly."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from emdx.commands.context import (
    ScoredDocument,
    compute_link_score,
    estimate_tokens,
    pack_context,
    traverse_graph,
)
from emdx.database.types import DocumentLinkDetail

# ── Unit tests (no DB needed) ───────────────────────────────────────


class TestEstimateTokens:
    """Test token estimation."""

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_short_string(self) -> None:
        assert estimate_tokens("hello") == 1

    def test_longer_string(self) -> None:
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_realistic_text(self) -> None:
        text = "The quick brown fox jumps over the lazy dog. " * 10
        tokens = estimate_tokens(text)
        assert 100 < tokens < 150


class TestComputeLinkScore:
    """Test link scoring logic."""

    def _make_link(
        self,
        method: str = "title_match",
        score: float = 1.0,
    ) -> DocumentLinkDetail:
        return DocumentLinkDetail(
            id=1,
            source_doc_id=1,
            source_title="Source",
            target_doc_id=2,
            target_title="Target",
            similarity_score=score,
            created_at=None,
            method=method,
        )

    def test_title_match_depth_1(self) -> None:
        link = self._make_link("title_match", 1.0)
        result = compute_link_score(link, depth=1, source_score=1.0)
        assert result == pytest.approx(0.6)

    def test_semantic_depth_2(self) -> None:
        link = self._make_link("semantic", 0.73)
        result = compute_link_score(link, depth=2, source_score=1.0)
        # 1.0 * 0.7 * 0.73 * 0.36 = 0.18396
        assert result == pytest.approx(0.18396, abs=0.001)

    def test_manual_link_full_weight(self) -> None:
        link = self._make_link("manual", 1.0)
        result = compute_link_score(link, depth=1, source_score=1.0)
        assert result == pytest.approx(0.6)

    def test_unknown_method_uses_default(self) -> None:
        link = self._make_link("unknown_method", 1.0)
        result = compute_link_score(link, depth=1, source_score=1.0)
        # default weight 0.5 * 1.0 * 0.6 = 0.3
        assert result == pytest.approx(0.3)

    def test_source_score_propagates(self) -> None:
        link = self._make_link("title_match", 1.0)
        result = compute_link_score(link, depth=1, source_score=0.5)
        # 0.5 * 1.0 * 1.0 * 0.6 = 0.3
        assert result == pytest.approx(0.3)

    def test_low_similarity_reduces_score(self) -> None:
        link = self._make_link("title_match", 0.3)
        result = compute_link_score(link, depth=1, source_score=1.0)
        # 1.0 * 1.0 * 0.3 * 0.6 = 0.18
        assert result == pytest.approx(0.18)


class TestPackContext:
    """Test token budget packing."""

    def _make_scored(self, doc_id: int, tokens: int, score: float) -> ScoredDocument:
        return ScoredDocument(
            doc_id=doc_id,
            title=f"Doc {doc_id}",
            content=f"Content of doc {doc_id}",
            tokens=tokens,
            hops=0,
            score=score,
        )

    def test_all_fit(self) -> None:
        docs = [
            self._make_scored(1, 100, 1.0),
            self._make_scored(2, 200, 0.8),
        ]
        included, excluded = pack_context(docs, 500)
        assert len(included) == 2
        assert len(excluded) == 0

    def test_budget_exceeded(self) -> None:
        docs = [
            self._make_scored(1, 300, 1.0),
            self._make_scored(2, 300, 0.8),
        ]
        included, excluded = pack_context(docs, 400)
        assert len(included) == 1
        assert included[0].doc_id == 1
        assert len(excluded) == 1
        assert excluded[0].doc_id == 2

    def test_empty_docs(self) -> None:
        included, excluded = pack_context([], 1000)
        assert len(included) == 0
        assert len(excluded) == 0

    def test_zero_budget(self) -> None:
        docs = [self._make_scored(1, 100, 1.0)]
        included, excluded = pack_context(docs, 0)
        assert len(included) == 0
        assert len(excluded) == 1

    def test_greedy_packing_skips_large_includes_small(self) -> None:
        docs = [
            self._make_scored(1, 100, 1.0),
            self._make_scored(2, 500, 0.9),  # too large
            self._make_scored(3, 100, 0.8),  # fits
        ]
        included, excluded = pack_context(docs, 250)
        assert len(included) == 2
        assert [d.doc_id for d in included] == [1, 3]
        assert [d.doc_id for d in excluded] == [2]


# ── Integration tests (use DB) ──────────────────────────────────────


def _setup_graph(conn: sqlite3.Connection) -> None:
    """Create a small test graph: A -> B -> C, A -> D."""
    # Insert documents
    for doc_id, title, content in [
        (1001, "Auth Architecture", "Core auth design"),
        (1002, "Session Handling", "Session middleware docs"),
        (1003, "Redis Config", "Redis TTL settings"),
        (1004, "Token Format", "JWT token format spec"),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
            (doc_id, title, content),
        )

    # Create links: 1001 -> 1002, 1002 -> 1003, 1001 -> 1004
    for src, tgt, score, method in [
        (1001, 1002, 0.9, "title_match"),
        (1002, 1003, 0.8, "entity_match"),
        (1001, 1004, 0.7, "semantic"),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO document_links "
            "(source_doc_id, target_doc_id, "
            "similarity_score, method) "
            "VALUES (?, ?, ?, ?)",
            (src, tgt, score, method),
        )
    conn.commit()


class TestTraverseGraph:
    """Test graph traversal with a real DB."""

    def test_single_seed_no_links(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(id, title, content, is_deleted) "
                "VALUES (?, ?, ?, 0)",
                (2001, "Standalone", "No links here"),
            )
            conn.commit()

        results = traverse_graph([2001], max_depth=2)
        assert len(results) == 1
        assert results[0].doc_id == 2001
        assert results[0].score == 1.0
        assert results[0].hops == 0

    def test_depth_1_traversal(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_graph(conn)

        results = traverse_graph([1001], max_depth=1)
        ids = {r.doc_id for r in results}
        # Should include seed + 1-hop neighbors
        assert 1001 in ids
        assert 1002 in ids
        assert 1004 in ids
        # Should NOT include 2-hop neighbor
        assert 1003 not in ids

    def test_depth_2_traversal(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_graph(conn)

        results = traverse_graph([1001], max_depth=2)
        ids = {r.doc_id for r in results}
        # Should include all reachable docs
        assert 1001 in ids
        assert 1002 in ids
        assert 1003 in ids
        assert 1004 in ids

    def test_scores_decrease_with_depth(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_graph(conn)

        results = traverse_graph([1001], max_depth=2)
        by_id = {r.doc_id: r for r in results}
        # Seed has highest score
        assert by_id[1001].score == 1.0
        # 1-hop should be lower
        assert by_id[1002].score < 1.0
        # 2-hop should be lowest
        assert by_id[1003].score < by_id[1002].score

    def test_missing_seed_skipped(self, isolate_test_database: Path) -> None:
        results = traverse_graph([99999], max_depth=1)
        assert len(results) == 0

    def test_multiple_seeds(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_graph(conn)

        results = traverse_graph([1001, 1003], max_depth=1)
        ids = {r.doc_id for r in results}
        assert 1001 in ids
        assert 1003 in ids
        # 1-hop from 1001
        assert 1002 in ids

    def test_path_tracking(self, isolate_test_database: Path) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _setup_graph(conn)

        results = traverse_graph([1001], max_depth=2)
        by_id = {r.doc_id: r for r in results}
        # Seed path is just itself
        assert by_id[1001].path == [1001]
        # 1-hop path is seed + target
        assert by_id[1002].path == [1001, 1002]
        # 2-hop path is seed + intermediate + target
        assert by_id[1003].path == [1001, 1002, 1003]


# ── CLI output tests ────────────────────────────────────────────────


class TestRenderJson:
    """Test JSON output rendering."""

    def test_json_structure(self) -> None:
        from emdx.commands.context import _render_json

        included = [
            ScoredDocument(
                doc_id=1,
                title="Seed Doc",
                content="Content here",
                tokens=100,
                hops=0,
                score=1.0,
                path=[1],
                link_methods=[],
                reason="seed",
            ),
            ScoredDocument(
                doc_id=2,
                title="Linked Doc",
                content="More content",
                tokens=80,
                hops=1,
                score=0.6,
                path=[1, 2],
                link_methods=["title_match"],
                reason="1-hop title_match from #1",
            ),
        ]
        excluded = [
            ScoredDocument(
                doc_id=3,
                title="Excluded Doc",
                content="Too much",
                tokens=500,
                hops=2,
                score=0.3,
                path=[1, 2, 3],
                link_methods=["title_match", "semantic"],
                reason="2-hop semantic from #2",
            ),
        ]

        output = json.loads(_render_json([1], included, excluded, 4000, 2))

        assert output["seed_ids"] == [1]
        assert output["depth"] == 2
        assert output["max_tokens"] == 4000
        assert output["tokens_used"] == 180
        assert len(output["documents"]) == 2
        assert len(output["excluded"]) == 1

        # Check seed document
        seed_doc = output["documents"][0]
        assert seed_doc["id"] == 1
        assert seed_doc["traversal"]["hops"] == 0
        assert seed_doc["traversal"]["score"] == 1.0
        assert "path" not in seed_doc["traversal"]

        # Check linked document
        linked_doc = output["documents"][1]
        assert linked_doc["id"] == 2
        assert linked_doc["traversal"]["path"] == [1, 2]
        assert linked_doc["traversal"]["link_methods"] == ["title_match"]

        # Check excluded document
        exc_doc = output["excluded"][0]
        assert exc_doc["traversal"]["reason"] == "budget_exceeded"


class TestRenderHuman:
    """Test human-readable output rendering."""

    def test_includes_header(self) -> None:
        from emdx.commands.context import _render_human

        included = [
            ScoredDocument(
                doc_id=1,
                title="Test Doc",
                content="x",
                tokens=100,
                hops=0,
                score=1.0,
                path=[1],
            ),
        ]
        output = _render_human([1], included, [], 4000, 2)
        assert "Test Doc (#1)" in output
        assert "Budget: 4,000 tokens" in output

    def test_plan_mode_label(self) -> None:
        from emdx.commands.context import _render_human

        included = [
            ScoredDocument(
                doc_id=1,
                title="Test",
                content="x",
                tokens=100,
                hops=0,
                score=1.0,
                path=[1],
            ),
        ]
        output = _render_human([1], included, [], 4000, 2, plan_only=True)
        assert "Would include" in output

    def test_shows_excluded(self) -> None:
        from emdx.commands.context import _render_human

        excluded = [
            ScoredDocument(
                doc_id=2,
                title="Excluded",
                content="x",
                tokens=500,
                hops=2,
                score=0.3,
                path=[1, 2],
            ),
        ]
        output = _render_human([1], [], excluded, 100, 2)
        assert "Excluded (budget)" in output
        assert "#2" in output
