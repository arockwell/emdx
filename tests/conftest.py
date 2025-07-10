"""Shared pytest fixtures for emdx tests."""

import pytest
from pathlib import Path
import tempfile
from unittest.mock import patch

from emdx.sqlite_database import SQLiteDatabase
from emdx.tags import add_tags_to_document
from test_fixtures import TestDatabase


@pytest.fixture
def temp_db():
    """Create a temporary in-memory SQLite database for testing."""
    db = TestDatabase(":memory:")
    yield db
    db.close()


@pytest.fixture
def temp_db_file():
    """Create a temporary SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    db = TestDatabase(str(db_path))
    yield db
    
    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture
def sample_documents(temp_db):
    """Add some sample documents to the database."""
    docs = [
        {
            "title": "Python Testing Guide",
            "content": "This is a comprehensive guide to testing in Python using pytest.",
            "project": "test-project",
            "tags": ["python", "testing", "pytest"]
        },
        {
            "title": "Docker Best Practices",
            "content": "Learn about Docker containers and best practices for production.",
            "project": "test-project",
            "tags": ["docker", "devops"]
        },
        {
            "title": "Git Workflow",
            "content": "Understanding git branches, commits, and collaborative workflows.",
            "project": "another-project",
            "tags": ["git", "version-control"]
        }
    ]
    
    doc_ids = []
    for doc in docs:
        doc_id = temp_db.save_document(
            title=doc["title"],
            content=doc["content"],
            project=doc["project"]
        )
        import emdx.tags
        original_db = emdx.tags.db
        emdx.tags.db = temp_db
        add_tags_to_document(doc_id, doc["tags"])
        emdx.tags.db = original_db
        doc_ids.append(doc_id)
    
    return doc_ids