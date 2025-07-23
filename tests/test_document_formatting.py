"""
Comprehensive test suite for document formatting validation
"""

import pytest
from typing import Optional, Tuple
from emdx.utils.formatting import DocumentFormatter, FormatValidationError


class TestDocumentFormatter:
    """Test the DocumentFormatter class"""
    
    def test_empty_content_rejection(self):
        """Empty content should be rejected"""
        formatter = DocumentFormatter()
        
        with pytest.raises(FormatValidationError, match="empty"):
            formatter.validate_and_format("")
            
        with pytest.raises(FormatValidationError, match="empty"):
            formatter.validate_and_format(None)
    
    def test_whitespace_only_rejection(self):
        """Whitespace-only content should be rejected"""
        formatter = DocumentFormatter()
        
        test_cases = [
            " ",
            "\n",
            "\t",
            "   \n   \n   ",
            "\t\t\n\n\t\t",
            " " * 100,
        ]
        
        for content in test_cases:
            with pytest.raises(FormatValidationError, match="whitespace"):
                formatter.validate_and_format(content)
    
    def test_line_ending_normalization(self):
        """CRLF should be converted to LF"""
        formatter = DocumentFormatter()
        
        # Windows line endings
        content = "Line 1\r\nLine 2\r\nLine 3"
        formatted = formatter.validate_and_format(content)
        assert "\r\n" not in formatted
        assert formatted == "Line 1\nLine 2\nLine 3\n"
        
        # Mixed line endings
        content = "Line 1\r\nLine 2\nLine 3\r\n"
        formatted = formatter.validate_and_format(content)
        assert "\r\n" not in formatted
        assert formatted == "Line 1\nLine 2\nLine 3\n"
    
    def test_trailing_whitespace_removal(self):
        """Trailing whitespace should be removed from lines"""
        formatter = DocumentFormatter()
        
        content = "Line 1   \nLine 2\t\t\nLine 3 "
        formatted = formatter.validate_and_format(content)
        assert formatted == "Line 1\nLine 2\nLine 3\n"
        
        # Preserve intentional indentation
        content = "  Indented line   \n\tTabbed line\t\n"
        formatted = formatter.validate_and_format(content)
        assert formatted == "  Indented line\n\tTabbed line\n"
    
    def test_final_newline_enforcement(self):
        """Documents should end with exactly one newline"""
        formatter = DocumentFormatter()
        
        # Missing final newline
        content = "Line 1\nLine 2"
        formatted = formatter.validate_and_format(content)
        assert formatted.endswith("\n")
        assert not formatted.endswith("\n\n")
        
        # Multiple final newlines
        content = "Line 1\nLine 2\n\n\n"
        formatted = formatter.validate_and_format(content)
        assert formatted.endswith("\n")
        assert not formatted.endswith("\n\n")
    
    def test_unicode_preservation(self):
        """Unicode characters including emoji should be preserved"""
        formatter = DocumentFormatter()
        
        content = "Hello 🎯 World\nTag: 🚀\nChinese: 你好"
        formatted = formatter.validate_and_format(content)
        assert "🎯" in formatted
        assert "🚀" in formatted
        assert "你好" in formatted
    
    def test_code_block_preservation(self):
        """Code blocks should preserve formatting"""
        formatter = DocumentFormatter()
        
        content = """
```python
def hello():
    print("Hello")  # Comment
    return True
```
"""
        formatted = formatter.validate_and_format(content)
        assert "    print(" in formatted  # Indentation preserved
        assert "  # Comment" in formatted  # Spacing preserved
    
    def test_markdown_table_preservation(self):
        """Markdown tables should preserve alignment"""
        formatter = DocumentFormatter()
        
        content = """
| Column 1 | Column 2   | Column 3 |
|----------|------------|----------|
| Data 1   | Data 2     | Data 3   |
| Long data| Short      | Medium   |
"""
        formatted = formatter.validate_and_format(content)
        # Verify table structure is maintained
        lines = formatted.strip().split('\n')
        assert all('|' in line for line in lines)
        assert lines[1].count('-') > 10  # Separator line
    
    def test_large_document_performance(self):
        """Formatting should be performant for large documents"""
        import time
        formatter = DocumentFormatter()
        
        # Create a large document (10,000 lines)
        lines = []
        for i in range(10000):
            lines.append(f"Line {i} with some content   ")
        content = "\n".join(lines)
        
        start_time = time.time()
        formatted = formatter.validate_and_format(content)
        end_time = time.time()
        
        # Should complete in under 1 second
        assert end_time - start_time < 1.0
        # Should have formatted correctly
        assert not any(line.endswith(' ') for line in formatted.split('\n') if line)
    
    def test_special_content_edge_cases(self):
        """Test various edge cases"""
        formatter = DocumentFormatter()
        
        # Single character
        assert formatter.validate_and_format("a") == "a\n"
        
        # Single line
        assert formatter.validate_and_format("Single line") == "Single line\n"
        
        # Lines with only spaces (should become empty lines)
        content = "Line 1\n   \nLine 3"
        formatted = formatter.validate_and_format(content)
        assert formatted == "Line 1\n\nLine 3\n"
    
    def test_title_formatting(self):
        """Test title-specific formatting"""
        formatter = DocumentFormatter()
        
        # Title with whitespace
        assert formatter.format_title("  Title  ") == "Title"
        assert formatter.format_title("\nTitle\n") == "Title"
        assert formatter.format_title("\tTitle\t") == "Title"
        
        # Empty title should raise error
        with pytest.raises(FormatValidationError, match="title"):
            formatter.format_title("   ")
        
        with pytest.raises(FormatValidationError, match="title"):
            formatter.format_title("")
    
    def test_format_options(self):
        """Test configurable formatting options"""
        # Strict mode - rejects any formatting issues
        strict_formatter = DocumentFormatter(strict=True)
        
        # Non-strict mode - fixes formatting issues
        lenient_formatter = DocumentFormatter(strict=False)
        
        content = "Line 1  \nLine 2\r\n"
        
        # Strict mode might reject poorly formatted content
        # Lenient mode fixes it
        formatted = lenient_formatter.validate_and_format(content)
        assert formatted == "Line 1\nLine 2\n"


