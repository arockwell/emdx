"""Tests for the explore command.

Tests cover:
- Unit tests for clustering and topic label extraction
- Unit tests for gap detection
- Integration tests for the explore CLI command
"""


import pytest

# Skip all tests if sklearn not installed
sklearn = pytest.importorskip(
    "sklearn",
    reason="scikit-learn not installed (install with: pip install 'emdx[similarity]')"
)


@pytest.fixture
def clean_db(isolate_test_database):
    """Ensure clean database for each test."""
    from emdx.database import db

    def cleanup():
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM tasks")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    yield
    cleanup()


@pytest.fixture
def sample_docs(clean_db):
    """Create sample documents spanning multiple topics."""
    from emdx.database import db

    docs = []
    with db.get_connection() as conn:
        # Python/ML cluster
        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 10)""",
            (
                "Python Machine Learning Guide",
                "Python is widely used in machine learning and data science. "
                "Libraries like scikit-learn, TensorFlow, and PyTorch make it "
                "the go-to language for training neural networks and building "
                "predictive models. Data preprocessing with pandas and numpy "
                "is essential for any ML pipeline." * 3,
                "ml-project",
            ),
        )
        docs.append(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 8)""",
            (
                "Deep Learning with PyTorch",
                "PyTorch is a popular deep learning framework for Python. "
                "It provides automatic differentiation and GPU acceleration "
                "for training neural networks. Common architectures include "
                "CNNs for image recognition and transformers for NLP tasks. "
                "Data loading with DataLoader and Dataset classes." * 3,
                "ml-project",
            ),
        )
        docs.append(cursor.lastrowid)

        # Web development cluster
        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 5)""",
            (
                "React Frontend Development",
                "React is a JavaScript library for building user interfaces. "
                "Components, hooks, and state management are key concepts. "
                "Next.js provides server-side rendering and routing. "
                "CSS-in-JS solutions like styled-components are popular. "
                "TypeScript adds type safety to React projects." * 3,
                "web-project",
            ),
        )
        docs.append(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 12)""",
            (
                "Node.js API Development",
                "Node.js enables JavaScript server-side development. "
                "Express.js is the most popular web framework for building "
                "REST APIs. Middleware handles authentication and validation. "
                "MongoDB or PostgreSQL for database integration. "
                "TypeScript improves code quality in Node.js projects." * 3,
                "web-project",
            ),
        )
        docs.append(cursor.lastrowid)

        # Singleton (unrelated)
        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 2)""",
            (
                "Sourdough Bread Recipe",
                "Mix flour, water, salt, and sourdough starter. "
                "Knead the dough for ten minutes until smooth. "
                "Let it rise for four hours at room temperature. "
                "Shape and proof overnight in the refrigerator. "
                "Bake at 450F in a Dutch oven for 40 minutes." * 3,
                None,
            ),
        )
        docs.append(cursor.lastrowid)

        conn.commit()

    return docs


class TestTfidfAndClustering:
    """Unit tests for the core clustering logic."""

    def test_compute_tfidf_returns_matrix_and_vectorizer(self, sample_docs):
        """_compute_tfidf returns a matrix, doc_ids, and vectorizer."""
        from emdx.commands.explore import _compute_tfidf, _fetch_all_documents

        documents = _fetch_all_documents()
        tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(documents)

        assert tfidf_matrix is not None
        assert len(doc_ids) == len(documents)
        assert hasattr(vectorizer, "get_feature_names_out")

    def test_find_clusters_groups_similar_docs(self):
        """Similar documents form clusters."""
        import numpy as np

        from emdx.commands.explore import _find_clusters

        # High similarity between docs 0,1 and between docs 2,3
        matrix = np.array([
            [1.0, 0.8, 0.1, 0.1, 0.05],
            [0.8, 1.0, 0.1, 0.1, 0.05],
            [0.1, 0.1, 1.0, 0.7, 0.05],
            [0.1, 0.1, 0.7, 1.0, 0.05],
            [0.05, 0.05, 0.05, 0.05, 1.0],
        ])
        clusters = _find_clusters(matrix, [10, 11, 20, 21, 30], threshold=0.5)

        assert len(clusters) == 2
        cluster_sets = [set(c) for c in clusters]
        assert {10, 11} in cluster_sets
        assert {20, 21} in cluster_sets

    def test_find_clusters_empty(self):
        """Empty input returns empty clusters."""
        import numpy as np

        from emdx.commands.explore import _find_clusters

        clusters = _find_clusters(np.array([]), [], threshold=0.5)
        assert clusters == []

    def test_find_clusters_no_similar(self):
        """Dissimilar documents produce no clusters."""
        import numpy as np

        from emdx.commands.explore import _find_clusters

        matrix = np.array([
            [1.0, 0.1, 0.05],
            [0.1, 1.0, 0.05],
            [0.05, 0.05, 1.0],
        ])
        clusters = _find_clusters(matrix, [1, 2, 3], threshold=0.5)
        assert clusters == []

    def test_clusters_sorted_by_size_descending(self):
        """Clusters are returned largest first."""
        import numpy as np

        from emdx.commands.explore import _find_clusters

        # 3-doc cluster and 2-doc cluster
        matrix = np.array([
            [1.0, 0.9, 0.8, 0.1, 0.1],
            [0.9, 1.0, 0.9, 0.1, 0.1],
            [0.8, 0.9, 1.0, 0.1, 0.1],
            [0.1, 0.1, 0.1, 1.0, 0.7],
            [0.1, 0.1, 0.1, 0.7, 1.0],
        ])
        clusters = _find_clusters(matrix, [1, 2, 3, 4, 5], threshold=0.5)

        assert len(clusters) == 2
        assert len(clusters[0]) >= len(clusters[1])


class TestTopicLabels:
    """Unit tests for topic label extraction."""

    def test_extract_topic_labels_returns_terms(self, sample_docs):
        """Labels contain meaningful terms from cluster documents."""
        from sklearn.metrics.pairwise import cosine_similarity

        from emdx.commands.explore import (
            _compute_tfidf,
            _extract_topic_labels,
            _fetch_all_documents,
            _find_clusters,
        )

        documents = _fetch_all_documents()
        tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(documents)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        clusters = _find_clusters(similarity_matrix, doc_ids, threshold=0.3)

        labels = _extract_topic_labels(
            tfidf_matrix, doc_ids, clusters, vectorizer, top_n=5
        )

        assert len(labels) == len(clusters)
        for label_terms in labels:
            assert len(label_terms) > 0
            # All terms should be non-empty strings
            assert all(isinstance(t, str) and t for t in label_terms)

    def test_extract_topic_labels_empty_cluster(self):
        """Empty cluster list returns empty labels."""
        from emdx.commands.explore import _compute_tfidf, _extract_topic_labels

        docs = [
            {"id": 1, "title": "Test", "content": "Some test content here for tfidf."},
            {"id": 2, "title": "Other", "content": "Other content that is different."},
        ]
        tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(docs)

        labels = _extract_topic_labels(
            tfidf_matrix, doc_ids, [], vectorizer
        )
        assert labels == []


class TestBuildTopicClusters:
    """Unit tests for topic cluster metadata building."""

    def test_build_topic_clusters_computes_metadata(self, sample_docs):
        """Topic clusters include doc count, size, tags, projects."""
        from sklearn.metrics.pairwise import cosine_similarity

        from emdx.commands.explore import (
            _build_topic_clusters,
            _compute_tfidf,
            _extract_topic_labels,
            _fetch_all_documents,
            _find_clusters,
        )

        documents = _fetch_all_documents()
        tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(documents)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        clusters = _find_clusters(similarity_matrix, doc_ids, threshold=0.3)
        labels = _extract_topic_labels(tfidf_matrix, doc_ids, clusters, vectorizer)

        topics = _build_topic_clusters(clusters, labels, documents)

        assert len(topics) > 0
        for topic in topics:
            assert topic["doc_count"] >= 2
            assert topic["total_chars"] > 0
            assert len(topic["doc_ids"]) == topic["doc_count"]
            assert len(topic["titles"]) == topic["doc_count"]
            assert isinstance(topic["label"], str)
            assert isinstance(topic["stale"], bool)
            assert isinstance(topic["avg_views"], float)


class TestGapDetection:
    """Unit tests for gap detection."""

    def test_detect_gaps_finds_thin_topics(self, sample_docs):
        """Topics with only 2 docs are flagged as thin coverage."""
        from sklearn.metrics.pairwise import cosine_similarity

        from emdx.commands.explore import (
            _build_topic_clusters,
            _compute_tfidf,
            _detect_gaps,
            _extract_topic_labels,
            _fetch_all_documents,
            _find_clusters,
        )

        documents = _fetch_all_documents()
        tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(documents)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        clusters = _find_clusters(similarity_matrix, doc_ids, threshold=0.3)
        labels = _extract_topic_labels(tfidf_matrix, doc_ids, clusters, vectorizer)
        topics = _build_topic_clusters(clusters, labels, documents)

        gaps = _detect_gaps(topics, documents)

        # With 2-doc clusters, we should see thin coverage warnings
        thin_gaps = [g for g in gaps if "Thin coverage" in g]
        assert len(thin_gaps) > 0

    def test_detect_gaps_empty_kb(self, clean_db):
        """No gaps detected on empty KB."""
        from emdx.commands.explore import _detect_gaps

        gaps = _detect_gaps([], [])
        assert gaps == []


class TestExploreCommand:
    """Integration tests for the explore CLI command."""

    def test_explore_help(self):
        """--help shows command usage."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--help"])

        assert result.exit_code == 0
        assert "threshold" in result.stdout.lower()
        assert "questions" in result.stdout.lower()
        assert "gaps" in result.stdout.lower()

    def test_explore_empty_db(self, clean_db):
        """Empty database shows appropriate message."""
        from typer.testing import CliRunner

        from emdx.commands.explore import app as explore_app

        runner = CliRunner()
        result = runner.invoke(explore_app, [])

        assert result.exit_code == 0
        assert "no documents" in result.stdout.lower()

    def test_explore_empty_db_via_main(self, clean_db):
        """Empty database shows appropriate message via main app with flag."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--json"])

        assert result.exit_code == 0
        assert "total_documents" in result.stdout

    def test_explore_shows_topic_map(self, sample_docs):
        """Default explore shows a topic map."""
        from typer.testing import CliRunner

        from emdx.commands.explore import app as explore_app

        runner = CliRunner()
        result = runner.invoke(explore_app, [])

        assert result.exit_code == 0
        output = result.stdout.lower()
        assert "knowledge map" in output
        assert "topics" in output or "unclustered" in output

    def test_explore_with_gaps(self, sample_docs):
        """--gaps flag shows coverage gaps."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--gaps"])

        assert result.exit_code == 0
        output = result.stdout.lower()
        assert "knowledge map" in output
        # Should have some gap analysis output
        assert "coverage gaps" in output or "no coverage gaps" in output

    def test_explore_json_output(self, sample_docs):
        """--json outputs valid JSON with expected structure."""
        import json

        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)

        assert "total_documents" in data
        assert "topic_count" in data
        assert "topics" in data
        assert "singletons" in data
        assert "tag_landscape" in data
        assert data["total_documents"] == 5
        assert isinstance(data["topics"], list)

    def test_explore_json_topics_have_metadata(self, sample_docs):
        """JSON topics include all expected metadata fields."""
        import json

        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--json"])
        data = json.loads(result.stdout)

        if data["topics"]:
            topic = data["topics"][0]
            assert "label" in topic
            assert "doc_count" in topic
            assert "total_chars" in topic
            assert "doc_ids" in topic
            assert "titles" in topic
            assert "stale" in topic
            assert "avg_views" in topic

    def test_explore_threshold_affects_clusters(self, sample_docs):
        """Higher threshold produces fewer/smaller clusters."""
        import json

        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()

        # Low threshold (more grouping)
        result_low = runner.invoke(app, ["explore", "--json", "--threshold", "0.2"])
        data_low = json.loads(result_low.stdout)

        # High threshold (less grouping)
        result_high = runner.invoke(app, ["explore", "--json", "--threshold", "0.8"])
        data_high = json.loads(result_high.stdout)

        # Higher threshold should have same or fewer clustered docs
        assert data_high["clustered_documents"] <= data_low["clustered_documents"]

    def test_explore_limit_restricts_topics(self, sample_docs):
        """--limit restricts number of topics shown."""
        import json

        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--json", "--limit", "1"])
        data = json.loads(result.stdout)

        assert len(data["topics"]) <= 1

    def test_explore_single_doc_handled(self, clean_db):
        """Single document shows appropriate message."""
        from typer.testing import CliRunner

        from emdx.commands.explore import app as explore_app
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Only Doc", "Some content that is long enough for indexing" * 5, "test"),
            )
            conn.commit()

        runner = CliRunner()
        result = runner.invoke(explore_app, [])

        assert result.exit_code == 0
        assert "at least 2" in result.stdout.lower()

    def test_explore_rich_output(self, sample_docs):
        """--rich flag produces Rich-formatted output."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["explore", "--rich"])

        assert result.exit_code == 0
        # Rich output uses table formatting
        assert "Knowledge Map" in result.stdout
