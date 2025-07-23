# EMDX Formatting Guide

This guide documents the markdown formatting capabilities of EMDX and best practices for document creation.

## Supported Markdown Features

EMDX fully supports standard markdown formatting with excellent preservation of content through save/retrieve cycles.

### Text Formatting

- **Bold text**: `**bold**` or `__bold__`
- *Italic text*: `*italic*` or `_italic_`
- ***Bold and italic***: `***both***` or `___both___`
- `Inline code`: `` `code` ``
- ~~Strikethrough~~: `~~text~~`

### Headers

All header levels (1-6) are supported:

```markdown
# Level 1
## Level 2
### Level 3
#### Level 4
##### Level 5
###### Level 6
```

### Lists

#### Unordered Lists
```markdown
- Item 1
- Item 2
  - Nested item
    - Deep nested
- Item 3
```

#### Ordered Lists
```markdown
1. First step
2. Second step
   1. Sub-step A
   2. Sub-step B
3. Third step
```

#### Task Lists
```markdown
- [x] Completed task
- [ ] Pending task
- [x] Another completed task
```

### Code Blocks

Fenced code blocks with syntax highlighting:

````markdown
```python
def hello():
    print("Hello, EMDX!")
```

```javascript
const greeting = () => {
    console.log("Hello, EMDX!");
};
```
````

### Tables

Basic markdown tables are supported:

```markdown
| Feature | Status | Notes |
|---------|--------|-------|
| Markdown | ✅ | Full support |
| Unicode | ✅ | All characters |
| Emojis | 🎯 | Perfect |
```

### Links

- External links: `[text](https://example.com)`
- Reference links: `[text][ref]` with `[ref]: https://example.com`
- Auto-links: `<https://example.com>`

### Blockquotes

```markdown
> Single line quote

> Multi-line quote
> continues here
>
> > Nested quotes
> > are supported
```

### Images

```markdown
![Alt text](image.png)
![Alt text](https://example.com/image.png)
```

### Horizontal Rules

Use three or more hyphens, asterisks, or underscores:

```markdown
---
***
___
```

## Unicode and International Support

EMDX has excellent Unicode support for international content:

- **Chinese**: 你好世界
- **Japanese**: こんにちは世界
- **Arabic**: مرحبا بالعالم
- **Russian**: Привет мир
- **Korean**: 안녕하세요
- **Hindi**: नमस्ते

### Emoji Support

EMDX fully supports emojis in content and tags:

- Document type emojis: 🎯 📝 📚 🔍 🏗️
- Status emojis: 🚀 ✅ 🚧
- Technical emojis: 🔧 🧪 🐛 ✨ 💎
- Priority emojis: 🚨 🐌

### Mathematical Symbols

Mathematical and special symbols are preserved:

- Summation: ∑
- Product: ∏
- Integral: ∫
- Square root: √
- Infinity: ∞
- Approximately: ≈
- Not equal: ≠
- Less/Greater equal: ≤ ≥

## Special Characters

EMDX correctly handles special characters:

### HTML Entities
- Less than: `<`
- Greater than: `>`
- Ampersand: `&`
- Quotes: `"` and `'`

### Escape Sequences
Use backslashes to escape markdown characters:
- `\*` for literal asterisk
- `\_` for literal underscore
- `\`` for literal backtick
- `\[` and `\]` for literal brackets

## Best Practices

### 1. Consistent Formatting
- Use consistent header hierarchy
- Choose either asterisks or underscores for emphasis
- Maintain consistent list formatting

### 2. Code Block Languages
Always specify the language for syntax highlighting:
```python
# Good - language specified
def example():
    pass
```

### 3. Large Documents
- EMDX handles large documents well
- Long lines are preserved without truncation
- Performance remains good even with extensive formatting

### 4. Whitespace Preservation
- Trailing spaces are preserved
- Multiple blank lines are maintained
- Indentation (spaces and tabs) is kept intact

### 5. Tag Organization
Use EMDX's emoji tag system for organization:
- `emdx save doc.md --tags "docs,active"`
- Tags auto-convert: `docs` → 📚, `active` → 🚀

## Rendering Modes

### CLI View (`emdx view`)
- Rich terminal formatting
- Syntax highlighting for code blocks
- Proper list and table rendering
- Unicode and emoji display

### TUI Browser (`emdx gui`)
- Interactive document browser
- Live preview with formatting
- Vim-like navigation
- In-place editing with 'e' key

### Raw Content
- Original markdown is always preserved
- No data loss during save/retrieve
- Perfect for version control

## Known Limitations

1. **Complex Tables**: Advanced table features (alignment, spanning) have basic support
2. **Footnotes**: Not currently rendered in CLI view
3. **Definition Lists**: Stored but not specially formatted
4. **Mermaid Diagrams**: Preserved as code blocks

## Testing Your Formatting

To verify formatting works correctly:

1. Save a test document:
   ```bash
   emdx save test.md --tags "test"
   ```

2. View the formatted output:
   ```bash
   emdx view <id>
   ```

3. Check raw preservation:
   ```bash
   # The content is stored exactly as written
   ```

## Summary

EMDX provides robust markdown support with:
- ✅ Full markdown syntax preservation
- ✅ Excellent Unicode and emoji handling
- ✅ Proper special character support
- ✅ Clean rendering in CLI and TUI
- ✅ No data loss in save/retrieve cycles

This makes EMDX ideal for technical documentation, international content, and any markdown-based knowledge management needs.