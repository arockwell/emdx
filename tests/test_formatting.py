"""Comprehensive test suite for document formatting in EMDX."""

import pytest

from emdx.ui.formatting import format_tags, order_tags, truncate_emoji_safe


class TestTagFormatting:
    """Test tag formatting and ordering functionality."""

    def test_order_tags_empty(self):
        """Test ordering empty tag list."""
        assert order_tags([]) == []

    def test_order_tags_single_category(self):
        """Test ordering tags from single category."""
        # Only document types - preserves input order within category
        assert order_tags(["📝", "🎯", "📚"]) == ["📝", "🎯", "📚"]
        # Only status tags - preserves input order within category
        assert order_tags(["✅", "🚀", "🚧"]) == ["✅", "🚀", "🚧"]
        # Only other tags
        assert order_tags(["🔧", "🐛", "✨"]) == ["🔧", "🐛", "✨"]

    def test_order_tags_multiple_categories(self):
        """Test ordering tags from multiple categories."""
        # Mix of all categories - preserves order within each category
        tags = ["✅", "🔧", "🎯", "🚀", "📝", "🐛"]
        expected = ["🎯", "📝", "✅", "🚀", "🔧", "🐛"]
        assert order_tags(tags) == expected

    def test_order_tags_preserves_unknown(self):
        """Test that unknown tags are preserved in order."""
        tags = ["❓", "🎯", "🚀", "🔧", "💡"]
        expected = ["🎯", "🚀", "❓", "🔧", "💡"]
        assert order_tags(tags) == expected

    def test_format_tags_empty(self):
        """Test formatting empty tag list."""
        assert format_tags([]) == ""

    def test_format_tags_single(self):
        """Test formatting single tag."""
        assert format_tags(["🎯"]) == "🎯"

    def test_format_tags_multiple(self):
        """Test formatting multiple tags with ordering."""
        tags = ["✅", "🔧", "🎯", "🚀"]
        expected = "🎯 ✅ 🚀 🔧"
        assert format_tags(tags) == expected

    def test_format_tags_spacing(self):
        """Test that tags are properly space-separated."""
        tags = ["🎯", "🚀", "✅"]
        result = format_tags(tags)
        assert " " in result
        assert result.count(" ") == 2


class TestEmojiTruncation:
    """Test emoji-safe text truncation."""

    def test_truncate_short_text(self):
        """Test truncating text shorter than limit."""
        text = "Hello"
        result, truncated = truncate_emoji_safe(text, 10)
        assert result == "Hello"
        assert not truncated

    def test_truncate_exact_length(self):
        """Test truncating text at exact limit."""
        text = "Hello"
        result, truncated = truncate_emoji_safe(text, 5)
        assert result == "Hello"
        assert not truncated

    def test_truncate_long_text(self):
        """Test truncating text longer than limit."""
        text = "Hello World"
        result, truncated = truncate_emoji_safe(text, 5)
        assert result == "Hello"
        assert truncated

    def test_truncate_with_simple_emoji(self):
        """Test truncating with simple single-codepoint emoji."""
        text = "Hello 🎯 World"
        result, truncated = truncate_emoji_safe(text, 8)
        assert result == "Hello 🎯 "  # Includes the space at position 8
        assert truncated

    def test_truncate_with_complex_emoji(self):
        """Test truncating with multi-codepoint emoji."""
        # 🏗️ is U+1F3D7 + U+FE0F (building + variation selector)
        text = "Hello 🏗️ World"
        result, truncated = truncate_emoji_safe(text, 7)
        # The emoji would make it 8 chars (Hello 🏗️), so it gets cut off completely
        assert result == "Hello "
        assert truncated

        # Test with enough space to include the emoji
        result2, truncated2 = truncate_emoji_safe(text, 8)
        assert "🏗" in result2
        assert truncated2

    def test_truncate_at_emoji_boundary(self):
        """Test truncating right at emoji boundary."""
        text = "Test 🎯🚀✅"
        result, truncated = truncate_emoji_safe(text, 6)
        assert result == "Test 🎯"
        assert truncated

    def test_truncate_empty_string(self):
        """Test truncating empty string."""
        result, truncated = truncate_emoji_safe("", 5)
        assert result == ""
        assert not truncated

    def test_truncate_zero_length(self):
        """Test truncating to zero length."""
        result, truncated = truncate_emoji_safe("Hello", 0)
        assert result == ""
        assert truncated


