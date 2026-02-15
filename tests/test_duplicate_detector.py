"""Tests for the duplicate detection service with LSH/MinHash.

Tests cover:
- Unit tests for tokenization and MinHash creation
- Integration tests for near-duplicate detection
- Performance comparison between LSH and exact methods
- Edge cases and boundary conditions
"""

import pytest

# Skip all tests if datasketch not installed - must come before module imports
datasketch = pytest.importorskip("datasketch", reason="datasketch not installed (install with: pip install 'emdx[similarity]')")

from emdx.services.duplicate_detector import (  # noqa: E402
    DEFAULT_NUM_PERM,
    DuplicateDetector,
    _create_minhash,
    _tokenize,
)


@pytest.fixture
def clean_db(isolate_test_database):
    """Ensure clean database for each test by deleting all documents."""
    from emdx.database import db

    def cleanup():
        with db.get_connection() as conn:
            # Disable foreign key checks for cleanup
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM documents")
            conn.execute("DELETE FROM tags")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    yield
    cleanup()


class TestTokenization:
    """Unit tests for the tokenization function."""

    def test_tokenize_empty_string(self):
        """Empty string returns empty set."""
        assert _tokenize("") == set()
        assert _tokenize(None) == set()

    def test_tokenize_single_word(self):
        """Single word produces word token and character n-grams."""
        tokens = _tokenize("hello")
        assert "hello" in tokens
        # Should have character 3-grams
        assert "hel" in tokens
        assert "ell" in tokens
        assert "llo" in tokens

    def test_tokenize_multiple_words(self):
        """Multiple words produce word tokens and bigrams."""
        tokens = _tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens
        # Should have word bigram
        assert "hello_world" in tokens

    def test_tokenize_normalizes_case(self):
        """Tokenization is case-insensitive."""
        tokens1 = _tokenize("Hello World")
        tokens2 = _tokenize("hello world")
        assert tokens1 == tokens2

    def test_tokenize_normalizes_whitespace(self):
        """Extra whitespace is normalized."""
        tokens1 = _tokenize("hello    world")
        tokens2 = _tokenize("hello world")
        assert tokens1 == tokens2

    def test_tokenize_preserves_content(self):
        """All words are captured."""
        text = "The quick brown fox jumps over the lazy dog"
        tokens = _tokenize(text)
        words = ["the", "quick", "brown", "fox", "jumps", "over", "lazy", "dog"]
        for word in words:
            assert word in tokens


class TestMinHashCreation:
    """Unit tests for MinHash signature creation."""

    def test_create_minhash_empty_tokens(self):
        """Empty token set produces valid MinHash."""
        mh = _create_minhash(set())
        assert mh is not None
        assert len(mh.hashvalues) == DEFAULT_NUM_PERM

    def test_create_minhash_custom_num_perm(self):
        """Custom number of permutations is respected."""
        tokens = {"hello", "world"}
        mh = _create_minhash(tokens, num_perm=64)
        assert len(mh.hashvalues) == 64

    def test_identical_tokens_produce_identical_minhash(self):
        """Same tokens produce same MinHash signature."""
        tokens = {"hello", "world", "test"}
        mh1 = _create_minhash(tokens)
        mh2 = _create_minhash(tokens)
        assert mh1.jaccard(mh2) == 1.0

    def test_different_tokens_produce_different_minhash(self):
        """Different tokens produce different MinHash signatures."""
        tokens1 = {"hello", "world"}
        tokens2 = {"foo", "bar", "baz"}
        mh1 = _create_minhash(tokens1)
        mh2 = _create_minhash(tokens2)
        # Should have low similarity
        assert mh1.jaccard(mh2) < 0.5

    def test_similar_tokens_have_high_similarity(self):
        """Overlapping tokens have proportional similarity."""
        tokens1 = {"a", "b", "c", "d", "e"}
        tokens2 = {"a", "b", "c", "f", "g"}  # 3/7 overlap
        mh1 = _create_minhash(tokens1, num_perm=256)  # More permutations for accuracy
        mh2 = _create_minhash(tokens2, num_perm=256)
        # Jaccard similarity should be approximately 3/7 ≈ 0.43
        similarity = mh1.jaccard(mh2)
        assert 0.3 < similarity < 0.6


