"""Tests for wiki triage, auto-label, and setup commands (Issue #846)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _setup_wiki_topic(
    conn: sqlite3.Connection,
    topic_id: int,
    label: str = "Test Topic",
    status: str = "active",
    coherence: float = 0.1,
) -> None:
    """Insert a wiki topic for testing."""
    conn.execute(
        "INSERT INTO wiki_topics "
        "(id, topic_slug, topic_label, entity_fingerprint, "
        "coherence_score, status) "
        "VALUES (?, ?, ?, 'fp', ?, ?)",
        (topic_id, f"test-topic-{topic_id}", label, coherence, status),
    )
    conn.commit()


def _get_topic_status(conn: sqlite3.Connection, topic_id: int) -> str | None:
    row = conn.execute("SELECT status FROM wiki_topics WHERE id = ?", (topic_id,)).fetchone()
    return row[0] if row else None


def _get_topic_label(conn: sqlite3.Connection, topic_id: int) -> str | None:
    row = conn.execute("SELECT topic_label FROM wiki_topics WHERE id = ?", (topic_id,)).fetchone()
    return row[0] if row else None


# ── Triage command tests ──────────────────────────────────────────


class TestWikiTriageSkipBelow:
    """Test 'wiki triage --skip-below' functionality."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=80, label="Low Coherence", coherence=0.01)
            _setup_wiki_topic(conn, topic_id=81, label="High Coherence", coherence=0.2)
            _setup_wiki_topic(
                conn, topic_id=82, label="Already Skipped", coherence=0.01, status="skipped"
            )
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topics WHERE id IN (80, 81, 82)")
            conn.commit()

    def test_skip_below_skips_low_coherence(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "triage", "--skip-below", "0.05"])
        assert result.exit_code == 0
        assert "Skipped" in result.output or "skipped" in result.output

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 80) == "skipped"
            assert _get_topic_status(conn, 81) == "active"

    def test_skip_below_ignores_already_skipped(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "triage", "--skip-below", "0.05"])
        assert result.exit_code == 0
        # Topic 82 was already skipped — should not appear in output
        assert "Already Skipped" not in result.output

    def test_skip_below_dry_run(self) -> None:
        result = runner.invoke(
            app,
            ["maintain", "wiki", "triage", "--skip-below", "0.05", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()

        with db.get_connection() as conn:
            assert _get_topic_status(conn, 80) == "active"

    def test_triage_requires_flags(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "triage"])
        assert result.exit_code == 1
        assert "Specify" in result.output


class TestWikiTriageNoTopics:
    """Test triage with no saved topics."""

    def test_triage_no_topics(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "triage", "--skip-below", "0.05"])
        assert result.exit_code == 1
        assert "No saved topics" in result.output


