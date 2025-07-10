"""Integration tests that test actual functionality."""

import pytest
from unittest.mock import patch
import tempfile
from pathlib import Path
from typer.testing import CliRunner

from emdx.cli import app
from test_fixtures import TestDatabase


runner = CliRunner()


@pytest.mark.skip(reason="Integration tests need actual database setup")
class TestIntegration:
    """Integration tests using temporary databases."""
    
    def test_save_and_find_integration(self):
        """Test saving a document and then finding it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Patch the database path
            with patch('emdx.config.get_db_path', return_value=db_path):
                # Save a document
                result = runner.invoke(app, [
                    "save", 
                    "Integration test content",
                    "--title", "Integration Test Doc",
                    "--project", "test-project"
                ])
                
                # Should succeed
                assert result.exit_code == 0
                assert "Saved as" in result.stdout
                
                # Now find it
                result = runner.invoke(app, ["find", "Integration"])
                assert result.exit_code == 0
                assert "Integration Test Doc" in result.stdout
    
    def test_list_command_integration(self):
        """Test listing documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            with patch('emdx.config.get_db_path', return_value=db_path):
                # Save a few documents
                for i in range(3):
                    result = runner.invoke(app, [
                        "save",
                        f"Document {i} content",
                        "--title", f"Document {i}"
                    ])
                    assert result.exit_code == 0
                
                # List them
                result = runner.invoke(app, ["list"])
                assert result.exit_code == 0
                assert "Document 0" in result.stdout
                assert "Document 1" in result.stdout
                assert "Document 2" in result.stdout
    
    def test_save_from_file_integration(self):
        """Test saving content from a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Create a test file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Content from file")
            
            with patch('emdx.config.get_db_path', return_value=db_path):
                result = runner.invoke(app, [
                    "save",
                    str(test_file),
                    "--title", "File Content"
                ])
                
                assert result.exit_code == 0
                assert "Saved as" in result.stdout
                
                # Verify it was saved
                result = runner.invoke(app, ["find", "Content from file"])
                assert result.exit_code == 0
                assert "File Content" in result.stdout