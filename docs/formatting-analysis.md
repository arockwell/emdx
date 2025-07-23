# Document Formatting Analysis

## Current State

### Document Storage
- Documents are stored directly in SQLite database without any formatting normalization
- Content field is TEXT type with no constraints
- No validation occurs during save operations

### Current Formatting Behavior

#### Inconsistent Whitespace Handling
1. **Input Processing** (`get_input_content`):
   - Stdin content: Checked with `content.strip()` to verify non-empty
   - File content: Read as-is without modification
   - Direct content: Used as-is

2. **Title Generation** (`generate_title`):
   - First line stripped with `first_line.strip()`
   - Truncated to 50 characters if needed

3. **Edit Operations** (`edit` command):
   - New content stripped with `new_content.strip()`
   - Comparison uses stripped content

4. **Save Operations**:
   - No formatting applied
   - Content saved exactly as provided

### Issues Identified

1. **Empty Document Problem**:
   - No validation prevents saving empty or whitespace-only content
   - Led to creation of ~40 empty documents (per release notes)
   - Wrong command syntax (`emdx save "text"`) created empty docs

2. **Inconsistent Line Endings**:
   - No normalization of CRLF to LF
   - Different platforms may introduce different line endings

3. **Trailing Whitespace**:
   - Not removed from lines
   - Can cause diff noise and storage inefficiency

4. **Missing Final Newline**:
   - No enforcement of newline at end of file
   - Against user preferences (per CLAUDE.md)

## Formatting Requirements

### Document Format Specification

1. **Content Validation**:
   - Must contain non-whitespace characters
   - Minimum content length after stripping whitespace

2. **Line Ending Normalization**:
   - Convert all CRLF to LF
   - Consistent across all platforms

3. **Whitespace Management**:
   - Remove trailing whitespace from each line
   - Preserve intentional indentation
   - Ensure single newline at end of document

4. **Title Formatting**:
   - Strip leading/trailing whitespace
   - Ensure non-empty after stripping

5. **Special Characters**:
   - Preserve Unicode characters
   - Handle emoji properly (important for tag system)

### Edge Cases to Handle

1. **Empty Documents**:
   - Reject completely empty content
   - Reject whitespace-only content

2. **Large Documents**:
   - Ensure formatting doesn't impact performance
   - Handle documents with thousands of lines

3. **Binary Content**:
   - Detect and reject non-text content
   - Provide clear error messages

4. **Special Formatting**:
   - Preserve code blocks with intentional formatting
   - Maintain markdown structure
   - Keep table alignment

## Implementation Approach

The formatting system should:
1. Be applied consistently at save time
2. Provide clear error messages for invalid content
3. Not modify semantic content
4. Be performant for large documents
5. Be backward compatible with existing documents