"""Tests for the AutoTagger service."""

import sqlite3
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from emdx.services.auto_tagger import AutoTagger


@pytest.fixture
def test_db() -> Generator[str, None, None]:
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Initialize database schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            project TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            accessed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            deleted_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE document_tags (
            document_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (document_id, tag_id),
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (tag_id) REFERENCES tags(id)
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def tagger(test_db: str) -> AutoTagger:
    """Create an AutoTagger instance with test database."""
    return AutoTagger(db_path=test_db)


class TestAutoTaggerPatterns:
    """Test pattern matching and confidence scoring."""

    def test_gameplan_detection(self, tagger: AutoTagger) -> None:
        """Test gameplan pattern detection."""
        # Title match
        suggestions = tagger.analyze_document("Gameplan: Implement new feature", "Some content")
        assert any(tag == "gameplan" for tag, _ in suggestions)
        assert any(tag == "active" for tag, _ in suggestions)

        # Content match
        suggestions = tagger.analyze_document(
            "Implementation Strategy",
            "## Goals\n- Implement feature\n## Success Criteria\n- Tests pass",
        )
        assert any(tag == "gameplan" for tag, _ in suggestions)

    def test_bug_detection(self, tagger: AutoTagger) -> None:
        """Test bug pattern detection."""
        # Title match
        suggestions = tagger.analyze_document("Bug: Login fails on mobile", "Description of bug")
        assert any(tag == "bug" for tag, _ in suggestions)
        assert any(tag == "active" for tag, _ in suggestions)

        # Content match
        suggestions = tagger.analyze_document(
            "Login issue", "Error: TypeError exception thrown when user clicks login"
        )
        assert any(tag == "bug" for tag, _ in suggestions)

    def test_confidence_scores(self, tagger: AutoTagger) -> None:
        """Test confidence scoring logic."""
        # High confidence - title match
        suggestions = tagger.analyze_document("Test: Unit tests for auth", "def test_login():")
        test_tag = next((conf for tag, conf in suggestions if tag == "test"), None)
        assert test_tag is not None
        assert test_tag >= 0.9

        # Medium confidence - content only
        suggestions = tagger.analyze_document("Auth implementation", "def test_login():")
        test_tag = next((conf for tag, conf in suggestions if tag == "test"), None)
        assert test_tag is not None
        assert 0.6 <= test_tag < 0.9

    def test_multiple_patterns(self, tagger: AutoTagger) -> None:
        """Test detection of multiple patterns."""
        suggestions = tagger.analyze_document(
            "Urgent Bug: Fix critical error in payment system",
            "Error traceback shows exception in payment processing",
        )

        tags = [tag for tag, _ in suggestions]
        assert "bug" in tags
        assert "urgent" in tags
        assert "active" in tags

    def test_no_duplicate_suggestions(self, tagger: AutoTagger) -> None:
        """Test that existing tags are not suggested again."""
        existing_tags = ["gameplan", "active"]
        suggestions = tagger.analyze_document(
            "Gameplan: New project", "## Goals", existing_tags=existing_tags
        )

        suggested_tags = [tag for tag, _ in suggestions]
        assert "gameplan" not in suggested_tags
        assert "active" not in suggested_tags


class TestAutoTaggerDatabase:
    """Test database operations."""

    def test_suggest_tags_for_document(self, tagger: AutoTagger, test_db: str) -> None:
        """Test suggesting tags for a saved document."""
        # Create a document
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (title, content) VALUES (?, ?)",
            ("Bug: Test fails randomly", "Error in test_auth.py line 42"),
        )
        doc_id = cursor.lastrowid
        assert doc_id is not None
        conn.commit()
        conn.close()

        # Get suggestions
        suggestions = tagger.suggest_tags(doc_id)
        assert len(suggestions) > 0
        assert any(tag == "bug" for tag, _ in suggestions)

    def test_auto_tag_document(self, tagger: AutoTagger, test_db: str) -> None:
        """Test automatically applying tags to a document."""
        # Create a document
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (title, content) VALUES (?, ?)",
            ("Gameplan: Refactor authentication", "## Goals\n- Improve security"),
        )
        doc_id = cursor.lastrowid
        assert doc_id is not None
        conn.commit()

        # Auto-tag
        applied_tags = tagger.auto_tag_document(doc_id, confidence_threshold=0.7)
        assert len(applied_tags) > 0
        assert "gameplan" in applied_tags

        # Verify tags were saved
        cursor.execute(
            """
            SELECT t.name FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            WHERE dt.document_id = ?
        """,
            (doc_id,),
        )
        saved_tags = [row[0] for row in cursor.fetchall()]
        conn.close()

        assert "gameplan" in saved_tags

    def test_batch_suggest(self, tagger: AutoTagger, test_db: str) -> None:
        """Test batch suggestion for multiple documents."""
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        # Create multiple documents
        docs = [
            ("Bug: Login error", "Exception in auth module"),
            ("Feature: Add dark mode", "Implement theme switching"),
            ("Meeting notes", "Discussed project timeline"),
        ]

        for title, content in docs:
            cursor.execute("INSERT INTO documents (title, content) VALUES (?, ?)", (title, content))

        conn.commit()
        conn.close()

        # Get batch suggestions
        suggestions = tagger.batch_suggest(untagged_only=False)
        assert len(suggestions) == 3

        # Verify each document has suggestions
        for _doc_id, doc_suggestions in suggestions.items():
            assert len(doc_suggestions) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_document(self, tagger: AutoTagger) -> None:
        """Test handling empty content."""
        suggestions = tagger.analyze_document("", "")
        assert isinstance(suggestions, list)

    def test_none_content(self, tagger: AutoTagger) -> None:
        """Test handling None content."""
        suggestions = tagger.analyze_document("Title", None)
        assert isinstance(suggestions, list)

    def test_invalid_document_id(self, tagger: AutoTagger, test_db: str) -> None:
        """Test handling invalid document ID."""
        suggestions = tagger.suggest_tags(99999)
        assert len(suggestions) == 0

    def test_confidence_threshold_bounds(self, tagger: AutoTagger, test_db: str) -> None:
        """Test confidence threshold boundaries."""
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO documents (title, content) VALUES (?, ?)", ("Test doc", "content")
        )
        doc_id = cursor.lastrowid
        assert doc_id is not None
        conn.commit()
        conn.close()

        # Very high threshold - should apply nothing
        applied = tagger.auto_tag_document(doc_id, confidence_threshold=0.99)
        assert len(applied) == 0

        # Very low threshold - should apply matches
        applied = tagger.auto_tag_document(doc_id, confidence_threshold=0.1)
        # May or may not apply tags depending on content


