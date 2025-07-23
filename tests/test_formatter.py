"""Tests for document formatting and validation."""

import pytest

from emdx.utils.formatter import DocumentFormatter, ErrorLevel, FormatIssue
from emdx.utils.format_helpers import apply_auto_fixes, extract_line_context, suggest_fixes


class TestDocumentFormatter:
    """Test document formatting validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.formatter = DocumentFormatter()

    def test_valid_document(self):
        """Test validation of properly formatted document."""
        content = """# Test Document

This is a properly formatted document.

## Section One

Content goes here.

### Subsection

More content with proper formatting.
"""
        result = self.formatter.validate(content)
        assert result.valid
        assert len(result.issues) == 0

    def test_missing_title(self):
        """Test detection of missing H1 title."""
        content = """## Section without title

This document has no H1 title.
"""
        result = self.formatter.validate(content)
        assert not result.valid
        assert any(i.rule == "missing-title" and i.level == ErrorLevel.ERROR 
                  for i in result.issues)

    def test_line_too_long(self):
        """Test detection of lines exceeding max length."""
        long_line = "x" * 101
        content = f"""# Title

{long_line}

Normal line.
"""
        result = self.formatter.validate(content)
        assert not result.valid
        assert any(i.rule == "line-too-long" and i.level == ErrorLevel.ERROR 
                  for i in result.issues)

    def test_line_length_exceptions(self):
        """Test that URLs and code blocks can exceed line length."""
        content = """# Title

This is a very long URL that exceeds the normal line limit: https://example.com/very/long/path/that/exceeds/one/hundred/characters/limit/but/should/be/allowed

```python
# This is a code block with a very long line that should also be allowed to exceed the normal character limit
very_long_variable_name = "this is a string that makes the line exceed 100 characters but it's in a code block"
```
"""
        result = self.formatter.validate(content)
        assert result.valid

    def test_header_hierarchy_skip(self):
        """Test detection of skipped header levels."""
        content = """# Title

### Skipped H2

This skips from H1 to H3.
"""
        result = self.formatter.validate(content)
        assert not result.valid
        assert any(i.rule == "header-hierarchy" and "H1 to H3" in i.message 
                  for i in result.issues)

    def test_header_punctuation(self):
        """Test detection of trailing punctuation in headers."""
        content = """# Title.

## Section:

### Question?

#### Statement!
"""
        result = self.formatter.validate(content)
        # Questions marks are allowed
        issues = [i for i in result.issues if i.rule == "header-punctuation"]
        assert len(issues) == 3  # Period, colon, exclamation
        assert all(i.level == ErrorLevel.WARNING for i in issues)

    def test_code_block_validation(self):
        """Test code block formatting validation."""
        content = """# Title

```
Code without language
```

```python
# Proper code block
def hello():
    pass
```
"""
        result = self.formatter.validate(content)
        assert any(i.rule == "missing-code-language" for i in result.issues)

    def test_unclosed_code_block(self):
        """Test detection of unclosed code blocks."""
        content = """# Title

