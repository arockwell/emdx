"""Tests for the compact command and SynthesisService.

Tests cover:
- Unit tests for clustering logic
- Unit tests for SynthesisService with mocked Anthropic API
- Integration tests for the compact command
"""

import re
from unittest.mock import patch

import pytest

# Skip all tests if sklearn not installed - must come before module imports
sklearn = pytest.importorskip(
    "sklearn", reason="scikit-learn not installed (install with: pip install 'emdx[similarity]')"
)


@pytest.fixture
def clean_db(isolate_test_database):
    """Ensure clean database for each test by deleting all documents."""
    from emdx.database import db

    def cleanup():
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM tags")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    yield
    cleanup()


@pytest.fixture
def sample_docs_for_clustering(clean_db):
    """Create sample documents for clustering tests."""
    from emdx.database import db

    docs = []
    with db.get_connection() as conn:
        # Create two very similar documents about Python
        python_content_1 = """
        Python is a versatile programming language widely used in data science,
        machine learning, and web development. It features clean syntax and
        extensive libraries like NumPy, Pandas, and TensorFlow for data analysis.
        Python's readability makes it excellent for beginners and experts alike.
        The language supports multiple paradigms including procedural, OOP, and functional.
        """
        python_content_2 = """
        Python is a versatile programming language widely used in data science,
        machine learning, and web development. It features clean syntax and
        extensive libraries like NumPy, Pandas, and PyTorch for data analysis.
        Python's readability makes it excellent for beginners and professionals alike.
        The language supports multiple paradigms including OOP and functional programming.
        """

        # Create a different document about JavaScript
        js_content = """
        JavaScript is the language of the web, enabling interactive websites
        and dynamic user interfaces. Modern frameworks like React, Vue, and
        Angular have revolutionized frontend development. Node.js brought
        JavaScript to the server side, enabling full-stack development.
        ES6 and later versions introduced modern features like arrow functions.
        """

        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 10)""",
            ("Python Programming Guide", python_content_1, "test-project"),
        )
        docs.append(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 5)""",
            ("Python for Data Science", python_content_2, "test-project"),
        )
        docs.append(cursor.lastrowid)

        cursor = conn.execute(
            """INSERT INTO documents (title, content, project, is_deleted, access_count)
               VALUES (?, ?, ?, 0, 8)""",
            ("JavaScript Web Development", js_content, "test-project"),
        )
        docs.append(cursor.lastrowid)

        conn.commit()

    return docs


class TestClusteringLogic:
    """Unit tests for the clustering functions in compact module."""

    def test_compute_similarity_matrix_empty(self):
        """Empty document list returns None matrix."""
        from emdx.commands.compact import _compute_similarity_matrix

        matrix, doc_ids = _compute_similarity_matrix([])
        assert matrix is None
        assert doc_ids == []

    def test_compute_similarity_matrix_single_doc(self):
        """Single document produces 1x1 matrix."""
        from emdx.commands.compact import _compute_similarity_matrix

        docs = [{"id": 1, "title": "Test", "content": "Some test content here."}]
        matrix, doc_ids = _compute_similarity_matrix(docs)
        assert matrix is not None
        assert matrix.shape == (1, 1)
        assert doc_ids == [1]

    def test_compute_similarity_matrix_multiple_docs(self):
        """Multiple documents produce NxN matrix."""
        from emdx.commands.compact import _compute_similarity_matrix

        docs = [
            {"id": 1, "title": "Python Guide", "content": "Learn Python programming here."},
            {"id": 2, "title": "Python Tutorial", "content": "Python programming tutorial."},
            {"id": 3, "title": "JavaScript Guide", "content": "Learn JavaScript for web."},
        ]
        matrix, doc_ids = _compute_similarity_matrix(docs)
        assert matrix is not None
        assert matrix.shape == (3, 3)
        assert doc_ids == [1, 2, 3]
        # Diagonal should be 1.0 (self-similarity)
        assert matrix[0, 0] == pytest.approx(1.0)
        assert matrix[1, 1] == pytest.approx(1.0)

    def test_find_clusters_empty(self):
        """Empty inputs return empty clusters."""
        import numpy as np

        from emdx.commands.compact import _find_clusters

        # Empty matrix
        clusters = _find_clusters(np.array([]), [], threshold=0.5)
        assert clusters == []

    def test_find_clusters_no_similar_docs(self):
        """Dissimilar documents don't form clusters."""
        import numpy as np

        from emdx.commands.compact import _find_clusters

        # Low similarity matrix
        matrix = np.array(
            [
                [1.0, 0.1, 0.1],
                [0.1, 1.0, 0.1],
                [0.1, 0.1, 1.0],
            ]
        )
        clusters = _find_clusters(matrix, [1, 2, 3], threshold=0.5)
        # No clusters with more than 1 document
        assert clusters == []

    def test_find_clusters_similar_docs(self):
        """Similar documents form clusters."""
        import numpy as np

        from emdx.commands.compact import _find_clusters

        # High similarity between docs 1 and 2
        matrix = np.array(
            [
                [1.0, 0.8, 0.1],
                [0.8, 1.0, 0.1],
                [0.1, 0.1, 1.0],
            ]
        )
        clusters = _find_clusters(matrix, [1, 2, 3], threshold=0.5)
        assert len(clusters) == 1
        assert set(clusters[0]) == {1, 2}

    def test_find_clusters_transitive_closure(self):
        """Clusters use transitive closure (union-find)."""
        import numpy as np

        from emdx.commands.compact import _find_clusters

        # A~B and B~C should put A,B,C in same cluster
        matrix = np.array(
            [
                [1.0, 0.7, 0.2],
                [0.7, 1.0, 0.7],
                [0.2, 0.7, 1.0],
            ]
        )
        clusters = _find_clusters(matrix, [1, 2, 3], threshold=0.5)
        assert len(clusters) == 1
        assert set(clusters[0]) == {1, 2, 3}


