# Formatting Requirements Analysis

## Current State of EMDX Formatting

Based on code analysis, EMDX currently supports:

### 1. Markdown Rendering
- Uses Rich library's Markdown class for rendering
- Supports code syntax highlighting with configurable themes
- Handles inline code with Python lexer by default
- Enables hyperlinks in markdown

### 2. Tag Formatting
- Emoji tag display with proper ordering (Document Type → Status → Other)
- Smart truncation to avoid breaking multi-character emojis
- Space-separated tag display

### 3. Display Features
- Raw markdown view option (`--raw` flag)
- Pager support for long documents
- Header information display (ID, title, project, dates, tags)
- Console width adaptation

### 4. External Integrations
- mdcat renderer for enhanced terminal display
- Support for tables, images, and advanced formatting via mdcat

## Identified Limitations

1. **No comprehensive formatting tests** - The formatting functions lack dedicated test coverage
2. **Limited markdown feature testing** - No tests for edge cases or complex markdown
3. **No validation of rendering consistency** across different viewing methods
4. **Code theme detection** is simplistic (only checks COLORFGBG)

## Required Test Coverage

### Basic Markdown Elements
- Headers (H1-H6)
- Bold, italic, strikethrough
- Lists (ordered, unordered, nested)
- Links and images
- Blockquotes
- Horizontal rules

### Code Formatting
- Inline code
- Code blocks with language specification
- Syntax highlighting for multiple languages
- Long lines in code blocks

### Special Cases
- Unicode and emoji handling
- Very long lines
- Nested markdown structures
- Mixed content types

### Tag Formatting
- Single emoji tags
- Multi-character emoji tags
- Tag ordering
- Empty tag lists

## Success Criteria

1. All basic markdown elements render correctly
2. Code blocks display with appropriate syntax highlighting
3. Tags display consistently with proper ordering
4. No breaking of multi-character emojis
5. Consistent rendering across CLI, TUI, and raw output
6. Graceful handling of edge cases