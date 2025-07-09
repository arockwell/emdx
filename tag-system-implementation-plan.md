# emdx Tag System Implementation Plan

## Overview

Implement a robust tag system for emdx using a normalized database design (many-to-many relationship) to provide referential integrity, clean tag management, and excellent UX through auto-completion and tag browsing.

## Database Schema Changes

### New Tables

```sql
-- Tags table for normalized tag storage
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0  -- Cached count for performance
);

-- Junction table for many-to-many relationship
CREATE TABLE document_tags (
    document_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, tag_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

-- Index for fast tag lookups
CREATE INDEX idx_document_tags_tag_id ON document_tags(tag_id);
CREATE INDEX idx_tags_name ON tags(name);
```

### Migration Strategy

1. Create new tables without dropping existing data
2. Add migration script in `emdx/migrations/add_tags.py`
3. Track schema version in a new `schema_version` table
4. Run migrations automatically on startup if needed

## Core Features Implementation

### 1. Tag Management Commands

#### `emdx tag <doc_id> <tags...>` - Add tags to a document
```python
# In emdx/tags.py
def add_tags(doc_id: int, tag_names: List[str]):
    """Add tags to a document, creating new tags if necessary"""
    # Get or create each tag
    # Insert into document_tags
    # Update tag usage counts
```

**UX Features:**
- Support multiple tags: `emdx tag 123 python api backend`
- Auto-complete existing tags using FZF when no tags provided
- Show confirmation with added tags

#### `emdx untag <doc_id> <tags...>` - Remove tags from a document
```python
def remove_tags(doc_id: int, tag_names: List[str]):
    """Remove specific tags from a document"""
    # Delete from document_tags
    # Update tag usage counts
    # Optionally clean up unused tags
```

#### `emdx tags` - List all tags with statistics
```python
def list_tags(sort_by: str = 'usage'):
    """List all tags with usage counts"""
    # Query tags with counts
    # Support sorting by: name, usage, created_at
    # Rich table output showing: tag, count, last used
```

### 2. Search Enhancement

#### Update `emdx find` with tag support
```python
# In emdx/core.py, modify find_documents()
def find_documents(search_term: str = None, tags: List[str] = None, 
                   tag_mode: str = 'all', project: str = None):
    """
    Search documents by content and/or tags
    
    tag_mode: 'all' (must have all tags), 'any' (has any of the tags)
    """
```

**New CLI options:**
- `emdx find --tags python,api` - Find documents with ALL specified tags
- `emdx find --any-tags python,rust` - Find documents with ANY of the tags
- `emdx find "docker" --tags backend` - Combined content + tag search
- `emdx find --tag-only python` - Search only by tags, ignore content

### 3. Save Enhancement

#### Update `emdx save` to accept tags
```python
# In emdx/core.py
@cli.command()
@click.option('--tags', '-t', help='Comma-separated tags')
def save(file_path: str, title: str = None, project: str = None, tags: str = None):
    """Save a markdown file with optional tags"""
```

**Usage:**
- `emdx save README.md --tags documentation,setup`
- `emdx save notes.md -t python,tutorial,api`

### 4. Interactive Tag Browser

#### New `emdx browse-tags` command
```python
def browse_tags():
    """Interactive tag browser using FZF"""
    # Show all tags with counts
    # Select tag → show all documents with that tag
    # Multi-select for OR queries
```

### 5. Bulk Tag Operations

#### `emdx retag <old_tag> <new_tag>` - Rename a tag globally
```python
def rename_tag(old_name: str, new_name: str):
    """Rename a tag across all documents"""
    # Update tag name in tags table
    # Handles referential integrity automatically
```

#### `emdx merge-tags <tag1> <tag2> <target>` - Merge multiple tags
```python
def merge_tags(source_tags: List[str], target_tag: str):
    """Merge multiple tags into one"""
    # Get or create target tag
    # Update all document_tags entries
    # Delete source tags
```