class TestSynthesisService:
    """Unit tests for SynthesisService with mocked Anthropic API."""

    def test_fetch_documents_returns_dict_list(self, clean_db):
        """_fetch_documents returns list of document dicts."""
        from emdx.database import db
        from emdx.services.synthesis_service import SynthesisService

        # Create test documents
        with db.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Test Doc", "Test content here", "test"),
            )
            doc_id = cursor.lastrowid
            conn.commit()

        service = SynthesisService()
        docs = service._fetch_documents([doc_id])

        assert len(docs) == 1
        assert docs[0]["id"] == doc_id
        assert docs[0]["title"] == "Test Doc"
        assert docs[0]["content"] == "Test content here"

    def test_fetch_documents_excludes_deleted(self, clean_db):
        """_fetch_documents excludes deleted documents."""
        from emdx.database import db
        from emdx.services.synthesis_service import SynthesisService

        with db.get_connection() as conn:
            # Create active document
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Active Doc", "Active content", "test"),
            )
            active_id = cursor.lastrowid

            # Create deleted document
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 1)""",
                ("Deleted Doc", "Deleted content", "test"),
            )
            deleted_id = cursor.lastrowid
            conn.commit()

        service = SynthesisService()
        docs = service._fetch_documents([active_id, deleted_id])

        assert len(docs) == 1
        assert docs[0]["id"] == active_id

    def test_extract_title_from_markdown_heading(self):
        """_extract_title extracts title from markdown heading."""
        from emdx.services.synthesis_service import SynthesisService

        service = SynthesisService()
        content = "# My Synthesized Document\n\nSome content here."
        title = service._extract_title(content, ["Original 1", "Original 2"])

        assert title == "My Synthesized Document"

    def test_extract_title_fallback_single(self):
        """_extract_title uses fallback for single doc without heading."""
        from emdx.services.synthesis_service import SynthesisService

        service = SynthesisService()
        content = "No heading in this content."
        title = service._extract_title(content, ["Only Title"])

        assert title == "Only Title (synthesized)"

    def test_extract_title_fallback_multiple(self):
        """_extract_title uses fallback for multiple docs without heading."""
        from emdx.services.synthesis_service import SynthesisService

        service = SynthesisService()
        content = "No heading in this content."
        title = service._extract_title(content, ["First", "Second", "Third"])

        assert "Synthesis" in title
        assert "First" in title
        assert "+ 2 more" in title

    def test_estimate_cost(self, clean_db):
        """estimate_cost returns token and cost estimates."""
        from emdx.database import db
        from emdx.services.synthesis_service import SynthesisService

        # Create test documents
        with db.get_connection() as conn:
            ids = []
            for i in range(2):
                cursor = conn.execute(
                    """INSERT INTO documents (title, content, project, is_deleted)
                       VALUES (?, ?, ?, 0)""",
                    (f"Doc {i}", f"Content for document {i}. " * 100, "test"),
                )
                ids.append(cursor.lastrowid)
            conn.commit()

        service = SynthesisService()
        estimate = service.estimate_cost(ids)

        assert "input_tokens" in estimate
        assert "output_tokens" in estimate
        assert "estimated_cost" in estimate
        assert "document_count" in estimate
        assert estimate["document_count"] == 2
        assert estimate["input_tokens"] > 0
        assert estimate["estimated_cost"] >= 0

    @patch("emdx.services.synthesis_service._execute_prompt")
    def test_synthesize_documents_success(self, mock_execute, clean_db):
        """synthesize_documents calls CLI and returns result."""
        from emdx.database import db
        from emdx.services.synthesis_service import ExecutionResult, SynthesisService

        # Create test documents
        with db.get_connection() as conn:
            ids = []
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Doc 1", "Content about Python programming.", "test"),
            )
            ids.append(cursor.lastrowid)
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Doc 2", "More Python programming content.", "test"),
            )
            ids.append(cursor.lastrowid)
            conn.commit()

        # Mock the unified executor
        from pathlib import Path

        mock_execute.return_value = ExecutionResult(
            success=True,
            execution_id=1,
            log_file=Path("/tmp/test.log"),
            output_content="# Python Programming Guide\n\nSynthesized.",
            input_tokens=500,
            output_tokens=100,
        )

        service = SynthesisService()
        result = service.synthesize_documents(ids)

        assert result.title == "Python Programming Guide"
        assert "Synthesized" in result.content
        assert result.input_tokens == 500
        assert result.output_tokens == 100
        assert set(result.source_doc_ids) == set(ids)


class TestCompactCommand:
    """Integration tests for the compact command."""

    def test_compact_dry_run_shows_clusters(self, sample_docs_for_clustering, capsys):
        """--dry-run shows clusters without API calls."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", "--dry-run", "--threshold", "0.3"])

        # Should succeed
        assert result.exit_code == 0
        # Should show cluster information
        output = result.stdout
        assert "cluster" in output.lower() or "found" in output.lower()

    def test_compact_specific_docs_validates_ids(self, clean_db, capsys):
        """Specifying non-existent doc IDs shows error."""
        from typer.testing import CliRunner

        from emdx.database import db
        from emdx.main import app

        # Create at least one document so we don't get "no documents" message
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Existing Doc", "Some content here" * 10, "test"),
            )
            conn.commit()

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", "99999", "99998"])

        # Should show error about documents not found
        assert "not found" in result.stdout.lower()

    def test_compact_requires_at_least_two_docs(self, clean_db, capsys):
        """Compacting a single document shows error."""
        from typer.testing import CliRunner

        from emdx.database import db
        from emdx.main import app

        # Create documents - need at least one with enough content
        with db.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Single Doc", "Content here that is long enough to be indexed" * 5, "test"),
            )
            doc_id = cursor.lastrowid
            # Create another doc so we pass the "no documents" check
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Another Doc", "Different content that is long enough" * 5, "test"),
            )
            conn.commit()

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", str(doc_id)])

        # Should show error about needing at least 2 documents
        assert "at least 2" in result.stdout.lower()

    def test_compact_help_shows_usage(self):
        """--help shows command usage."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", "--help"])

        assert result.exit_code == 0
        output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout).lower()
        assert "dry-run" in output
        assert "threshold" in output
        assert "auto" in output

    def test_compact_empty_db_handles_gracefully(self, clean_db):
        """Empty database shows appropriate message."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", "--dry-run"])

        assert result.exit_code == 0
        assert "no documents" in result.stdout.lower()

    def test_compact_no_clusters_shows_message(self, clean_db):
        """No similar documents shows appropriate message."""
        from typer.testing import CliRunner

        from emdx.database import db
        from emdx.main import app

        # Create very different documents
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Python Doc", "Python is a programming language for data science." * 10, "test"),
            )
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Cooking Recipe", "Mix flour eggs and sugar to bake a cake." * 10, "test"),
            )
            conn.commit()

        runner = CliRunner()
        # Use high threshold to ensure no clusters
        result = runner.invoke(app, ["maintain", "compact", "--dry-run", "--threshold", "0.95"])

        assert result.exit_code == 0
        assert "no clusters" in result.stdout.lower()

    def test_compact_topic_filter(self, sample_docs_for_clustering):
        """--topic filters documents before clustering."""
        from typer.testing import CliRunner

        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["maintain", "compact", "--dry-run", "--topic", "Python"])

        assert result.exit_code == 0
        # Should filter to only Python documents
        output = result.stdout.lower()
        assert "python" in output or "filtered" in output
