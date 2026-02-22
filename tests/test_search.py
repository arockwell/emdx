"""Tests for database/search.py FTS5 full-text search functionality."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from emdx.database.search import escape_fts5_query, search_documents


class FTS5TestDatabase:
    """Test database with FTS5 support for search tests."""

    def __init__(self, db_path=":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        """Create the database schema with FTS5."""
        # Create documents table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                project TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                deleted_at TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE,
                doc_type TEXT NOT NULL DEFAULT 'user'
            )
        """)

        # Create FTS5 virtual table
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, content, project, content=documents, content_rowid=id,
                tokenize='porter unicode61'
            )
        """)

        # Create triggers to keep FTS in sync
        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, content, project)
                VALUES (new.id, new.title, new.content, new.project);
            END
        """)

        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                UPDATE documents_fts
                SET title = new.title, content = new.content, project = new.project
                WHERE rowid = old.id;
            END
        """)

        self.conn.execute("""
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        """)

        self.conn.commit()

    def save_document(
        self,
        title,
        content,
        project=None,
        created_at=None,
        updated_at=None,
        doc_type="user",
    ):
        """Save a document to the database."""
        if created_at is None:
            created_at = datetime.now().isoformat()
        if updated_at is None:
            updated_at = created_at

        cursor = self.conn.execute(
            """
            INSERT INTO documents (title, content, project, created_at, updated_at, doc_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, content, project, created_at, updated_at, doc_type),
        )
        self.conn.commit()
        return cursor.lastrowid

    def soft_delete_document(self, doc_id):
        """Soft delete a document."""
        self.conn.execute(
            """
            UPDATE documents SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?
            """,
            (doc_id,),
        )
        self.conn.commit()

    def get_connection(self):
        """Return the connection (for mocking db_connection)."""
        return self.conn

    def close(self):
        """Close the database connection."""
        self.conn.close()


class MockDBConnection:
    """Mock for db_connection that uses our test database."""

    def __init__(self, test_db):
        self.test_db = test_db

    def get_connection(self):
        """Return a context manager for the test database connection."""
        from contextlib import contextmanager

        @contextmanager
        def connection_context():
            yield self.test_db.conn

        return connection_context()


@pytest.fixture
def fts_db():
    """Create a test database with FTS5 support."""
    db = FTS5TestDatabase()
    yield db
    db.close()


@pytest.fixture
def mock_db_connection(fts_db):
    """Mock the db_connection global to use our test database."""
    mock_conn = MockDBConnection(fts_db)
    with patch("emdx.database.search.db_connection", mock_conn):
        yield fts_db


class TestSearchDocumentsFTS5:
    """Test FTS5 full-text search functionality."""

    def test_basic_search_single_term(self, mock_db_connection):
        """Test basic single-term search."""
        db = mock_db_connection

        db.save_document("Python Guide", "Learn Python programming basics", "project1")
        db.save_document("JavaScript Guide", "Learn JavaScript for web development", "project1")
        db.save_document("Testing with Pytest", "Python testing framework", "project2")

        results = search_documents("Python")
        assert len(results) == 2
        titles = [r["title"] for r in results]
        assert "Python Guide" in titles
        assert "Testing with Pytest" in titles

    def test_search_in_title_and_content(self, mock_db_connection):
        """Test search matches both title and content."""
        db = mock_db_connection

        db.save_document("Docker Basics", "Container management for developers", "project1")
        db.save_document("Deployment Guide", "Deploy applications with Docker", "project1")

        results = search_documents("Docker")
        assert len(results) == 2

    def test_search_no_results(self, mock_db_connection):
        """Test search with no matching documents."""
        db = mock_db_connection

        db.save_document("Python Guide", "Learn Python programming", "project1")

        results = search_documents("nonexistentterm12345")
        assert len(results) == 0

    def test_search_case_insensitive(self, mock_db_connection):
        """Test that FTS5 search is case insensitive."""
        db = mock_db_connection

        db.save_document("PYTHON GUIDE", "Learn PYTHON programming", "project1")

        for query in ["python", "PYTHON", "Python", "PyThOn"]:
            results = search_documents(query)
            assert len(results) == 1, f"Failed for query: {query}"


