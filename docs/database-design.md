# EMDX Database Design

## Schema Overview

EMDX uses SQLite with FTS5 (Full-Text Search) for efficient local storage and searching. The design emphasizes simplicity, performance, and data integrity.

### Core Design Principles
- **Local-first** — All data stored locally, no cloud dependencies
- **Performance-optimized** — Indexed for fast search and retrieval
- **Version-controlled** — Set-based migration system (59 migrations, 0–58)
- **Data integrity** — Foreign key constraints and validation
- **Space-efficient** — Normalized design with text-based tags

## Database Schema

### Core Tables

#### `documents` — Document Storage
```sql
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    parent_id INTEGER,                          -- document generation parent
    relationship TEXT,                          -- relationship to parent
    archived_at TIMESTAMP,                     -- soft archive timestamp
    stage TEXT DEFAULT NULL,                    -- cascade pipeline stage
    pr_url TEXT DEFAULT NULL,                   -- associated PR URL
    doc_type TEXT NOT NULL DEFAULT 'user'       -- user | wiki | entity-page | synthesis
);
```

#### `tags` — Tag Definitions
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    usage_count INTEGER DEFAULT 0
);
```

#### `document_tags` — Many-to-Many Tag Relationships
```sql
CREATE TABLE document_tags (
    document_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, tag_id),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);
