# EMDX Formatting Test Document

This document contains various markdown elements to test EMDX formatting capabilities.

## Basic Text Formatting

This is a **bold text** example and this is *italic text*. We can also use ***bold and italic*** together.

Here's some `inline code` and a ~~strikethrough~~ example.

## Headers at Different Levels

### Level 3 Header
#### Level 4 Header
##### Level 5 Header
###### Level 6 Header

## Lists

### Unordered List
- First item
- Second item with **bold**
  - Nested item 1
  - Nested item 2 with `code`
    - Deep nested item
- Third item

### Ordered List
1. First step
2. Second step with *emphasis*
   1. Sub-step A
   2. Sub-step B
3. Third step

### Task List
- [x] Completed task
- [ ] Pending task
- [x] Another completed task with **formatting**

## Code Blocks

### Python Code
```python
def test_formatting():
    """Test function with docstring"""
    message = "Hello, EMDX!"
    special_chars = "Special: <>&\"'"
    unicode_text = "Unicode: 你好 🎯 🚀 ✨"
    return {"message": message, "special": special_chars, "unicode": unicode_text}
```

### JavaScript Code
```javascript
const formatTest = () => {
    const data = {
        tags: ["🎯", "🚀", "✅"],
        text: "EMDX Test"
    };
    console.log(JSON.stringify(data, null, 2));
};
```

### Shell Commands
```bash
# Test EMDX commands
emdx save test.md --tags "test,active"
emdx find "formatting test"
emdx view 123
```

## Tables

| Feature | Status | Notes |
|---------|--------|-------|
| Basic Markdown | ✅ | Works well |
| Code Blocks | ✅ | Syntax highlighting |
| Unicode/Emoji | 🎯 | Full support |
| Tables | ⚡ | Basic support |

## Links and References

- [EMDX Documentation](https://example.com/emdx)
- [Local Reference](#basic-text-formatting)
- Raw URL: https://github.com/example/emdx

## Blockquotes

> This is a blockquote with multiple lines.
> It can contain **formatted text** and `code`.
>
> > Nested blockquotes are also possible.
> > With multiple levels of nesting.

## Horizontal Rules

---

Another section after horizontal rule.

***

And another one.

## Special Characters and Edge Cases

### Unicode and Emojis
- Chinese: 你好世界
- Japanese: こんにちは
- Arabic: مرحبا بالعالم
- Emojis: 🎯 🚀 ✨ 🔧 🐛 💎
- Math symbols: ∑ ∏ ∫ √ ∞ ≈ ≠ ≤ ≥

### Special Characters
- HTML entities: < > & " '
- Escaped characters: \* \_ \` \[ \]
- Line with trailing spaces:    
- Empty line above and below:

- Very long line that should wrap properly: Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.

### Code with Special Characters
```
<html>
    <body class="test">
        <p>HTML & "special" characters</p>
    </body>
</html>
```

## Mixed Content

Here's a paragraph with [a link](https://example.com), some **bold text**, and an inline equation: `E = mc²`.

1. A list item with a [link](#tables)
2. Another item with `inline code` and **bold**
3. Item with emoji tag: 🎯

> A blockquote with a list inside:
> - Item 1
> - Item 2 with `code`
> 
> And some **formatted text**.

## Edge Case: Very Long Code Line
```python
very_long_variable_name_that_should_not_break_formatting = {"key1": "value1", "key2": "value2", "key3": "value3", "key4": "value4", "key5": "value5", "key6": "value6"}
```

## Final Test: Complex Nested Structure

1. **Main point** with emphasis
   - Sub-point with `code`
     ```python
     # Code block in list
     print("nested code")
     ```
   - Another sub-point with [link](#)
     > Blockquote in list
     > With multiple lines
2. Second main point
   | Col1 | Col2 |
   |------|------|
   | Data | ✅   |

---

End of test document. This covers most markdown elements and edge cases.