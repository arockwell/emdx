"""Test using the new reset_db functionality."""

import pytest
import tempfile
from pathlib import Path
from typer.testing import CliRunner

from emdx.database import reset_db
from emdx.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_db():
    """Reset database to use a test database for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = Path(tmpdir) / "test.db"
        
        # Reset the global database to use our test path
        reset_db(test_db_path)
        
        # Also update the reference in database module
        import emdx.database
        emdx.database.db = emdx.database.get_db()
        
        yield test_db_path


def test_save_and_list():
    """Test saving and listing documents."""
    with runner.isolated_filesystem():
        # Create a test file
        Path("test.md").write_text("# Test Document\n\nThis is a test.")
        
        # Save it
        result = runner.invoke(app, ["save", "test.md", "Test Doc"])
        assert result.exit_code == 0
        
        # List documents
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Test Doc" in result.stdout


def test_save_and_find():
    """Test saving and finding documents."""
    with runner.isolated_filesystem():
        # Create test files
        Path("python.md").write_text("# Python Guide\n\nLearn Python programming.")
        Path("js.md").write_text("# JavaScript Guide\n\nLearn JavaScript.")
        
        # Save them
        runner.invoke(app, ["save", "python.md"])
        runner.invoke(app, ["save", "js.md"])
        
        # Search for Python
        result = runner.invoke(app, ["find", "Python"])
        assert result.exit_code == 0
        assert "Python" in result.stdout


def test_stats_command():
    """Test stats command."""
    with runner.isolated_filesystem():
        # Create and save a few documents
        for i in range(3):
            Path(f"doc{i}.md").write_text(f"# Document {i}\n\nContent.")
            runner.invoke(app, ["save", f"doc{i}.md"])
        
        # Check stats
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "3" in result.stdout  # Should show 3 documents