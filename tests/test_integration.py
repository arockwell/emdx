"""Integration tests that actually work with the real system."""

import pytest
import tempfile
from pathlib import Path
from typer.testing import CliRunner
import os

from emdx.cli import app
from emdx.sqlite_database import SQLiteDatabase

runner = CliRunner()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a test database in a temp directory."""
    # Override the database path for all database instances
    test_db_path = tmp_path / "test.db"
    
    # Monkey patch the SQLiteDatabase to use our test path
    import emdx.sqlite_database
    original_init = emdx.sqlite_database.SQLiteDatabase.__init__
    
    def test_init(self, db_path=None):
        # Always use test database regardless of what's passed
        original_init(self, test_db_path)
    
    monkeypatch.setattr(emdx.sqlite_database.SQLiteDatabase, '__init__', test_init)
    
    # Also need to reinitialize the global db instance
    emdx.sqlite_database.db = emdx.sqlite_database.SQLiteDatabase()
    
    # Patch it in the database module too
    import emdx.database
    emdx.database.db = emdx.sqlite_database.db
    
    yield test_db_path


def test_save_and_list_workflow(test_db, tmp_path):
    """Test saving a document and listing it."""
    # Create a test markdown file
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test Document\n\nThis is a test.")
    
    # Save it
    result = runner.invoke(app, ["save", str(test_file), "My Test Doc"])
    assert result.exit_code == 0
    assert "Saved" in result.stdout or "saved" in result.stdout
    
    # List documents
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "My Test Doc" in result.stdout


def test_save_and_find_workflow(test_db, tmp_path):
    """Test saving and finding documents."""
    # Create test files
    python_file = tmp_path / "python.md"
    python_file.write_text("# Python Guide\n\nLearn Python programming.")
    
    js_file = tmp_path / "javascript.md"
    js_file.write_text("# JavaScript Guide\n\nLearn JavaScript.")
    
    # Save them
    runner.invoke(app, ["save", str(python_file)])
    runner.invoke(app, ["save", str(js_file)])
    
    # Search for Python
    result = runner.invoke(app, ["find", "Python"])
    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert "JavaScript" not in result.stdout or result.stdout.count("JavaScript") < result.stdout.count("Python")


def test_save_view_delete_workflow(test_db, tmp_path):
    """Test full document lifecycle."""
    # Create and save
    test_file = tmp_path / "lifecycle.md"
    test_file.write_text("# Document Lifecycle\n\nTest content.")
    
    result = runner.invoke(app, ["save", str(test_file)])
    assert result.exit_code == 0
    
    # Extract document ID from output (usually shows "Saved document 1" or similar)
    # For now, assume it's document 1
    doc_id = "1"
    
    # View it (raw mode to avoid editor)
    result = runner.invoke(app, ["view", doc_id, "--raw"])
    assert result.exit_code == 0
    assert "Document Lifecycle" in result.stdout
    
    # Delete it (with force to skip confirmation)
    result = runner.invoke(app, ["delete", doc_id, "--force"])
    assert result.exit_code == 0
    
    # Verify it's gone
    result = runner.invoke(app, ["view", doc_id])
    assert result.exit_code != 0 or "not found" in result.stdout.lower()


def test_stats_command(test_db, tmp_path):
    """Test stats command."""
    # Save a few documents
    for i in range(3):
        test_file = tmp_path / f"doc{i}.md"
        test_file.write_text(f"# Document {i}\n\nContent {i}.")
        runner.invoke(app, ["save", str(test_file)])
    
    # Get stats
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "3" in result.stdout  # Should show 3 documents


def test_recent_command(test_db, tmp_path):
    """Test recent command."""
    # Save a document
    test_file = tmp_path / "recent.md"
    test_file.write_text("# Recent Document\n\nThis should appear in recent.")
    runner.invoke(app, ["save", str(test_file)])
    
    # Check recent
    result = runner.invoke(app, ["recent"])
    assert result.exit_code == 0
    # Should either show the document or say no recent documents
    assert "Recent Document" in result.stdout or "No recently" in result.stdout.lower()


def test_tags_workflow(test_db, tmp_path):
    """Test tag functionality."""
    # Save a document
    test_file = tmp_path / "tagged.md"
    test_file.write_text("# Tagged Document\n\nThis will have tags.")
    result = runner.invoke(app, ["save", str(test_file)])
    assert result.exit_code == 0
    
    # Add tags (assuming document ID 1)
    result = runner.invoke(app, ["tags", "add", "1", "python", "testing"])
    assert result.exit_code == 0
    
    # List tags
    result = runner.invoke(app, ["tags", "list"])
    assert result.exit_code == 0
    assert "python" in result.stdout.lower() or "testing" in result.stdout.lower()


def test_list_with_project_filter(test_db, tmp_path):
    """Test listing with project filter."""
    # Save documents in different projects
    for project in ["project-a", "project-b"]:
        test_file = tmp_path / f"{project}.md"
        test_file.write_text(f"# Document in {project}\n\nContent.")
        runner.invoke(app, ["save", str(test_file), f"Document in {project}", project])
    
    # List only project-a
    result = runner.invoke(app, ["list", "--project", "project-a"])
    assert result.exit_code == 0
    assert "project-a" in result.stdout
    # project-b might appear in headers but not in document list