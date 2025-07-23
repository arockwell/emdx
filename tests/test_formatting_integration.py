"""Integration tests for document formatting across EMDX interfaces."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from emdx.config import get_db_path
from emdx.database.connection import DatabaseConnection


class TestFormattingIntegration:
    """Test formatting across different EMDX interfaces."""

    @pytest.fixture
    def test_db(self):
        """Create a temporary test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            os.environ["EMDX_DB_PATH"] = str(db_path)
            db = DatabaseConnection(db_path)
            db.ensure_schema()
            yield db_path
            # Cleanup
            if "EMDX_DB_PATH" in os.environ:
                del os.environ["EMDX_DB_PATH"]

    @pytest.fixture
    def formatting_test_doc(self):
        """Path to the comprehensive formatting test document."""
        return Path(__file__).parent / "fixtures" / "formatting_test.md"

    def run_emdx(self, args, check=True):
        """Run emdx command and return result."""
        cmd = ["python", "-m", "emdx"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result

    def test_save_and_view_formatting(self, test_db, formatting_test_doc):
        """Test saving and viewing a document with complex formatting."""
        # Save the test document
        result = self.run_emdx(["save", str(formatting_test_doc), "--title", "Formatting Test"])
        assert result.returncode == 0
        assert "Saved as #1" in result.stdout

        # View the document in raw mode
        result = self.run_emdx(["view", "1", "--raw", "--no-pager"])
        assert result.returncode == 0
        assert "# EMDX Formatting Test Document" in result.stdout
        assert "**Bold text**" in result.stdout
        assert "```python" in result.stdout

        # View the document with formatting (no-pager to capture output)
        result = self.run_emdx(["view", "1", "--no-pager"])
        assert result.returncode == 0
        # Rich will format the markdown, so we check for content presence
        assert "EMDX Formatting Test Document" in result.stdout

    def test_search_formatting_display(self, test_db, formatting_test_doc):
        """Test that search results display formatting correctly."""
        # Save multiple documents
        self.run_emdx(["save", str(formatting_test_doc), "--title", "Test Doc 1"])

        # Create another test document
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Simple Document\n\nThis has **bold** text and `code`.")
            simple_doc = f.name

        self.run_emdx(["save", simple_doc, "--title", "Test Doc 2"])
        os.unlink(simple_doc)

        # Search for content
        result = self.run_emdx(["find", "bold"])
        assert result.returncode == 0
        assert "Test Doc 1" in result.stdout
        assert "Test Doc 2" in result.stdout

    def test_tag_formatting_display(self, test_db):
        """Test that tags display correctly with proper formatting."""
        # Create a document with tags
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Tagged Document\n\nContent with tags.")
            doc_path = f.name

        # Save with tags using emoji aliases
        result = self.run_emdx(
            ["save", doc_path, "--title", "Tagged Doc", "--tags", "gameplan,active,refactor"]
        )
        assert result.returncode == 0
        os.unlink(doc_path)

        # Extract document ID
        doc_id = result.stdout.split("#")[1].split(":")[0]

        # View to see tag display
        result = self.run_emdx(["view", doc_id, "--no-pager"])
        assert result.returncode == 0
        # Should show tags in proper order: Document Type → Status → Other
        assert "🎯" in result.stdout  # gameplan
        assert "🚀" in result.stdout  # active
        assert "🔧" in result.stdout  # refactor

    def test_list_command_formatting(self, test_db, formatting_test_doc):
        """Test that list command displays documents with proper formatting."""
        # Save multiple documents
        self.run_emdx(["save", str(formatting_test_doc), "--title", "Doc 1", "--tags", "gameplan"])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Another Document\n\nWith different content.")
            doc2_path = f.name

        self.run_emdx(["save", doc2_path, "--title", "Doc 2", "--tags", "bug,urgent"])
        os.unlink(doc2_path)

        # List all documents
        result = self.run_emdx(["list"])
        assert result.returncode == 0
        assert "Doc 1" in result.stdout
        assert "Doc 2" in result.stdout
        assert "🎯" in result.stdout  # gameplan tag
        assert "🐛" in result.stdout  # bug tag
        assert "🚨" in result.stdout  # urgent tag

    def test_unicode_content_handling(self, test_db):
        """Test handling of unicode content."""
        # Create document with unicode
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(
                """# Unicode Test 🎯

Emojis: 🚀 ✅ 🏗️
Math: π ≈ ∑
Languages: 中文 日本語 한국어
"""
            )
            unicode_doc = f.name

        # Save and verify
        result = self.run_emdx(["save", unicode_doc, "--title", "Unicode Test"])
        assert result.returncode == 0
        os.unlink(unicode_doc)

        # View the document
        result = self.run_emdx(["view", "1", "--raw", "--no-pager"])
        assert result.returncode == 0
        assert "🎯" in result.stdout
        assert "π" in result.stdout
        assert "中文" in result.stdout

    def test_code_syntax_themes(self, test_db):
        """Test code syntax highlighting with different themes."""
        # Create document with code
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                """# Code Test

```python
def hello():
    print("Hello, World!")
```
"""
            )
            code_doc = f.name

        self.run_emdx(["save", code_doc, "--title", "Code Test"])
        os.unlink(code_doc)

        # View with default theme
        result = self.run_emdx(["view", "1", "--no-pager"])
        assert result.returncode == 0
        assert "def hello():" in result.stdout

        # Test with custom theme via environment
        env = os.environ.copy()
        env["EMDX_CODE_THEME"] = "dracula"
        cmd = ["python", "-m", "emdx", "view", "1", "--no-pager"]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        assert result.returncode == 0

    def test_long_content_truncation(self, test_db):
        """Test handling of very long content."""
        # Create document with long lines
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            long_line = "x" * 300
            f.write(f"# Long Content\n\n{long_line}\n\nEnd of document.")
            long_doc = f.name

        result = self.run_emdx(["save", long_doc, "--title", "Long Content"])
        assert result.returncode == 0
        os.unlink(long_doc)

        # Search should show truncated snippet
        result = self.run_emdx(["find", "xxx"])
        assert result.returncode == 0
        # Snippet should be truncated, not show full 300 chars
        assert "..." in result.stdout or len(result.stdout.split("\n")[2]) < 200

    def test_edge_case_markdown(self, test_db):
        """Test edge cases in markdown formatting."""
        # Create document with edge cases
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(
                """# Edge Cases

Empty code block:
```
```

Unclosed **bold

Nested ***bold and *italic* inside***

HTML entities: &lt; &gt; &amp;
"""
            )
            edge_doc = f.name

        result = self.run_emdx(["save", edge_doc, "--title", "Edge Cases"])
        assert result.returncode == 0
        os.unlink(edge_doc)

        # View should handle edge cases gracefully
        result = self.run_emdx(["view", "1", "--no-pager"])
        assert result.returncode == 0
        # Should not crash on malformed markdown

    def test_json_output_formatting(self, test_db, formatting_test_doc):
        """Test JSON output preserves formatting."""
        # Save document
        self.run_emdx(["save", str(formatting_test_doc), "--title", "JSON Test", "--tags", "test"])

        # Search with JSON output
        result = self.run_emdx(["find", "EMDX", "--json"])
        assert result.returncode == 0

        import json

        data = json.loads(result.stdout)
        assert len(data) == 1
        assert data[0]["title"] == "JSON Test"
        assert "🧪" in data[0]["tags"]  # test emoji

    @pytest.mark.parametrize(
        "content,expected",
        [
            ("", True),  # Empty content
            ("\n\n\n", True),  # Only newlines
            ("   ", True),  # Only spaces
            ("# Title", True),  # Minimal content
            ("🎯" * 100, True),  # Many emojis
        ],
    )
    def test_minimal_content_handling(self, test_db, content, expected):
        """Test handling of minimal or edge-case content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            doc_path = f.name

        result = self.run_emdx(["save", doc_path, "--title", "Minimal"], check=False)
        os.unlink(doc_path)

        if expected:
            assert result.returncode == 0
        # Verify document was saved and can be viewed
        if result.returncode == 0:
            result = self.run_emdx(["view", "1", "--no-pager"])
            assert result.returncode == 0