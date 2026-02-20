"""Shared pytest fixtures for emdx tests."""

import os
import tempfile
from pathlib import Path

import pytest
from test_fixtures import DatabaseForTesting

# =============================================================================
# CRITICAL: Automatic test database isolation
# =============================================================================
# This fixture runs automatically for ALL tests, ensuring that no test can
# ever accidentally write to the real user database at ~/.config/emdx/knowledge.db
#
# It works by setting EMDX_TEST_DB environment variable before any emdx imports,
# which redirects all database operations to a temporary file.
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def isolate_test_database(tmp_path_factory):
    """Automatically isolate ALL tests from the real database.

    This session-scoped fixture runs once before any tests and ensures that
    the global db_connection in emdx.database.connection uses a temp database
    instead of the real user database.

    This protects against:
    - Tests that forget to mock the database
    - Tests that use CLI commands (emdx save, etc.)
    - Tests that import modules that use the global db_connection
    - Workflow agents that generate tests without proper isolation
    """
    # Create a temp database file that persists for the entire test session
    test_db_dir = tmp_path_factory.mktemp("emdx_test_db")
    test_db_path = test_db_dir / "test_knowledge.db"

    # Set environment variable BEFORE any emdx imports
    old_env = os.environ.get("EMDX_TEST_DB")
    os.environ["EMDX_TEST_DB"] = str(test_db_path)

    # Force reload of the db_connection singleton with the new path
    # This is necessary because the module may have been imported already
    try:
        import emdx.database.connection as conn_module
        # Recreate the global instance with the test path
        new_db_connection = conn_module.DatabaseConnection()
        conn_module.db_connection = new_db_connection

        # SAFETY CHECK: Verify we're using the test database, not the real one
        real_db = Path.home() / ".config" / "emdx" / "knowledge.db"
        assert str(conn_module.db_connection.db_path) != str(real_db), \
            f"CRITICAL: Test is using real database! Expected temp path, got {conn_module.db_connection.db_path}"  # noqa: E501

        # Run migrations on the test database
        conn_module.db_connection.ensure_schema()

        # CRITICAL: Import and patch ALL modules that import db_connection directly
        # Python caches import bindings, so `from X import Y` doesn't see updates to X.Y
        # We MUST import these modules now (if not already) and patch them
        modules_to_patch = [
            'emdx.database.documents',
            'emdx.database.search',
            'emdx.database.groups',
            'emdx.database.document_links',
            'emdx.models.executions',
            'emdx.services.execution_monitor',
            'emdx.services.execution_service',
        ]
        import importlib
        import sys
        for mod_name in modules_to_patch:
            try:
                # Import the module if not already imported
                if mod_name not in sys.modules:
                    importlib.import_module(mod_name)
                # Patch its db_connection reference
                if hasattr(sys.modules[mod_name], 'db_connection'):
                    sys.modules[mod_name].db_connection = new_db_connection
            except ImportError:
                pass  # Module doesn't exist, skip

        # Final safety verification
        assert str(conn_module.db_connection.db_path) == str(test_db_path), \
            f"Database path mismatch: expected {test_db_path}, got {conn_module.db_connection.db_path}"  # noqa: E501

    except ImportError:
        pass  # Module not imported yet, will pick up env var on first import

    yield test_db_path

    # Cleanup
    if old_env is None:
        os.environ.pop("EMDX_TEST_DB", None)
    else:
        os.environ["EMDX_TEST_DB"] = old_env


@pytest.fixture(scope="function")
def temp_db():
    """Create a temporary in-memory SQLite database for testing."""
    db = DatabaseForTesting(":memory:")
    yield db
    db.close()


@pytest.fixture(scope="function")
def temp_db_file():
    """Create a temporary SQLite database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = DatabaseForTesting(str(db_path))
    yield db

    # Cleanup
    db_path.unlink(missing_ok=True)


@pytest.fixture(scope="function")
def sample_documents(temp_db):
    """Add some sample documents to the database with tags.

    Tags are added directly via SQL to avoid global state contamination
    from the emdx.models.tags module which uses the global database connection.
    """
    docs = [
        {
            "title": "Python Testing Guide",
            "content": "This is a comprehensive guide to testing in Python using pytest.",
            "project": "test-project",
            "tags": ["python", "testing", "pytest"],
        },
        {
            "title": "Docker Best Practices",
            "content": "Learn about Docker containers and best practices for production.",
            "project": "test-project",
            "tags": ["docker", "devops"],
        },
        {
            "title": "Git Workflow",
            "content": "Understanding git branches, commits, and collaborative workflows.",
            "project": "another-project",
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

        # Add tags directly via SQL to avoid global state contamination
        for tag_name in doc["tags"]:
            tag_name = tag_name.lower().strip()
            # Get or create tag
            cursor = conn.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            result = cursor.fetchone()
            if result:
                tag_id = result[0]
            else:
                cursor = conn.execute(
                    "INSERT INTO tags (name, usage_count) VALUES (?, 0)", (tag_name,)
                )
                tag_id = cursor.lastrowid

            # Link tag to document
            conn.execute(
                "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )
            # Update usage count
            conn.execute(
                "UPDATE tags SET usage_count = usage_count + 1 WHERE id = ?",
                (tag_id,),
            )

    conn.commit()
    return doc_ids
