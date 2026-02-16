"""Tests for the compact command and SynthesisService."""

from unittest.mock import MagicMock, patch

import pytest

# Skip all tests if sklearn not installed - must come before module imports
sklearn = pytest.importorskip(
    "sklearn",
    reason="scikit-learn not installed (install with: pip install 'emdx[similarity]')",
)


class TestFindClusters:
    """Tests for the cluster discovery logic."""

    def test_find_clusters_empty_list(self):
        """Test clustering with empty document list."""
        from emdx.commands.compact import _find_clusters

        clusters = _find_clusters([], threshold=0.5)
        assert clusters == []

    def test_find_clusters_single_doc(self):
        """Test clustering with single document."""
        from emdx.commands.compact import DocumentInfo, _find_clusters

        docs = [
            DocumentInfo(id=1, title="Test", content="Some content", tags=["test"]),
        ]
        clusters = _find_clusters(docs, threshold=0.5)
        assert clusters == []  # Need at least 2 docs for a cluster

    def test_find_clusters_similar_documents(self):
        """Test clustering finds similar documents."""
        from emdx.commands.compact import DocumentInfo, _find_clusters

        docs = [
            DocumentInfo(
                id=1,
                title="Python Machine Learning Guide",
                content="Machine learning with Python using scikit-learn and TensorFlow. "
                        "Deep learning models and neural networks for AI applications.",
                tags=["python", "ml"],
            ),
            DocumentInfo(
                id=2,
                title="Python ML Tutorial",
                content="Machine learning tutorial in Python. Learn scikit-learn and "
                        "TensorFlow for building AI models and neural networks.",
                tags=["python", "ml"],
            ),
            DocumentInfo(
                id=3,
                title="Docker Container Guide",
                content="Docker containers for deployment. Kubernetes orchestration and "
                        "container best practices for DevOps.",
                tags=["docker", "devops"],
            ),
        ]

        clusters = _find_clusters(docs, threshold=0.3)

        # Should find at least one cluster with the similar ML docs
        assert len(clusters) >= 1

        # The ML documents (1 and 2) should be clustered together
        ml_cluster = None
        for cluster in clusters:
            if 1 in cluster.doc_ids and 2 in cluster.doc_ids:
                ml_cluster = cluster
                break

        assert ml_cluster is not None, "ML documents should be clustered together"
        assert 3 not in ml_cluster.doc_ids, "Docker doc should not be in ML cluster"

    def test_find_clusters_threshold_affects_results(self):
        """Test that threshold parameter affects clustering."""
        from emdx.commands.compact import DocumentInfo, _find_clusters

        docs = [
            DocumentInfo(
                id=1,
                title="Python Guide",
                content="Python programming language basics and syntax.",
                tags=["python"],
            ),
            DocumentInfo(
                id=2,
                title="Python Tutorial",
                content="Python programming tutorial for beginners.",
                tags=["python"],
            ),
            DocumentInfo(
                id=3,
                title="JavaScript Guide",
                content="JavaScript programming language for web development.",
                tags=["javascript"],
            ),
        ]

        # High threshold should find fewer clusters
        high_thresh_clusters = _find_clusters(docs, threshold=0.9)
        low_thresh_clusters = _find_clusters(docs, threshold=0.2)

        # Low threshold should generally find more/larger clusters
        high_total = sum(len(c.doc_ids) for c in high_thresh_clusters)
        low_total = sum(len(c.doc_ids) for c in low_thresh_clusters)

        # With very different content, high threshold may find nothing
        # while low threshold might cluster Python docs together
        assert low_total >= high_total

    def test_find_clusters_respects_min_cluster_size(self):
        """Test that min_cluster_size is respected."""
        from emdx.commands.compact import DocumentInfo, _find_clusters

        # Need longer content with varied vocabulary for TF-IDF to work properly
        docs = [
            DocumentInfo(
                id=1,
                title="Python Programming Guide",
                content="Python is a versatile programming language used for web development.",
                tags=["python"],
            ),
            DocumentInfo(
                id=2,
                title="Python Tutorial",
                content="Learn Python programming language basics and web frameworks.",
                tags=["python"],
            ),
        ]

        # With min_cluster_size=3, shouldn't find any clusters (we only have 2 docs)
        clusters = _find_clusters(docs, threshold=0.1, min_cluster_size=3)
        assert len(clusters) == 0


