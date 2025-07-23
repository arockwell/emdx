# EMDX Document Formatting Standards

## Overview

This document defines the formatting standards for all documents in the EMDX knowledge base. These standards ensure consistency, readability, and maintainability across all stored documents.

## Core Formatting Rules

### 1. Markdown Structure

#### Headers
- Use ATX-style headers (`#`, `##`, etc.) not Setext-style
- Start with H1 (`#`) for document title
- Follow proper hierarchy (no skipping levels)
- One blank line before and after headers
- No trailing punctuation in headers unless it's a question

```markdown
# Good Header

## Subsection

### Details
```

#### Line Length
- Maximum 100 characters per line for prose
- Code blocks can exceed if necessary
- URLs can exceed line limit

#### Spacing
- Single blank line between paragraphs
- Single blank line between sections
- No trailing whitespace
- File must end with exactly one newline

### 2. Code Blocks

#### Fenced Code Blocks
- Always use triple backticks (```)
- Always specify language identifier
- No spaces before opening backticks
- Blank line before and after code blocks

```python
# Good example
def hello():
    return "world"
```

#### Inline Code
- Use single backticks for inline code
- No spaces inside backticks unless part of the code

### 3. Lists

#### Unordered Lists
- Use `-` for all unordered lists (not `*` or `+`)
- Consistent indentation (2 spaces for nested items)
- Blank line before and after list blocks

#### Ordered Lists
- Use `1.` style numbering
- Let markdown handle auto-numbering

### 4. Links and References

#### Inline Links
- Prefer inline links: `[text](url)`
- Descriptive link text (no "click here")

#### Reference Links
- Group at document bottom
- Use descriptive reference names

### 5. Special Elements

#### Tables
- Use pipe tables with alignment markers
- Headers required
- Consistent column spacing

| Column | Description |
|--------|-------------|
| Name   | The name    |

#### Blockquotes
- Use `>` with space after
- Blank line before and after

> This is a properly formatted quote

#### Horizontal Rules
- Use three hyphens: `---`
- Blank line before and after

## Validation Rules

### Required Elements
1. Document must have a title (H1)
2. Minimum content length: 10 characters
3. Valid UTF-8 encoding

### Prohibited Elements
1. No HTML tags (except in code blocks)
2. No tabs (convert to spaces)
3. No DOS line endings (CRLF)

### Auto-Fixable Issues
1. Trailing whitespace
2. Multiple consecutive blank lines
3. Missing final newline
4. Inconsistent list markers
5. Header hierarchy issues

## Error Severity Levels

### Error (Must Fix)
- Missing document title
- Invalid markdown syntax
- Broken header hierarchy
- Line length > 100 chars (prose)

### Warning (Should Fix)
- Missing language in code blocks
- Inconsistent list markers
- Multiple blank lines
- Missing blank lines around blocks

### Info (Nice to Have)
- Could use more descriptive headers
- Long paragraphs could be split
- Consider adding code examples

## Implementation Notes

The formatter will:
1. Parse documents using Python-Markdown
2. Apply fixes for auto-fixable issues
3. Report errors with line numbers
4. Suggest improvements
5. Optionally auto-format on save