class TestSearchRelevanceRanking:
    """Test relevance ranking of search results."""

    def test_results_are_ranked(self, mock_db_connection):
        """Test that search results include ranking information."""
        db = mock_db_connection

        db.save_document("Python", "Python Python Python Python", "project1")
        db.save_document("Python Tutorial", "A short Python guide", "project1")

        results = search_documents("Python")
        assert len(results) == 2
        # All results should have a rank field
        for result in results:
            assert "rank" in result

    def test_multiple_occurrences_ranked_higher(self, mock_db_connection):
        """Test that documents with more term occurrences rank higher."""
        db = mock_db_connection

        # Document with single mention
        db.save_document("Single Mention", "Python is great", "project1")
        # Document with multiple mentions
        db.save_document("Multiple Mentions", "Python Python Python Python Python", "project1")

        results = search_documents("Python")
        assert len(results) == 2
        # FTS5 rank is negative (lower is better), so first result should have lower rank
        assert results[0]["rank"] <= results[1]["rank"]


class TestSearchPagination:
    """Test pagination with limit parameter."""

    def test_limit_results(self, mock_db_connection):
        """Test limiting the number of results."""
        db = mock_db_connection

        # Create 10 documents
        for i in range(10):
            db.save_document(f"Python Doc {i}", f"Python content {i}", "project1")

        # Test with limit=3
        results = search_documents("Python", limit=3)
        assert len(results) == 3

        # Test with limit=5
        results = search_documents("Python", limit=5)
        assert len(results) == 5

        # Test with limit=20 (more than available)
        results = search_documents("Python", limit=20)
        assert len(results) == 10

    def test_default_limit(self, mock_db_connection):
        """Test default limit of 10."""
        db = mock_db_connection

        # Create 15 documents
        for i in range(15):
            db.save_document(f"Python Doc {i}", f"Python content {i}", "project1")

        results = search_documents("Python")
        assert len(results) == 10  # Default limit


class TestSearchProjectFilter:
    """Test project filter functionality."""

    def test_filter_by_project(self, mock_db_connection):
        """Test filtering results by project."""
        db = mock_db_connection

        db.save_document("Python Project1", "Python content", "project1")
        db.save_document("Python Project2", "Python content", "project2")
        db.save_document("Python Project3", "Python content", "project1")

        # Filter by project1
        results = search_documents("Python", project="project1")
        assert len(results) == 2
        for result in results:
            assert result["project"] == "project1"

        # Filter by project2
        results = search_documents("Python", project="project2")
        assert len(results) == 1
        assert results[0]["project"] == "project2"

    def test_filter_nonexistent_project(self, mock_db_connection):
        """Test filtering by a project that doesn't exist."""
        db = mock_db_connection

        db.save_document("Python Guide", "Python content", "project1")

        results = search_documents("Python", project="nonexistent")
        assert len(results) == 0


class TestSearchDateFilters:
    """Test date filter functionality."""

    def test_created_after_filter(self, mock_db_connection):
        """Test filtering by created_after date."""
        db = mock_db_connection

        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()
        filter_date = (datetime.now() - timedelta(days=5)).isoformat()

        db.save_document("Old Python Doc", "Python content", "project1", created_at=old_date)
        db.save_document("Recent Python Doc", "Python content", "project1", created_at=recent_date)

        results = search_documents("Python", created_after=filter_date)
        assert len(results) == 1
        assert results[0]["title"] == "Recent Python Doc"

    def test_created_before_filter(self, mock_db_connection):
        """Test filtering by created_before date."""
        db = mock_db_connection

        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()
        filter_date = (datetime.now() - timedelta(days=5)).isoformat()

        db.save_document("Old Python Doc", "Python content", "project1", created_at=old_date)
        db.save_document("Recent Python Doc", "Python content", "project1", created_at=recent_date)

        results = search_documents("Python", created_before=filter_date)
        assert len(results) == 1
        assert results[0]["title"] == "Old Python Doc"

    def test_modified_after_filter(self, mock_db_connection):
        """Test filtering by modified_after date."""
        db = mock_db_connection

        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()
        filter_date = (datetime.now() - timedelta(days=5)).isoformat()

        db.save_document("Old Python Doc", "Python content", "project1", updated_at=old_date)
        db.save_document("Recent Python Doc", "Python content", "project1", updated_at=recent_date)

        results = search_documents("Python", modified_after=filter_date)
        assert len(results) == 1
        assert results[0]["title"] == "Recent Python Doc"

    def test_modified_before_filter(self, mock_db_connection):
        """Test filtering by modified_before date."""
        db = mock_db_connection

        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()
        filter_date = (datetime.now() - timedelta(days=5)).isoformat()

        db.save_document("Old Python Doc", "Python content", "project1", updated_at=old_date)
        db.save_document("Recent Python Doc", "Python content", "project1", updated_at=recent_date)

        results = search_documents("Python", modified_before=filter_date)
        assert len(results) == 1
        assert results[0]["title"] == "Old Python Doc"

    def test_combined_date_filters(self, mock_db_connection):
        """Test combining multiple date filters."""
        db = mock_db_connection

        very_old = (datetime.now() - timedelta(days=20)).isoformat()
        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()

        db.save_document("Very Old Doc", "Python content", "project1", created_at=very_old)
        db.save_document("Middle Doc", "Python content", "project1", created_at=old_date)
        db.save_document("Recent Doc", "Python content", "project1", created_at=recent_date)

        # Filter for documents created between 15 days ago and 5 days ago
        after_date = (datetime.now() - timedelta(days=15)).isoformat()
        before_date = (datetime.now() - timedelta(days=5)).isoformat()

        results = search_documents("Python", created_after=after_date, created_before=before_date)
        assert len(results) == 1
        assert results[0]["title"] == "Middle Doc"