class TestIntegration:
    """Integration tests with real patterns."""

    def test_real_world_gameplan(self, tagger: AutoTagger) -> None:
        """Test with real gameplan content."""
        content = """
        # Gameplan: Implement EMDX Maintenance Features

        ## Goals
        1. Add duplicate detection
        2. Implement auto-tagging
        3. Create health monitoring

        ## Success Criteria
        - 95% tag coverage
        - <1% false positive rate
        - User satisfaction >4.5/5

        ## Timeline
        - Week 1: Core cleanup
        - Week 2: Auto-tagging
        """

        suggestions = tagger.analyze_document("Gameplan: EMDX Maintenance", content)
        tags = [tag for tag, _ in suggestions]

        assert "gameplan" in tags
        assert "active" in tags
        # Should have high confidence
        gameplan_conf = next(conf for tag, conf in suggestions if tag == "gameplan")
        assert gameplan_conf >= 0.9

    def test_real_world_bug_report(self, tagger: AutoTagger) -> None:
        """Test with real bug report content."""
        content = """
        Error when running emdx gui:

        Traceback (most recent call last):
          File "main.py", line 42, in <module>
            app.run()
        TypeError: 'NoneType' object is not callable

        This is blocking my workflow and needs urgent attention.
        """

        suggestions = tagger.analyze_document("Bug: emdx gui crashes", content)
        tags = [tag for tag, _ in suggestions]

        assert "bug" in tags
        assert "urgent" in tags  # due to "urgent attention"
        assert "active" in tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