class TestWikiTriageAutoLabel:
    """Test 'wiki triage --auto-label' functionality."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents (id, title, content, is_deleted) "
                "VALUES (183, 'Test Doc', 'Content for testing', 0)"
            )
            _setup_wiki_topic(conn, topic_id=83, label="entity1 / entity2 / entity3")
            conn.execute("INSERT INTO wiki_topic_members (topic_id, document_id) VALUES (83, 183)")
            conn.commit()
        yield
        with db.get_connection() as conn:
            conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = 83")
            conn.execute("DELETE FROM wiki_topics WHERE id = 83")
            conn.execute("DELETE FROM documents WHERE id = 183")
            conn.commit()

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    @patch("emdx.services.wiki_clustering_service.subprocess.run")
    def test_auto_label_renames_topics(
        self, mock_run: MagicMock, mock_has_claude: MagicMock
    ) -> None:
        mock_has_claude.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout="Better Topic Name", stderr="")

        result = runner.invoke(app, ["maintain", "wiki", "triage", "--auto-label"])
        assert result.exit_code == 0
        assert "Better Topic Name" in result.output

        with db.get_connection() as conn:
            assert _get_topic_label(conn, 83) == "Better Topic Name"

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    def test_auto_label_fails_without_claude(self, mock_has_claude: MagicMock) -> None:
        mock_has_claude.return_value = False
        result = runner.invoke(app, ["maintain", "wiki", "triage", "--auto-label"])
        assert result.exit_code == 1
        assert "Claude CLI not found" in result.output


# ── Topics --auto-label tests ────────────────────────────────────


class TestWikiTopicsAutoLabel:
    """Test 'wiki topics --save --auto-label' functionality."""

    @patch("emdx.services.wiki_clustering_service.save_topics")
    @patch("emdx.services.wiki_clustering_service.auto_label_clusters")
    @patch("emdx.services.wiki_clustering_service.discover_topics")
    def test_auto_label_called_on_save(
        self,
        mock_discover: MagicMock,
        mock_auto_label: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import ClusteringResult, TopicCluster

        cluster = TopicCluster(
            cluster_id=0,
            label="Better Name",
            slug="better-name",
            doc_ids=[1, 2, 3],
            top_entities=[("entity1", 1.0)],
            coherence_score=0.15,
        )
        mock_discover.return_value = ClusteringResult(
            clusters=[cluster],
            total_docs=10,
            docs_clustered=3,
            docs_unclustered=7,
            resolution=0.005,
        )
        mock_auto_label.return_value = [cluster]
        mock_save.return_value = 1

        result = runner.invoke(app, ["maintain", "wiki", "topics", "--save", "--auto-label"])
        assert result.exit_code == 0
        mock_auto_label.assert_called_once()

    @patch("emdx.services.wiki_clustering_service.discover_topics")
    def test_auto_label_not_called_without_flag(self, mock_discover: MagicMock) -> None:
        from emdx.services.wiki_clustering_service import ClusteringResult

        mock_discover.return_value = ClusteringResult(
            clusters=[],
            total_docs=10,
            docs_clustered=0,
            docs_unclustered=10,
            resolution=0.005,
        )

        result = runner.invoke(app, ["maintain", "wiki", "topics"])
        assert result.exit_code == 0


# ── Auto-label service tests ─────────────────────────────────────


class TestAutoLabelCluster:
    """Test auto_label_cluster function."""

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    def test_fallback_without_claude(self, mock_has: MagicMock) -> None:
        from emdx.services.wiki_clustering_service import TopicCluster, auto_label_cluster

        mock_has.return_value = False
        cluster = TopicCluster(
            cluster_id=0,
            label="original / label",
            slug="original-label",
            doc_ids=[1],
            top_entities=[("entity", 1.0)],
        )
        assert auto_label_cluster(cluster) == "original / label"

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    @patch("emdx.services.wiki_clustering_service._get_doc_titles")
    @patch("emdx.services.wiki_clustering_service.subprocess.run")
    def test_uses_claude_cli(
        self,
        mock_run: MagicMock,
        mock_titles: MagicMock,
        mock_has: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import TopicCluster, auto_label_cluster

        mock_has.return_value = True
        mock_titles.return_value = ["Doc 1", "Doc 2"]
        mock_run.return_value = MagicMock(returncode=0, stdout="Database Architecture", stderr="")

        cluster = TopicCluster(
            cluster_id=0,
            label="sqlite / db / query",
            slug="sqlite-db-query",
            doc_ids=[1, 2],
            top_entities=[("sqlite", 1.0), ("db", 0.8)],
        )
        result = auto_label_cluster(cluster)
        assert result == "Database Architecture"
        mock_run.assert_called_once()

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    @patch("emdx.services.wiki_clustering_service._get_doc_titles")
    @patch("emdx.services.wiki_clustering_service.subprocess.run")
    def test_fallback_on_cli_failure(
        self,
        mock_run: MagicMock,
        mock_titles: MagicMock,
        mock_has: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import TopicCluster, auto_label_cluster

        mock_has.return_value = True
        mock_titles.return_value = ["Doc 1"]
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        cluster = TopicCluster(
            cluster_id=0,
            label="original",
            slug="original",
            doc_ids=[1],
            top_entities=[("entity", 1.0)],
        )
        assert auto_label_cluster(cluster) == "original"

    @patch("emdx.services.wiki_clustering_service._has_claude_cli")
    @patch("emdx.services.wiki_clustering_service._get_doc_titles")
    @patch("emdx.services.wiki_clustering_service.subprocess.run")
    def test_rejects_too_long_label(
        self,
        mock_run: MagicMock,
        mock_titles: MagicMock,
        mock_has: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import TopicCluster, auto_label_cluster

        mock_has.return_value = True
        mock_titles.return_value = ["Doc"]
        mock_run.return_value = MagicMock(returncode=0, stdout="A" * 100, stderr="")

        cluster = TopicCluster(
            cluster_id=0,
            label="fallback",
            slug="fallback",
            doc_ids=[1],
            top_entities=[("x", 1.0)],
        )
        assert auto_label_cluster(cluster) == "fallback"


# ── Setup command tests ───────────────────────────────────────────


class TestWikiSetup:
    """Test 'wiki setup' command."""

    @patch("shutil.which", return_value=None)
    @patch("emdx.services.wiki_clustering_service.save_topics", return_value=1)
    @patch("emdx.services.wiki_clustering_service.discover_topics")
    @patch("emdx.services.entity_service.entity_wikify_all")
    @patch("emdx.services.embedding_service.EmbeddingService")
    def test_setup_runs_all_steps(
        self,
        mock_embed_cls: MagicMock,
        mock_entities: MagicMock,
        mock_discover: MagicMock,
        mock_save: MagicMock,
        mock_which: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import ClusteringResult, TopicCluster

        mock_service = MagicMock()
        mock_service.stats.return_value = MagicMock(
            indexed_documents=100, total_documents=100, indexed_chunks=50
        )
        mock_embed_cls.return_value = mock_service
        mock_entities.return_value = (500, 200, 100)

        cluster = TopicCluster(
            cluster_id=0,
            label="Test Cluster",
            slug="test-cluster",
            doc_ids=[1, 2, 3],
            top_entities=[("test", 1.0)],
            coherence_score=0.1,
        )
        mock_discover.return_value = ClusteringResult(
            clusters=[cluster],
            total_docs=100,
            docs_clustered=3,
            docs_unclustered=97,
            resolution=0.005,
        )

        result = runner.invoke(app, ["maintain", "wiki", "setup"])
        assert result.exit_code == 0
        assert "Wiki Setup Complete" in result.output
        assert "Saved" in result.output

    @patch("emdx.services.wiki_clustering_service.discover_topics")
    @patch("emdx.services.entity_service.entity_wikify_all")
    @patch("emdx.services.embedding_service.EmbeddingService")
    def test_setup_no_clusters(
        self,
        mock_embed_cls: MagicMock,
        mock_entities: MagicMock,
        mock_discover: MagicMock,
    ) -> None:
        from emdx.services.wiki_clustering_service import ClusteringResult

        mock_service = MagicMock()
        mock_service.stats.return_value = MagicMock(
            indexed_documents=10, total_documents=10, indexed_chunks=5
        )
        mock_embed_cls.return_value = mock_service
        mock_entities.return_value = (50, 10, 10)
        mock_discover.return_value = ClusteringResult(
            clusters=[],
            total_docs=10,
            docs_clustered=0,
            docs_unclustered=10,
            resolution=0.005,
        )

        result = runner.invoke(app, ["maintain", "wiki", "setup"])
        assert result.exit_code == 0
        assert "No topic clusters found" in result.output
