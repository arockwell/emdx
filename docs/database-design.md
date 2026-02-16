# EMDX Database Design

## 🗃️ **Schema Overview**

EMDX uses SQLite with FTS5 (Full-Text Search) for efficient local storage and searching. The design emphasizes simplicity, performance, and data integrity.

### **Core Design Principles**
- **Local-first** - All data stored locally, no cloud dependencies
- **Performance-optimized** - Indexed for fast search and retrieval
- **Version-controlled** - Comprehensive migration system
- **Data integrity** - Foreign key constraints and validation
- **Space-efficient** - Normalized design with emoji tags

## 📊 **Database Schema**

### **Core Tables**

#### **`documents` - Document Storage**
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    is_deleted INTEGER DEFAULT 0,
    deleted_at TEXT,
    file_path TEXT,
    checksum TEXT
);
```

#### **`tags` - Tag Definitions**
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    emoji TEXT,
    color TEXT,
    created_at TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0
);
```

#### **`document_tags` - Many-to-Many Relationships**
```sql
CREATE TABLE document_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE,
    UNIQUE(document_id, tag_id)
);
```

#### **`executions` - Execution Tracking**
```sql
CREATE TABLE executions (
    id TEXT PRIMARY KEY,  -- UUID for unique identification
    doc_id INTEGER,
    doc_title TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    pid INTEGER,
    exit_code INTEGER,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    last_heartbeat TEXT,
    log_file TEXT,
    working_dir TEXT,
    old_id TEXT,  -- Migration compatibility
    FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE SET NULL
);
```

### **Additional Tables**

The database also includes tables for:
- **`document_groups`** — Hierarchical document organization
- **`tasks`** — Task management with dependencies and status tracking
- **`document_embeddings`** — Semantic search vectors (384-dimensional)

See `emdx/database/migrations.py` for complete schema definitions.

### **Search Infrastructure**

#### **`documents_fts` - Full-Text Search**
```sql
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, 
    content, 
    project,
    content='documents',
    content_rowid='id'
);
```

### **Indexes for Performance**

```sql
-- Document access patterns
CREATE INDEX idx_documents_project ON documents(project);
CREATE INDEX idx_documents_created_at ON documents(created_at);
CREATE INDEX idx_documents_accessed_at ON documents(accessed_at);
CREATE INDEX idx_documents_is_deleted ON documents(is_deleted);

-- Tag relationships
CREATE INDEX idx_document_tags_document_id ON document_tags(document_id);
CREATE INDEX idx_document_tags_tag_id ON document_tags(tag_id);

-- Execution queries
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_started_at ON executions(started_at);
CREATE INDEX idx_executions_doc_id ON executions(doc_id);
```

## 🔄 **Migration System**

### **Version-Controlled Schema Evolution**

```python
# Migration structure in emdx/database/migrations.py
# Each migration is a tuple: (version, description, function)
# Currently 36 migrations (0-35)
# See emdx/database/migrations.py for the full list
```

### **Migration Best Practices**
- **Incremental changes** - Each migration is a small, focused change
- **Backward compatibility** - Old data preserved during upgrades
- **Rollback safety** - Migrations designed to be reversible
- **Data validation** - Verify integrity after each migration

### **Example Migration**
```python
def migration_007_add_emoji_tags(conn):
    """Add emoji support to tags table."""
    cursor = conn.cursor()
    
    # Add new columns
    cursor.execute("ALTER TABLE tags ADD COLUMN emoji TEXT")
    cursor.execute("ALTER TABLE tags ADD COLUMN color TEXT")
    
    # Update existing tags with default emojis
    cursor.execute("""
        UPDATE tags 
        SET emoji = '📝' 
        WHERE name LIKE '%note%' OR name LIKE '%memo%'
    """)
    
    conn.commit()
```

## 🎯 **Data Access Patterns**

### **Common Query Patterns**

#### **Document Retrieval**
```sql
-- Recent documents
SELECT * FROM documents 
WHERE is_deleted = 0 
ORDER BY accessed_at DESC 
LIMIT 10;

-- Project-specific documents
SELECT d.*, GROUP_CONCAT(t.emoji) as tag_emojis
FROM documents d
LEFT JOIN document_tags dt ON d.id = dt.document_id
LEFT JOIN tags t ON dt.tag_id = t.id
WHERE d.project = ? AND d.is_deleted = 0
GROUP BY d.id
ORDER BY d.updated_at DESC;
```

#### **Full-Text Search**
```sql
-- Search with ranking
SELECT d.*, rank
FROM documents_fts fts
JOIN documents d ON fts.rowid = d.id
WHERE documents_fts MATCH ?
AND d.is_deleted = 0
ORDER BY rank;

-- Combined text and tag search
SELECT DISTINCT d.*, rank
FROM documents_fts fts
JOIN documents d ON fts.rowid = d.id
JOIN document_tags dt ON d.id = dt.document_id
JOIN tags t ON dt.tag_id = t.id
WHERE documents_fts MATCH ?
AND t.name IN (?, ?, ?)
AND d.is_deleted = 0
ORDER BY rank;
```