class TestFormatValidation:
    """Test format validation functions"""
    
    def test_is_binary_content(self):
        """Test binary content detection"""
        formatter = DocumentFormatter()
        
        # Text content
        assert not formatter._is_binary(b"Hello world")
        assert not formatter._is_binary("Hello world".encode('utf-8'))
        
        # Binary content
        assert formatter._is_binary(b"\x00\x01\x02\x03")
        assert formatter._is_binary(b"\xff\xfe\xfd\xfc")
        
        # UTF-8 content should not be considered binary
        assert not formatter._is_binary("Hello 🎯 World".encode('utf-8'))
    
    def test_line_counting(self):
        """Test line counting functionality"""
        formatter = DocumentFormatter()
        
        assert formatter._count_lines("") == 0
        assert formatter._count_lines("Single line") == 1
        assert formatter._count_lines("Line 1\nLine 2") == 2
        assert formatter._count_lines("Line 1\nLine 2\n") == 2
        assert formatter._count_lines("Line 1\n\nLine 3") == 3


# Integration tests with actual save operations
class TestFormattingIntegration:
    """Test formatting integration with document operations"""
    
    def test_save_with_formatting(self, temp_db):
        """Test that save operations apply formatting"""
        from emdx.models.documents import save_document
        from emdx.database import db
        
        # Ensure schema
        db.ensure_schema()
        
        # Try to save empty content (should fail with formatting)
        with pytest.raises(FormatValidationError):
            save_document("Title", "", "test-project")
        
        # Save content with formatting issues
        doc_id = save_document(
            "Test Doc",
            "Line 1  \r\nLine 2\r\n",  # Has CRLF and trailing spaces
            "test-project"
        )
        
        # Retrieve and verify formatting was applied
        from emdx.models.documents import get_document
        doc = get_document(str(doc_id))
        
        # Should have normalized line endings and removed trailing spaces
        assert doc['content'] == "Line 1\nLine 2\n"
    
    def test_edit_with_formatting(self, temp_db):
        """Test that edit operations apply formatting"""
        from emdx.models.documents import save_document, update_document
        from emdx.database import db
        
        db.ensure_schema()
        
        # Create a document
        doc_id = save_document("Original", "Original content", "test-project")
        
        # Update with formatting issues
        success = update_document(
            doc_id,
            "Updated Title  ",  # Trailing spaces
            "Updated content\r\n\r\n"  # CRLF and extra newlines
        )
        
        assert success
        
        # Verify formatting was applied
        from emdx.models.documents import get_document
        doc = get_document(str(doc_id))
        
        assert doc['title'] == "Updated Title"  # Trimmed
        assert doc['content'] == "Updated content\n"  # Normalized