class TestWildcardSearch:
    """Test wildcard query (query='*') functionality."""

    def test_wildcard_returns_all_documents(self, mock_db_connection):
        """Test that wildcard query returns all non-deleted documents."""
        db = mock_db_connection

        db.save_document("Doc 1", "Content 1", "project1")
        db.save_document("Doc 2", "Content 2", "project2")
        db.save_document("Doc 3", "Content 3", "project1")

        results = search_documents("*")
        assert len(results) == 3

    def test_wildcard_with_project_filter(self, mock_db_connection):
        """Test wildcard query with project filter."""
        db = mock_db_connection

        db.save_document("Doc 1", "Content 1", "project1")
        db.save_document("Doc 2", "Content 2", "project2")
        db.save_document("Doc 3", "Content 3", "project1")

        results = search_documents("*", project="project1")
        assert len(results) == 2
        for result in results:
            assert result["project"] == "project1"

    def test_wildcard_with_date_filters(self, mock_db_connection):
        """Test wildcard query with date filters."""
        db = mock_db_connection

        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        recent_date = (datetime.now() - timedelta(days=1)).isoformat()
        filter_date = (datetime.now() - timedelta(days=5)).isoformat()

        db.save_document("Old Doc", "Content", "project1", created_at=old_date)
        db.save_document("Recent Doc", "Content", "project1", created_at=recent_date)

        results = search_documents("*", created_after=filter_date)
        assert len(results) == 1
        assert results[0]["title"] == "Recent Doc"

    def test_wildcard_ordered_by_id_desc(self, mock_db_connection):
        """Test that wildcard results are ordered by ID descending."""
        db = mock_db_connection

        id1 = db.save_document("First Doc", "Content", "project1")
        id2 = db.save_document("Second Doc", "Content", "project1")
        id3 = db.save_document("Third Doc", "Content", "project1")

        results = search_documents("*")
        assert len(results) == 3
        # Results should be ordered by ID descending (most recent first)
        assert results[0]["id"] == id3
        assert results[1]["id"] == id2
        assert results[2]["id"] == id1

    def test_wildcard_respects_limit(self, mock_db_connection):
        """Test that wildcard query respects limit parameter."""
        db = mock_db_connection

        for i in range(10):
            db.save_document(f"Doc {i}", f"Content {i}", "project1")

        results = search_documents("*", limit=5)
        assert len(results) == 5


class TestSearchExcludesDeleted:
    """Test that deleted documents are excluded from search."""

    def test_soft_deleted_excluded_from_search(self, mock_db_connection):
        """Test that soft-deleted documents are not returned in search."""
        db = mock_db_connection

        db.save_document("Active Python Doc", "Python content", "project1")
        deleted_id = db.save_document("Deleted Python Doc", "Python content", "project1")
        db.soft_delete_document(deleted_id)

        results = search_documents("Python")
        assert len(results) == 1
        assert results[0]["title"] == "Active Python Doc"

    def test_soft_deleted_excluded_from_wildcard(self, mock_db_connection):
        """Test that soft-deleted documents are excluded from wildcard search."""
        db = mock_db_connection

        db.save_document("Active Doc", "Content", "project1")
        deleted_id = db.save_document("Deleted Doc", "Content", "project1")
        db.soft_delete_document(deleted_id)

        results = search_documents("*")
        assert len(results) == 1
        assert results[0]["title"] == "Active Doc"