#### **Tag Analytics**
```sql
-- Tag usage statistics
SELECT t.name, t.emoji, COUNT(dt.document_id) as usage_count
FROM tags t
LEFT JOIN document_tags dt ON t.id = dt.id
GROUP BY t.id
ORDER BY usage_count DESC;

-- Project tag distribution
SELECT d.project, t.emoji, COUNT(*) as count
FROM documents d
JOIN document_tags dt ON d.id = dt.document_id  
JOIN tags t ON dt.tag_id = t.id
WHERE d.is_deleted = 0
GROUP BY d.project, t.id
ORDER BY d.project, count DESC;
```

#### **Execution Monitoring**
```sql
-- Running executions with health check
SELECT e.*, 
       (strftime('%s', 'now') - strftime('%s', e.last_heartbeat)) as stale_seconds
FROM executions e
WHERE e.status = 'running'
ORDER BY e.started_at DESC;

-- Execution success rates
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN status = 'completed' AND exit_code = 0 THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status = 'failed' OR exit_code != 0 THEN 1 ELSE 0 END) as failed
FROM executions
WHERE started_at > datetime('now', '-30 days');
```

## 🔧 **Database Operations**

### **Connection Management**
```python
class DatabaseConnection:
    """Centralized database connection management."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection = None
    
    def get_connection(self):
        """Get database connection with context manager."""
        if not self._connection:
            self._connection = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                isolation_level=None  # Autocommit mode
            )
            self._configure_connection(self._connection)
        return self._connection
    
    def _configure_connection(self, conn):
        """Configure connection for optimal performance."""
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
        conn.execute("PRAGMA synchronous = NORMAL")   # Balanced safety/speed
        conn.execute("PRAGMA cache_size = 10000")     # 40MB cache
```

### **Transaction Patterns**
```python
# Context manager for transactions
@contextmanager
def transaction(connection):
    """Safe transaction context manager."""
    try:
        connection.execute("BEGIN")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

# Usage example
with db.get_connection() as conn:
    with transaction(conn):
        # Multiple related operations
        doc_id = insert_document(conn, title, content)
        add_tags(conn, doc_id, tag_ids)
        update_fts_index(conn, doc_id)
```

## 📈 **Performance Optimization**

### **Query Optimization Strategies**
- **Proper indexing** - Indexes on all commonly queried columns
- **FTS5 integration** - Fast full-text search with ranking
- **Connection pooling** - Reuse connections for better performance
- **WAL mode** - Better concurrency for read-heavy workloads
- **Prepared statements** - Parameter binding prevents SQL injection

### **Database Tuning**
```python
# Performance-optimized settings
PRAGMA_SETTINGS = [
    "PRAGMA journal_mode = WAL",        # Write-Ahead Logging
    "PRAGMA synchronous = NORMAL",      # Balanced durability/speed
    "PRAGMA cache_size = 10000",        # 40MB cache
    "PRAGMA temp_store = memory",       # Temporary tables in memory
    "PRAGMA mmap_size = 268435456",     # Memory-mapped I/O (256MB)
]
```

### **Monitoring and Analytics**
```sql
-- Database size and performance
SELECT 
    page_count * page_size / 1024 / 1024 as size_mb,
    freelist_count,
    page_count
FROM pragma_page_count(), pragma_page_size(), pragma_freelist_count();

-- Index usage analysis
EXPLAIN QUERY PLAN 
SELECT * FROM documents WHERE project = 'emdx';
```

## 🛡️ **Data Integrity and Security**

### **Integrity Constraints**
- **Foreign key constraints** - Referential integrity across tables
- **Unique constraints** - Prevent duplicate tags and relationships
- **Check constraints** - Validate data at database level
- **NOT NULL constraints** - Required fields enforcement

### **Data Validation**
```python
def validate_document(title: str, content: str) -> None:
    """Validate document data before database insertion."""
    if not title or not title.strip():
        raise ValueError("Document title cannot be empty")
    
    if len(title) > 500:
        raise ValueError("Document title too long (max 500 chars)")
    
    if not content:
        raise ValueError("Document content cannot be empty")
```

### **Backup and Recovery**
```python
def backup_database(source_path: Path, backup_path: Path) -> None:
    """Create backup using SQLite backup API."""
    source = sqlite3.connect(source_path)
    backup = sqlite3.connect(backup_path)
    
    # Use SQLite's backup API for consistent backup
    source.backup(backup)
    
    backup.close()
    source.close()
```

## 🚀 **Future Enhancements**

### **Planned Schema Improvements**
- **Document versioning** - Track document history and changes
- **User system** - Multi-user support with permissions
- **Attachment support** - File attachments linked to documents
- **Advanced search** - Semantic search and AI-powered discovery

### **Performance Scaling**
- **Read replicas** - Multiple read-only database copies
- **Partitioning** - Split large tables by project or date
- **Caching layer** - Redis or in-memory caching for frequent queries
- **Index optimization** - Adaptive indexing based on query patterns

This database design provides a solid foundation for EMDX's knowledge management capabilities while maintaining simplicity and performance for local-first operation.