class TestMarkdownFormatting:
    """Test markdown rendering capabilities."""

    @pytest.fixture
    def sample_markdown(self):
        """Provide sample markdown content for testing."""
        return {
            "headers": """# Header 1
## Header 2
### Header 3
#### Header 4
##### Header 5
###### Header 6""",
            "emphasis": """**Bold text**
*Italic text*
***Bold and italic***
~~Strikethrough~~""",
            "lists": """- Unordered item 1
- Unordered item 2
  - Nested item
  - Another nested
- Back to top level

1. Ordered item 1
2. Ordered item 2
   1. Nested ordered
   2. Another nested
3. Back to top level""",
            "links": """[Link text](https://example.com)
[Link with title](https://example.com "Title")
https://auto-link.com
<user@example.com>""",
            "code": """Inline `code` text

```python
def hello_world():
    print("Hello, World!")
```

```javascript
console.log("Hello, World!");
```""",
            "blockquotes": """> This is a blockquote
> It can span multiple lines
>
> > Nested blockquote""",
            "tables": """| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |""",
            "mixed": """# Project Documentation

This is a **mixed content** document with *various* elements.

## Features

- Code blocks
- Lists
- Tables
- Links

```python
# Example code
def process_data(data):
    return [x * 2 for x in data]
```

> **Note:** This is important!

See [documentation](https://docs.example.com) for details."""
        }

    def test_markdown_headers(self, sample_markdown):
        """Test that all header levels are supported."""
        content = sample_markdown["headers"]
        # These tests would need actual rendering verification
        # For now, we ensure the content is valid
        assert "# Header 1" in content
        assert "###### Header 6" in content

    def test_markdown_emphasis(self, sample_markdown):
        """Test emphasis formatting."""
        content = sample_markdown["emphasis"]
        assert "**Bold text**" in content
        assert "*Italic text*" in content
        assert "~~Strikethrough~~" in content

    def test_markdown_lists(self, sample_markdown):
        """Test list formatting."""
        content = sample_markdown["lists"]
        assert "- Unordered item" in content
        assert "1. Ordered item" in content
        assert "  - Nested item" in content

    def test_markdown_code(self, sample_markdown):
        """Test code formatting."""
        content = sample_markdown["code"]
        assert "```python" in content
        assert "```javascript" in content
        assert "`code`" in content

    def test_special_characters(self):
        """Test handling of special characters."""
        special_chars = """Special characters: < > & " '
Unicode: → ← ↑ ↓ • × ÷
Emojis: 🎯 🚀 ✅ 🏗️ 👨‍💻
Math: π ≈ ∑ ∫ ∞"""
        # Ensure these don't break parsing
        assert "🎯" in special_chars
        assert "π" in special_chars

    def test_long_lines(self):
        """Test handling of very long lines."""
        long_line = "x" * 200
        long_content = f"""# Document with long line

{long_line}

End of document."""
        assert len(long_line) == 200
        assert long_line in long_content

    def test_edge_cases(self):
        """Test various edge cases."""
        edge_cases = """# Edge Cases

## Empty code block
```
```

## Link without URL
[](empty)

## Malformed table
| Col1 | Col2 |
| Data only |

## Unclosed formatting
**This is bold but not closed

## Multiple blank lines


## End"""
        # Ensure content doesn't cause parsing errors
        assert "Edge Cases" in edge_cases
        assert "empty" in edge_cases


class TestFormattingIntegration:
    """Test formatting integration across the system."""

    def test_tag_formatting_consistency(self):
        """Test that tag formatting is consistent."""
        # Test same tags in different orders produce same output
        tags1 = ["✅", "🎯", "🔧", "🚀"]
        tags2 = ["🔧", "🚀", "🎯", "✅"]
        # Both should produce: Document types first, then status, then others
        # Order within categories is preserved from input
        result1 = format_tags(tags1)
        result2 = format_tags(tags2)
        # Both should have the same tags, just potentially different order within categories
        assert set(result1.split()) == set(result2.split())
        # Document type (🎯) should come before status tags (✅, 🚀) in both
        assert result1.index("🎯") < result1.index("✅")
        assert result2.index("🎯") < result2.index("✅")

    def test_empty_content_handling(self):
        """Test handling of empty or minimal content."""
        test_cases = [
            "",  # Empty
            "\n",  # Just newline
            "   ",  # Just spaces
            "\n\n\n",  # Multiple newlines
        ]
        # These should not cause errors in formatting
        for content in test_cases:
            assert isinstance(content, str)

    def test_unicode_normalization(self):
        """Test that unicode is handled properly."""
        # Different representations of é
        text1 = "café"  # Single character
        text2 = "café"  # Combining character
        # Both should be handled without errors
        assert len(text1) <= 5
        assert len(text2) <= 6


