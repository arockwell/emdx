"""Tests for the document merger service with TF-IDF pre-filtering."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.document_merger import (
    DocumentMerger,
    MergeCandidate,
    MergeStrategy,
)


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / ".config" / "emdx"
    cache_dir.mkdir(parents=True)
    return cache_dir


@pytest.fixture
def merger_documents(temp_db):
    """Create test documents for merge candidate testing.

    Includes similar and dissimilar documents to test the TF-IDF filtering.
    """
    docs = [
        # Group 1: Similar Python ML documents
        {
            "title": "Python Machine Learning Guide",
            "content": """Machine learning is a subset of artificial intelligence.
            Python is the most popular language for machine learning.
            Libraries like scikit-learn, TensorFlow, and PyTorch are commonly used.
            This guide covers supervised and unsupervised learning algorithms.
            Neural networks and deep learning are advanced topics.""",
            "project": "ml-project",
        },
        {
            "title": "Python Machine Learning Tutorial",
            "content": """Machine learning with Python is powerful.
            Python's scikit-learn library provides many machine learning algorithms.
            TensorFlow and PyTorch are used for deep learning.
            This tutorial covers supervised learning and neural networks.
            Deep learning models can learn complex patterns.""",
            "project": "ml-project",
        },
        # Group 2: Similar Docker documents
        {
            "title": "Docker Container Guide",
            "content": """Docker containers are lightweight virtualization.
            Containers package applications with their dependencies.
            Docker Compose orchestrates multi-container applications.
            This guide covers Dockerfile best practices.
            Container images are built from Dockerfiles.""",
            "project": "devops-project",
        },
        {
            "title": "Docker Container Tutorial",
            "content": """Docker provides container virtualization.
            Applications and dependencies are packaged in containers.
            Docker Compose manages multi-container deployments.
            This tutorial covers Dockerfile creation.
            Building container images is straightforward.""",
            "project": "devops-project",
        },
        # Unrelated document
        {
            "title": "Git Version Control",
            "content": """Git is a distributed version control system.
            Branches allow parallel development workflows.
            Commits track changes to your codebase.
            This covers merging and rebasing strategies.
            Git remotes enable collaboration.""",
            "project": "tools-project",
        },
    ]

    doc_ids = []
    conn = temp_db.get_connection()

    for doc in docs:
        doc_id = temp_db.save_document(
            title=doc["title"], content=doc["content"], project=doc["project"]
        )
        doc_ids.append(doc_id)

    conn.commit()
    return {"db": temp_db, "doc_ids": doc_ids}


@pytest.fixture
def high_access_documents(temp_db):
    """Create documents with high access counts."""
    conn = temp_db.get_connection()

    # Create two similar documents with high access counts
    doc1_id = temp_db.save_document(
        title="Popular Guide A",
        content="This is a very popular document about Python programming.",
        project="test-project"
    )
    doc2_id = temp_db.save_document(
        title="Popular Guide B",
        content="This is a very popular document about Python programming.",
        project="test-project"
    )

    # Set high access counts
    conn.execute("UPDATE documents SET access_count = 100 WHERE id = ?", (doc1_id,))
    conn.execute("UPDATE documents SET access_count = 75 WHERE id = ?", (doc2_id,))
    conn.commit()

    return {"db": temp_db, "doc_ids": [doc1_id, doc2_id]}


class TestMergeCandidate:
    """Tests for MergeCandidate dataclass."""

    def test_merge_candidate_creation(self):
        """Test creating a MergeCandidate instance."""
        candidate = MergeCandidate(
            doc1_id=1,
            doc2_id=2,
            doc1_title="Document A",
            doc2_title="Document B",
            similarity_score=0.85,
            merge_reason="Similar content",
            recommended_action="Merge into #1 (more views)"
        )

        assert candidate.doc1_id == 1
        assert candidate.doc2_id == 2
        assert candidate.doc1_title == "Document A"
        assert candidate.doc2_title == "Document B"
        assert candidate.similarity_score == 0.85
        assert candidate.merge_reason == "Similar content"
        assert candidate.recommended_action == "Merge into #1 (more views)"


class TestMergeStrategy:
    """Tests for MergeStrategy dataclass."""

    def test_merge_strategy_creation(self):
        """Test creating a MergeStrategy instance."""
        strategy = MergeStrategy(
            keep_doc_id=1,
            merge_doc_id=2,
            merged_title="Combined Document",
            merged_content="Full merged content here",
            merged_tags=["python", "testing"],
            preserve_metadata={"original_ids": [1, 2]}
        )

        assert strategy.keep_doc_id == 1
        assert strategy.merge_doc_id == 2
        assert strategy.merged_title == "Combined Document"
        assert strategy.merged_content == "Full merged content here"
        assert strategy.merged_tags == ["python", "testing"]
        assert strategy.preserve_metadata == {"original_ids": [1, 2]}


class TestDocumentMergerUnit:
    """Unit tests for DocumentMerger."""

    def test_calculate_similarity_identical(self):
        """Test similarity calculation for identical strings."""
        merger = DocumentMerger.__new__(DocumentMerger)

        similarity = merger._calculate_similarity("hello world", "hello world")
        assert similarity == 1.0

    def test_calculate_similarity_similar(self):
        """Test similarity calculation for similar strings."""
        merger = DocumentMerger.__new__(DocumentMerger)

        similarity = merger._calculate_similarity(
            "Python machine learning guide",
            "Python machine learning tutorial"
        )
        assert similarity > 0.7

    def test_calculate_similarity_different(self):
        """Test similarity calculation for different strings."""
        merger = DocumentMerger.__new__(DocumentMerger)

        similarity = merger._calculate_similarity(
            "Docker containers and kubernetes orchestration",
            "Python programming language fundamentals"
        )
        assert similarity < 0.5

    def test_calculate_similarity_empty(self):
        """Test similarity calculation with empty strings."""
        merger = DocumentMerger.__new__(DocumentMerger)

        assert merger._calculate_similarity("", "text") == 0.0
        assert merger._calculate_similarity("text", "") == 0.0
        assert merger._calculate_similarity("", "") == 0.0
        assert merger._calculate_similarity(None, "text") == 0.0


class TestDocumentMergerIntegration:
    """Integration tests for DocumentMerger with TF-IDF pre-filtering."""

    def test_find_merge_candidates_finds_similar_docs(
        self, merger_documents, temp_cache_dir
    ):
        """Test that find_merge_candidates identifies similar documents."""
        db = merger_documents["db"]
        doc_ids = merger_documents["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_sim_db, \
             patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:

            # Set up mock similarity service
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            # Mock the find_all_duplicate_pairs to return similar pairs
            mock_service.find_all_duplicate_pairs.return_value = [
                (doc_ids[0], doc_ids[1], "Python Machine Learning Guide",
                 "Python Machine Learning Tutorial", 0.85),
                (doc_ids[2], doc_ids[3], "Docker Container Guide",
                 "Docker Container Tutorial", 0.82),
            ]
            mock_service.build_index.return_value = None

            # Create merger with mocked database
            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            # Mock _get_document_metadata
            def mock_metadata(project=None):
                return {
                    doc_ids[0]: {"title": "Python Machine Learning Guide", "content": "ML content", "project": "ml-project", "access_count": 5},
                    doc_ids[1]: {"title": "Python Machine Learning Tutorial", "content": "ML tutorial", "project": "ml-project", "access_count": 3},
                    doc_ids[2]: {"title": "Docker Container Guide", "content": "Docker content", "project": "devops-project", "access_count": 10},
                    doc_ids[3]: {"title": "Docker Container Tutorial", "content": "Docker tutorial", "project": "devops-project", "access_count": 2},
                    doc_ids[4]: {"title": "Git Version Control", "content": "Git content", "project": "tools-project", "access_count": 1},
                }

            merger._get_document_metadata = mock_metadata

            candidates = merger.find_merge_candidates(similarity_threshold=0.7)

            # Should find the similar document pairs
            assert len(candidates) >= 2

            # Check that candidates are sorted by similarity
            for i in range(len(candidates) - 1):
                assert candidates[i].similarity_score >= candidates[i + 1].similarity_score

    def test_find_merge_candidates_respects_project_filter(
        self, merger_documents, temp_cache_dir
    ):
        """Test that project filter works correctly."""
        db = merger_documents["db"]
        doc_ids = merger_documents["doc_ids"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            # Return pairs from different projects
            mock_service.find_all_duplicate_pairs.return_value = [
                (doc_ids[0], doc_ids[1], "Python ML Guide", "Python ML Tutorial", 0.85),
                (doc_ids[2], doc_ids[3], "Docker Guide", "Docker Tutorial", 0.82),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            def mock_metadata(project=None):
                all_docs = {
                    doc_ids[0]: {"title": "Python ML Guide", "content": "content", "project": "ml-project", "access_count": 5},
                    doc_ids[1]: {"title": "Python ML Tutorial", "content": "content", "project": "ml-project", "access_count": 3},
                    doc_ids[2]: {"title": "Docker Guide", "content": "content", "project": "devops-project", "access_count": 10},
                    doc_ids[3]: {"title": "Docker Tutorial", "content": "content", "project": "devops-project", "access_count": 2},
                }
                if project:
                    return {k: v for k, v in all_docs.items() if v["project"] == project}
                return all_docs

            merger._get_document_metadata = mock_metadata

            # Filter by ml-project
            candidates = merger.find_merge_candidates(
                project="ml-project",
                similarity_threshold=0.7
            )

            # Should only find ML document pair
            for candidate in candidates:
                # The candidate should be from ml-project
                assert candidate.doc1_id in [doc_ids[0], doc_ids[1]]
                assert candidate.doc2_id in [doc_ids[0], doc_ids[1]]

    def test_find_merge_candidates_skips_high_access_docs(
        self, high_access_documents, temp_cache_dir
    ):
        """Test that pairs with both high access counts are skipped."""
        db = high_access_documents["db"]
        doc_ids = high_access_documents["doc_ids"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            # Return pair of high-access documents
            mock_service.find_all_duplicate_pairs.return_value = [
                (doc_ids[0], doc_ids[1], "Popular Guide A", "Popular Guide B", 0.95),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            def mock_metadata(project=None):
                return {
                    doc_ids[0]: {"title": "Popular Guide A", "content": "content", "project": "test-project", "access_count": 100},
                    doc_ids[1]: {"title": "Popular Guide B", "content": "content", "project": "test-project", "access_count": 75},
                }

            merger._get_document_metadata = mock_metadata

            candidates = merger.find_merge_candidates(similarity_threshold=0.7)

            # Should skip pairs where both have high access counts
            assert len(candidates) == 0

    def test_find_merge_candidates_progress_callback(
        self, merger_documents, temp_cache_dir
    ):
        """Test that progress callback is called correctly."""
        db = merger_documents["db"]
        doc_ids = merger_documents["doc_ids"]

        progress_calls = []

        def progress_callback(current, total, found):
            progress_calls.append((current, total, found))

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service
            mock_service.find_all_duplicate_pairs.return_value = []
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service
            merger._get_document_metadata = lambda p=None: {}

            merger.find_merge_candidates(
                similarity_threshold=0.7,
                progress_callback=progress_callback
            )

            # Should have called progress callback multiple times
            assert len(progress_calls) > 0
            # Last call should be at 100%
            assert progress_calls[-1][0] == 100

    def test_find_merge_candidates_merge_reason_titles(
        self, merger_documents, temp_cache_dir
    ):
        """Test that merge reason correctly identifies similar titles."""
        db = merger_documents["db"]
        doc_ids = merger_documents["doc_ids"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            # Return pair with very similar titles
            mock_service.find_all_duplicate_pairs.return_value = [
                (1, 2, "Python Machine Learning Guide", "Python Machine Learning Guide", 0.95),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            def mock_metadata(project=None):
                return {
                    1: {"title": "Python Machine Learning Guide", "content": "a" * 100, "project": "ml", "access_count": 5},
                    2: {"title": "Python Machine Learning Guide", "content": "b" * 50, "project": "ml", "access_count": 3},
                }

            merger._get_document_metadata = mock_metadata

            candidates = merger.find_merge_candidates(similarity_threshold=0.5)

            assert len(candidates) > 0
            # Identical titles should give "Nearly identical titles" reason
            assert candidates[0].merge_reason == "Nearly identical titles"

    def test_find_merge_candidates_recommended_action_views(
        self, merger_documents, temp_cache_dir
    ):
        """Test recommended action based on view count."""
        db = merger_documents["db"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            mock_service.find_all_duplicate_pairs.return_value = [
                (1, 2, "Doc A", "Doc B", 0.85),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            def mock_metadata(project=None):
                return {
                    1: {"title": "Doc A", "content": "content", "project": "test", "access_count": 20},
                    2: {"title": "Doc B", "content": "content", "project": "test", "access_count": 5},
                }

            merger._get_document_metadata = mock_metadata

            candidates = merger.find_merge_candidates(similarity_threshold=0.5)

            assert len(candidates) > 0
            assert "more views" in candidates[0].recommended_action
            assert "#1" in candidates[0].recommended_action

    def test_find_merge_candidates_recommended_action_content(
        self, merger_documents, temp_cache_dir
    ):
        """Test recommended action based on content length when views are equal."""
        db = merger_documents["db"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            mock_service.find_all_duplicate_pairs.return_value = [
                (1, 2, "Doc A", "Doc B", 0.85),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service

            def mock_metadata(project=None):
                return {
                    1: {"title": "Doc A", "content": "a" * 500, "project": "test", "access_count": 5},
                    2: {"title": "Doc B", "content": "b" * 100, "project": "test", "access_count": 5},
                }

            merger._get_document_metadata = mock_metadata

            candidates = merger.find_merge_candidates(similarity_threshold=0.5)

            assert len(candidates) > 0
            assert "more content" in candidates[0].recommended_action
            assert "#1" in candidates[0].recommended_action


class TestDocumentMergerHelpers:
    """Tests for helper methods of DocumentMerger."""

    def test_get_document_metadata(self, merger_documents):
        """Test fetching document metadata."""
        db = merger_documents["db"]
        doc_ids = merger_documents["doc_ids"]

        with patch("emdx.services.document_merger.SimilarityService"):
            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = MagicMock()

            metadata = merger._get_document_metadata()

            # Should have all documents
            assert len(metadata) == 5

            # Check structure
            for doc_id in doc_ids:
                assert doc_id in metadata
                assert "title" in metadata[doc_id]
                assert "content" in metadata[doc_id]
                assert "project" in metadata[doc_id]
                assert "access_count" in metadata[doc_id]

    def test_get_document_metadata_with_project_filter(self, merger_documents):
        """Test fetching document metadata with project filter."""
        db = merger_documents["db"]

        with patch("emdx.services.document_merger.SimilarityService"):
            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = MagicMock()

            metadata = merger._get_document_metadata(project="ml-project")

            # Should only have ML project documents
            assert len(metadata) == 2
            for doc_meta in metadata.values():
                assert doc_meta["project"] == "ml-project"


class TestTFIDFPrefiltering:
    """Tests specifically for the TF-IDF pre-filtering optimization."""

    def test_prefilter_threshold_lower_than_main_threshold(self):
        """Verify pre-filter threshold is lower to catch edge cases."""
        merger = DocumentMerger.__new__(DocumentMerger)

        # PREFILTER_THRESHOLD should be lower than SIMILARITY_THRESHOLD
        assert merger.PREFILTER_THRESHOLD < merger.SIMILARITY_THRESHOLD

    def test_uses_similarity_service(self, merger_documents, temp_cache_dir):
        """Verify that SimilarityService is used for pre-filtering."""
        db = merger_documents["db"]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service
            mock_service.find_all_duplicate_pairs.return_value = []
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = db
            merger._similarity_service = mock_service
            merger._get_document_metadata = lambda p=None: {}

            merger.find_merge_candidates()

            # Should have called build_index
            mock_service.build_index.assert_called_once_with(force=True)
            # Should have called find_all_duplicate_pairs
            mock_service.find_all_duplicate_pairs.assert_called_once()

    def test_efficient_at_scale(self, temp_db, temp_cache_dir):
        """Test that the algorithm scales efficiently (doesn't do O(n²) comparisons)."""
        # Create many documents
        for i in range(50):
            temp_db.save_document(
                title=f"Document {i}",
                content=f"Content for document {i} with some text",
                project="test-project"
            )

        comparison_count = [0]

        with patch("emdx.services.document_merger.SimilarityService") as MockSimilarityService:
            mock_service = MagicMock()
            MockSimilarityService.return_value = mock_service

            # Only return a few candidates (simulating TF-IDF filtering)
            mock_service.find_all_duplicate_pairs.return_value = [
                (1, 2, "Doc 1", "Doc 2", 0.8),
                (3, 4, "Doc 3", "Doc 4", 0.75),
            ]
            mock_service.build_index.return_value = None

            merger = DocumentMerger.__new__(DocumentMerger)
            merger.db_path = Path(":memory:")
            merger._db = temp_db
            merger._similarity_service = mock_service

            # Track calls to _calculate_similarity
            original_calc = DocumentMerger._calculate_similarity
            def tracking_calc(self, t1, t2):
                comparison_count[0] += 1
                return original_calc(self, t1, t2)

            merger._calculate_similarity = lambda t1, t2: tracking_calc(merger, t1, t2)
            merger._get_document_metadata = lambda p=None: {
                1: {"title": "Doc 1", "content": "c", "project": "p", "access_count": 1},
                2: {"title": "Doc 2", "content": "c", "project": "p", "access_count": 1},
                3: {"title": "Doc 3", "content": "c", "project": "p", "access_count": 1},
                4: {"title": "Doc 4", "content": "c", "project": "p", "access_count": 1},
            }

            merger.find_merge_candidates()

            # Should only do detailed comparison on pre-filtered candidates
            # NOT on all 50*49/2 = 1225 pairs
            # With 2 pre-filtered pairs, we expect ~2 title comparisons
            assert comparison_count[0] <= 5  # Small number, not O(n²)
