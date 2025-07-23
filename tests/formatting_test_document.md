# EMDX Formatting Test Document

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
This is a very long line that contains more than 200 characters to test line wrapping behavior. Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

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

End of formatting test document. If this renders correctly, all major markdown features are working properly.