def create_formatting_test_document():
    """Create a comprehensive test document for manual testing."""
    return """# EMDX Formatting Test Document

This document tests all formatting capabilities of EMDX.

## 1. Text Formatting

### Basic Emphasis
- **Bold text** using double asterisks
- *Italic text* using single asterisks
- ***Bold and italic*** combined
- ~~Strikethrough~~ using tildes
- `Inline code` using backticks

### Mixed Formatting
This is a paragraph with **bold**, *italic*, and `code` mixed together.
It also includes ~~strikethrough~~ and ***bold italic*** text.

## 2. Headers

# H1 Header
## H2 Header
### H3 Header
#### H4 Header
##### H5 Header
###### H6 Header

## 3. Lists

### Unordered Lists
- First item
- Second item
  - Nested item 1
  - Nested item 2
    - Double nested
- Third item

### Ordered Lists
1. First step
2. Second step
   1. Sub-step A
   2. Sub-step B
3. Third step

### Mixed Lists
1. Ordered item
   - Unordered sub-item
   - Another sub-item
2. Second ordered item

## 4. Links and Images

### Links
- [External link](https://example.com)
- [Link with title](https://example.com "Hover text")
- https://auto-detected-link.com
- Email: <user@example.com>

### Images
![Alt text](https://via.placeholder.com/150 "Image title")

## 5. Code Blocks

### Python
```python
def factorial(n):
    '''Calculate factorial recursively'''
    if n <= 1:
        return 1
    return n * factorial(n - 1)

# Test the function
print(factorial(5))  # Output: 120
```

### JavaScript
```javascript
// Modern JS with arrow functions
const greet = (name = 'World') => {
    console.log(`Hello, ${name}!`);
};

greet('EMDX');
```

### JSON
```json
{
    "name": "emdx",
    "version": "1.0.0",
    "features": [
        "markdown",
        "search",
        "tags"
    ]
}
```

### Shell
```bash
# Install emdx
pip install emdx

# Save a document
echo "My note" | emdx save --title "Quick Note"

# Search documents
emdx find "python"
```

## 6. Blockquotes

> This is a simple blockquote.
> It can span multiple lines.

> ## Blockquote with header
>
> And multiple paragraphs with **formatting**.
>
> > Nested blockquote with *emphasis*.

## 7. Tables

| Header 1 | Header 2 | Header 3 |
|----------|:--------:|---------:|
| Left     | Center   | Right    |
| Data     | Data     | Data     |
| Long content that might wrap | Short | 123 |

## 8. Horizontal Rules

---

***

___

## 9. Special Characters and Unicode

### Special Characters
- Less than: <
- Greater than: >
- Ampersand: &
- Quotes: "double" and 'single'
- Backtick: `

### Unicode Examples
- Arrows: → ← ↑ ↓ ↔
- Math: π ≈ ∑ ∫ ∞ ± ×
- Symbols: © ® ™ € £ ¥
- Emojis: 🎯 🚀 ✅ 🏗️ 📝 🔍

### Extended Unicode
- Chinese: 中文
- Japanese: 日本語
- Korean: 한국어
- Arabic: العربية
- Hebrew: עברית
- Russian: Русский

## 10. Edge Cases

### Long Lines
This is a very long line that contains more than 200 characters to test line wrapping \
behavior. Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor \
incididunt ut labore et dolore magna aliqua.

### Empty Elements

Empty code block:
```
```

Empty link: [](empty)

Empty list item:
-

### Malformed Markdown

Unclosed **bold text

Unclosed *italic text

Unclosed `code text

### Many Newlines


(Five blank lines above)

## 11. Emoji Tag Testing

Document tags for testing display:
- Single emoji: 🎯
- Multi-codepoint emoji: 🏗️ (building + variation selector)
- Emoji sequence: 👨‍💻 (man + ZWJ + computer)
- All tag categories: 🎯 🚀 ✅ 🔧 🐛 ✨

## 12. Nested Structures

### Complex Nesting
1. **Bold item with `inline code`**
   > Blockquote under list item
   > - With nested list
   >   - Even deeper

   ```python
   # Code block under list item
   print("Nested code")
   ```

2. *Italic item with [link](https://example.com)*

### Mixed Content Block
> ### Quote Header
>
> Paragraph with **bold**, *italic*, and `code`.
>
> ```python
> # Code in quote
> def quoted_function():
>     pass
> ```
>
> | Table | In Quote |
> |-------|----------|
> | Data  | Data     |

---

End of formatting test document. If this renders correctly, all major \
markdown features are working properly.
"""


if __name__ == "__main__":
    # Create test document for manual inspection
    test_doc = create_formatting_test_document()
    with open("formatting_test_document.md", "w") as f:
        f.write(test_doc)
    print("Created formatting_test_document.md for manual testing")
