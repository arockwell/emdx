# SQLite Migration Plan for emdx

## Overview
Convert emdx from PostgreSQL to SQLite with FTS5 for full-text search, making it a zero-dependency personal knowledge base.

## Database Design

### 1. File Location
- Database: `~/.config/emdx/knowledge.db`
- Config remains at: `~/.config/emdx/.env` (optional now)
- Auto-create directories on first use

### 2. Schema with FTS5
```sql
-- Main table for metadata
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    project TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0
);

-- FTS5 virtual table for searchable content
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    content,
    project,
    content=documents,
    content_rowid=id,
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, content, project) 
    VALUES (new.id, new.title, '', new.project);
END;
```

### 3. Implementation Changes

#### Database class refactor:
- Replace psycopg with sqlite3 (built-in!)
- New connection: `sqlite3.connect(db_path)`
- Use FTS5 MATCH for searches: `WHERE documents_fts MATCH ?`
- Add helper for ranking: `ORDER BY rank`

#### Search features:
- Basic search: `title:python OR content:async`
- Phrase search: `"exact phrase"`
- Prefix search: `doc*`
- NEAR queries: `NEAR(python database)`

#### Simplified fuzzy search:
- For typos: Use Python's `rapidfuzz` library
- Search titles first with fuzzy matching
- Fall back to FTS5 for content

### 4. Migration Strategy

#### For new users:
- Just works! No setup needed
- Database created on first `emdx save`

#### For existing PostgreSQL users:
- Add `emdx migrate` command
- Exports from PostgreSQL → SQLite
- One-time operation

### 5. Benefits
- **Zero setup**: pip install and go
- **No dependencies**: SQLite is built into Python
- **Portable**: Database is one file
- **Fast**: SQLite is incredibly fast for reads
- **Simple backups**: Just copy the .db file

### 6. What we lose (and don't need)
- Fuzzy search via pg_trgm (replaceable with Python)
- Multi-user access (it's personal)
- Network access (it's local)

## Files to modify:
1. `database.py` - Complete rewrite for SQLite
2. `pyproject.toml` - Remove psycopg dependency
3. `README.md` - Update installation (simpler!)
4. Add `migrate.py` - Optional migration tool

This makes emdx a true "install and go" tool!