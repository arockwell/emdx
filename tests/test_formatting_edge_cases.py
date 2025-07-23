"""
Edge case tests for document formatting
"""

import pytest
from emdx.utils.formatting import DocumentFormatter, FormatValidationError


class TestFormattingEdgeCases:
    """Test edge cases and error conditions"""
    
    def test_maximum_line_length(self):
        """Test handling of very long lines"""
        formatter = DocumentFormatter()
        
        # Very long line (10,000 characters)
        long_line = "x" * 10000
        formatted = formatter.validate_and_format(long_line)
        assert len(formatted) == 10001  # +1 for newline
        
    def test_null_bytes(self):
        """Null bytes should be rejected"""
        formatter = DocumentFormatter()
        
        with pytest.raises(FormatValidationError, match="binary"):
            formatter.validate_and_format("Hello\x00World")
    
    def test_control_characters(self):
        """Most control characters should be rejected except tab and newline"""
        formatter = DocumentFormatter()
        
        # Tab and newline are OK
        content = "Hello\tWorld\nNext line"
        formatted = formatter.validate_and_format(content)
        assert "\t" in formatted
        
        # Other control characters should be rejected
        for i in range(32):
            if i in [9, 10, 13]:  # Tab, LF, CR are handled
                continue
            with pytest.raises(FormatValidationError):
                formatter.validate_and_format(f"Hello{chr(i)}World")
    
    def test_bom_handling(self):
        """Byte Order Mark should be handled gracefully"""
        formatter = DocumentFormatter()
        
        # UTF-8 BOM
        content = "\ufeffHello World"
        formatted = formatter.validate_and_format(content)
        assert formatted == "Hello World\n"
        assert "\ufeff" not in formatted
    
    def test_mixed_indentation(self):
        """Mixed tabs and spaces should be preserved but warned about"""
        formatter = DocumentFormatter()
        
        content = "\tTabbed line\n    Spaced line\n\t    Mixed line"
        formatted = formatter.validate_and_format(content)
        
        # Content should be preserved
        assert "\tTabbed line" in formatted
        assert "    Spaced line" in formatted
        assert "\t    Mixed line" in formatted
    
    def test_very_long_document(self):
        """Test document size limits"""
        formatter = DocumentFormatter()
        
        # 1MB document
        content = "Line\n" * 200000  # ~1MB
        formatted = formatter.validate_and_format(content)
        assert formatted.endswith("\n")
        
        # 10MB document (might have size limit)
        huge_content = "x" * (10 * 1024 * 1024)
        # This might raise an error or succeed based on limits
        try:
            formatted = formatter.validate_and_format(huge_content)
            assert formatted.endswith("\n")
        except FormatValidationError as e:
            assert "size" in str(e).lower()
    
    def test_special_unicode_categories(self):
        """Test various Unicode categories"""
        formatter = DocumentFormatter()
        
        # Zero-width characters
        content = "Hello\u200bWorld"  # Zero-width space
        formatted = formatter.validate_and_format(content)
        # Could either preserve or remove based on policy
        
        # Right-to-left text
        content = "Hello עברית Arabic العربية"
        formatted = formatter.validate_and_format(content)
        assert "עברית" in formatted
        assert "العربية" in formatted
        
        # Combining characters
        content = "e\u0301"  # e with acute accent
        formatted = formatter.validate_and_format(content)
        assert len(formatted) >= 2  # Base + combining + newline
    
    def test_malformed_utf8(self):
        """Malformed UTF-8 should be handled gracefully"""
        formatter = DocumentFormatter()
        
        # This would need to handle bytes directly
        # In practice, Python strings are already valid Unicode
        # So this tests the binary detection path
        
    def test_recursive_formatting(self):
        """Formatting should be idempotent"""
        formatter = DocumentFormatter()
        
        content = "Line 1  \r\nLine 2\t\nLine 3"
        
        # Format once
        formatted1 = formatter.validate_and_format(content)
        
        # Format again - should be identical
        formatted2 = formatter.validate_and_format(formatted1)
        
        assert formatted1 == formatted2
    
    def test_formatting_with_metadata(self):
        """Test formatting with document metadata preservation"""
        formatter = DocumentFormatter()
        
        # YAML frontmatter
        content = """---
title: My Document
tags: [test, formatting]
---

Content here
"""
        formatted = formatter.validate_and_format(content)
        assert "---" in formatted
        assert "title: My Document" in formatted
        assert "Content here" in formatted
    
    def test_html_content(self):
        """HTML content should be allowed but not processed"""
        formatter = DocumentFormatter()
        
        content = "<h1>Title</h1>\n<p>Paragraph   </p>  "
        formatted = formatter.validate_and_format(content)
        assert "<h1>Title</h1>" in formatted
        # Trailing spaces at end of line are removed, but spaces inside tags are preserved
        assert "<p>Paragraph   </p>" in formatted
        assert not formatted.rstrip().endswith("  ")  # Trailing spaces removed
    
    def test_url_preservation(self):
        """URLs should not be modified"""
        formatter = DocumentFormatter()
        
        content = "Visit https://example.com/path?query=value&foo=bar   "
        formatted = formatter.validate_and_format(content)
        assert "https://example.com/path?query=value&foo=bar" in formatted
        assert not formatted.rstrip().endswith(" ")  # Trailing space removed
    
    def test_list_formatting(self):
        """Markdown lists should preserve structure"""
        formatter = DocumentFormatter()
        
        content = """
- Item 1  
  - Subitem 1.1  
  - Subitem 1.2  
- Item 2  

1. Numbered  
   1. Nested  
   2. Items  
"""
        formatted = formatter.validate_and_format(content)
        # Verify structure is maintained
        assert "  - Subitem" in formatted
        assert "   1. Nested" in formatted
    
    def test_blockquote_preservation(self):
        """Blockquotes should maintain structure"""
        formatter = DocumentFormatter()
        
        content = """
> This is a quote
> with multiple lines
> > And nested quotes
"""
        formatted = formatter.validate_and_format(content)
        assert "> This is a quote" in formatted
        assert "> > And nested quotes" in formatted


