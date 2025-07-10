"""Simplified pytest fixtures for emdx tests."""

import pytest
from pathlib import Path
import tempfile

from test_fixtures_simple import TestDatabase


@pytest.fixture
def test_db():
    """Create a test database for testing."""
    db = TestDatabase(":memory:")
    yield db
    db.close()


@pytest.fixture
def test_db_with_data(test_db):
    """Create a test database with sample data."""
    # Add some documents
    doc1 = test_db.save_document(
        title="Python Testing Guide",
        content="This is a comprehensive guide to testing in Python using pytest.",
        project="test-project"
    )
    
    doc2 = test_db.save_document(
        title="Docker Best Practices", 
        content="Learn about Docker containers and best practices for production.",
        project="test-project"
    )
    
    doc3 = test_db.save_document(
        title="Git Workflow",
        content="Understanding git branches, commits, and collaborative workflows.",
        project="another-project"
    )
    
    return test_db, [doc1, doc2, doc3]