## Import/Export Enhancements

### Update existing commands to preserve tags

#### Gist export includes tags in frontmatter
```python
def create_gist_with_tags(doc_id: int):
    """Export to Gist with tags in frontmatter"""
    # Add YAML frontmatter with tags before content
```

#### Future: Import from Obsidian/Notion with tag parsing
```python
def import_with_tags(file_path: str):
    """Import markdown, parsing frontmatter or #tags"""
    # Detect and parse various tag formats
    # Store in normalized tag system
```

## UI/UX Improvements

### 1. Rich Terminal Output
- Color-code tags in search results
- Show tag badges in document listings
- Tag cloud visualization in stats

### 2. Shell Aliases (document in README)
```bash
# Quick tag search
alias eft='emdx find --tags'
alias efta='emdx find --any-tags'

# Tag management  
alias et='emdx tag'
alias ets='emdx tags'  # show all tags
alias etb='emdx browse-tags'
```

### 3. Auto-completion
- Generate bash/zsh completions for tag names
- Cache frequently used tags for faster completion

## Implementation Order

1. **Phase 1: Core Infrastructure** (Week 1)
   - Create database schema and migrations
   - Implement basic tag CRUD operations
   - Add tag support to save command

2. **Phase 2: Search Integration** (Week 1-2)
   - Enhance find command with tag filters
   - Implement combined content + tag search
   - Add tag-only search mode

3. **Phase 3: Tag Management** (Week 2)
   - List tags command with statistics
   - Rename and merge tag operations
   - Interactive tag browser

4. **Phase 4: Polish** (Week 3)
   - Rich terminal formatting
   - Shell completions
   - Performance optimizations
   - Comprehensive tests

## Performance Considerations

### For 10k+ documents:
- Cache tag counts in tags table
- Use covering indexes for tag queries
- Batch operations for bulk tagging
- Consider tag search cache for frequent queries

### Query Examples:
```sql
-- Fast tag search with document info
SELECT d.id, d.title, d.snippet, GROUP_CONCAT(t.name) as tags
FROM documents d
JOIN document_tags dt ON d.id = dt.document_id
JOIN tags t ON dt.tag_id = t.id
WHERE d.id IN (
    SELECT document_id FROM document_tags
    WHERE tag_id IN (SELECT id FROM tags WHERE name IN ('python', 'api'))
    GROUP BY document_id
    HAVING COUNT(DISTINCT tag_id) = 2  -- Has ALL tags
)
GROUP BY d.id;
```

## Testing Strategy

### Unit Tests
- Tag CRUD operations
- Search query builders
- Migration scripts

### Integration Tests
- Full command workflows
- Database integrity checks
- Performance benchmarks

### Manual Testing Checklist
- [ ] Add tags to new document
- [ ] Add tags to existing document
- [ ] Search by single tag
- [ ] Search by multiple tags (AND/OR)
- [ ] Combined content + tag search
- [ ] Rename tag across all documents
- [ ] Browse tags interactively
- [ ] Export to Gist with tags

## Future Enhancements

1. **Smart Tagging**
   - Auto-suggest tags based on content analysis
   - Tag hierarchies (parent/child relationships)
   - Tag aliases (python → py)

2. **Advanced Queries**
   - Exclude tags: `--not-tags archived,old`
   - Tag combinations: `(python AND api) OR (rust AND web)`
   - Saved tag queries/filters

3. **Integrations**
   - Sync tags with Obsidian/Notion
   - Export tag statistics
   - Tag-based RSS feeds

## Success Metrics

- Clean, typo-free tag system through referential integrity
- Sub-100ms tag searches for 10k documents  
- Intuitive CLI UX with auto-completion
- Zero data loss during migration
- Comprehensive test coverage

## Questions to Resolve

1. Should we auto-clean unused tags or keep them?
2. Tag name constraints: lowercase only? Allow spaces?
3. Maximum tags per document limit?
4. Should tag order matter for display?