```python
def unclosed():
    pass
"""
        result = self.formatter.validate(content)
        assert not result.valid
        assert any(i.rule == "unclosed-code-block" and i.level == ErrorLevel.ERROR 
                  for i in result.issues)

    def test_whitespace_issues(self):
        """Test detection of whitespace problems."""
        content = """# Title  

## Section

	Tab character here


Multiple blank lines above.
"""
        result = self.formatter.validate(content)
        assert any(i.rule == "trailing-whitespace" for i in result.issues)
        assert any(i.rule == "no-tabs" for i in result.issues)
        assert any(i.rule == "multiple-blanks" for i in result.issues)

    def test_list_consistency(self):
        """Test list marker consistency checks."""
        content = """# Title

- Good list item
* Bad list item
+ Another bad item
- Back to good
"""
        result = self.formatter.validate(content)
        assert sum(1 for i in result.issues if i.rule == "list-marker-consistency") == 2

    def test_missing_final_newline(self):
        """Test detection of missing final newline."""
        content = "# Title\n\nNo final newline"
        result = self.formatter.validate(content)
        assert any(i.rule == "missing-final-newline" for i in result.issues)

    def test_auto_fix_mode(self):
        """Test auto-fix functionality."""
        content = """# Title.  

## Section	

* List item


Multiple blanks above"""
        
        result = self.formatter.validate(content, auto_fix=True)
        fixed = result.fixed_content
        
        # Check fixes were applied
        assert "# Title" in fixed  # Punctuation removed
        assert "  " not in fixed  # Trailing spaces removed
        assert "\t" not in fixed  # Tabs converted
        assert "- List item" in fixed  # List marker fixed
        assert "\n\n\n" not in fixed  # Multiple blanks fixed
        assert fixed.endswith("\n")  # Final newline added

    def test_format_method(self):
        """Test the format method."""
        content = "# Title.  \n\nContent"
        formatted = self.formatter.format(content)
        assert formatted == "# Title\n\nContent\n"

    def test_complex_document(self):
        """Test validation of complex document with multiple issues."""
        content = """## Missing Title

This document has several issues.  

### Code Examples

```
print("No language specified")
```

#### Deeply Nested.

* List with wrong marker
+ Another wrong marker  

""" + "x" * 101 + """

No final newline"""

        result = self.formatter.validate(content)
        assert not result.valid
        
        # Check various issues are detected
        assert any(i.rule == "missing-title" for i in result.issues)
        assert any(i.rule == "trailing-whitespace" for i in result.issues)
        assert any(i.rule == "missing-code-language" for i in result.issues)
        assert any(i.rule == "header-punctuation" for i in result.issues)
        assert any(i.rule == "list-marker-consistency" for i in result.issues)
        assert any(i.rule == "line-too-long" for i in result.issues)
        assert any(i.rule == "missing-final-newline" for i in result.issues)
        assert any(i.rule == "multiple-blanks" for i in result.issues)


class TestFormatHelpers:
    """Test formatting helper functions."""

    def test_apply_auto_fixes(self):
        """Test the apply_auto_fixes function."""
        content = """# Title.  

* Wrong marker
	Tab here


Multiple blanks"""
        
        fixed, applied = apply_auto_fixes(content)
        
        assert "# Title" in fixed
        assert "- Wrong marker" in fixed
        assert "\t" not in fixed
        assert "\n\n\n" not in fixed
        assert fixed.endswith("\n")
        
        assert "Removed trailing whitespace" in applied
        assert "Standardized list markers" in applied
        assert "Converted tabs to spaces" in applied
        assert "Normalized blank lines" in applied

    def test_extract_line_context(self):
        """Test line context extraction."""
        content = """Line 1
Line 2
Line 3
Line 4
Line 5"""
        
        context = extract_line_context(content, 3, context_lines=1)
        assert len(context) == 3
        assert context[0] == (2, "Line 2", False)
        assert context[1] == (3, "Line 3", True)
        assert context[2] == (4, "Line 4", False)

    def test_suggest_fixes(self):
        """Test fix suggestions."""
        assert "Add a title" in suggest_fixes("", "missing-title")
        assert "Break long lines" in suggest_fixes("", "line-too-long")
        assert "proper nesting" in suggest_fixes("", "header-hierarchy")
        assert "```python" in suggest_fixes("", "missing-code-language")
        assert suggest_fixes("", "unknown-rule") is None


class TestFormatResult:
    """Test FormatResult dataclass."""

    def test_stats_calculation(self):
        """Test automatic stats calculation."""
        issues = [
            FormatIssue(1, None, ErrorLevel.ERROR, "Error", "rule1"),
            FormatIssue(2, None, ErrorLevel.ERROR, "Error", "rule2"),
            FormatIssue(3, None, ErrorLevel.WARNING, "Warning", "rule3", fixable=True),
            FormatIssue(4, None, ErrorLevel.INFO, "Info", "rule4", fixable=True),
        ]
        
        from emdx.utils.formatter import FormatResult
        result = FormatResult(valid=False, issues=issues)
        
        assert result.stats["errors"] == 2
        assert result.stats["warnings"] == 1
        assert result.stats["info"] == 1
        assert result.stats["fixable"] == 2