class TestFormatterConfiguration:
    """Test formatter configuration options"""
    
    def test_custom_validation_rules(self):
        """Test custom validation rules"""
        # Create formatter with custom rules
        formatter = DocumentFormatter(
            max_line_length=80,
            max_document_size=1024 * 1024,  # 1MB
            allow_tabs=False,
            require_final_newline=True
        )
        
        # Line too long
        with pytest.raises(FormatValidationError, match="exceeds maximum length"):
            formatter.validate_and_format("x" * 100)
        
        # Tabs not allowed
        with pytest.raises(FormatValidationError, match="tabs"):
            formatter.validate_and_format("\tTabbed content")
    
    def test_warning_vs_error_modes(self):
        """Test warning vs error behavior"""
        # Strict formatter - raises errors
        strict = DocumentFormatter(strict=True)
        
        # Lenient formatter - fixes issues
        lenient = DocumentFormatter(strict=False)
        
        content = "Line with issues  \r\n"
        
        # Lenient fixes it
        result = lenient.validate_and_format(content)
        assert result == "Line with issues\n"
        
        # Strict still fixes basic issues
        result = strict.validate_and_format(content)
        assert result == "Line with issues\n"
    
    def test_format_report(self):
        """Test formatting report generation"""
        formatter = DocumentFormatter(generate_report=True)
        
        content = "Line 1  \r\nLine 2\nLine 3"
        formatted, report = formatter.validate_and_format_with_report(content)
        
        assert report['changes_made']
        assert 'trailing_whitespace_removed' in report
        assert 'line_endings_normalized' in report
        assert report['lines_affected'] == [1]