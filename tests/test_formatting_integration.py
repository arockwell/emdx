"""Integration tests for formatting with save command."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from emdx.main import app


class TestFormattingIntegration:
    """Test formatting integration with save command."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_with_validation(self):
        """Test saving with default validation enabled."""
        content = """# Test Document

This is a test with trailing spaces.  

## Section

Good content here.
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_file = f.name

        result = self.runner.invoke(app, ["save", temp_file, "--title", "Test"])
        
        # Should succeed but show warnings
        assert result.exit_code == 0
        assert "Document formatting validation" in result.output
        assert "trailing-whitespace" in result.output
        assert "Saved as #" in result.output

    def test_save_with_no_validate(self):
        """Test saving with validation disabled."""
        content = """Bad document without title  

Has issues but should save."""
        
        result = self.runner.invoke(app, ["save", "-", "--title", "Test", "--no-validate"], input=content)
        
        assert result.exit_code == 0
        assert "Document formatting validation" not in result.output
        assert "Saved as #" in result.output

    def test_save_with_strict_mode(self):
        """Test strict mode fails on errors."""
        content = """## No H1 Title

This document will fail in strict mode.
"""
        result = self.runner.invoke(app, ["save", "-", "--title", "Test", "--strict"], input=content)
        
        assert result.exit_code == 1
        assert "Document has formatting errors" in result.output
        assert "missing-title" in result.output

    def test_save_with_format_flag(self):
        """Test auto-formatting on save."""
        content = """# Title.  

* Wrong list marker  
	Tab character


Multiple blank lines"""

        result = self.runner.invoke(app, ["save", "-", "--title", "Test", "--format"], input=content)
        
        assert result.exit_code == 0
        assert "Document formatted successfully" in result.output
        assert "Saved as #" in result.output

    def test_save_format_and_strict(self):
        """Test that format fixes allow strict mode to pass."""
        content = """# Title.  

Content with fixable issues.  """

        # Without format, strict should show issues
        result = self.runner.invoke(app, ["save", "-", "--title", "Test", "--strict", "--no-validate"], input=content)
        assert result.exit_code == 0  # No validation, so passes

        # With format, should fix and pass strict
        result = self.runner.invoke(app, ["save", "-", "--title", "Test", "--strict", "--format"], input=content)
        assert result.exit_code == 0
        assert "Document formatted successfully" in result.output

    def test_save_shows_issue_table(self):
        """Test that validation shows detailed issue table."""
        content = """# Title

""" + "x" * 101 + """

```
Code without language
```

* Wrong marker
"""
        result = self.runner.invoke(app, ["save", "-", "--title", "Test"], input=content)
        
        assert result.exit_code == 0
        assert "Line" in result.output  # Table header
        assert "Level" in result.output
        assert "Rule" in result.output
        assert "Message" in result.output
        assert "line-too-long" in result.output
        assert "missing-code-language" in result.output
        assert "list-marker-consistency" in result.output

    def test_piped_content_formatting(self):
        """Test formatting works with piped content."""
        content = "# Title\n\nGood content\n"
        
        result = self.runner.invoke(app, ["save", "--title", "Piped"], input=content)
        
        assert result.exit_code == 0
        assert "Saved as #" in result.output
        # Valid document doesn't show validation message when no issues

    @patch('emdx.commands.core.get_git_project')
    def test_file_save_with_format(self, mock_git):
        """Test saving file with formatting."""
        mock_git.return_value = "test-project"
        
        content = """# Document  

Content here.  
"""
        temp_file = Path(self.temp_dir) / "test.md"
        temp_file.write_text(content)
        
        result = self.runner.invoke(app, ["save", str(temp_file), "--format"])
        
        assert result.exit_code == 0
        assert "Document formatted successfully" in result.output
        assert "test-project" in result.output

    def test_empty_document_validation(self):
        """Test validation of empty or minimal documents."""
        # Empty content
        result = self.runner.invoke(app, ["save", "-", "--title", "Empty"], input="")
        assert result.exit_code == 0
        assert "missing-title" in result.output
        
        # Just whitespace
        result = self.runner.invoke(app, ["save", "-", "--title", "Whitespace"], input="   \n\n   ")
        assert result.exit_code == 0
        assert "missing-title" in result.output