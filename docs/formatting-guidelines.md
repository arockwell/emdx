# Document Formatting Guidelines

## Overview

EMDX automatically formats and validates all documents to ensure consistency and prevent common issues. This document describes the formatting rules applied and provides guidance for users.

## Automatic Formatting

When you save or update any document in EMDX, the following formatting is automatically applied:

### 1. Content Validation
- **Empty documents are rejected** - Documents must contain at least some non-whitespace content
- **Binary content is rejected** - Only text documents are supported
- **Control characters are rejected** - Except for tabs, newlines, and carriage returns

### 2. Line Ending Normalization
- All line endings are converted to Unix format (LF)
- Windows (CRLF) and old Mac (CR) line endings are automatically converted
- This ensures consistency across platforms

### 3. Whitespace Management
- **Trailing whitespace is removed** from the end of each line
- **Multiple trailing newlines are collapsed** to a single newline
- **A final newline is added** if missing (following Unix convention)
- Leading whitespace (indentation) is preserved

### 4. Title Formatting
- Leading and trailing whitespace is removed from titles
- Empty titles are rejected

### 5. Special Characters
- Unicode characters are fully supported (including emoji 🎯)
- UTF-8 encoding is used throughout
- Byte Order Marks (BOM) are automatically removed

## Examples

### Before Formatting
```
Title with spaces   

Content with trailing spaces   
Windows line endings
Multiple empty lines at end


```

### After Formatting
```
Title with spaces

Content with trailing spaces
Windows line endings
Multiple empty lines at end
```

## Preserved Content

The formatter preserves:
- Intentional indentation (spaces and tabs at start of lines)
- Code block formatting
- Markdown table alignment
- Unicode characters and emoji
- URLs and special formatting

## Error Messages

If your document fails validation, you'll see one of these errors:

- **"Document content cannot be empty"** - The document has no content or only whitespace
- **"Document contains binary content"** - Binary files are not supported
- **"Document title cannot be empty"** - The title is missing or only whitespace

## Configuration Options

While the default formatter works well for most cases, advanced users can configure:

- Maximum line length
- Tab handling (allow/disallow)
- Maximum document size
- Strict vs lenient mode

## Best Practices

1. **Don't worry about formatting** - EMDX handles it automatically
2. **Use meaningful titles** - They're trimmed but otherwise preserved
3. **Focus on content** - Let the system handle line endings and whitespace
4. **Use UTF-8 encoding** - For maximum compatibility

## Technical Details

The formatting system:
- Runs at the database layer, ensuring all saves are formatted
- Is idempotent - formatting already-formatted content produces no changes
- Preserves semantic content while normalizing presentation
- Has comprehensive test coverage for edge cases

## Migration Notes

For existing documents:
- Documents are formatted when next edited
- Read operations don't modify content
- Bulk formatting tools are available if needed