class TestDuplicateDetector:
    """Integration tests for the DuplicateDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a DuplicateDetector instance."""
        return DuplicateDetector()

    def test_find_near_duplicates_empty_db(self, detector, clean_db):
        """Empty database returns no duplicates."""
        result = detector.find_near_duplicates()
        assert result == []

    def test_find_near_duplicates_single_doc(self, detector, clean_db):
        """Single document returns no duplicates."""
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Test Doc", "This is a test document with enough content to be indexed." * 5, "test"),
            )
            conn.commit()

        result = detector.find_near_duplicates()
        assert result == []

    def test_find_near_duplicates_with_duplicates(self, detector, clean_db):
        """Near-duplicate documents are detected."""
        from emdx.database import db

        # Create two very similar documents
        base_content = """
        This is a comprehensive guide to Python programming. It covers
        variables, functions, classes, and modules. Python is a versatile
        language used for web development, data science, and automation.
        Learning Python opens many career opportunities in technology.
        """ * 3

        similar_content = """
        This is a comprehensive guide to Python programming. It covers
        variables, functions, classes, and modules. Python is a versatile
        language used for web development, data science, and automation.
        Learning Python opens many career opportunities in tech industry.
        """ * 3

        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 10)""",
                ("Python Guide 1", base_content, "test"),
            )
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 5)""",
                ("Python Guide 2", similar_content, "test"),
            )
            conn.commit()

        result = detector.find_near_duplicates(threshold=0.7)
        assert len(result) >= 1
        # Check that similarity is above threshold
        for _doc1, _doc2, similarity in result:
            assert similarity >= 0.7

    def test_find_near_duplicates_ignores_short_docs(self, detector, clean_db):
        """Documents with less than 50 characters are ignored."""
        from emdx.database import db

        with db.get_connection() as conn:
            # Short document (should be ignored)
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted)
                   VALUES (?, ?, ?, 0)""",
                ("Short Doc", "Too short", "test"),
            )
            conn.commit()

        result = detector.find_near_duplicates()
        assert result == []

    def test_find_near_duplicates_respects_threshold(self, detector, clean_db):
        """Threshold parameter filters results correctly."""
        from emdx.database import db

        # Create documents with moderate similarity
        content1 = "Python is a programming language. It is widely used for data science and web development." * 5
        content2 = "JavaScript is a programming language. It is widely used for web development and frontend." * 5

        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 10)""",
                ("Python Doc", content1, "test"),
            )
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 5)""",
                ("JavaScript Doc", content2, "test"),
            )
            conn.commit()

        # High threshold should find nothing or few matches
        high_threshold_result = detector.find_near_duplicates(threshold=0.95)
        # Low threshold should find more matches
        low_threshold_result = detector.find_near_duplicates(threshold=0.3)

        # Low threshold should find at least as many as high threshold
        assert len(low_threshold_result) >= len(high_threshold_result)

    def test_find_near_duplicates_max_documents(self, detector, clean_db):
        """max_documents parameter limits processed documents."""
        from emdx.database import db

        # Create several documents
        with db.get_connection() as conn:
            for i in range(10):
                conn.execute(
                    """INSERT INTO documents (title, content, project, is_deleted, access_count)
                       VALUES (?, ?, ?, 0, ?)""",
                    (f"Doc {i}", f"Content for document number {i}. " * 20, "test", i),
                )
            conn.commit()

        # Should work without error even with limit
        result = detector.find_near_duplicates(max_documents=5)
        # Result can be empty or have some matches, but shouldn't crash
        assert isinstance(result, list)


class TestDuplicateDetectorExactMethod:
    """Tests for the legacy exact pairwise comparison method."""

    @pytest.fixture
    def detector(self):
        return DuplicateDetector()

    def test_find_near_duplicates_exact_empty_db(self, detector, clean_db):
        """Empty database returns no duplicates."""
        result = detector.find_near_duplicates_exact()
        assert result == []

    def test_find_near_duplicates_exact_with_duplicates(self, detector, clean_db):
        """Exact method finds near-duplicates."""
        from emdx.database import db

        # Create two identical documents
        content = "This is a test document with enough content to be indexed properly." * 5

        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 10)""",
                ("Doc 1", content, "test"),
            )
            conn.execute(
                """INSERT INTO documents (title, content, project, is_deleted, access_count)
                   VALUES (?, ?, ?, 0, 5)""",
                ("Doc 2", content, "test"),
            )
            conn.commit()

        result = detector.find_near_duplicates_exact(threshold=0.9)
        assert len(result) == 1
        assert result[0][2] >= 0.9  # Similarity should be high


class TestMinHashSimilarityAccuracy:
    """Tests validating MinHash similarity accuracy against exact methods."""

    def test_minhash_approximates_jaccard(self):
        """MinHash similarity approximates true Jaccard similarity."""
        # Create sets with known overlap
        set1 = {f"word{i}" for i in range(100)}
        set2 = {f"word{i}" for i in range(50, 150)}
        # True Jaccard: |intersection| / |union| = 50 / 150 ≈ 0.333

        mh1 = _create_minhash(set1, num_perm=256)
        mh2 = _create_minhash(set2, num_perm=256)

        estimated = mh1.jaccard(mh2)
        true_jaccard = len(set1 & set2) / len(set1 | set2)

        # Should be within 10% of true value with high probability
        assert abs(estimated - true_jaccard) < 0.1


class TestContentHashDeduplication:
    """Tests for exact duplicate detection via content hash."""

    @pytest.fixture
    def detector(self):
        return DuplicateDetector()

    def test_find_duplicates_returns_groups(self, detector, clean_db):
        """Exact duplicates are grouped together."""
        from emdx.database import db

        content = "Exactly the same content for testing."

        with db.get_connection() as conn:
            for i in range(3):
                conn.execute(
                    """INSERT INTO documents (title, content, project, is_deleted, access_count)
                       VALUES (?, ?, ?, 0, ?)""",
                    (f"Copy {i}", content, "test", i * 10),
                )
            conn.commit()

        groups = detector.find_duplicates()
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_get_content_hash_consistency(self, detector):
        """Same content produces same hash."""
        content = "Test content for hashing"
        hash1 = detector._get_content_hash(content)
        hash2 = detector._get_content_hash(content)
        assert hash1 == hash2

    def test_get_content_hash_empty(self, detector):
        """Empty content returns 'empty' marker."""
        assert detector._get_content_hash("") == "empty"
        assert detector._get_content_hash(None) == "empty"