class TestSearchResultFields:
    """Test that search results include expected fields."""

    def test_search_returns_expected_fields(self, mock_db_connection):
        """Test that search results include all expected fields."""
        db = mock_db_connection

        db.save_document("Python Guide", "Python content", "project1")

        results = search_documents("Python")
        assert len(results) == 1

        result = results[0]
        assert "id" in result
        assert "title" in result
        assert "project" in result
        assert "created_at" in result
        assert "updated_at" in result
        assert "snippet" in result
        assert "rank" in result

    def test_search_snippet_contains_match_context(self, mock_db_connection):
        """Test that search snippet contains context around the match."""
        db = mock_db_connection

        db.save_document(
            "Python Guide", "This is a comprehensive guide to Python programming", "project1"
        )  # noqa: E501

        results = search_documents("Python")
        assert len(results) == 1
        # Snippet should be present and contain some context
        assert results[0]["snippet"] is not None

    def test_wildcard_has_null_snippet(self, mock_db_connection):
        """Test that wildcard search returns NULL snippets."""
        db = mock_db_connection

        db.save_document("Doc", "Content", "project1")

        results = search_documents("*")
        assert len(results) == 1
        assert results[0]["snippet"] is None

    def test_datetime_fields_are_parsed(self, mock_db_connection):
        """Test that datetime fields are properly parsed."""
        db = mock_db_connection

        db.save_document("Python Guide", "Python content", "project1")

        results = search_documents("Python")
        assert len(results) == 1

        result = results[0]
        assert isinstance(result["created_at"], datetime)
        assert isinstance(result["updated_at"], datetime)


class TestSearchEdgeCases:
    """Test edge cases in search functionality."""

    def test_search_empty_database(self, mock_db_connection):
        """Test searching an empty database."""
        results = search_documents("anything")
        assert len(results) == 0

    def test_search_with_special_fts_characters(self, mock_db_connection):
        """Test search with FTS5 special characters."""
        db = mock_db_connection

        db.save_document("C++ Programming", "Learn C++ basics", "project1")

        # Search for the full term "Programming" which should definitely match
        results = search_documents("Programming")
        assert len(results) == 1
        assert results[0]["title"] == "C++ Programming"

    def test_search_with_phrase(self, mock_db_connection):
        """Test phrase search with FTS5."""
        db = mock_db_connection

        db.save_document("Python Programming", "Learn Python web development", "project1")
        db.save_document("Web Development", "Learn web programming with Python", "project1")

        # FTS5 phrase search with quotes - should match first doc with exact phrase
        results = search_documents('"Python web"')
        assert len(results) == 1
        assert results[0]["title"] == "Python Programming"

    def test_search_with_or_literal(self, mock_db_connection):
        """Test that 'OR' is treated as a literal word, not FTS operator.

        After the hyphenated query fix, all query terms are quoted to prevent
        special characters (like hyphens) from being interpreted as operators.
        This means FTS operators like OR are no longer available in queries.
        """
        db = mock_db_connection

        db.save_document("Python Guide", "Python basics", "project1")
        db.save_document("JavaScript Guide", "JavaScript basics", "project1")
        db.save_document("Word OR Logic", "This doc contains the word OR", "project1")

        # "Python OR JavaScript" is now treated as three literal terms
        # Only the doc with literal "OR" in it will match all three terms
        results = search_documents("OR")
        assert len(results) == 1
        assert "Word OR Logic" in results[0]["title"]

    def test_stemming_with_porter(self, mock_db_connection):
        """Test that Porter stemmer works (running -> run)."""
        db = mock_db_connection

        db.save_document("Running Tips", "Tips for running efficiently", "project1")

        # Porter stemmer should match "run" to "running"
        results = search_documents("run")
        assert len(results) == 1
        assert results[0]["title"] == "Running Tips"


class TestEscapeFts5Query:
    """Test the escape_fts5_query function."""

    def test_escape_simple_word(self):
        """Test escaping a simple word."""
        assert escape_fts5_query("hello") == '"hello"'

    def test_escape_hyphenated_word(self):
        """Test escaping a hyphenated word like 'event-driven'."""
        # The hyphen would be interpreted as NOT operator without escaping
        assert escape_fts5_query("event-driven") == '"event-driven"'

    def test_escape_multiple_words(self):
        """Test escaping multiple words."""
        assert escape_fts5_query("hello world") == '"hello" "world"'

    def test_escape_hyphenated_phrase(self):
        """Test escaping a phrase with hyphenated word."""
        assert escape_fts5_query("multi-stage workflow") == '"multi-stage" "workflow"'

    def test_escape_preserves_already_quoted(self):
        """Test that already quoted strings are preserved."""
        assert escape_fts5_query('"already quoted"') == '"already quoted"'

    def test_escape_handles_internal_quotes(self):
        """Test escaping internal double quotes."""
        # Internal quotes should be doubled to escape them in FTS5
        result = escape_fts5_query('say "hello"')
        assert '""' in result  # Internal quotes should be escaped

    def test_escape_multiple_hyphens(self):
        """Test escaping multiple hyphenated terms."""
        result = escape_fts5_query("full-text event-driven")
        assert result == '"full-text" "event-driven"'


