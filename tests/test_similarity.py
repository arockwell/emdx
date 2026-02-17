"""Tests for the TF-IDF similarity service."""

from pathlib import Path
from unittest.mock import patch

import pytest

# Skip all tests if sklearn not installed - must come before module imports
sklearn = pytest.importorskip(
    "sklearn", reason="scikit-learn not installed (install with: pip install 'emdx[similarity]')"
)  # noqa: E501

from emdx.services.similarity import IndexStats, SimilarDocument, SimilarityService  # noqa: E402


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / ".config" / "emdx"
    cache_dir.mkdir(parents=True)
    return cache_dir


@pytest.fixture
def similarity_service(temp_cache_dir, temp_db):
    """Create a SimilarityService with mocked cache and database."""
    # Patch the cache directory
    with patch.object(SimilarityService, "__init__", lambda self, db_path=None: None):
        service = object.__new__(SimilarityService)
        service._cache_dir = temp_cache_dir
        service._cache_path = temp_cache_dir / "similarity_cache.pkl"
        service._vectorizer = None
        service._tfidf_matrix = None
        service._doc_ids = []
        service._doc_titles = []
        service._doc_projects = []
        service._doc_tags = []
        service._last_built = None
    return service


@pytest.fixture
def populated_db(temp_db):
    """Create a database with test documents for similarity testing."""
    docs = [
        {
            "title": "Python Machine Learning Guide",
            "content": """Machine learning is a subset of artificial intelligence.
            Python is the most popular language for machine learning.
            Libraries like scikit-learn, TensorFlow, and PyTorch are commonly used.
            This guide covers supervised and unsupervised learning algorithms.""",
            "project": "ml-project",
            "tags": ["python", "machine-learning", "guide"],
        },
        {
            "title": "Python Data Science Tutorial",
            "content": """Data science involves extracting insights from data.
            Python with pandas and numpy is great for data analysis.
            Machine learning models can be used for predictions.
            This tutorial covers data visualization with matplotlib.""",
            "project": "ml-project",
            "tags": ["python", "data-science", "tutorial"],
        },
        {
            "title": "Docker Container Guide",
            "content": """Docker containers are lightweight virtualization.
            Containers package applications with their dependencies.
            Docker Compose orchestrates multi-container applications.
            This guide covers Dockerfile best practices.""",
            "project": "devops-project",
            "tags": ["docker", "containers", "devops"],
        },
        {
            "title": "Kubernetes Deployment Tutorial",
            "content": """Kubernetes orchestrates container deployments.
            It works with Docker containers and other runtimes.
            Services, deployments, and pods are key concepts.
            This tutorial covers production deployments.""",
            "project": "devops-project",
            "tags": ["kubernetes", "containers", "devops"],
        },
        {
            "title": "Git Version Control",
            "content": """Git is a distributed version control system.
            Branches allow parallel development workflows.
            Commits track changes to your codebase.
            This covers merging and rebasing strategies.""",
            "project": "tools-project",
            "tags": ["git", "version-control"],
        },
    ]

    doc_ids = []
    conn = temp_db.get_connection()

    for doc in docs:
        doc_id = temp_db.save_document(
            title=doc["title"], content=doc["content"], project=doc["project"]
        )
        doc_ids.append(doc_id)

        # Add tags directly via SQL
        for tag_name in doc["tags"]:
            tag_name = tag_name.lower().strip()
            cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            result = cursor.fetchone()
            if result:
                tag_id = result[0]
            else:
                cursor = conn.execute(
                    "INSERT INTO tags (name, usage_count) VALUES (?, 0)", (tag_name,)
                )
                tag_id = cursor.lastrowid

            conn.execute(
                "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )
            conn.execute(
                "UPDATE tags SET usage_count = usage_count + 1 WHERE id = ?",
                (tag_id,),
            )

    conn.commit()
    return {"db": temp_db, "doc_ids": doc_ids}


class TestSimilarDocument:
    """Tests for SimilarDocument dataclass."""

    def test_similar_document_creation(self):
        """Test creating a SimilarDocument instance."""
        doc = SimilarDocument(
            doc_id=42,
            title="Test Document",
            project="test-project",
            similarity_score=0.85,
            content_similarity=0.9,
            tag_similarity=0.7,
            common_tags=["python", "testing"],
        )

        assert doc.doc_id == 42
        assert doc.title == "Test Document"
        assert doc.project == "test-project"
        assert doc.similarity_score == 0.85
        assert doc.content_similarity == 0.9
        assert doc.tag_similarity == 0.7
        assert doc.common_tags == ["python", "testing"]


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_index_stats_creation(self):
        """Test creating an IndexStats instance."""
        from datetime import datetime

        now = datetime.now()
        stats = IndexStats(
            document_count=100,
            vocabulary_size=5000,
            cache_size_bytes=1024000,
            cache_age_seconds=3600.0,
            last_built=now,
        )

        assert stats.document_count == 100
        assert stats.vocabulary_size == 5000
        assert stats.cache_size_bytes == 1024000
        assert stats.cache_age_seconds == 3600.0
        assert stats.last_built == now


class TestSimilarityServiceUnit:
    """Unit tests for SimilarityService."""

    def test_calculate_tag_similarity_identical_tags(self):
        """Test Jaccard similarity for identical tag sets."""
        service = SimilarityService.__new__(SimilarityService)
        service._cache_dir = Path("/tmp")
        service._cache_path = Path("/tmp/test_cache.pkl")

        tags1 = {"python", "testing", "pytest"}
        tags2 = {"python", "testing", "pytest"}

        similarity = service._calculate_tag_similarity(tags1, tags2)
        assert similarity == 1.0

    def test_calculate_tag_similarity_partial_overlap(self):
        """Test Jaccard similarity for partially overlapping tags."""
        service = SimilarityService.__new__(SimilarityService)
        service._cache_dir = Path("/tmp")
        service._cache_path = Path("/tmp/test_cache.pkl")

        tags1 = {"python", "testing", "pytest"}
        tags2 = {"python", "testing", "unittest"}

        # Intersection: {python, testing} = 2
        # Union: {python, testing, pytest, unittest} = 4
        # Jaccard = 2/4 = 0.5
        similarity = service._calculate_tag_similarity(tags1, tags2)
        assert similarity == 0.5

    def test_calculate_tag_similarity_no_overlap(self):
        """Test Jaccard similarity for non-overlapping tags."""
        service = SimilarityService.__new__(SimilarityService)
        service._cache_dir = Path("/tmp")
        service._cache_path = Path("/tmp/test_cache.pkl")

        tags1 = {"python", "testing"}
        tags2 = {"docker", "kubernetes"}

        similarity = service._calculate_tag_similarity(tags1, tags2)
        assert similarity == 0.0

    def test_calculate_tag_similarity_empty_sets(self):
        """Test Jaccard similarity for empty tag sets."""
        service = SimilarityService.__new__(SimilarityService)
        service._cache_dir = Path("/tmp")
        service._cache_path = Path("/tmp/test_cache.pkl")

        assert service._calculate_tag_similarity(set(), set()) == 0.0
        assert service._calculate_tag_similarity({"python"}, set()) == 0.0
        assert service._calculate_tag_similarity(set(), {"python"}) == 0.0


class TestSimilarityServiceIntegration:
    """Integration tests for SimilarityService with database."""

    def test_build_index_empty_database(self, temp_db, temp_cache_dir):
        """Test building index with empty database."""
        with patch("emdx.services.similarity.db") as mock_db:
            # Set up mock to return empty results
            mock_conn = temp_db.get_connection()
            mock_db.get_connection.return_value.__enter__ = lambda s: mock_conn
            mock_db.get_connection.return_value.__exit__ = lambda s, *args: None

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            stats = service.build_index()

            assert stats.document_count == 0
            assert stats.vocabulary_size == 0

    def test_build_index_with_documents(self, populated_db, temp_cache_dir):
        """Test building index with documents."""
        db = populated_db["db"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            stats = service.build_index()

            assert stats.document_count == 5
            assert stats.vocabulary_size > 0
            assert service._cache_path.exists()

    def test_find_similar_returns_ordered_results(self, populated_db, temp_cache_dir):
        """Test that similar documents are returned in order of similarity."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            # Find similar to the first Python ML document
            results = service.find_similar(doc_ids[0], limit=4)

            assert len(results) > 0
            # Results should be sorted by similarity (descending)
            for i in range(len(results) - 1):
                assert results[i].similarity_score >= results[i + 1].similarity_score

    def test_find_similar_respects_limit(self, populated_db, temp_cache_dir):
        """Test that limit parameter is respected."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            results = service.find_similar(doc_ids[0], limit=2)
            assert len(results) <= 2

    def test_find_similar_respects_threshold(self, populated_db, temp_cache_dir):
        """Test that min_similarity threshold filters results."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            # With very high threshold, should get fewer results
            high_threshold_results = service.find_similar(doc_ids[0], limit=10, min_similarity=0.9)
            low_threshold_results = service.find_similar(doc_ids[0], limit=10, min_similarity=0.01)

            # All high threshold results should meet the threshold
            for result in high_threshold_results:
                assert result.similarity_score >= 0.9

            # Low threshold should return more results
            assert len(low_threshold_results) >= len(high_threshold_results)

    def test_content_only_ignores_tags(self, populated_db, temp_cache_dir):
        """Test that content_only=True uses only TF-IDF similarity."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            results = service.find_similar(doc_ids[0], limit=5, content_only=True)

            # In content-only mode, score should equal content_similarity
            for result in results:
                assert result.similarity_score == result.content_similarity

    def test_tags_only_ignores_content(self, populated_db, temp_cache_dir):
        """Test that tags_only=True uses only tag similarity."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            results = service.find_similar(doc_ids[0], limit=5, tags_only=True)

            # In tags-only mode, score should equal tag_similarity
            for result in results:
                assert result.similarity_score == result.tag_similarity

    def test_same_project_filters_results(self, populated_db, temp_cache_dir):
        """Test that same_project=True only returns docs from same project."""
        db = populated_db["db"]
        doc_ids = populated_db["doc_ids"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            # Query for first doc (ml-project)
            results = service.find_similar(doc_ids[0], limit=10, same_project=True)

            # All results should be from ml-project
            for result in results:
                assert result.project == "ml-project"

    def test_find_similar_by_text(self, populated_db, temp_cache_dir):
        """Test finding similar documents by text query."""
        db = populated_db["db"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()

            # Search for machine learning content
            results = service.find_similar_by_text("machine learning python scikit-learn", limit=5)

            assert len(results) > 0
            # The Python ML documents should rank highly
            top_titles = [r.title for r in results[:2]]
            assert any(
                "Python" in t and ("Machine Learning" in t or "Data Science" in t)
                for t in top_titles
            )

    def test_cache_invalidation(self, populated_db, temp_cache_dir):
        """Test that invalidate_cache clears the index."""
        db = populated_db["db"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            # Build index first
            service.build_index()
            assert service._cache_path.exists()
            assert service._vectorizer is not None

            # Invalidate cache
            service.invalidate_cache()

            assert not service._cache_path.exists()
            assert service._vectorizer is None
            assert len(service._doc_ids) == 0

    def test_get_index_stats(self, populated_db, temp_cache_dir):
        """Test getting index statistics."""
        db = populated_db["db"]

        with patch("emdx.services.similarity.db") as mock_db:
            mock_conn = db.get_connection()

            class MockContextManager:
                def __enter__(self):
                    return mock_conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            service = SimilarityService.__new__(SimilarityService)
            service._cache_dir = temp_cache_dir
            service._cache_path = temp_cache_dir / "similarity_cache.pkl"
            service._vectorizer = None
            service._tfidf_matrix = None
            service._doc_ids = []
            service._doc_titles = []
            service._doc_projects = []
            service._doc_tags = []
            service._last_built = None

            service.build_index()
            stats = service.get_index_stats()

            assert stats.document_count == 5
            assert stats.vocabulary_size > 0
            assert stats.cache_size_bytes > 0
            assert stats.last_built is not None