class TestSynthesisService:
    """Tests for the SynthesisService."""

    def test_synthesis_service_requires_anthropic(self):
        """Test that SynthesisService raises error when anthropic not installed."""
        with patch("emdx.services.synthesis_service.HAS_ANTHROPIC", False):
            from emdx.services.synthesis_service import SynthesisService

            service = SynthesisService()

            with pytest.raises(ImportError, match="anthropic is required"):
                service.synthesize_documents([1, 2, 3])

    def test_synthesis_service_validates_doc_ids(self):
        """Test that SynthesisService validates input."""
        with patch("emdx.services.synthesis_service.HAS_ANTHROPIC", True):
            from emdx.services.synthesis_service import SynthesisService

            service = SynthesisService()

            with pytest.raises(ValueError, match="No document IDs provided"):
                service.synthesize_documents([])

    def test_synthesis_service_fetch_documents(self, temp_db):
        """Test document fetching logic."""
        # Save some test documents
        doc1_id = temp_db.save_document(
            title="Test Doc 1", content="Content for doc 1", project="test"
        )
        doc2_id = temp_db.save_document(
            title="Test Doc 2", content="Content for doc 2", project="test"
        )

        with patch("emdx.services.synthesis_service.db") as mock_db:
            mock_conn = temp_db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn
                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            from emdx.services.synthesis_service import SynthesisService

            service = SynthesisService()
            docs = service._fetch_documents([doc1_id, doc2_id])

            assert len(docs) == 2
            assert docs[0][0] == doc1_id
            assert docs[0][1] == "Test Doc 1"

    def test_synthesis_service_extract_title(self):
        """Test title extraction from synthesized content."""
        from emdx.services.synthesis_service import SynthesisService

        service = SynthesisService()

        # Test H1 extraction
        content_with_h1 = "# My Synthesized Document\n\nSome content here."
        documents = [(1, "Doc 1", ""), (2, "Doc 2", "")]

        title = service._extract_title(content_with_h1, documents)
        assert title == "My Synthesized Document"

        # Test fallback when no H1
        content_no_h1 = "No heading here\nJust content."
        title = service._extract_title(content_no_h1, documents)
        assert "synthesis" in title.lower()

    def test_synthesis_service_estimate_cost(self, temp_db):
        """Test cost estimation."""
        # Save some test documents
        doc1_id = temp_db.save_document(
            title="Test Doc 1",
            content="A" * 4000,  # ~1000 tokens
            project="test",
        )
        doc2_id = temp_db.save_document(
            title="Test Doc 2",
            content="B" * 4000,  # ~1000 tokens
            project="test",
        )

        with patch("emdx.services.synthesis_service.db") as mock_db:
            mock_conn = temp_db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn
                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            from emdx.services.synthesis_service import SynthesisService

            service = SynthesisService()
            estimate = service.estimate_cost([doc1_id, doc2_id])

            assert estimate["document_count"] == 2
            assert estimate["estimated_input_tokens"] > 0
            assert estimate["estimated_output_tokens"] > 0
            assert estimate["estimated_cost_usd"] > 0

    def test_synthesis_service_with_mocked_api(self, temp_db):
        """Test full synthesis flow with mocked Anthropic API."""
        # Save test documents
        doc1_id = temp_db.save_document(
            title="Python Basics",
            content="Python is a programming language. It has simple syntax.",
            project="test",
        )
        doc2_id = temp_db.save_document(
            title="Python Guide",
            content="This guide covers Python programming fundamentals.",
            project="test",
        )

        with patch("emdx.services.synthesis_service.db") as mock_db, \
             patch("emdx.services.synthesis_service.HAS_ANTHROPIC", True):

            mock_conn = temp_db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn
                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            # Create mock Anthropic client
            mock_anthropic = MagicMock()
            mock_response = MagicMock()
            synth_text = "# Python Complete Guide\n\nSynthesized content."
            mock_response.content = [MagicMock(text=synth_text)]
            mock_response.usage.input_tokens = 100
            mock_response.usage.output_tokens = 50
            mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

            with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
                from emdx.services.synthesis_service import SynthesisService

                service = SynthesisService()
                service._client = mock_anthropic.Anthropic()

                result = service.synthesize_documents([doc1_id, doc2_id])

                assert result.title == "Python Complete Guide"
                assert "Synthesized content" in result.content
                assert result.input_tokens == 100
                assert result.output_tokens == 50
                assert result.source_doc_ids == [doc1_id, doc2_id]


class TestCompactCommand:
    """Tests for the compact CLI command."""

    def test_compact_dry_run_no_clusters(self, temp_db):
        """Test dry-run with no similar documents."""
        from typer.testing import CliRunner

        from emdx.commands.compact import app

        # Save documents with very different content
        temp_db.save_document(
            title="Python Guide",
            content="Python programming language guide with syntax examples.",
            project="test",
        )
        temp_db.save_document(
            title="Cooking Recipes",
            content="Delicious recipes for pasta and pizza with Italian herbs.",
            project="test",
        )

        runner = CliRunner()

        with patch("emdx.commands.compact.db"), \
             patch("emdx.commands.compact._fetch_all_documents") as mock_fetch:

            # Return documents that are very different
            from emdx.commands.compact import DocumentInfo
            mock_fetch.return_value = [
                DocumentInfo(
                    id=1,
                    title="Python Guide",
                    content="Python programming language guide with syntax examples.",
                    tags=[],
                ),
                DocumentInfo(
                    id=2,
                    title="Cooking Recipes",
                    content="Delicious recipes for pasta and pizza with Italian herbs.",
                    tags=[],
                ),
            ]

            result = runner.invoke(app, ["--dry-run", "--threshold", "0.9"])

            # Should complete without error
            assert result.exit_code == 0

    def test_compact_requires_multiple_doc_ids(self):
        """Test that compact with single doc ID fails."""
        from typer.testing import CliRunner

        from emdx.commands.compact import app

        runner = CliRunner()

        with patch("emdx.commands.compact.db"):
            result = runner.invoke(app, ["42"])

            assert result.exit_code == 1
            assert "at least 2 documents" in result.output.lower()

    def test_compact_displays_clusters(self, temp_db):
        """Test that dry-run displays found clusters."""
        from typer.testing import CliRunner

        from emdx.commands.compact import app

        runner = CliRunner()

        with patch("emdx.commands.compact._fetch_all_documents") as mock_fetch:
            from emdx.commands.compact import DocumentInfo
            mock_fetch.return_value = [
                DocumentInfo(
                    id=1,
                    title="Python ML Guide",
                    content="Machine learning with Python using scikit-learn TensorFlow.",
                    tags=["python", "ml"],
                ),
                DocumentInfo(
                    id=2,
                    title="Python Machine Learning Tutorial",
                    content="Machine learning tutorial Python scikit-learn TensorFlow neural.",
                    tags=["python", "ml"],
                ),
            ]

            result = runner.invoke(app, ["--dry-run", "--threshold", "0.3"])

            # Should show some output about documents
            assert result.exit_code == 0
            assert "document" in result.output.lower() or "cluster" in result.output.lower()
