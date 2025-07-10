"""Integration tests using environment variable override."""

import pytest
import tempfile
from pathlib import Path
from typer.testing import CliRunner
import os

# Set test database BEFORE any imports
TEST_DB_PATH = None

def pytest_configure(config):
    """Set up test database path before any imports."""
    global TEST_DB_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        TEST_DB_PATH = Path(tmpdir) / "test.db"


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Force all tests to use a temporary database."""
    # Create a test database path
    test_db = tmp_path / "test.db"
    
    # Override environment to use test path
    monkeypatch.setenv("EMDX_DB_PATH", str(test_db))
    
    # Patch SQLiteDatabase.__init__ to respect the env var
    from emdx.sqlite_database import SQLiteDatabase
    original_init = SQLiteDatabase.__init__
    
    def test_init(self, db_path=None):
        # Always use env var if set
        env_path = os.getenv("EMDX_DB_PATH")
        if env_path:
            db_path = Path(env_path)
        original_init(self, db_path)
    
    monkeypatch.setattr(SQLiteDatabase, "__init__", test_init)
    
    # Force recreation of the global db instance
    import emdx.sqlite_database
    import emdx.database
    emdx.sqlite_database.db = SQLiteDatabase()
    emdx.database.db = emdx.sqlite_database.db
    
    yield test_db


# Import AFTER fixture is defined
from emdx.cli import app

runner = CliRunner()


def test_basic_save_list():
    """Test basic save and list workflow."""
    with runner.isolated_filesystem():
        # Create a test file
        Path("test.md").write_text("# Test\n\nContent")
        
        # Save it
        result = runner.invoke(app, ["save", "test.md"])
        assert result.exit_code == 0
        
        # List should show it
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "test.md" in result.stdout or "Test" in result.stdout


def test_find_documents():
    """Test finding documents."""
    with runner.isolated_filesystem():
        # Create test files
        Path("python.md").write_text("# Python Guide\n\nLearn Python")
        Path("js.md").write_text("# JavaScript Guide\n\nLearn JS")
        
        # Save them
        runner.invoke(app, ["save", "python.md"])
        runner.invoke(app, ["save", "js.md"])
        
        # Find Python docs
        result = runner.invoke(app, ["find", "Python"])
        assert result.exit_code == 0
        assert "Python" in result.stdout


def test_stats_empty():
    """Test stats on empty database."""
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "0" in result.stdout or "No documents" in result.stdout