```

### Task System

#### `tasks` — Agent Work Queue
```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open',
    priority INTEGER DEFAULT 3,
    gameplan_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    project TEXT,
    current_step TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    type TEXT DEFAULT 'single',
    source_doc_id INTEGER REFERENCES documents(id),
    parent_task_id INTEGER REFERENCES tasks(id),
    epic_key TEXT REFERENCES categories(key),
    epic_seq INTEGER
);
```

#### `categories` — Task Category Definitions
```sql
CREATE TABLE categories (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Execution Tracking

#### `executions` — Claude Execution Runs
```sql
CREATE TABLE executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER,
    doc_title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    log_file TEXT NOT NULL,
    exit_code INTEGER,
    working_dir TEXT,
    pid INTEGER,
    cascade_run_id INTEGER REFERENCES cascade_runs(id),
    task_id INTEGER REFERENCES tasks(id),
    cost_usd REAL DEFAULT 0.0,
    tokens_used INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    output_text TEXT,
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE SET NULL
);
```

### Search Infrastructure

#### `documents_fts` — Full-Text Search (FTS5)
```sql
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title, content, project,
    content='documents', content_rowid='id',
    tokenize='porter unicode61'
);
```

FTS is kept in sync via triggers (`documents_ai`, `documents_au`, `documents_ad`) that fire on insert, update, and delete.

#### `document_embeddings` — Document-Level Semantic Search
```sql
CREATE TABLE document_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    dimension INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, model_name)
);
```

#### `chunk_embeddings` — Chunk-Level Semantic Search
```sql
CREATE TABLE chunk_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading_path TEXT NOT NULL,
    text TEXT NOT NULL,
    model_name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    dimension INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, chunk_index, model_name)
);
```

### Knowledge Graph

#### `document_links` — Bidirectional Document Links
```sql
CREATE TABLE document_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_doc_id INTEGER NOT NULL,
    target_doc_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    method TEXT NOT NULL DEFAULT 'auto',       -- auto | manual
    FOREIGN KEY (source_doc_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (target_doc_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(source_doc_id, target_doc_id)
);
```

#### `document_entities` — Entity Extraction for Wikification
```sql
CREATE TABLE document_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    entity TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, entity)
);
```

### Wiki System

#### `wiki_topics` — Topic Cluster Definitions
```sql
CREATE TABLE wiki_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_slug TEXT NOT NULL UNIQUE,
    topic_label TEXT NOT NULL,
    description TEXT DEFAULT '',
    entity_fingerprint TEXT NOT NULL DEFAULT '',
    coherence_score REAL DEFAULT 0.0,
    resolution_level TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `wiki_topic_members` — Document-to-Topic Membership
```sql
CREATE TABLE wiki_topic_members (
    topic_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    relevance_score REAL DEFAULT 1.0,
    content_hash TEXT DEFAULT '',
    is_primary BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (topic_id, document_id),
    FOREIGN KEY (topic_id) REFERENCES wiki_topics(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

#### `wiki_articles` — Generated Wiki Articles
```sql
CREATE TABLE wiki_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL UNIQUE,
    article_type TEXT NOT NULL DEFAULT 'topic_article',
    source_hash TEXT NOT NULL DEFAULT '',
    model TEXT DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    is_stale BOOLEAN DEFAULT FALSE,
    stale_reason TEXT DEFAULT '',
    version INTEGER DEFAULT 1,
    quality_score REAL DEFAULT 0.0,
    previous_content TEXT DEFAULT '',
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (topic_id) REFERENCES wiki_topics(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

#### `wiki_article_sources` — Article Provenance
```sql
CREATE TABLE wiki_article_sources (
    article_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    content_hash TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (article_id, document_id),
    FOREIGN KEY (article_id) REFERENCES wiki_articles(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

#### `wiki_runs` — Wiki Generation Run Tracking
```sql
CREATE TABLE wiki_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    topics_attempted INTEGER DEFAULT 0,
    articles_generated INTEGER DEFAULT 0,
    articles_skipped INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    model TEXT DEFAULT '',
    dry_run BOOLEAN DEFAULT FALSE
);
```

### Analytics & History

#### `knowledge_events` — KB Interaction Tracking
```sql
CREATE TABLE knowledge_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    doc_id INTEGER,
    query TEXT,
    session_id TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `document_versions` — Content History
```sql
CREATE TABLE document_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    content_hash TEXT,
    char_delta INTEGER,
    change_source TEXT DEFAULT 'manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
```

#### `standing_queries` — Saved/Watched Searches
```sql
CREATE TABLE standing_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    tags TEXT,
    project TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notify_count INTEGER DEFAULT 0
);
```

### Other Tables

The database also includes tables for:
- **`document_groups`** — Hierarchical document organization (batches, initiatives, sessions)
- **`cascade_runs`** — Cascade pipeline run tracking
- **`gists`** — Document-to-gist relationships

See `emdx/database/migrations.py` for complete schema definitions of all tables.

## Indexes

The database uses 100+ indexes for performance. Key index categories:

```sql
-- Document access patterns
CREATE INDEX idx_documents_project ON documents(project);
CREATE INDEX idx_documents_accessed ON documents(accessed_at DESC);
CREATE INDEX idx_documents_deleted ON documents(is_deleted, deleted_at);
CREATE INDEX idx_documents_parent_id ON documents(parent_id);

-- Tag relationships
CREATE INDEX idx_document_tags_document_id ON document_tags(document_id);
CREATE INDEX idx_document_tags_tag_id ON document_tags(tag_id);
CREATE INDEX idx_tags_name ON tags(name);

-- Execution queries
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_started_at ON executions(started_at);
CREATE INDEX idx_executions_doc_id ON executions(doc_id);

-- Knowledge graph
CREATE INDEX idx_doc_links_source ON document_links(source_doc_id);
CREATE INDEX idx_doc_links_target ON document_links(target_doc_id);
CREATE INDEX idx_entities_document ON document_entities(document_id);
CREATE INDEX idx_entities_entity ON document_entities(entity);

-- Wiki system
CREATE INDEX idx_wiki_topics_slug ON wiki_topics(topic_slug);
CREATE INDEX idx_wiki_topics_status ON wiki_topics(status);
CREATE INDEX idx_wiki_articles_topic ON wiki_articles(topic_id);
CREATE INDEX idx_wiki_articles_stale ON wiki_articles(is_stale);

-- Analytics
CREATE INDEX idx_events_type_created ON knowledge_events(event_type, created_at);
CREATE INDEX idx_events_doc ON knowledge_events(doc_id);
```

See `emdx/database/migrations.py` for the full index list.

## Migration System

### Set-Based Migration Tracking

Migrations use **set-based tracking** with string IDs. Each migration is identified by a unique version string, and the system only runs migrations that haven't been applied yet. This prevents collisions when branches diverge (unlike sequential max-based tracking).

```python
# Migration structure in emdx/database/migrations.py
# Each migration is a tuple: (version_id, description, function)
# Currently 59 migrations (versions "0" through "58")
# Legacy migrations (0–54) use numeric strings
# New migrations use timestamp IDs: "YYYYMMDD_HHMMSS"
```

Tracking is stored in the `schema_migrations` table:

```sql
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Migration Best Practices
- **Incremental changes** — Each migration is a small, focused change
- **Backward compatibility** — Old data preserved during upgrades
- **Set-based** — Migrations identified by string version, not sequential integers
- **Table recreation** — SQLite doesn't support DROP COLUMN; use CREATE TABLE new → INSERT → DROP old → RENAME pattern with `foreign_keys_disabled()` context manager

## Data Access Patterns

### Common Query Patterns

#### Document Retrieval
```sql
-- Recent documents
SELECT * FROM documents
WHERE is_deleted = 0
ORDER BY accessed_at DESC
LIMIT 10;

-- Project-specific documents with tags
SELECT d.*, GROUP_CONCAT(t.name) as tag_names
FROM documents d
LEFT JOIN document_tags dt ON d.id = dt.document_id
LEFT JOIN tags t ON dt.tag_id = t.id
WHERE d.project = ? AND d.is_deleted = 0
GROUP BY d.id
ORDER BY d.updated_at DESC;
```

#### Full-Text Search
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

#### Tag Analytics
```sql
-- Tag usage statistics
SELECT t.name, COUNT(dt.document_id) as usage_count
FROM tags t
LEFT JOIN document_tags dt ON t.id = dt.tag_id
GROUP BY t.id
ORDER BY usage_count DESC;

-- Project tag distribution
SELECT d.project, t.name, COUNT(*) as count
FROM documents d
JOIN document_tags dt ON d.id = dt.document_id
JOIN tags t ON dt.tag_id = t.id
WHERE d.is_deleted = 0
GROUP BY d.project, t.id
ORDER BY d.project, count DESC;
```

#### Execution Monitoring
```sql
-- Running executions
SELECT e.*
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

## Database Operations

### Connection Management
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

### Transaction Patterns
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

## Performance Optimization

### Query Optimization Strategies
- **Proper indexing** — Indexes on all commonly queried columns
- **FTS5 integration** — Fast full-text search with ranking
- **Connection pooling** — Reuse connections for better performance
- **WAL mode** — Better concurrency for read-heavy workloads
- **Prepared statements** — Parameter binding prevents SQL injection

### Database Tuning
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

## Data Integrity and Security

### Integrity Constraints
- **Foreign key constraints** — Referential integrity across tables with ON DELETE CASCADE
- **Unique constraints** — Prevent duplicate tags, links, and relationships
- **Check constraints** — Validate execution status values at database level
- **NOT NULL constraints** — Required fields enforcement

### Backup and Recovery
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

Use `emdx maintain backup` / `emdx maintain backup --restore <file>` for CLI-driven backups.
