"""
Tests for document formatting preservation and rendering
"""

import pytest
from pathlib import Path
from emdx.database.connection import DatabaseConnection
from emdx.database.documents import save_document, get_document
from emdx.ui.formatting import format_tags
from emdx.utils.emoji_aliases import expand_aliases


class TestDocumentFormatting:
    """Test document formatting preservation"""
    
    @pytest.fixture
    def test_content(self):
        """Complex markdown content for testing"""
        return """# Test Document

## Formatting Tests

**Bold text** and *italic text* and ***both***.

### Code Blocks

```python
def hello():
    print("Hello, 世界!")
    return {"emoji": "🎯", "special": "<>&"}
```

### Lists

- Item 1
  - Nested with `code`
- Item 2 with **bold**

### Special Characters

Unicode: 你好 こんにちは مرحبا
Emojis: 🎯 🚀 ✨ 🔧
HTML: <tag> & "quotes"
Math: ∑ ∏ ∫ √ ∞

### Table

| Col1 | Col2 |
|------|------|
| Data | ✅   |
"""

    def test_save_and_retrieve_formatting(self, temp_db, test_content):
        """Test that formatting is preserved through save/retrieve cycle"""
        # Save document
        doc_id = save_document(
            title="Formatting Test",
            content=test_content,
            project="test"
        )
        
        # Retrieve document
        doc = get_document(str(doc_id))
        
        # Verify content is identical
        assert doc['content'] == test_content
        assert doc['title'] == "Formatting Test"
        
        # Check specific elements are preserved
        assert "**Bold text**" in doc['content']
        assert "```python" in doc['content']
        assert "你好" in doc['content']
        assert "🎯" in doc['content']
        assert "<tag>" in doc['content']
        assert "| Col1 | Col2 |" in doc['content']

    def test_unicode_preservation(self, temp_db):
        """Test Unicode and emoji preservation"""
        unicode_content = """
Chinese: 你好世界
Japanese: こんにちは世界
Arabic: مرحبا بالعالم
Russian: Привет мир
Emojis: 🎯 🚀 ✨ 🔧 🐛 💎
Math: ∑ ∏ ∫ √ ∞ ≈ ≠ ≤ ≥
"""
        doc_id = save_document(
            title="Unicode Test",
            content=unicode_content,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Verify all unicode is preserved
        assert "你好世界" in doc['content']
        assert "こんにちは" in doc['content']
        assert "مرحبا" in doc['content']
        assert "Привет" in doc['content']
        assert "🎯" in doc['content']
        assert "∑" in doc['content']

    def test_special_characters(self, temp_db):
        """Test special character handling"""
        special_content = r"""
HTML entities: < > & " '
Escaped: \* \_ \` \[ \]
Quotes: "double" 'single' `backtick`
Brackets: {curly} [square] (round) <angle>
Special: @ # $ % ^ & * ( ) - _ = + \\ | / ? . , ; :
"""
        doc_id = save_document(
            title="Special Chars Test",
            content=special_content,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Verify special characters
        assert "< > & \" '" in doc['content']
        assert "\\*" in doc['content']
        assert "{curly}" in doc['content']
        assert "@" in doc['content']

    def test_code_block_formatting(self, temp_db):
        """Test code block preservation"""
        code_content = '''# Code Examples

```python
def complex_function():
    """Docstring with "quotes" """
    data = {
        'key': 'value',
        'special': '<>&',
        'unicode': '你好'
    }
    return data
```

```javascript
const test = () => {
    console.log("Hello, 世界!");
    const special = "<tag attr='value'>";
};
```

```
Plain code block
With multiple lines
    And indentation
```
'''
        doc_id = save_document(
            title="Code Block Test",
            content=code_content,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Verify code blocks
        assert '```python' in doc['content']
        assert '```javascript' in doc['content']
        assert 'def complex_function():' in doc['content']
        assert 'const test = () =>' in doc['content']
        assert '    And indentation' in doc['content']

    def test_nested_structures(self, temp_db):
        """Test nested markdown structures"""
        nested_content = """# Nested Structures

1. Ordered list
   - Nested unordered
     ```python
     # Code in list
     print("nested")
     ```
   - Another item
     > Blockquote in list
2. Second item
   | Nested | Table |
   |--------|-------|
   | Data   | ✅    |

> Blockquote with **bold** and `code`
> - List in quote
> - With items
"""
        doc_id = save_document(
            title="Nested Test",
            content=nested_content,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Verify nested structures
        assert '   - Nested unordered' in doc['content']
        assert '     ```python' in doc['content']
        assert '   | Nested | Table |' in doc['content']
        assert '> - List in quote' in doc['content']

    def test_very_long_lines(self, temp_db):
        """Test handling of very long lines"""
        long_line = "A" * 500  # 500 character line
        long_content = f"""# Long Lines Test

Normal paragraph.

{long_line}

Another paragraph.

Code with long line:
```
{long_line}
```
"""
        doc_id = save_document(
            title="Long Lines Test",
            content=long_content,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Verify long lines are preserved
        assert long_line in doc['content']
        assert doc['content'].count(long_line) == 2

    def test_empty_document(self, temp_db):
        """Test empty document handling"""
        doc_id = save_document(
            title="Empty Test",
            content="",
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        assert doc['content'] == ""
        assert doc['title'] == "Empty Test"


class TestTagFormatting:
    """Test tag display and emoji handling"""
    
    def test_emoji_alias_expansion(self):
        """Test text alias to emoji conversion"""
        # Test single aliases
        assert expand_aliases(["gameplan"]) == ["🎯"]
        assert expand_aliases(["active"]) == ["🚀"]
        assert expand_aliases(["done"]) == ["✅"]
        
        # Test multiple aliases
        tags = expand_aliases(["gameplan", "active", "refactor"])
        assert "🎯" in tags
        assert "🚀" in tags
        assert "🔧" in tags
        
        # Test mixed input
        mixed = expand_aliases(["gameplan", "🚀", "test"])
        assert "🎯" in mixed
        assert "🚀" in mixed
        assert "🧪" in mixed
        
        # Test unknown aliases (should pass through)
        unknown = expand_aliases(["unknown", "gameplan"])
        assert "unknown" in unknown
        assert "🎯" in unknown

    def test_tag_display_formatting(self):
        """Test tag display formatting"""
        # Test emoji tags
        display = format_tags(["🎯", "🚀", "✅"])
        assert "🎯" in display
        assert "🚀" in display
        assert "✅" in display
        
        # Test mixed tags
        display = format_tags(["🎯", "custom", "🚀"])
        assert "🎯" in display
        assert "custom" in display
        assert "🚀" in display


class TestMarkdownEdgeCases:
    """Test edge cases in markdown handling"""
    
    def test_malformed_markdown(self, temp_db):
        """Test handling of malformed markdown"""
        malformed = """# Unclosed code block

```python
def test():
    print("no closing fence")

# Broken table

| Col1 | Col2
|------|
| Data |

# Unclosed bold

**This is never closed

# Mixed markers

*italic with **nested bold* ending**
"""
        doc_id = save_document(
            title="Malformed Test",
            content=malformed,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Content should be preserved as-is
        assert doc['content'] == malformed

    def test_whitespace_preservation(self, temp_db):
        """Test whitespace handling"""
        whitespace = """Line with trailing spaces    

Double blank lines


Tab	separated	values

    Indented with spaces
	Indented with tab

Mixed   spacing   between   words
"""
        doc_id = save_document(
            title="Whitespace Test",
            content=whitespace,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # All whitespace should be preserved
        assert doc['content'] == whitespace
        assert "    \n" in doc['content']  # Trailing spaces
        assert "\n\n\n" in doc['content']  # Multiple blanks
        assert "\t" in doc['content']  # Tabs

    def test_markdown_in_code_blocks(self, temp_db):
        """Test markdown syntax inside code blocks"""
        meta_markdown = '''# Meta Markdown

```markdown
# This is markdown in a code block
**It should not be rendered**
- Just displayed as text
[Link](http://example.com)
```

```
# Even in plain code blocks
**No rendering** should happen
```
'''
        doc_id = save_document(
            title="Meta Markdown Test",
            content=meta_markdown,
            project="test"
        )
        
        doc = get_document(str(doc_id))
        
        # Markdown in code blocks should be preserved
        assert "**It should not be rendered**" in doc['content']
        assert "[Link](http://example.com)" in doc['content']


class TestSearchWithFormatting:
    """Test search functionality with formatted content"""
    
    def test_search_unicode(self, temp_db):
        """Test searching for unicode content"""
        # Save document with unicode
        doc_id = save_document(
            title="Unicode Search Test",
            content="Hello 你好 world こんにちは",
            project="test"
        )
        
        from emdx.database.search import search_documents
        
        # Search for Chinese characters
        results = search_documents("你好")
        assert len(results) > 0
        assert results[0]['id'] == doc_id
        
        # Search for Japanese characters
        results = search_documents("こんにちは")
        assert len(results) > 0
        assert results[0]['id'] == doc_id

    def test_search_in_code_blocks(self, temp_db):
        """Test searching for content in code blocks"""
        doc_id = save_document(
            title="Code Search Test",
            content="""
```python
def special_function():
    return "unique_identifier_12345"
```
""",
            project="test"
        )
        
        from emdx.database.search import search_documents
        
        # Search for function name
        results = search_documents("special_function")
        assert len(results) > 0
        assert results[0]['id'] == doc_id
        
        # Search for string in code
        results = search_documents("unique_identifier_12345")
        assert len(results) > 0
        assert results[0]['id'] == doc_id

    def test_search_special_characters(self, temp_db):
        """Test searching with special characters"""
        doc_id = save_document(
            title="Special Search Test",
            content="Content with <tag> and & symbols",
            project="test"
        )
        
        from emdx.database.search import search_documents
        
        # Note: FTS5 may handle special chars differently
        # This tests that documents with special chars are searchable
        results = search_documents("tag")
        assert len(results) > 0
        
        results = search_documents("symbols")
        assert len(results) > 0