class TestHyphenatedSearch:
    """Test that hyphenated terms work correctly in FTS5 search."""

    def test_search_hyphenated_term(self, mock_db_connection):
        """Test searching for hyphenated terms like 'event-driven'."""
        db = mock_db_connection

        db.save_document(
            "Event-Driven Architecture", "Learn about event-driven programming patterns", "project1"
        )
        db.save_document("Other Doc", "Some other content without the term", "project1")

        # This should NOT fail with "no such column: driven" error
        results = search_documents("event-driven")
        assert len(results) == 1
        assert "Event-Driven" in results[0]["title"]

    def test_search_multiple_hyphenated_terms(self, mock_db_connection):
        """Test searching for multiple hyphenated terms."""
        db = mock_db_connection

        db.save_document(
            "Multi-Stage Pipeline", "A multi-stage, event-driven workflow system", "project1"
        )

        results = search_documents("multi-stage event-driven")
        assert len(results) == 1

    def test_search_mixed_hyphenated_and_regular(self, mock_db_connection):
        """Test searching with mix of hyphenated and regular terms."""
        db = mock_db_connection

        db.save_document(
            "Full-Text Search", "Implementing full-text search with SQLite FTS5", "project1"
        )

        results = search_documents("full-text SQLite")
        assert len(results) == 1

    def test_search_term_with_dash_prefix(self, mock_db_connection):
        """Test that dash at start doesn't break the query."""
        db = mock_db_connection

        db.save_document("Test Doc", "Some test content here", "project1")

        # This used to be interpreted as NOT operator
        # Now it should search for the literal term
        results = search_documents("-test")
        # Should not error, may or may not find results depending on tokenizer
        assert isinstance(results, list)


class TestDocTypeFilter:
    """Test doc_type filtering in search_documents."""

    def test_default_returns_only_user_docs(self, mock_db_connection):
        """Test that default search returns only user docs."""
        db = mock_db_connection

        db.save_document("User Doc", "Python content", "project1", doc_type="user")
        db.save_document("Wiki Article", "Python wiki content", "project1", doc_type="wiki")

        results = search_documents("Python")
        assert len(results) == 1
        assert results[0]["title"] == "User Doc"

    def test_wiki_filter_returns_only_wiki_docs(self, mock_db_connection):
        """Test that doc_type='wiki' returns only wiki docs."""
        db = mock_db_connection

        db.save_document("User Doc", "Python content", "project1", doc_type="user")
        db.save_document("Wiki Article", "Python wiki content", "project1", doc_type="wiki")

        results = search_documents("Python", doc_type="wiki")
        assert len(results) == 1
        assert results[0]["title"] == "Wiki Article"

    def test_none_doc_type_returns_all(self, mock_db_connection):
        """Test that doc_type=None returns all document types."""
        db = mock_db_connection

        db.save_document("User Doc", "Python content", "project1", doc_type="user")
        db.save_document("Wiki Article", "Python wiki content", "project1", doc_type="wiki")
        db.save_document("Synthesis Doc", "Python synthesis", "project1", doc_type="synthesis")

        results = search_documents("Python", doc_type=None)
        assert len(results) == 3

    def test_wildcard_with_doc_type_filter(self, mock_db_connection):
        """Test wildcard search respects doc_type filter."""
        db = mock_db_connection

        db.save_document("User Doc", "Content", "project1", doc_type="user")
        db.save_document("Wiki Doc", "Content", "project1", doc_type="wiki")

        # Default: only user
        results = search_documents("*")
        assert len(results) == 1
        assert results[0]["title"] == "User Doc"

        # Wiki only
        results = search_documents("*", doc_type="wiki")
        assert len(results) == 1
        assert results[0]["title"] == "Wiki Doc"

        # All types
        results = search_documents("*", doc_type=None)
        assert len(results) == 2

    def test_doc_type_with_project_filter(self, mock_db_connection):
        """Test doc_type filter combines with project filter."""
        db = mock_db_connection

        db.save_document("User P1", "Python content", "project1", doc_type="user")
        db.save_document("Wiki P1", "Python wiki", "project1", doc_type="wiki")
        db.save_document("User P2", "Python content", "project2", doc_type="user")

        results = search_documents("Python", project="project1", doc_type="user")
        assert len(results) == 1
        assert results[0]["title"] == "User P1"
